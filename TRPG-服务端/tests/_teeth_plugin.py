"""牙齿测试插件: 把 R8 修复**行为等价地**倒回去, 用于证明回归用例真会变红。

用法: PYTHONPATH=<本目录> python -m pytest <用例文件> -q -p _teeth_plugin --no-header
严格说明: 这是行为等价复刻 (重新注入调用方 expected_seq + 让派发锁变成空操作),
不是字节级回滚 —— 字节级回滚由 verify 用『把两行装回去』的方法独立做。
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from app.store.event_store import EventStore
import app.app_core.command_bus as cb

_orig_append = EventStore.append


async def _append_with_caller_cas(self, campaign_id, events, expected_seq=None):
    """复刻修复前 dispatch 的『先读 tip 再回传』: 读与写之间留下可被抢占的 await。"""
    if expected_seq is None:
        expected_seq = await self.max_seq(campaign_id)
    return await _orig_append(self, campaign_id, events, expected_seq=expected_seq)


@asynccontextmanager
async def _noop_lock(campaign_id):
    """复刻修复前『无派发锁』: 幂等键的 check→append→record 不再原子。"""
    yield


EventStore.append = _append_with_caller_cas
cb._dispatch_lock = _noop_lock
print("[_teeth_plugin] R8 修复已行为等价倒回: caller-side expected_seq + 无派发锁")
