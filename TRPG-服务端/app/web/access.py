"""通用接入层 /access/* (ACC-1, MIT).

独立于既有 /api/* 与冻结契约 (ws_protocol.py/events.py 禁改; 既有端点不动)
的新接入层:
  - 统一响应包裹 {ok, data|error, code}; 统一错误码
    0 ok / 400 param / 401 auth / 404 notfound / 500 server
  - token 鉴权: Authorization: Bearer <token> 或 ?token=;
    未启用端一律 401 (即使带 token)
  - 复用既有逻辑: command_bus (玩家行动)、audio_import 语义 (录音导入)、
    EventStore (会话状态投影)
  - 配置 configs/access_config.yaml; token 为空时首次加载自动生成并写回
    (明文仅存 config, 日志/响应不回显 token)
Python 3.12 compatible; 只新增不破坏。
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml
from fastapi import (APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException,
                     Query, UploadFile)
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.app_core.command_bus import CommandBus, CommandError
from app.agent.gateway import GatewayError, gateway_from_config_file
from app.scheduler.branch_guard import BranchGuard, BranchViolation, ConflictError
from app.config import APP_ROOT, CONFIGS_DIR, get_version
from app.voice import stt_service
from app.web import rest as rest_mod

router = APIRouter()

ACCESS_CONFIG_PATH = CONFIGS_DIR / "access_config.yaml"

# 统一错误码 (ACC-1)
CODE_OK = 0
CODE_PARAM = 400
CODE_AUTH = 401
CODE_NOTFOUND = 404
CODE_SERVER = 500
# T2 (additive): 冲突 (table_id 已存在且 campaign_id 不同)
CODE_CONFLICT = 409

# T2: /access/host/turn 行动窗参数 (ENDPOINT-SPEC-NEW §5)
WINDOW_SEC_DEFAULT = 300
WINDOW_SEC_MIN = 5
WINDOW_SEC_MAX = 3600


def _epoch_ts(ts: Any) -> int:
    """ISO 字符串/数值 -> epoch 秒 (int); 解析失败回退 0。"""
    if isinstance(ts, (int, float)):
        return int(ts)
    if isinstance(ts, str) and ts:
        try:
            dt = datetime.fromisoformat(ts)
        except ValueError:
            return 0
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    return 0

ENABLED_ENDS = ("mobile", "webapp", "recorder")

AUDIO_IMPORT_DIR = APP_ROOT / "data" / "audio_import"

# EX-1 (additive): voice 预留端点 (register/transcript) 归属 recorder 端。
VOICE_EMBEDDINGS_DIR = APP_ROOT / "data" / "voice_embeddings"

# transcript 幂等 (内存态, 同 WS hub seen_req_ids 风格; 重启即清)
_TRANSCRIPT_SEQS: dict[str, int] = {}

# T2 (additive, 缺陷修复): 每 campaign 共享一个 BranchGuard, 让 req_id 幂等跨请求生效。
# 背景: CommandBus.__init__ 默认每次 self.guard = BranchGuard() (command_bus.py:60),
# 而 /access 每个请求都新建 CommandBus -> 幂等 keys 每次都是空的, 于是"同 req_id
# 重复提交"不会被识别, 会重复落事件 (违反 AC-3 #12 与玩家端 F6 "重复提交已忽略")。
# 修法: 用 CommandBus 既有的 guard 参数注入共享实例 (不新造幂等体系; 语义同 WS hub
# 的 seen_req_ids)。内存态, 重启即清; 与 _TRANSCRIPT_SEQS 同一生命周期约定。
_GUARDS: dict[str, BranchGuard] = {}


def _guard_for(campaign: str) -> BranchGuard:
    """取该 campaign 的共享幂等 guard (首次访问创建)。"""
    guard = _GUARDS.get(campaign)
    if guard is None:
        guard = BranchGuard()
        _GUARDS[campaign] = guard
    return guard


# T2 (additive): /access/host/turn 幂等表 (内存态, 同 _TRANSCRIPT_SEQS 风格)。
# 为什么不用 bus 的 key: start_turn 的 payload 含服务端派生的 countdown_end_ts
# (每次调用都不同), 而 CommandBus 对**全部** params 做 canonical 签名 -> 同 req_id
# 重试会被判成 "reused with new payload" (ConflictError)。故按既有 voice_transcript
# 的做法在端点层按 (campaign, req_id) 短路重放。
_TURN_OPEN_KEYS: dict[tuple[str, str], dict[str, Any]] = {}


def reset_command_guards() -> None:
    """测试隔离用: 清空共享幂等 guard 表与 host/turn 幂等表。"""
    _GUARDS.clear()
    _TURN_OPEN_KEYS.clear()

# speaker 取值: "kp" | "player:<id>" | 裸 id (字母数字下划线连字符, 1..64)
_SPEAKER_RE = re.compile(r"^(kp|player:[A-Za-z0-9_\-]{1,64}|[A-Za-z0-9_\-]{1,64})$")


# ---- EX-AI (additive): AI 副KP 建议端点 (D2) --------------------------------
# 语义对齐 scripts/sim/blackwater_run.py DeputyKP: 三选一建议 -> KP 拍板;
# 建议仅供 KP 决断, 绝不自动执行 / 绝不替 PC 行动 (无 AINPC)。
CODE_FORBIDDEN = 403  # additive 错误码: kp_only (玩家端/录音端不可调用建议端点)

ADVICE_TYPES = ("npc_react", "ruling", "narration")

# 降级模板 (确定性兜底, 同 sim DeputyKP ADVICE_*_OPTIONS 语义; LLM 不可用时返回)
ADVICE_TEMPLATES: dict[str, list[str]] = {
    "npc_react": [
        "NPC 以套话开场，观察对方是否回避眼神（情报获取检定）。",
        "NPC 直接出示/暗示一条线索，把对话推向关键信息。",
        "NPC 借故离开，制造独处或跟踪的机会。",
    ],
    "ruling": [
        "按规则书常规检定处理（无调整）。",
        "视为困难检定（难度提升一级）。",
        "直接拍板叙事推进，不再掷骰。",
    ],
    "narration": [
        "用环境描写收束当前动作，给下一个行动留钩子。",
        "直接陈述结果并揭示一条线索或事件。",
        "留白：点到即止，把诠释权交给玩家。",
    ],
}

# 上一轮建议缓存 (内存态, 供 LLM 不可用时降级返回; 重启即清)
_ADVICE_LAST: dict[str, dict[str, Any]] = {}
# 幂等: campaign::req_id -> advice_id
_ADVICE_KEYS: dict[str, str] = {}
# 每 campaign 建议计数 (advice_id 唯一)
_ADVICE_SEQ: dict[str, int] = {}


# ---- V-1 (additive): 录音设备状态 DEVICE_STATUS ------------------------------
# 内存态注册表: device_id -> 最新状态记录 (含 seq=该设备累计上报次数);
# per-device 追加式状态历史 (审计打点, 每设备上限 _DEVICE_HISTORY_LIMIT 条, 超限裁旧)。
# "事件流打点"降级条款: events.py 为冻结契约 (头部注明 "Adding a new type requires a
# contract change", 各事件 payload StrictModel(extra=forbid)), 不存在适合承载设备状态的
# 既有 kind -> 不新增冻结枚举 / 不伪造既有事件, 改 per-device 追加历史 + mark 状态变化。
_DEVICE_STATUS: dict[str, dict[str, Any]] = {}
_DEVICE_HISTORY: dict[str, list[dict[str, Any]]] = {}
_DEVICE_HISTORY_LIMIT = 50


def _valid_speaker(s: str) -> bool:
    return bool(s and _SPEAKER_RE.match(s))


def _safe_file_id(name: str) -> str:
    """说话人/会话名 -> 文件名安全片段 (防路径穿越, Windows 不合法字符替换)。"""
    return re.sub(r"[^A-Za-z0-9_\-]", "_", name)


class AccessError(Exception):
    """/access 层统一错误: 响应体 = 统一包裹 {ok,error,code} (扁平, 非 detail 嵌套)."""

    def __init__(self, status: int, code: int, error: str) -> None:
        super().__init__(error)
        self.status = status
        self.code = code
        self.error = error


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ok(data: Any = None) -> dict[str, Any]:
    return {"ok": True, "data": data, "code": CODE_OK}


def _err(code: int, error: str) -> dict[str, Any]:
    return {"ok": False, "error": error, "code": code}


def _raise(code: int, error: str) -> None:
    """状态码与业务错误码一致: 400/401/404/500."""
    raise AccessError(code, code, error)


def install_access_error_handler(app: Any) -> None:
    """把 AccessError 挂到 app: 响应体保持 {ok,error,code} 扁平包裹. 仅 additive."""
    @app.exception_handler(AccessError)
    async def _access_error_handler(_request, exc: AccessError) -> JSONResponse:
        return JSONResponse(status_code=exc.status,
                            content=_err(exc.code, exc.error))

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(request, exc: RequestValidationError) -> JSONResponse:
        """ACC-F1: /access 前缀的校验错误统一转 {ok,error,code:400} + HTTP 400.

        非 /access 路由保持 FastAPI 原生 422 行为不变 (detail 列表), 与默认
        request_validation_exception_handler 输出一致 —— 修复不破坏既有 /api。
        """
        url = getattr(request, "url", None)
        path = url.path if url is not None else ""
        if path.startswith("/access"):
            errors = exc.errors()
            first = errors[0] if errors else {}
            loc = ".".join(str(x) for x in first.get("loc", ()) if x != "body")
            msg = str(first.get("msg", "") or "")
            field = loc or str(first.get("type", "param"))
            # T2 (additive, DX): multipart 端点被显式设了非 multipart 的 Content-Type
            # (典型: 客户端手动带 Content-Type: application/json) 会让 boundary 丢失,
            # file 字段解析不到 -> 只报 "Field required" 很难排查。此处补一句明确提示。
            # 仅当错误落在 file 字段且 Content-Type 确实不是 multipart 时追加,
            # 不影响正常 multipart 请求与既有报错文案。
            hint = ""
            try:
                ctype = str(request.headers.get("content-type") or "")
            except Exception:  # noqa: BLE001
                ctype = ""
            if "file" in loc and ctype and "multipart/form-data" not in ctype.lower():
                hint = (" [multipart/form-data required: 请勿手动设置 Content-Type,"
                        " 否则 boundary 丢失, file 字段无法解析]")
            return JSONResponse(status_code=CODE_PARAM,
                                content=_err(CODE_PARAM,
                                             "invalid param: %s: %s%s"
                                             % (field, msg, hint)))
        return JSONResponse(status_code=422,
                            content={"detail": jsonable_encoder(exc.errors())})


def _load_config() -> dict[str, Any]:
    """Load access_config.yaml; generate + persist empty tokens (once).

    token 为空则生成 (secrets.token_hex) 并写回 config 文件——明文仅存 config;
    控制台只提示生成事实与存放位置, 不回显 token 值。
    """
    cfg: dict[str, Any] = {}
    if ACCESS_CONFIG_PATH.is_file():
        with open(ACCESS_CONFIG_PATH, encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
            if isinstance(loaded, dict):
                cfg = loaded
    ends: dict[str, Any] = cfg.setdefault("ends", {})
    changed = False
    for end in ENABLED_ENDS:
        entry = ends.setdefault(end, {})
        if not isinstance(entry, dict):
            entry = {}
            ends[end] = entry
        if not entry.get("token"):
            entry["token"] = secrets.token_hex(16)
            changed = True
    if changed:
        try:
            ACCESS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(ACCESS_CONFIG_PATH, "w", encoding="utf-8") as f:
                yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
            print("[access] token generated for enabled end(s); "
                  "plaintext stored only in %s" % ACCESS_CONFIG_PATH)
        except OSError:
            pass  # 只读环境: 本次会话 token 内存生效, 不落盘
    return cfg


def _end_entry(end: str) -> dict[str, Any]:
    cfg = _load_config()
    ends = cfg.get("ends") or {}
    entry = ends.get(end)
    if not isinstance(entry, dict):
        _raise(CODE_AUTH, "end not configured: %s" % end)
    return entry


def _require_end(end: str):
    """端级 token 鉴权依赖工厂: 未启用端 401; token 不匹配 401."""
    def dep(authorization: str | None = Header(default=None),
            token: str | None = Query(default=None)) -> dict[str, Any]:
        entry = _end_entry(end)
        if not entry.get("enabled"):
            _raise(CODE_AUTH, "end disabled: %s" % end)
        expected = str(entry.get("token") or "")
        provided = ""
        if authorization and authorization.lower().startswith("bearer "):
            provided = authorization[7:].strip()
        if token:
            provided = token
        if not expected or not provided or provided != expected:
            _raise(CODE_AUTH, "bad or missing token")
        return entry
    return dep


def _matches_any_enabled_end(provided: str, cfg: dict[str, Any]) -> dict[str, Any] | None:
    """/access 同源 token 判定: provided 匹配任一启用端 token 时返回该端 entry, 否则 None.

    供 _require_any_end 与 /ws 握手校验 (EX-2 D3) 共用 —— 单一真相源。
    """
    ends = cfg.get("ends") or {}
    for end in ENABLED_ENDS:
        entry = ends.get(end)
        if not isinstance(entry, dict) or not entry.get("enabled"):
            continue
        if provided and provided == str(entry.get("token") or ""):
            return entry
    return None


def token_matches_any_enabled_end(token: str | None) -> bool:
    """EX-2 D3: /ws 握手 token 校验 —— 与 /access 同源 (任一启用端 token 放行).

    供 app/main.py::ws_endpoint 在 accept 前调用; 无 token / 未启用端 / 不匹配 -> False。
    不抛异常, 由调用方决定拒绝方式 (4400 关闭, 与既有参数错误码一致)。
    """
    return _matches_any_enabled_end(token or "", _load_config()) is not None


def token_end_name(token: str | None) -> str | None:
    """R9 (additive): token -> 启用端名 ("webapp"|"mobile"|"recorder")；未知返回 None。

    与 _matches_any_enabled_end 同源（单一真相源），供 /ws 握手与 REST 事件流
    判定「调用方是不是 KP 端」。不抛异常。
    """
    cfg = _load_config()
    ends = cfg.get("ends") or {}
    provided = token or ""
    if not provided:
        return None
    for end in ENABLED_ENDS:
        entry = ends.get(end)
        if (isinstance(entry, dict) and entry.get("enabled")
                and provided == str(entry.get("token") or "")):
            return end
    return None


def _require_any_end(authorization: str | None = Header(default=None),
                     token: str | None = Query(default=None)) -> dict[str, Any]:
    """info 端点: 任意启用端的有效 token 即可."""
    cfg = _load_config()
    provided = ""
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    if token:
        provided = token
    entry = _matches_any_enabled_end(provided, cfg)
    if entry is None:
        _raise(CODE_AUTH, "bad or missing token")
    return entry


def _require_kp_end(authorization: str | None = Header(default=None),
                    token: str | None = Query(default=None)) -> dict[str, Any]:
    """EX-AI/DSH-2: KP 专属端鉴权 (webapp=主持端) —— 玩家端/录音端 token 显式 403 kp_only.

    语义: mobile/recorder 端凭证 (含未启用端, 端未配置除外) 表明"非 KP 调用方" -> 403;
    webapp 端校验与 _require_end("webapp") 完全一致 (未配置/未启用/不匹配 -> 401)。
    """
    cfg = _load_config()
    ends = cfg.get("ends") or {}
    provided = ""
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    if token:
        provided = token
    for end in ("mobile", "recorder"):
        entry = ends.get(end)
        # t5 fix (reviewer P3): 与 _require_recorder_end 对齐 —— 仅当该端 enabled 时
        # 才判定"非 KP 调用方"并 403 kp_only; 未启用端的残余 token 落到 webapp 校验 (401)。
        if (isinstance(entry, dict) and entry.get("enabled")
                and provided and provided == str(entry.get("token") or "")):
            _raise(CODE_FORBIDDEN, "kp_only")
    entry = _end_entry("webapp")
    if not entry.get("enabled"):
        _raise(CODE_AUTH, "end disabled: webapp")
    expected = str(entry.get("token") or "")
    if not expected or not provided or provided != expected:
        _raise(CODE_AUTH, "bad or missing token")
    return entry


def _require_recorder_end(authorization: str | None = Header(default=None),
                          token: str | None = Query(default=None)) -> dict[str, Any]:
    """V-1: recorder 专属端鉴权 (录音设备状态) —— 其它启用端 token 显式 403 recorder_only.

    语义: mobile/webapp 启用端凭证表明"非 recorder 调用方" -> 403 recorder_only
    (同 _require_kp_end 的 kp_only 模式); recorder 端校验与 _require_end("recorder")
    完全一致 (未配置/未启用/不匹配 -> 401), 与既有端隔离语义对齐。
    """
    cfg = _load_config()
    ends = cfg.get("ends") or {}
    provided = ""
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    if token:
        provided = token
    for end in ("mobile", "webapp"):
        entry = ends.get(end)
        if (isinstance(entry, dict) and entry.get("enabled")
                and provided and provided == str(entry.get("token") or "")):
            _raise(CODE_FORBIDDEN, "recorder_only")
    entry = _end_entry("recorder")
    if not entry.get("enabled"):
        _raise(CODE_AUTH, "end disabled: recorder")
    expected = str(entry.get("token") or "")
    if not expected or not provided or provided != expected:
        _raise(CODE_AUTH, "bad or missing token")
    return entry


def _require_player_end(authorization: str | None = Header(default=None),
                        token: str | None = Query(default=None)) -> dict[str, Any]:
    """T2 (additive): 玩家端专属端鉴权 (POST /access/player/audio)。

    与既有 _require_recorder_end / _require_kp_end 同构 (端隔离, 不新造鉴权体系):
    mobile 通过; 其它启用端 token 显式 403 mobile_only; 无/错 token -> 401。

    注意 (ENDPOINT-SPEC-NEW §0.2 陷阱): 不能直接用 _require_end("mobile") ——
    它对"合法但属于别的端"的 token 返回 401, 而 AC-1.6 要求 403。
    """
    cfg = _load_config()
    provided = ""
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    if token:
        provided = token
    entry = _matches_any_enabled_end(provided, cfg)
    if entry is None:
        _raise(CODE_AUTH, "bad or missing token")          # 401
    ends = cfg.get("ends") or {}
    if entry is ends.get("mobile"):
        return entry
    _raise(CODE_FORBIDDEN, "mobile_only")                  # 403


# LLM 通道工厂 (测试可替换): 读 configs/llm_providers.yaml -> GatewayRouter
_advice_gateway_factory = gateway_from_config_file


def _parse_advice_json(text: str) -> tuple[list[str], str] | None:
    """从 LLM 输出提取 {options:[...], rationale:"..."}; 失败返回 None (走降级)。"""
    obj = _parse_json_object(text)
    if obj is None:
        return None
    options = obj.get("options") if isinstance(obj, dict) else None
    rationale = str(obj.get("rationale", "") or "")
    if not isinstance(options, list) or not options:
        return None
    cleaned = [str(x).strip() for x in options if str(x).strip()]
    if not cleaned:
        return None
    return cleaned, rationale


def _parse_json_object(text: str) -> dict[str, Any] | None:
    """通用: 提取首个 {...} JSON 对象; 失败返回 None."""
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _advice_core(campaign: str, request_type: str, scene: str,
                 events_raw: Any, hint: str, req_id: str) -> dict[str, Any]:
    """AI 副KP 建议核心 (EX-AI + DSH-2 复用): 三选一 + rationale + advice_id。

    幂等 (req_id) / 降级 (degraded-cache|degraded-template) / 不落事件 (无 AINPC)。
    """
    key = ""
    if req_id:
        key = "%s::%s" % (campaign, req_id)
        prev = _ADVICE_KEYS.get(key)
        if prev is not None:
            last = _ADVICE_LAST.get(campaign, {})
            return {
                "advice_id": prev,
                "request_type": last.get("request_type", request_type),
                "options": list(last.get("options", [])),
                "rationale": str(last.get("rationale", "")),
                "status": "duplicate", "ts": _now(),
            }
    # 上下文
    events_summary = ""
    if isinstance(events_raw, list):
        events_summary = "；".join(str(e)[:120] for e in events_raw[:20])
    elif events_raw:
        events_summary = str(events_raw)[:1000]
    prompt = (
        "你是 TRPG 桌游的 AI 副KP（deputy keeper）。你只提供建议，绝不替玩家或 KP 做决定"
        "（无 AINPC，不自动执行任何行动）。\n"
        "会话: %s\n请求类型: %s（npc_react=NPC反应 / ruling=规则裁决 / narration=旁白叙事）\n"
        "场景: %s\n最近事件: %s\n额外提示: %s\n"
        "请给出 3 条互不相同、一句话即可执行的候选方案，并给一句简短 rationale（为什么这样建议）。\n"
        "只输出 JSON：{\"options\": [\"...\", \"...\", \"...\"], \"rationale\": \"...\"}"
        % (campaign, request_type, scene or "（未提供）",
           events_summary or "（未提供）", hint or "（无）"))
    options: list[str] = []
    rationale = ""
    status = ""
    model = ""
    mode = ""
    try:
        gw = _advice_gateway_factory()
        result = gw.complete(
            [{"role": "system", "content": prompt},
             {"role": "user", "content": "请给出建议。"}],
            max_tokens=1024, temperature=0.6)
        parsed = _parse_advice_json(result.text)
        if parsed is None:
            raise GatewayError("unparseable advice output")
        options, rationale = parsed
        status = "ok"
        model = result.model
        mode = result.mode
    except Exception:
        # 降级: 不阻断 (缓存上一轮 / 内置模板), 明确 status 标注来源
        return _degraded_advice(campaign, request_type)
    advice_id = _advice_id(campaign)
    record = {
        "advice_id": advice_id, "request_type": request_type,
        "options": list(options), "rationale": rationale,
        "status": status, "model": model, "mode": mode, "ts": _now(),
    }
    _ADVICE_LAST[campaign] = dict(record)
    if req_id:
        _ADVICE_KEYS[key] = advice_id
    return record


def _advice_id(campaign: str) -> str:
    n = _ADVICE_SEQ.get(campaign, 0) + 1
    _ADVICE_SEQ[campaign] = n
    return "adv_%s_%d" % (_safe_file_id(campaign), n)


def _degraded_advice(campaign: str, request_type: str) -> dict[str, Any]:
    """LLM 不可用降级: 优先返回上一轮建议 (degraded-cache); 否则内置模板 (degraded-template)。

    不阻断: 总是返回 200 + 明确 status/来源, 建议仅供 KP 拍板。
    """
    last = _ADVICE_LAST.get(campaign)
    if last:
        return {
            "advice_id": _advice_id(campaign),
            "request_type": last.get("request_type", request_type),
            "options": list(last.get("options", [])),
            "rationale": str(last.get("rationale", "")) + "（[degraded] 复用上一轮建议）",
            "status": "degraded-cache",
            "ts": _now(),
        }
    return {
        "advice_id": _advice_id(campaign),
        "request_type": request_type,
        "options": list(ADVICE_TEMPLATES.get(request_type, ADVICE_TEMPLATES["ruling"])),
        "rationale": "LLM 建议通道不可用，以下为内置兜底模板；仅供 KP 拍板，不自动执行。",
        "status": "degraded-template",
        "ts": _now(),
    }


# ---- 端点 ----------------------------------------------------------------

@router.get("/access/info")
def access_info(entry: dict[str, Any] = Depends(_require_any_end)) -> dict[str, Any]:
    """服务信息 + 启用端 + 版本 + openapi 链接 (任意启用端 token)."""
    cfg = _load_config()
    ends = cfg.get("ends") or {}
    return _ok({
        "service": "trpg",
        "version": get_version(),
        "ends": {end: bool(ends.get(end, {}).get("enabled"))
                 for end in ENABLED_ENDS},
        "openapi": "/openapi.json",
        "ws": "/access/ws",
        "ts": _now(),
    })


@router.get("/access/ws")
def access_ws(entry: dict[str, Any] = Depends(_require_any_end)) -> dict[str, Any]:
    """WS 通道说明: 既有 /ws 事件流 + token 查询参数."""
    return _ok({
        "channel": "/ws",
        "params": {"table": "", "viewer": "", "role": "kp|pl|spectator",
                   "token": "<access token>"},
        "note": "既有 WS 事件流 (AUDIO_CHUNK/STATE_DELTA/...), token 经查询参数传递; "
                "上行 AUDIO_CHUNK 为录音流, 离线批量文件走 POST /access/audio_upload",
        "example": "ws://<host>:9210/ws?table=t1&viewer=pl1&role=pl&token=<token>",
    })


@router.get("/access/mobile/state")
async def mobile_state(table_id: str = Query(..., min_length=1),
                       entry: dict[str, Any] = Depends(_require_end("mobile"))) -> dict[str, Any]:
    """轻量会话状态 (移动端字段裁剪): tip/count/by_type + 回合摘要."""
    campaign = rest_mod.TABLES.get(table_id, {}).get("campaign_id") or table_id
    store = rest_mod._store()
    await store.init()
    events = await store.replay(campaign)
    by_type: dict[str, int] = {}
    for e in events:
        by_type[e.type] = by_type.get(e.type, 0) + 1
    turn = rest_mod.project(events, campaign).turn
    return _ok({
        "table_id": table_id,
        "campaign": campaign,
        "tip": events[-1].seq if events else -1,
        "count": len(events),
        "by_type": by_type,
        "turn": ({"turn_no": turn.turn_no, "state": turn.state,
                  "submitted": len(turn.submitted)}
                 if turn else None),
    })


@router.get("/access/mobile/events")
async def mobile_events(table_id: str = Query(..., min_length=1),
                        viewer: str = Query(default=""),
                        since: int = Query(default=-1),
                        limit: int = Query(default=200),
                        entry: dict[str, Any] = Depends(_require_end("mobile"))) -> dict[str, Any]:
    """R9 (additive): 玩家端事件流 —— **服务端权威裁剪**后才下发。

    与 GET /api/campaigns/{c}/events 同源（复用 app.domain.visibility.clip_events），
    但身份来自 mobile 端 token（端隔离）。viewer 只用于选择「以谁的视角裁剪」，
    不构成提权：非 KP 永远拿不到 KP-only 事件、他人 whisper、秘密指针与骰种。
    """
    if limit < 1 or limit > 1000:
        _raise(CODE_PARAM, "limit must be 1..1000")
    campaign = rest_mod.TABLES.get(table_id, {}).get("campaign_id") or table_id
    store = rest_mod._store()
    await store.init()
    events = await store.replay(campaign)
    out = [e for e in events if e.seq > since][:limit]
    dtos = [e.model_dump(mode="json") for e in out]
    from app.domain.visibility import clip_events
    # 同 rest.py：state 仅供 MAP_UPDATED 的 can_see_map 使用，无 MAP_UPDATED 则跳过投影。
    state = None
    if any(str(d.get("type") or "") == "MAP_UPDATED" for d in dtos):
        try:
            state = rest_mod.project(events, campaign)
        except Exception:  # noqa: BLE001 — 投影失败不阻断读取（保守裁剪）
            state = None
    clipped = clip_events(dtos, viewer, False, state)
    return _ok({"table_id": table_id, "campaign": campaign,
                "viewer": viewer, "scope": "player", "filtered": True,
                "tip": events[-1].seq if events else -1,
                "events": clipped})


@router.post("/access/mobile/action")
async def mobile_action(body: dict[str, Any],
                        entry: dict[str, Any] = Depends(_require_end("mobile"))) -> dict[str, Any]:
    """玩家行动提交: 复用 command_bus submit_action (唯一写路径)."""
    campaign = str(body.get("campaign") or body.get("campaign_id") or "")
    if not campaign.strip():
        _raise(CODE_PARAM, "campaign required")
    raw_action = body.get("action")
    # 冻结契约 ActionSubmitted.action 是 dict; 兼容裸字符串 -> {text}
    action: Any = raw_action
    if isinstance(raw_action, str):
        action = {"text": raw_action}
    params = {
        "campaign_id": campaign,
        "turn_no": body.get("turn_no"),
        "player_id": body.get("player_id"),
        "action": action,
        "intent_summary": body.get("intent_summary", ""),
    }
    missing = [k for k in ("turn_no", "player_id", "action") if params.get(k) in (None, "")]
    if missing:
        _raise(CODE_PARAM, "missing params: %s" % missing)
    store = rest_mod._store()
    await store.init()
    bus = CommandBus(store, campaign, guard=_guard_for(campaign))
    _t0 = time.perf_counter()
    try:
        receipt = await bus.dispatch("submit_action", params,
                                     actor=str(body.get("player_id")),
                                     key=body.get("req_id"))
    except ConflictError as exc:
        # 同 req_id 复用但 payload 变了 (幂等键冲突): 显式 409 + 统一包裹。
        # 注: 共享 guard 生效后该分支才会被触发; 若不捕获会变成 HTTP 500 (空响应体),
        # 客户端拿不到结构化错误 —— 故在此显式映射。
        _raise(CODE_CONFLICT, "idempotency_conflict: %s" % exc)
    except (CommandError, BranchViolation) as exc:
        _raise(CODE_PARAM, str(exc))
    rest_mod.record_latency_ms(int((time.perf_counter() - _t0) * 1000))  # G-1 采样
    return _ok(receipt)


async def _audio_import_core(file: UploadFile, campaign: str, kind: str,
                             player_id: str,
                             background_tasks: BackgroundTasks) -> dict[str, Any]:
    """录音导入核心 (T2 提取, 语义与提取前逐行一致)。

    /access/audio_upload (recorder 端) 与 /access/player/audio (mobile 端) 共用:
    落盘 data/audio_import/ (best-effort) -> TRANSCRIPT_APPENDED(source=import)
    -> 后台 STT -> TRANSCRIPT_APPENDED(source=stt)。
    只做"提取", 不改任何可观察行为 (响应体/事件/落盘路径均不变)。
    """
    if not campaign.strip():
        _raise(CODE_PARAM, "campaign required")
    data = await file.read()
    if not data:
        _raise(CODE_PARAM, "empty file")
    # 落盘 best-effort (音频审计归档), 失败不影响事件记录
    ref = ""
    try:
        AUDIO_IMPORT_DIR.mkdir(parents=True, exist_ok=True)
        safe = "".join(ch for ch in file.filename if ch.isalnum() or ch in "._-")
        # t5 fix (reviewer P1-1): campaign 原样拼文件名可被 ..\ 穿越出 audio_import;
        # 与 file.filename 同规则净化 (仅落盘文件名变化, 事件/响应不受影响)。
        safe_campaign = _safe_file_id(campaign)
        target = AUDIO_IMPORT_DIR / ("%s__%s__%s" % (safe_campaign, int(time.time()), safe or "audio.bin"))
        target.write_bytes(data)
        ref = str(target)
    except OSError:
        pass
    store = rest_mod._store()
    await store.init()
    # 冻结契约 TranscriptAppended 只允许 campaign_id/seg/source;
    # kind/file_ref 只进响应, 不写事件 payload。
    ev = rest_mod.make_event(
        seq=0, campaign_id=campaign,
        type="TRANSCRIPT_APPENDED",
        payload={"campaign_id": campaign,
                 "seg": {"text": "[imported %s file %s (%d bytes)]"
                                 % (kind, file.filename or "audio", len(data)),
                         "t0": 0.0, "t1": 0.0, "speaker": player_id},
                 "source": "import"},
        actor=player_id, ts=_now())
    _t0 = time.perf_counter()
    seqs = await store.append(campaign, [ev])
    rest_mod.record_latency_ms(int((time.perf_counter() - _t0) * 1000))  # G-1 采样

    # EX-STT (D1): 上传后异步真实 STT 转写 (后台任务) → TRANSCRIPT_APPENDED(source=stt,
    # speaker=player_id) 落库。降级不阻断: 无 key/后端失败 → 占位文本 + degraded 标注。
    audio_bytes = data
    stt_job: dict[str, Any] = {"status": "queued"}

    async def _run_stt() -> None:
        result = None
        error = ""
        try:
            result = await asyncio.to_thread(stt_service.transcribe, audio_bytes)
        except Exception as exc:  # noqa: BLE001 — STT 失败降级, 不阻断
            error = str(exc)
        degraded = True
        reason = error or "stt unavailable"
        if result is not None:
            text = result.text
            degraded = result.degraded
            reason = result.reason
        else:
            text = "[STT 降级] 转写不可用（%s）" % (error or "no backend")
        try:
            st = rest_mod._store()
            await st.init()
            ev_stt = rest_mod.make_event(
                seq=0, campaign_id=campaign,
                type="TRANSCRIPT_APPENDED",
                payload={"campaign_id": campaign,
                         "seg": {"text": text, "t0": 0.0, "t1": 0.0,
                                 "speaker": player_id},
                         "source": "stt"},
                actor=player_id, ts=_now())
            await st.append(campaign, [ev_stt])
        except Exception:  # noqa: BLE001 — 尽力而为, 不阻断主流程
            pass
        stt_job.update({"status": "degraded" if degraded else "done",
                        "degraded": degraded, "reason": reason, "text": text})
        if result is not None:
            stt_job["latency_ms"] = result.latency_ms

    # EX-STT (D1) 后台 STT: 用 FastAPI BackgroundTasks (TestClient 同步场景下也会等待任务完成;
    # fire-and-forget create_task 在 TestClient 会随 portal 关闭被取消, 导致事件不落库)。
    background_tasks.add_task(_run_stt)
    return _ok({
        "seq": seqs[0],
        "job": {"job_id": "job_import_%d" % int(time.time()), "status": "done"},
        "bytes": len(data), "kind": kind, "file_ref": ref,
        "stt": {"status": stt_job["status"]},
    })


# ---- EX-1 voice 预留端点 (additive, recorder 端) ----------------------------

@router.post("/access/voice/register")
async def voice_register(body: dict[str, Any],
                         entry: dict[str, Any] = Depends(_require_end("recorder"))) -> dict[str, Any]:
    """音色注册 (EX-1): name + audio|embedding 二选一 + meta + req_id.

    说话人元数据存 data/voice_embeddings/<campaign>/<speaker>.json
    (JSON 元数据 + 占位 embedding, 服务端不计算真实嵌入); 不落事件流。
    """
    campaign = str(body.get("campaign") or body.get("campaign_id") or "")
    if not campaign.strip():
        _raise(CODE_PARAM, "campaign required")
    name = str(body.get("name") or "").strip()
    if not name:
        _raise(CODE_PARAM, "name required")
    if not _valid_speaker(name):
        _raise(CODE_PARAM, "invalid name: expected kp / player:<id> / <id>")
    audio = body.get("audio")
    embedding = body.get("embedding")
    has_audio = isinstance(audio, str) and bool(audio.strip())
    has_embedding = isinstance(embedding, str) and bool(str(embedding).strip())
    if has_audio == has_embedding:
        _raise(CODE_PARAM, "exactly one of audio/embedding required")
    payload = audio if has_audio else embedding
    try:
        raw = base64.b64decode(payload)
    except Exception:
        _raise(CODE_PARAM, "bad base64 in audio/embedding")
    dim = None
    if has_embedding:
        if len(raw) % 4 != 0:
            _raise(CODE_PARAM, "embedding must be float32 array (len % 4 == 0)")
        dim = len(raw) // 4
    meta = body.get("meta")
    if meta is not None and not isinstance(meta, dict):
        _raise(CODE_PARAM, "meta must be object")
    req_id = str(body.get("req_id") or "")
    record = {
        "campaign": campaign,
        "name": name,
        "speaker_id": name,
        "dim": dim,
        "has_audio": has_audio,
        "has_embedding": has_embedding,
        "embedding": payload if has_embedding else None,  # 占位: 原样存, 不计算
        "meta": meta or {},
        "req_id": req_id,
        "ts": _now(),
    }
    target_dir = VOICE_EMBEDDINGS_DIR / _safe_file_id(campaign)
    target = target_dir / ("%s.json" % _safe_file_id(name))
    status = "registered"
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        if target.is_file():
            try:
                existing = json.loads(target.read_text(encoding="utf-8"))
                if req_id and existing.get("req_id") == req_id:
                    status = "duplicate"
            except Exception:
                pass
        if status != "duplicate":
            target.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    except OSError:
        _raise(CODE_SERVER, "voice_embedding write failed")
    return _ok({"speaker_id": name, "dim": dim, "status": status})


@router.post("/access/voice/transcript")
async def voice_transcript(body: dict[str, Any],
                           entry: dict[str, Any] = Depends(_require_end("recorder"))) -> dict[str, Any]:
    """STT 文本 + speaker 提交 (EX-1): 追加 TRANSCRIPT_APPENDED (source=stt, additive)。

    承接已在客户端/上游完成转写的文本 (如官方 SDK 云转写、玩家端本地转写);
    实时流组帧转写仍为 D1 主线, 本端点为旁路互补。speaker 校验 kp / player:<id> / <id>。
    """
    campaign = str(body.get("campaign") or body.get("campaign_id") or "")
    if not campaign.strip():
        _raise(CODE_PARAM, "campaign required")
    audio_b64 = body.get("audio")
    text = str(body.get("text") or "")
    if not text.strip() and not audio_b64:
        _raise(CODE_PARAM, "text required (or provide audio for server-side STT)")
    speaker = body.get("speaker")
    if speaker is not None:
        speaker = str(speaker).strip()
        if not speaker:
            speaker = None
        elif not _valid_speaker(speaker):
            _raise(CODE_PARAM, "invalid speaker: expected kp / player:<id> / <id>")
    source = str(body.get("source") or "stt").strip()
    if source not in ("stt", "sdk", "import", "cloud", "local"):
        _raise(CODE_PARAM, "invalid source: %s" % source)
    # EX-STT (D1): source=stt + audio(base64) → 服务端真实 STT 转写 (stt_service);
    # 不可用/无 key → 降级占位文本 (degraded=True), 不阻断落库; 无 audio 走既有文本路径。
    stt_info: dict[str, Any] | None = None
    if source == "stt" and audio_b64:
        if not isinstance(audio_b64, str) or not audio_b64.strip():
            _raise(CODE_PARAM, "audio must be base64 string")
        try:
            audio_bytes = base64.b64decode(audio_b64)
        except Exception:
            _raise(CODE_PARAM, "bad base64 in audio")
        if not audio_bytes:
            _raise(CODE_PARAM, "audio empty after base64 decode")
        result = stt_service.transcribe(audio_bytes)
        text = result.text
        stt_info = {"status": "degraded" if result.degraded else "done",
                    "degraded": result.degraded, "reason": result.reason,
                    "latency_ms": result.latency_ms}
    if not text.strip():
        _raise(CODE_PARAM, "text required (or provide audio for server-side STT)")
    t0 = body.get("t0")
    t1 = body.get("t1")
    if t0 is not None:
        try:
            t0 = float(t0)
        except (TypeError, ValueError):
            _raise(CODE_PARAM, "t0 must be number")
    if t1 is not None:
        try:
            t1 = float(t1)
        except (TypeError, ValueError):
            _raise(CODE_PARAM, "t1 must be number")
    if t0 is not None and t1 is not None and t1 < t0:
        _raise(CODE_PARAM, "t1 must be >= t0")
    seg_seq = body.get("seg_seq")
    if seg_seq is not None:
        try:
            seg_seq = int(seg_seq)
        except (TypeError, ValueError):
            _raise(CODE_PARAM, "seg_seq must be int")
    req_id = str(body.get("req_id") or "")
    ts = body.get("ts")
    if ts is not None:
        if not isinstance(ts, str) or not ts.strip():
            _raise(CODE_PARAM, "ts must be ISO8601 string")
        event_ts = ts
    else:
        event_ts = _now()
    # 幂等: (campaign, req_id) 已落过 -> duplicate (内存态, 同 WS 风格)
    if req_id:
        key = "%s::%s" % (campaign, req_id)
        prev = _TRANSCRIPT_SEQS.get(key)
        if prev is not None:
            return _ok({"seq": prev, "status": "duplicate", "seg_seq": seg_seq})
    store = rest_mod._store()
    await store.init()
    ev = rest_mod.make_event(
        seq=0, campaign_id=campaign,
        type="TRANSCRIPT_APPENDED",
        payload={"campaign_id": campaign,
                 "seg": {"text": text,
                         "t0": t0 if t0 is not None else 0.0,
                         "t1": t1 if t1 is not None else 0.0,
                         "speaker": speaker},
                 "source": source},
        actor=speaker or "stt", ts=event_ts)
    _t0 = time.perf_counter()
    seqs = await store.append(campaign, [ev])
    rest_mod.record_latency_ms(int((time.perf_counter() - _t0) * 1000))  # G-1 采样
    seq = seqs[0]
    if req_id:
        _TRANSCRIPT_SEQS[key] = seq
    resp: dict[str, Any] = {"seq": seq, "status": "ok", "source": source, "seg_seq": seg_seq}
    if stt_info is not None:
        resp["stt"] = stt_info
    return _ok(resp)


# ---- EX-AI (additive): AI 副KP 建议端点 (D2, 仅供 KP 拍板) ------------------

@router.post("/access/advice")
async def kp_advice(body: dict[str, Any],
                    entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    """AI 副KP 三选一建议 (D2, additive): 接 llm_providers 通道 -> {options:[3], rationale} + advice_id。

    语义对齐 sim DeputyKP: 建议仅供 KP 拍板; 本端点不落事件、不自动执行 (无 AINPC)。
    KP 拍板后走既有审稿链 (APPROVE_NARRATION / COMMAND / approvals 等)。
    入参: campaign(必填, 别名 campaign_id), request_type(必填: npc_react|ruling|narration),
    scene/events/hint(可选上下文), req_id(可选, 幂等)。
    降级: LLM 不可用 -> 上一轮建议 (degraded-cache) 或内置模板 (degraded-template), 不阻断。
    """
    campaign = str(body.get("campaign") or body.get("campaign_id") or "")
    if not campaign.strip():
        _raise(CODE_PARAM, "campaign required")
    request_type = str(body.get("request_type") or "").strip()
    if request_type not in ADVICE_TYPES:
        _raise(CODE_PARAM, "request_type must be one of %s" % "/".join(ADVICE_TYPES))
    record = _advice_core(
        campaign, request_type,
        str(body.get("scene") or ""), body.get("events"),
        str(body.get("hint") or ""), str(body.get("req_id") or ""))
    return _ok(record)


# ---- DSH-2 (additive): 自然语言 -> 调度链路 (NL 端点, 仅供 KP, 不自动执行) -----

# LLM 意图分类通道 (测试可替换); 失败/无 key → 规则路径
_nl_gateway_factory = gateway_from_config_file

# 意图关键词表 (规则路径, 无 LLM key 可用)
_NL_ADVICE_KW = ("建议", "怎么办", "咋办", "给个建议", "三选一", "怎么处理", "如何是好", "给点建议", "出个主意")
_NL_ADVANCE_KW = ("推进", "下一幕", "场景推进", "继续剧情", "进入下一幕", "往前走", "推进到", "到下一幕")
_NL_RECORD_KW = ("记录", "记一下", "记下", "追加记录", "记录一下", "存档")
_NL_SUMMARY_KW = ("摘要", "总结", "复盘", "回顾", "汇总", "概括")
# advice 子类型关键词
_NL_RULING_KW = ("裁判", "裁决", "判定", "检定", "规则", "怎么判", "判一下")
_NL_NPC_KW = ("npc", "角色", "反应", "回应", "互动")
_NL_NARR_KW = ("旁白", "叙述", "描写", "叙事", "描写一下")


def _extract_intent(text: str) -> tuple[str, dict[str, str]]:
    """纯规则意图解析 (DSH-2): 关键词优先级 摘要>建议>推进>记录; 无命中默认 advice (最安全, 不自动执行)。"""
    t = (text or "").strip()
    params: dict[str, str] = {"text": t}
    if not t:
        return "", params
    if any(k in t for k in _NL_SUMMARY_KW):
        intent = "summary"
    elif any(k in t for k in _NL_ADVICE_KW):
        intent = "advice"
    elif any(k in t for k in _NL_ADVANCE_KW):
        intent = "advance"
    elif any(k in t for k in _NL_RECORD_KW):
        intent = "record"
    else:
        intent = "advice"
    # 实体抽取
    if any(k in t for k in _NL_RULING_KW):
        params["request_type"] = "ruling"
    elif any(k in t for k in _NL_NPC_KW):
        params["request_type"] = "npc_react"
    elif any(k in t for k in _NL_NARR_KW):
        params["request_type"] = "narration"
    m = re.search(r"推进到\s*([\u4e00-\u9fa5A-Za-z0-9_\-]{1,16})", t)
    if m:
        params["target"] = m.group(1)
    return intent, params


def _classify_nl(text: str) -> tuple[str, dict[str, str], str]:
    """意图分类: LLM 优先 (seam, mock 可测); 失败/无 key -> 规则路径。

    返回 (intent, params, status) — status: "llm" | "ok" (规则)。
    """
    try:
        gw = _nl_gateway_factory()
        result = gw.complete(
            [{"role": "system", "content": (
                "你是 TRPG 桌游调度助手。把 KP 的自然语言请求分类为以下意图之一："
                "advance(场景推进) / advice(建议, 副KP三选一) / record(记录事件) / summary(最近事件摘要)。"
                "只输出 JSON：{\"intent\":\"...\",\"params\":{\"request_type\":\"ruling|npc_react|narration\""
                "(advice 时可选),\"target\":\"...(advance 时可选)\"}}")},
             {"role": "user", "content": str(text)}],
            max_tokens=512, temperature=0.2)
        parsed = _parse_json_object(result.text)
        if parsed and str(parsed.get("intent")) in ("advance", "advice", "record", "summary"):
            params = dict(parsed.get("params") or {})
            params["text"] = str(text)
            return str(parsed["intent"]), params, "llm"
    except Exception:
        pass  # 规则兜底
    intent, params = _extract_intent(str(text))
    return intent, params, "ok"


def _advance_proposal(campaign: str, params: dict[str, str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """advance 意图: 读取场景图给出推进提案 (SCENE 待批), 不写任何事件流 (无 AINPC)。"""
    target = str(params.get("target") or "")
    proposal: list[dict[str, Any]] = [{
        "kind": "SCENE", "pending": True,
        "payload": {"to": target, "branch": ""},
    }]
    try:
        from trpg.agent.scene_coordinator import SceneCoordinator
        sc = SceneCoordinator()
        delta = sc.advance([], None)  # 纯读当前场景 (空事件输入, 无持久化副作用)
        current = str(delta.get("scene_id", ""))
        return ({
            "current_scene": current,
            "target": target or current,
            "note": "场景推进提案: KP 确认后经场景推进事件落库; NL 端点本身不写事件流 (无 AINPC)",
        }, proposal)
    except Exception:
        return ({
            "current_scene": "",
            "target": target or "",
            "note": "场景推进建议: 场景图未加载, 请 KP 指定目标场景; NL 端点不自动执行",
        }, proposal)


def _record_proposal(campaign: str, params: dict[str, str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """record 意图: 叙事/行动记录提案 (TRANSCRIPT_APPENDED 待批), 不写事件流。"""
    t = str(params.get("text") or "")
    record_text = re.sub(r"^(记录|记一下|记录一下|记下|追加记录|存档)[:：\s]*", "", t).strip() or t
    proposal: list[dict[str, Any]] = [{
        "kind": "TRANSCRIPT_APPENDED", "pending": True,
        "payload": {"campaign_id": campaign, "text": record_text, "source": "import"},
    }]
    return ({
        "proposal": proposal[0],
        "note": "记录提案: KP 确认后经 /access/voice/transcript 或事件接口落库; NL 端点不自动执行",
    }, proposal)


async def _nl_summary(campaign: str, scene: str) -> dict[str, Any]:
    """summary 意图: 最近事件摘要 (只读 replay; LLM 优先, 模板兜底)。"""
    store = rest_mod._store()
    await store.init()
    events = await store.replay(campaign)
    by_type: dict[str, int] = {}
    for e in events:
        by_type[e.type] = by_type.get(e.type, 0) + 1
    tip = events[-1].seq if events else -1
    tail = events[-8:]
    tail_text = "；".join("[%s] %s" % (e.type, str(e.payload)[:100]) for e in tail)
    try:
        gw = _nl_gateway_factory()
        result = gw.complete(
            [{"role": "system", "content": "你是 TRPG 桌游摘要助手。对最近事件给出 3 句以内的结构化摘要（进展/悬念/待决）。只输出 JSON：{\"summary\":\"...\"}"},
             {"role": "user", "content": "会话: %s\n场景: %s\n最近事件: %s" % (campaign, scene or "（未提供）", tail_text or "（无）")}],
            max_tokens=512, temperature=0.5)
        parsed = _parse_json_object(result.text)
        if parsed and str(parsed.get("summary", "")).strip():
            return {"text": str(parsed["summary"]), "mode": "llm"}
    except Exception:
        pass  # 模板兜底
    return {
        "text": ("最近事件摘要（模板兜底）：共 %d 条事件（tip=%d），按类型：%s。"
                 "LLM 通道不可用，请 KP 审阅事件流。")
                % (len(events), tip, by_type or "无"),
        "mode": "template",
    }


@router.post("/access/nl")
async def nl_dispatch(body: dict[str, Any],
                      entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    """自然语言 -> 调度链路 (DSH-2, additive): 解析意图并按意图分发提案/建议。

    鉴权: webapp=KP 端 (同 /access/advice); mobile/recorder 合法 token -> 403 kp_only。
    铁律: **不自动执行 (无 AINPC)** —— 本端点从不写事件流; advance/record 仅返回待 KP 确认的
    提案 (events=[{kind,pending:true,...}]), advice/summary 只返回建议/摘要; KP 拍板走既有端点。
    返回: {intent, params, suggestion?, events?, status}。
    """
    campaign = str(body.get("campaign") or body.get("campaign_id") or "")
    if not campaign.strip():
        _raise(CODE_PARAM, "campaign required")
    text = str(body.get("text") or "")
    if not text.strip():
        _raise(CODE_PARAM, "text required")
    scene = str(body.get("scene") or "")
    intent, params, cls_status = _classify_nl(text)
    params.setdefault("campaign", campaign)
    if intent == "advice":
        rt = str(params.get("request_type") or "ruling")
        if rt not in ADVICE_TYPES:
            rt = "ruling"
        record = _advice_core(campaign, rt, scene, body.get("events"), text, "")
        return _ok({"intent": "advice", "params": params,
                    "suggestion": record, "events": [],
                    "status": record.get("status", cls_status)})
    if intent == "advance":
        suggestion, events = _advance_proposal(campaign, params)
        return _ok({"intent": "advance", "params": params,
                    "suggestion": suggestion, "events": events, "status": cls_status})
    if intent == "record":
        suggestion, events = _record_proposal(campaign, params)
        return _ok({"intent": "record", "params": params,
                    "suggestion": suggestion, "events": events, "status": cls_status})
    if intent == "summary":
        summary = await _nl_summary(campaign, scene)
        return _ok({"intent": "summary", "params": params,
                    "suggestion": summary, "events": [], "status": cls_status})
    _raise(CODE_PARAM, "unrecognized intent")


# ---- V-1 (additive): 录音设备状态 DEVICE_STATUS 端点 --------------------------

@router.post("/access/device/status")
async def device_status_post(body: dict[str, Any],
                             entry: dict[str, Any] = Depends(_require_recorder_end)) -> dict[str, Any]:
    """录音设备状态上报 (V-1, additive, recorder 端): 内存态注册表 + 追加式历史。

    body: device_id(必填, 非空), battery(可选, 数值或 None), recording(可选 bool, 默认 False),
    flagged(可选 bool 重点标记, 默认 False), note(可选 str), status_text(可选 str),
    ts(可选 ISO8601 str, 缺省服务端 now)。
    "事件流打点"降级: events.py 冻结 (禁新增 kind, 无合适既有 kind 承载设备状态)
    -> per-device 追加式状态历史 (审计打点); recording 翻转 / flagged 置位或翻转时
    历史项加 mark 并返回 change_marks。历史上限每设备 50 条 (超限裁剪旧项)。
    返回: {device_id, status:"ok", seq(累计上报次数), changed, change_marks}。
    """
    device_id = str(body.get("device_id") or "").strip()
    if not device_id:
        _raise(CODE_PARAM, "device_id required")
    battery = body.get("battery")
    if battery is not None and (isinstance(battery, bool)
                                or not isinstance(battery, (int, float))):
        _raise(CODE_PARAM, "battery must be number")
    recording = body.get("recording", False)
    if recording is None:
        recording = False
    if not isinstance(recording, bool):
        _raise(CODE_PARAM, "recording must be bool")
    flagged = body.get("flagged", False)
    if flagged is None:
        flagged = False
    if not isinstance(flagged, bool):
        _raise(CODE_PARAM, "flagged must be bool")
    note = body.get("note")
    note = str(note) if note is not None else ""
    status_text = body.get("status_text")
    status_text = str(status_text) if status_text is not None else ""
    ts = body.get("ts")
    if ts is not None:
        if not isinstance(ts, str) or not ts.strip():
            _raise(CODE_PARAM, "ts must be ISO8601 string")
        ts_value = ts
    else:
        ts_value = _now()
    prev = _DEVICE_STATUS.get(device_id)
    marks: list[str] = []
    if prev is not None:
        if bool(prev.get("recording", False)) != bool(recording):
            marks.append("recording_flip")
        if bool(prev.get("flagged", False)) != bool(flagged):
            marks.append("flagged")
    seq = int(prev.get("seq", 0)) + 1 if prev else 1
    item: dict[str, Any] = {
        "ts": ts_value,
        "recording": recording,
        "flagged": flagged,
        "battery": battery,
        "note": note,
        "status_text": status_text,
    }
    if marks:
        item["mark"] = list(marks)
    hist = _DEVICE_HISTORY.setdefault(device_id, [])
    hist.append(item)
    if len(hist) > _DEVICE_HISTORY_LIMIT:
        del hist[:len(hist) - _DEVICE_HISTORY_LIMIT]
    _DEVICE_STATUS[device_id] = {
        "device_id": device_id,
        "status_text": status_text,
        "recording": recording,
        "flagged": flagged,
        "battery": battery,
        "note": note,
        "ts": ts_value,
        "seq": seq,
    }
    return _ok({
        "device_id": device_id,
        "status": "ok",
        "seq": seq,
        "changed": bool(marks),
        "change_marks": marks,
    })


@router.get("/access/device/status")
def device_status_get(device_id: str = Query(..., min_length=1),
                      entry: dict[str, Any] = Depends(_require_any_end)) -> dict[str, Any]:
    """录音设备最新状态 + 最近 10 条历史 (V-1, additive, 任意启用端只读)。

    鉴权: _require_any_end (mobile/webapp 等任一启用端可查); 无记录 -> 404
    (保留码 CODE_NOTFOUND, error "device status not found")。
    """
    latest = _DEVICE_STATUS.get(device_id)
    if latest is None:
        _raise(CODE_NOTFOUND, "device status not found")
    hist = _DEVICE_HISTORY.get(device_id, [])
    return _ok({**dict(latest), "history": list(hist[-10:])})

# ---- T2 (additive): 玩家端接入 + 主持端开桌/开回合 ---------------------------
# 全部 additive: 不修改任何既有端点签名/行为, 不新增 WS 帧, 不改冻结契约文件。
# 统一响应包裹与错误码沿用本模块 (400/401/403/404/409/500)。

@router.post("/access/audio_upload")
async def audio_upload(file: UploadFile = File(...),
                       campaign: str = Form(...),
                       kind: str = Form("voice"),
                       player_id: str = Form("pl_mobile"),
                       background_tasks: BackgroundTasks = BackgroundTasks(),
                       entry: dict[str, Any] = Depends(_require_end("recorder"))) -> dict[str, Any]:
    """录音硬件文件导入: multipart (file + campaign + kind), 复用 audio_import 语义."""
    return await _audio_import_core(file, campaign, kind, player_id, background_tasks)


@router.post("/access/player/audio")
async def player_audio(file: UploadFile = File(...),
                       campaign: str = Form(...),
                       kind: str = Form("voice"),
                       player_id: str = Form("pl_player"),
                       background_tasks: BackgroundTasks = BackgroundTasks(),
                       entry: dict[str, Any] = Depends(_require_player_end)) -> dict[str, Any]:
    """玩家录音上传 (T2 additive, mobile 端 token)。

    合并玩家端中转层 (9321) 的关键: 玩家端只持 mobile token, 服务端内部复用
    recorder 落库语义 (_audio_import_core) —— recorder token 不返回客户端、
    不写日志 (token 端隔离 R5 不破)。响应与 /access/audio_upload 同构。
    鉴权矩阵: 无 token -> 401; webapp/recorder 启用端 token -> 403 mobile_only;
    mobile token -> 200。
    """
    return await _audio_import_core(file, campaign, kind, player_id, background_tasks)


# 连接码前缀 (大小写不敏感); 支持 "TABLE-XXXX" 与裸 table_id/campaign
_TABLE_CODE_PREFIX = "table-"

# ---- T2 (additive): table 注册表持久化 -------------------------------------
# 背景（队长实测 bug）：table_id <-> campaign_id 的映射原本**只存在于内存**的
# rest.TABLES 里（rest.py 的 create_table 不落事件；事件库里也没有
# CAMPAIGN_STARTED / TABLE_CREATED 记录）。因此**服务一重启，所有已开桌的
# table 都变成不可解析** -> /access/table/resolve 恒返回 exists:false、
# /access/host/turn 的 table_id 变空串（F2 实质不可用）。
# 修法（additive，不改冻结契约、不改既有端点签名）：把注册表快照到
# data/tables_registry.json，启动/首次使用时载入 rest.TABLES。
TABLES_REGISTRY_PATH = APP_ROOT / "data" / "tables_registry.json"   # 默认位置
_tables_loaded = False


def _registry_path() -> Path:
    """注册表文件路径 —— 跟随事件库所在目录。

    为什么不用固定常量: 所有测试 fixture 都会 monkeypatch rest_mod.DEFAULT_DB
    指向 tmp_path; 若注册表路径写死到 APP_ROOT/data, 测试里调用 /access/host/table
    就会把**生产注册表覆盖成测试数据**(实测事故: 远程跑 pytest 后 tables_registry.json
    只剩一个测试桌 t_bf, t_demo 等真实桌全部丢失 -> F2 失效)。
    改为跟随 DEFAULT_DB 后, 测试隔离自动生效, 不需要每个 fixture 都记得 patch。
    """
    try:
        return Path(rest_mod.DEFAULT_DB).parent / "tables_registry.json"
    except Exception:  # noqa: BLE001
        return TABLES_REGISTRY_PATH


def _load_tables_registry() -> None:
    """首次调用时把持久化的 table 注册表合并进 rest.TABLES (跨重启保留映射)。"""
    global _tables_loaded
    if _tables_loaded:
        return
    _tables_loaded = True
    try:
        path = _registry_path()
        if not path.is_file():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for tid, entry in data.items():
                if isinstance(entry, dict) and tid not in rest_mod.TABLES:
                    rest_mod.TABLES[str(tid)] = entry
    except Exception:  # noqa: BLE001 — 注册表损坏不得影响服务
        print("[access] tables_registry load failed; ignored")


def _save_tables_registry() -> None:
    """把当前 rest.TABLES 快照落盘 (best-effort, 失败不影响请求)。

    安全网: **拒绝用空注册表覆盖已有非空快照** —— 否则任何在「内存未载入」时
    触发的保存都会把全部已持久化的桌清空 (实测事故的第二个成因)。
    """
    try:
        path = _registry_path()
        if not rest_mod.TABLES and not _tables_loaded:
            # 内存为空**且从未载入** => 这是「未初始化」而非「真的空」, 拒绝覆盖
            # (载入过之后仍为空则属真实状态, 允许写入, 例如删掉最后一张桌)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(rest_mod.TABLES, ensure_ascii=False, indent=2),
            encoding="utf-8")
    except OSError:
        pass


def persist_tables() -> None:
    """供**其它写路径**调用: 先合并已持久化快照, 再落盘 (创建即落盘)。

    为什么必须先 load: 若内存为空(例如刚重启)而直接保存, 会把快照覆盖成
    「只剩本次新建的这张桌」, 其余已持久化的桌全部丢失 (实测事故的直接成因)。
    """
    _load_tables_registry()
    _save_tables_registry()


def reset_tables_registry_cache() -> None:
    """测试隔离用: 允许重新从磁盘载入。"""
    global _tables_loaded
    _tables_loaded = False


def load_persisted_tables() -> None:
    """启动时载入持久化的 table 注册表 (app/main.py lifespan 调用)。"""
    _load_tables_registry()


def _code_candidates(code: str) -> list[str]:
    """连接码候选 (去空白, 去 TABLE- 前缀, 保序去重)。"""
    out: list[str] = []
    raw = str(code or "").strip()
    if raw:
        out.append(raw)
    if raw.lower().startswith(_TABLE_CODE_PREFIX):
        rest = raw[len(_TABLE_CODE_PREFIX):].strip()
        if rest and rest not in out:
            out.append(rest)
    return out


async def _table_entry_by_campaign_async(campaign: str, events: list[Any]) -> str:
    """campaign -> table_id 反查 (持久化注册表优先, 其次投影的 session.table_id)。

    数据源优先级:
      1) rest.TABLES (含启动时从 tables_registry.json 载入的持久化项)
      2) 事件投影 SessionState.table_id (CAMPAIGN_STARTED 记录过 table_id 时可用)
    都查不到返回 "" (不报错)。
    """
    _load_tables_registry()
    tid = _table_entry_by_campaign(campaign)
    if tid:
        return tid
    try:
        turn_state = rest_mod.project(events, campaign)
        return str(getattr(turn_state, "table_id", "") or "")
    except Exception:  # noqa: BLE001
        return ""


def _table_entry_by_campaign(campaign: str) -> str:
    """campaign -> table_id 反查 (查不到返回 "")。"""
    for tid, t in list(rest_mod.TABLES.items()):
        if str(t.get("campaign_id") or "") == campaign:
            return str(tid)
    return ""


@router.get("/access/table/resolve")
async def table_resolve(code: str | None = Query(default=None),
                        entry: dict[str, Any] = Depends(_require_any_end)) -> dict[str, Any]:
    """连接码 -> {code,table_id,campaign,name,exists} (T2 additive, 任意启用端 token)。

    匹配顺序 (ENDPOINT-SPEC-NEW §2, 全部大小写不敏感):
      ① TABLES 的 table_id 精确匹配 (另兼容 "TABLE-<id>" 前缀写法)
      ② TABLES[t].config.code 匹配
      ③ TABLES 的 campaign_id 匹配 (additive 超集)
      ④ 事件库回退: 候选码即 campaign 且事件流非空 (table_id 即 campaign 的回退)
    未命中 -> **200** + exists=false + table_id/campaign/name 均为 "" (客户端据此
    显示"连接码不存在", 而非网络错误)。
    """
    raw = str(code or "").strip()
    if not raw:
        _raise(CODE_PARAM, "code required")
    # 载入持久化注册表 (跨重启保留 table<->campaign 映射, 见 TABLES_REGISTRY_PATH)
    _load_tables_registry()
    cands = _code_candidates(raw)
    lower = [c.lower() for c in cands]

    def _hit(tid: str, t: dict[str, Any]) -> dict[str, Any]:
        # 机会性落盘: 捕获经 /api/tables 等外部路径创建、尚未持久化的桌
        _save_tables_registry()
        return _ok({"code": raw, "table_id": tid,
                    "campaign": str(t.get("campaign_id") or tid),
                    "name": str(t.get("name") or tid), "exists": True})

    # ① table_id
    for tid, t in list(rest_mod.TABLES.items()):
        if str(tid).lower() in lower:
            return _hit(tid, t)
    # ② config.code
    for tid, t in list(rest_mod.TABLES.items()):
        cfg = t.get("config") if isinstance(t.get("config"), dict) else {}
        stored = str((cfg or {}).get("code") or "").strip()
        if stored and stored.lower() in lower:
            return _hit(tid, t)
    # ③ campaign_id
    for tid, t in list(rest_mod.TABLES.items()):
        cid = str(t.get("campaign_id") or "")
        if cid and cid.lower() in lower:
            return _hit(tid, t)
    # ④ 事件库回退 (table_id 即 campaign)
    store = rest_mod._store()
    await store.init()
    for cand in cands:
        if await store.replay(cand):
            return _ok({"code": raw, "table_id": cand, "campaign": cand,
                        "name": cand, "exists": True})
    return _ok({"code": raw, "table_id": "", "campaign": "",
                "name": "", "exists": False})


@router.post("/access/host/table")
async def host_table(body: dict[str, Any],
                     entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    """一键开桌 (T2 additive, webapp/KP 端): 复用 rest.TABLES 既有创建语义 + 幂等。

    - 同 table_id 且同 campaign_id 重复调用 -> created=false (幂等, 便于重跑验收)
    - 同 table_id 但 campaign_id 不同 -> 409 (沿用既有 "table exists" 冲突语义)
    鉴权: _require_kp_end (无 token 401 / mobile|recorder 403 kp_only / webapp 200)。
    """
    # 关键: 先载入已持久化的注册表, 否则重启后首次调用 host_table 时
    # 内存里只有新建的这一张桌, _save_tables_registry() 会把快照**覆盖成只剩它**,
    # 其余已持久化的桌全部丢失 (实测事故的直接成因)。
    _load_tables_registry()
    table_id = str(body.get("table_id") or "").strip()
    campaign_id = str(body.get("campaign_id") or "").strip()
    if not table_id or not campaign_id:
        _raise(CODE_PARAM, "table_id/campaign_id required")
    # t5 fix (reviewer P3): 与 /api/tables 同规则的长度上限, 防异常超长输入。
    if len(table_id) > 128 or len(campaign_id) > 128:
        _raise(CODE_PARAM, "table_id/campaign_id too long (max 128)")
    ruleset = str(body.get("ruleset") or "coc7")
    name = str(body.get("name") or "").strip() or table_id
    existing = rest_mod.TABLES.get(table_id)
    if existing is not None:
        if str(existing.get("campaign_id") or "") != campaign_id:
            _raise(CODE_CONFLICT, "table exists")
        return _ok({"table_id": table_id, "campaign_id": campaign_id,
                    "ruleset": str(existing.get("ruleset") or ruleset),
                    "name": str(existing.get("name") or name),
                    "exists": True, "created": False})
    rest_mod.TABLES[table_id] = {"table_id": table_id,
                                 "campaign_id": campaign_id,
                                 "ruleset": ruleset, "config": {},
                                 "name": name}
    _save_tables_registry()   # 持久化: 服务重启后仍可解析该桌 (F2 不失效)
    return _ok({"table_id": table_id, "campaign_id": campaign_id,
                "ruleset": ruleset, "name": name,
                "exists": True, "created": True})


@router.post("/access/host/turn")
async def host_turn(body: dict[str, Any],
                    entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    """开启行动窗 (T2 additive, webapp/KP 端): 复用 command_bus start_turn 唯一写路径。

    落库 TURN_STARTED -> 既有 projector 置 turn.state=COLLECTING
    (不另造状态机; 与 app/scheduler/turn_window.py 同一语义)。
    turn_no 缺省 = 当前投影 turn_no + 1 (无回合则 1)。
    req_id 幂等: 同 (campaign, req_id) 重复调用直接重放首次响应 (status=duplicate),
    不再落第二条 TURN_STARTED。
    """
    campaign = str(body.get("campaign") or body.get("campaign_id") or "").strip()
    if not campaign:
        _raise(CODE_PARAM, "campaign required")
    req_id = str(body.get("req_id") or "").strip()
    if req_id:
        prev = _TURN_OPEN_KEYS.get((campaign, req_id))
        if prev is not None:
            return _ok({**prev, "status": "duplicate"})
    raw_window = body.get("window_sec")
    try:
        window_sec = int(WINDOW_SEC_DEFAULT if raw_window is None else raw_window)
    except (TypeError, ValueError):
        _raise(CODE_PARAM, "invalid window_sec")
    if not (WINDOW_SEC_MIN <= window_sec <= WINDOW_SEC_MAX):
        _raise(CODE_PARAM, "invalid window_sec")
    store = rest_mod._store()
    await store.init()
    events = await store.replay(campaign)
    turn = rest_mod.project(events, campaign).turn
    table_id = await _table_entry_by_campaign_async(campaign, events)

    # spec §5 幂等②: 已在 COLLECTING -> 不新开回合, 直接返回当前回合。
    # 保证验收"开一次窗 + 两端各提交一次"精确产生 2 条 ACTION_SUBMITTED。
    if turn is not None and str(turn.state) == "COLLECTING":
        last_seq = None
        for ev in reversed(events):
            if ev.type == "TURN_STARTED":
                last_seq = ev.seq
                break
        return _ok({"campaign": campaign, "table_id": table_id,
                    "turn_no": turn.turn_no, "state": "COLLECTING",
                    "countdown_end_ts": str(turn.countdown_end_ts or ""),
                    "countdown_end_ts_epoch": _epoch_ts(turn.countdown_end_ts),
                    "window_sec": window_sec,
                    "already_collecting": True,
                    "status": "already_collecting", "seq": last_seq})

    raw_turn_no = body.get("turn_no")
    if raw_turn_no is None:
        turn_no = (turn.turn_no + 1) if turn is not None else 1
    else:
        try:
            turn_no = int(raw_turn_no)
        except (TypeError, ValueError):
            _raise(CODE_PARAM, "turn_no must be int")
        if turn_no <= 0:
            _raise(CODE_PARAM, "turn_no must be positive")
    countdown_end_ts = (datetime.now(timezone.utc)
                        + timedelta(seconds=window_sec)).isoformat()
    bus = CommandBus(store, campaign, guard=_guard_for(campaign))
    _t0 = time.perf_counter()
    try:
        receipt = await bus.dispatch("start_turn",
                                     {"campaign_id": campaign,
                                      "turn_no": turn_no,
                                      "window_sec": window_sec,
                                      "countdown_end_ts": countdown_end_ts},
                                     actor="kp")
    except (CommandError, BranchViolation, ConflictError) as exc:
        _raise(CODE_PARAM, str(exc))
    rest_mod.record_latency_ms(int((time.perf_counter() - _t0) * 1000))  # G-1 采样
    seqs = list(receipt.get("seqs") or [])
    data = {"campaign": campaign, "table_id": table_id,
            "turn_no": turn_no, "window_sec": window_sec,
            # 与冻结契约 TurnStarted.countdown_end_ts 同值 (str); epoch 另给便于客户端
            "countdown_end_ts": countdown_end_ts,
            "countdown_end_ts_epoch": _epoch_ts(countdown_end_ts),
            "state": "COLLECTING", "already_collecting": False,
            "status": receipt.get("status", "ok"),
            "seq": seqs[0] if seqs else None, "seqs": seqs}
    if req_id:
        _TURN_OPEN_KEYS[(campaign, req_id)] = data
    return _ok(data)

