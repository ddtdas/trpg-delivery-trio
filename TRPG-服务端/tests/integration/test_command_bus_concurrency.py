"""R8 并发回归: CommandBus 派发必须「不依赖调用方 read-then-write CAS」且「幂等键原子」。

背景（修复前实测, 真实 HTTP 对未重启进程）:
  8 并发 / 不同 req_id: http_codes={'200':1,'500':7}  status ok=1  事件流 +1  ⇒ 7 条行动整条丢失
  8 顺序 / 不同 req_id: http_codes={'200':8}          status ok=8  事件流 +8  (阳性对照)
根因两条:
  (a) dispatch 曾 max_seq() 后把同一值回传 expected_seq —— read-then-write TOCTOU,
      并发下后到者抛 SeqConflictError; access.mobile_action 只 catch
      ConflictError/CommandError/BranchViolation ⇒ 直接 500。
  (b) check_key → append → record_key 之间有 await, 同 req_id 并发会同时通过查重。
两条都要有回归面: 臂 C 是 (b) 的唯一回归面; 臂 A/F 覆盖 (a) 的带 key 与无 key 两条路径。
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.app_core.command_bus import CommandBus
from app.scheduler.branch_guard import BranchGuard
from app.store.event_store import EventStore

N = 8


async def _db(tmp_path: Path) -> Path:
    p = tmp_path / "events.db"
    await EventStore(p).init()
    return p


def _call(db: Path, campaign: str, guard: BranchGuard, i: int, *,
          key: str | None, actor_same: bool = False, params_same: bool = False):
    async def go():
        # 复刻生产: 每请求新建 store 与 CommandBus, guard 共享 (access.py:690)
        bus = CommandBus(EventStore(db), campaign, guard=guard)
        pid = "pl-0" if params_same else "pl-%d" % i
        params = {"campaign_id": campaign, "turn_no": 1, "player_id": pid,
                  "action": {"text": "same" if params_same else "a%d" % i}}
        actor = "pl-0" if actor_same else pid
        try:
            r = await bus.dispatch("submit_action", params, actor=actor, key=key)
            return str(r.get("status"))
        except Exception as exc:                       # noqa: BLE001
            return "EXC:" + type(exc).__name__
    return go()


async def _count(db: Path, campaign: str) -> int:
    evs = await EventStore(db).replay(campaign)
    return len([e for e in evs if e.type == "ACTION_SUBMITTED"])


@pytest.mark.asyncio
async def test_arm_a_concurrent_distinct_keys_all_persisted(tmp_path: Path) -> None:
    """臂 A: 8 并发 / 各自 req_id ⇒ 全部 ok, 落库条数 == 成功条数。"""
    db = await _db(tmp_path)
    g = BranchGuard()
    c = "c_arm_a"
    res = await asyncio.gather(*[_call(db, c, g, i, key="k-%d" % i) for i in range(N)])
    assert "EXC:SeqConflictError" not in res, res
    ok = sum(1 for r in res if r == "ok")
    assert ok == N, res
    assert await _count(db, c) == ok, res


@pytest.mark.asyncio
async def test_arm_f_concurrent_keyless_all_persisted(tmp_path: Path) -> None:
    """臂 F: 8 并发 / **不带 req_id**（key=None）⇒ 全部 ok, 落库 == 成功条数。

    生产里 key 来自 body.req_id（access.mobile_action: key=body.get("req_id")），
    客户端不带它时走的就是这条无 key 路径 —— 它同样受 (a) 影响, 必须单独覆盖。
    （本臂由 verify 指出「5 条臂全带 key = 无 key 路径无覆盖」后补入。）
    """
    db = await _db(tmp_path)
    g = BranchGuard()
    c = "c_arm_f"
    res = await asyncio.gather(*[_call(db, c, g, i, key=None) for i in range(N)])
    assert "EXC:SeqConflictError" not in res, res
    ok = sum(1 for r in res if r == "ok")
    assert ok == N, res
    assert await _count(db, c) == ok, res


@pytest.mark.asyncio
async def test_arm_b_sequential_distinct_keys_control(tmp_path: Path) -> None:
    """臂 B (阳性对照): 顺序提交本来就该全成功 —— 防止用例因环境坏掉而『通过』。"""
    db = await _db(tmp_path)
    g = BranchGuard()
    c = "c_arm_b"
    res = [await _call(db, c, g, i, key="ks-%d" % i) for i in range(N)]
    assert res.count("ok") == N, res
    assert await _count(db, c) == N, res


@pytest.mark.asyncio
async def test_arm_c_concurrent_same_key_is_idempotent(tmp_path: Path) -> None:
    """臂 C: 同 key + 同 actor + 同 params 并发 ⇒ 1 ok + N-1 duplicate, 落库 1。

    payload_sig 含 actor ⇒『真重放』必须 key+actor+params 三者全同。
    本臂是幂等键原子性 (b) 的唯一回归面。
    """
    db = await _db(tmp_path)
    g = BranchGuard()
    c = "c_arm_c"
    res = await asyncio.gather(*[_call(db, c, g, i, key="SHARED",
                                       actor_same=True, params_same=True)
                                for i in range(N)])
    assert res.count("ok") == 1, res
    assert res.count("duplicate") == N - 1, res
    assert await _count(db, c) == 1, res


@pytest.mark.asyncio
async def test_arm_d_sequential_same_key_control(tmp_path: Path) -> None:
    """臂 D (阳性对照): 顺序重放同一 req_id ⇒ 1 ok + N-1 duplicate, 落库 1。"""
    db = await _db(tmp_path)
    g = BranchGuard()
    c = "c_arm_d"
    res = [await _call(db, c, g, i, key="SHARED", actor_same=True,
                       params_same=True) for i in range(N)]
    assert res.count("ok") == 1 and res.count("duplicate") == N - 1, res
    assert await _count(db, c) == 1, res


@pytest.mark.asyncio
async def test_arm_e_same_key_different_payload_still_conflicts(tmp_path: Path) -> None:
    """臂 E: 同 key 但 payload 变 (actor 不同) ⇒ ConflictError, 不得被静默放行。

    证明加锁只回收了『同一幂等请求的并发重放』, 没有把 BranchGuard 的
    『键复用冲突』语义放宽。
    """
    db = await _db(tmp_path)
    g = BranchGuard()
    c = "c_arm_e"
    res = await asyncio.gather(*[_call(db, c, g, i, key="SHARED") for i in range(N)])
    assert res.count("ok") == 1, res
    assert res.count("EXC:ConflictError") == N - 1, res
    assert await _count(db, c) == 1, res
