"""R27 热重载: 保存文件 (mtime + sha256) 监听 -> 差异 -> 落库 -> 自动广播 -> 可回滚。

铁律 (与冻结契约一致):
  * 变更**只**通过 EventStore.append 落库; 广播交给既有单一收口
    (EventStore.on_append = app.web.ws_bridge.publish_events)。
    本模块**不** import hub / ws_bridge, 不直接 publish, 不新增帧类型。
  * 变更规格只使用既有 EVENT_TYPES (见 diff.py)。
  * 幂等: 同一份保存文件重复应用 -> diff 为空 -> **零事件**(可机器断言)。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.domain.events import make_event
from app.hotreload import compiled as hc
from app.hotreload.diff import changes_digest, diff_states
from app.hotreload.spec import (BINDINGS_RELPATH, BINDINGS_SCHEMA, HISTORY_DEPTH,
                                POLL_INTERVAL_S, SAVE_RELPATH, CompiledError)

logger = logging.getLogger("trpg.hotreload")

_PAYLOAD_BUILDERS = {
    "MAP_UPDATED": lambda cid, c: {"campaign_id": cid, "map_id": c.get("map_id", ""),
                                   "op": c.get("op", "set_status"),
                                   "target": c.get("target", ""),
                                   "delta": dict(c.get("delta") or {})},
    "EVENT_INJECTED": lambda cid, c: {"campaign_id": cid, "node_id": c.get("node_id", ""),
                                      "payload": dict(c.get("payload") or {}),
                                      "dry_run_result": dict(c.get("dry_run_result") or {})},
    "CLUE_GRANTED": lambda cid, c: {"campaign_id": cid, "clue_id": c.get("clue_id", ""),
                                    "ref": c.get("ref", ""),
                                    "condition_met": bool(c.get("condition_met", True))},
    "TABLE_CONFIG_UPDATED": lambda cid, c: {"table_id": cid, "diff": dict(c.get("diff") or {})},
    "SNAPSHOT_LOADED": lambda cid, c: {"campaign_id": cid,
                                       "snapshot_ref": c.get("snapshot_ref", ""),
                                       "resume_cursor": c.get("resume_cursor", "")},
    "SNAPSHOT_SAVED": lambda cid, c: {"campaign_id": cid,
                                      "snapshot_ref": c.get("snapshot_ref", ""),
                                      "event_seq_at": int(c.get("event_seq_at", -1))},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(p: str | Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class Binding:
    campaign_id: str
    module_id: str
    path: str
    table_id: str = ""
    last_mtime: float = 0.0
    last_sha: str = ""
    applied_norm: dict[str, Any] | None = None
    applied_digest: str = ""
    #: 历史条目 = {"norm": <规范化状态>, "digest": <该状态的确定性摘要>}
    #: 必须同时保存两者: 规范化状态无法反推原摘要, 否则回滚后摘要对不上。
    history: list[dict[str, Any]] = field(default_factory=list)
    last_changes: list[dict[str, Any]] = field(default_factory=list)
    last_change_digest: str = ""
    apply_count: int = 0
    event_count: int = 0
    last_applied_at: str = ""
    last_error: str = ""
    rollback_count: int = 0

    #: 持久化字段 —— 刻意**不含** last_mtime:
    #: 重载后 last_mtime 归 0, 于是 poll_once 的 `st_mtime == last_mtime` 短路必然不成立,
    #: 首轮就会比对 sha256 —— 进程停机期间发生的改动因而**会被检测到**, 不会被吞掉。
    def to_dict(self) -> dict[str, Any]:
        return {"campaign_id": self.campaign_id, "module_id": self.module_id,
                "path": self.path, "table_id": self.table_id, "last_sha": self.last_sha,
                "applied_norm": self.applied_norm, "applied_digest": self.applied_digest,
                "history": list(self.history), "apply_count": self.apply_count,
                "event_count": self.event_count, "last_applied_at": self.last_applied_at,
                "rollback_count": self.rollback_count}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Binding":
        b = cls(campaign_id=str(d.get("campaign_id", "")), module_id=str(d.get("module_id", "")),
                path=str(d.get("path", "")), table_id=str(d.get("table_id", "")))
        b.last_sha = str(d.get("last_sha", ""))
        norm = d.get("applied_norm")
        b.applied_norm = norm if isinstance(norm, dict) else None
        b.applied_digest = str(d.get("applied_digest", ""))
        hist = d.get("history")
        b.history = [x for x in hist if isinstance(x, dict)] if isinstance(hist, list) else []
        b.apply_count = int(d.get("apply_count", 0) or 0)
        b.event_count = int(d.get("event_count", 0) or 0)
        b.last_applied_at = str(d.get("last_applied_at", ""))
        b.rollback_count = int(d.get("rollback_count", 0) or 0)
        return b

    def snapshot(self) -> dict[str, Any]:
        return {"campaign_id": self.campaign_id, "module_id": self.module_id,
                "path": self.path, "table_id": self.table_id,
                "last_mtime": self.last_mtime, "last_sha": self.last_sha,
                "applied_digest": self.applied_digest, "apply_count": self.apply_count,
                "event_count": self.event_count, "rollback_count": self.rollback_count,
                "history_depth": len(self.history),
                "last_change_count": len(self.last_changes),
                "last_change_digest": self.last_change_digest,
                "last_applied_at": self.last_applied_at, "last_error": self.last_error}


class HotReloadWatcher:
    """保存文件监听器 (线程安全; poll_once 为纯异步, 由路由/后台任务调用)。"""

    def __init__(self, *, interval: float = POLL_INTERVAL_S) -> None:
        self.interval = float(interval)
        self.bindings: dict[str, Binding] = {}
        self.polls = 0
        self.hot_applies = 0
        self._task: asyncio.Task | None = None
        self._lock = threading.Lock()
        self._loop = None

    # ------------------------------------------------------------- 绑定管理
    def bind(self, campaign_id: str, module_id: str, save_path: str | Path,
             table_id: str = "", *, initial: dict[str, Any] | None = None) -> Binding:
        p = Path(save_path)
        with self._lock:
            b = Binding(campaign_id=str(campaign_id), module_id=str(module_id),
                        path=str(p), table_id=str(table_id or ""))
            if p.is_file():
                b.last_mtime = p.stat().st_mtime
                b.last_sha = sha256_file(p)
            if initial is not None:
                b.applied_norm = hc.normalize(initial)
                b.applied_digest = hc.canonical_digest(initial)
            self.bindings[b.campaign_id] = b
        self._persist()
        return b

    def unbind(self, campaign_id: str) -> bool:
        with self._lock:
            removed = self.bindings.pop(str(campaign_id), None) is not None
        if removed:
            self._persist()
        return removed

    def get(self, campaign_id: str) -> Binding | None:
        return self.bindings.get(str(campaign_id))

    def status(self) -> dict[str, Any]:
        return {"schema": "HotReloadStatus v1", "interval_s": self.interval,
                "polls": self.polls, "hot_applies": self.hot_applies,
                "running": bool(self._task and not self._task.done()),
                "binding_count": len(self.bindings),
                "bindings": [b.snapshot() for b in
                             sorted(self.bindings.values(), key=lambda x: x.campaign_id)]}

    # --------------------------------------------------------- 绑定表持久化 (F-9)
    def _persist(self) -> None:
        """把绑定表落盘 (原子写: tmp -> os.replace)。失败只告警, 不影响主流程。"""
        try:
            p = bindings_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                doc = {"schema": BINDINGS_SCHEMA,
                       "bindings": [b.to_dict() for b in
                                    sorted(self.bindings.values(), key=lambda x: x.campaign_id)]}
            tmp = p.with_name("%s.tmp-%d" % (p.name, os.getpid()))
            payload = json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(payload)
            os.replace(tmp, p)
        except Exception as exc:  # noqa: BLE001 — 持久化失败不得影响热重载主流程
            logger.warning("hotreload bindings persist failed: %s", exc)

    def load_persisted(self) -> int:
        """从磁盘回灌绑定表 (幂等: 已存在的 campaign 不覆盖, 磁盘为准)。

        返回**新增**的绑定数。文件缺失/损坏 -> 返回 0, 绝不抛。
        """
        try:
            p = bindings_path()
            if not p.is_file():
                return 0
            doc = json.loads(p.read_text(encoding="utf-8"))
            raw = doc.get("bindings") if isinstance(doc, dict) else None
            if not isinstance(raw, list):
                return 0
            added = 0
            for item in raw:
                if not isinstance(item, dict):
                    continue
                cid = str(item.get("campaign_id", "")).strip()
                if not cid:
                    continue
                with self._lock:
                    if cid in self.bindings:
                        continue
                    self.bindings[cid] = Binding.from_dict(item)
                added += 1
            return added
        except Exception as exc:  # noqa: BLE001 — 坏绑定表不得阻止进程启动
            logger.warning("hotreload bindings load failed: %s", exc)
            return 0

    # ------------------------------------------------------------- 应用变更
    async def _append(self, campaign_id: str, changes: list[dict[str, Any]]) -> list[int]:
        """把变更规格落库 (既有类型) -> 返回 seq 列表。广播由既有单一收口负责。"""
        if not changes:
            return []
        from app.web import rest as rest_mod
        store = rest_mod._store()
        await store.init()
        events = []
        for c in changes:
            builder = _PAYLOAD_BUILDERS.get(str(c.get("type")))
            if builder is None:
                continue
            events.append(make_event(seq=0, campaign_id=campaign_id, type=str(c["type"]),
                                     payload=builder(campaign_id, c), actor="system",
                                     ts=_now()))
        if not events:
            return []
        return await store.append(campaign_id, events)

    async def apply_state(self, campaign_id: str, raw: dict[str, Any], *,
                          source: str = "manual", push_history: bool = True) -> dict[str, Any]:
        """校验 -> 规范化 -> 差异 -> 落库(自动广播) -> 更新 applied/history。

        幂等: raw 与已应用状态规范化后相同 -> changes=[] -> 零事件。
        """
        b = self.get(campaign_id)
        if b is None:
            raise CompiledError("HOTRELOAD_NOT_BOUND",
                                "campaign 未绑定热重载: %s" % campaign_id,
                                {"campaign_id": campaign_id})
        summary = hc.validate_compiled(raw)          # 结构 + 可交互物契约
        norm = hc.normalize(raw)
        changes = diff_states(b.applied_norm, norm)
        seqs = await self._append(campaign_id, changes)
        if push_history and b.applied_norm is not None and changes:
            b.history.append({"norm": b.applied_norm, "digest": b.applied_digest})
            del b.history[:-HISTORY_DEPTH]
        b.applied_norm = norm
        b.applied_digest = hc.canonical_digest(raw)
        b.last_changes = changes
        b.last_change_digest = changes_digest(changes)
        b.apply_count += 1
        b.event_count += len(seqs)
        b.last_applied_at = _now()
        b.last_error = ""
        if changes:
            self.hot_applies += 1
        return {"ok": True, "campaign_id": campaign_id, "source": source,
                "digest": b.applied_digest, "change_count": len(changes),
                "change_digest": b.last_change_digest, "changes": changes,
                "seqs": seqs, "counts": summary["counts"],
                "history_depth": len(b.history), "idempotent": not changes}

    async def apply_file(self, campaign_id: str, *, source: str = "manual") -> dict[str, Any]:
        b = self.get(campaign_id)
        if b is None:
            raise CompiledError("HOTRELOAD_NOT_BOUND", "campaign 未绑定热重载: %s" % campaign_id,
                                {"campaign_id": campaign_id})
        raw = hc.load_compiled(b.path)
        out = await self.apply_state(campaign_id, raw, source=source)
        p = Path(b.path)
        if p.is_file():
            b.last_mtime = p.stat().st_mtime
            b.last_sha = sha256_file(p)
        return out

    async def rollback(self, campaign_id: str, steps: int = 1) -> dict[str, Any]:
        """回滚到上一个已应用状态 (可多步), 并落一条既有类型 SNAPSHOT_LOADED 标记。"""
        b = self.get(campaign_id)
        if b is None:
            raise CompiledError("HOTRELOAD_NOT_BOUND", "campaign 未绑定热重载: %s" % campaign_id,
                                {"campaign_id": campaign_id})
        steps = max(1, int(steps))
        if not b.history:
            raise CompiledError("HOTRELOAD_NO_HISTORY",
                                "没有可回滚的历史状态: %s" % campaign_id,
                                {"campaign_id": campaign_id, "history_depth": 0})
        steps = min(steps, len(b.history))
        entry = b.history[-steps]
        del b.history[-steps:]
        target = entry["norm"]
        changes = diff_states(b.applied_norm, target)
        changes.append({"type": "SNAPSHOT_LOADED",
                        "snapshot_ref": "hotreload:rollback:%d" % steps,
                        "resume_cursor": ""})
        seqs = await self._append(campaign_id, changes)
        b.applied_norm = target
        b.applied_digest = str(entry.get("digest") or "")
        b.last_changes = changes
        b.last_change_digest = changes_digest(changes)
        b.event_count += len(seqs)
        b.rollback_count += 1
        b.last_applied_at = _now()
        self.hot_applies += 1
        return {"ok": True, "campaign_id": campaign_id, "rolled_back_steps": steps,
                "change_count": len(changes), "changes": changes, "seqs": seqs,
                "digest": b.applied_digest, "history_depth": len(b.history)}

    # ------------------------------------------------------------- 轮询
    async def poll_once(self) -> dict[str, Any]:
        """扫一遍所有绑定: mtime 变了才读文件算 sha256; sha 变了才热重载。"""
        self.polls += 1
        fired: list[dict[str, Any]] = []
        for b in list(self.bindings.values()):
            p = Path(b.path)
            if not p.is_file():
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            if st.st_mtime == b.last_mtime:
                continue
            try:
                sha = sha256_file(p)
            except OSError:
                continue
            if sha == b.last_sha:
                b.last_mtime = st.st_mtime
                continue
            try:
                out = await self.apply_file(b.campaign_id, source="file_watch")
                fired.append({"campaign_id": b.campaign_id, "sha256": sha,
                              "change_count": out["change_count"],
                              "change_digest": out["change_digest"],
                              "changes": out["changes"], "seqs": out["seqs"]})
            except Exception as exc:  # noqa: BLE001 — 单个绑定失败不影响其它绑定
                b.last_error = "%s: %s" % (type(exc).__name__, exc)
                logger.warning("hotreload apply failed for %s: %s", b.campaign_id, exc)
        return {"ok": True, "polls": self.polls, "fired": fired, "fired_count": len(fired)}

    async def loop(self) -> None:
        while True:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("hotreload poll loop error")
            await asyncio.sleep(self.interval)

    def start(self, loop: asyncio.AbstractEventLoop | None = None) -> bool:
        """启动后台轮询任务 (幂等)。无运行中的事件循环时返回 False。"""
        if self._task is not None and not self._task.done():
            return True
        try:
            lp = loop or asyncio.get_running_loop()
        except RuntimeError:
            return False
        self._loop = lp
        self._task = lp.create_task(self.loop(), name="hotreload-watch")
        return True

    async def stop(self) -> None:
        t = self._task
        self._task = None
        if t is not None and not t.done():
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass


def bindings_path() -> Path:
    """绑定表位置 —— 每次调用都按**当前**仓库根解析 (测试会换根, 不能缓存)。

    优先级: 环境变量 TRPG_HOTRELOAD_BINDINGS > <app_root>/data/hotreload/bindings.json。
    """
    override = os.environ.get("TRPG_HOTRELOAD_BINDINGS", "").strip()
    if override:
        return Path(override)
    try:
        from app.web import rest_repo
        roots = rest_repo.get_roots()
    except Exception:  # noqa: BLE001 — 应用尚未装配完时退回默认根
        from app.repository.roots import RepoRoots
        roots = RepoRoots.default()
    # staging 是 <base>/data/.repo_staging, 其父即 data/
    return Path(roots.staging).parent / BINDINGS_RELPATH


def hunger_start() -> dict[str, Any]:
    """饥饿启动 (F-9): 回灌绑定表 + 启动后台轮询任务。

    为什么必须"回灌"而不能只"启动": 绑定表原本是纯内存的, 重启后为空 ——
    此时即便把轮询任务拉起来也没有任何绑定可监听, 单做"启动"是 no-op。
    因此这里先 load_persisted() 再把任务拉起来, 两者缺一不可。

    必须在**运行中的事件循环**内调用 (start() 依赖 get_running_loop())。
    """
    w = get_watcher()
    loaded = w.load_persisted()
    running = w.start()
    if loaded:
        logger.info("hotreload hunger-start: restored %d binding(s), task running=%s",
                    loaded, running)
    return {"loaded": loaded, "running": running, "binding_count": len(w.bindings)}


#: 进程内单例。**必须**保持模块级声明 —— get_watcher() 里的 `global _WATCHER`
#: 依赖它存在, 否则 NameError (曾因此让 /api/hotreload/status 与 bind 双双 500)。
_WATCHER: HotReloadWatcher | None = None


def get_watcher() -> HotReloadWatcher:
    global _WATCHER
    if _WATCHER is None:
        _WATCHER = HotReloadWatcher()
    return _WATCHER


def ensure_watcher() -> HotReloadWatcher:
    w = get_watcher()
    w.start()
    return w


def module_save_path(modules_root: str | Path, module_id: str) -> Path:
    return Path(modules_root) / str(module_id) / SAVE_RELPATH
