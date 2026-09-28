"""服务端 STT 接线 (EX-STT, D1 官方闭环最短板) — MIT.

把 llm_providers.yaml 的 ``stt`` 命名段接到 app/voice/stt_cloud.transcribe:

- 通道配置: llm_providers.yaml ``stt: {name, model, base_url, api_key}``;
  key/base_url 只走环境变量 (STT_API_KEY / STT_BASE_URL, 与 stt_cloud 一致);
- 降级: STT 不可用 (无 key / 后端失败) -> 占位文本 + degraded=True (stt_cloud 内建
  mock 兜底, 本模块不抛); 调用方 (access.py) 以 response 的 status 标注, 不阻断主流程;
- 铁律: 冻结契约 (TranscriptAppended 字段集) 不变; 本模块只负责"取配置 -> 转写"。

Python 3.12 compatible; 无网络于 import 时。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.voice.stt_cloud import STTResult, transcribe as _cloud_transcribe

CONFIGS_DIR = Path(__file__).resolve().parent.parent.parent / "configs"
LLM_PROVIDERS = CONFIGS_DIR / "llm_providers.yaml"

DEFAULT_MODEL = "whisper-1"


def _stt_config() -> dict[str, Any]:
    """读取 llm_providers.yaml 的 stt 命名段 (缺失/损坏 -> 空 dict, 走默认值)."""
    cfg: dict[str, Any] = {}
    try:
        if LLM_PROVIDERS.is_file():
            with open(LLM_PROVIDERS, encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
                if isinstance(loaded, dict) and isinstance(loaded.get("stt"), dict):
                    cfg = loaded["stt"]
    except Exception:  # noqa: BLE001 — 配置异常不阻断, 走默认通道
        cfg = {}
    return cfg


def transcribe(audio: bytes | str, model: str | None = None,
               allow_mock: bool = True) -> STTResult:
    """按 llm_providers stt 段配置转写; 无 key/失败 -> 降级结果 (degraded=True, 不抛).

    - ``audio``: 原始音频字节 (audio_upload 文件 / transcript audio 解码) 或引用串;
    - ``model``: 覆盖 stt 段 model; 未配则默认 whisper-1;
    - key/base_url 由 stt_cloud 从环境变量 (STT_API_KEY / STT_BASE_URL) 读取。
    """
    cfg = _stt_config()
    return _cloud_transcribe(
        audio,
        model=model or str(cfg.get("model") or DEFAULT_MODEL),
        allow_mock=allow_mock,
    )
