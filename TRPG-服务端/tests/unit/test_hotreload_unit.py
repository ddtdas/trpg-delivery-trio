"""R27/R24/R25/R26 单元测试: 编译产物契约 + 确定性差异 + 帧/事件类型复用 —— additive。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.domain.events import EVENT_TYPES, make_event
from app.hotreload import compiled as hc
from app.hotreload import watcher as hrw
from app.hotreload.diff import changes_digest, diff_states
from app.hotreload.spec import CompiledError


@pytest.fixture(autouse=True)
def _isolated_bindings(tmp_path, monkeypatch):
    """F-9: 绑定表持久化落到 tmp —— 单元测试不得写入真实 data/。"""
    monkeypatch.setenv("TRPG_HOTRELOAD_BINDINGS", str(tmp_path / "hr_bindings.json"))


def _compiled(**kw):
    base = {
        "schema": "DeadLightCompiled v1",
        "module_id": "dead_light",
        "maps": [{
            "id": "m1", "name": "加油站",
            "rooms": [{"id": "r1", "name": "前场", "rect": {"x": 0, "y": 0, "w": 100, "h": 100}},
                      {"id": "r2", "name": "便利店", "rect": {"x": 200, "y": 0, "w": 100, "h": 100}}],
            "interactables": [{"id": "it1", "name": "加油泵", "room": "r1", "anchor": "a1",
                               "x": 50.0, "y": 50.0, "actions": ["inspect", "use"]}],
        }],
        "event_graph": {"initial_scene": "n1",
                        "nodes": [{"id": "n1", "label": "抵达"}, {"id": "n2", "label": "终局"}],
                        "edges": [{"id": "e1", "from": "n1", "to": "n2"}]},
        "npcs": [{"id": "npc1", "name": "老周", "role": "店员"}],
        "clues": [{"id": "c1", "kind": "document", "location": "n1"}],
    }
    base.update(kw)
    return base


# ------------------------------------------------------------- 结构 / 可交互物契约

def test_valid_compiled_passes_and_counts():
    out = hc.validate_compiled(_compiled())
    assert out["valid"] is True
    assert out["counts"] == {"maps": 1, "rooms": 2, "interactables": 1, "event_nodes": 2,
                             "event_edges": 1, "npcs": 1, "clues": 1}


def test_interactable_out_of_room_bounds_rejected():
    """可交互物位置必须落在所属房间矩形边界内 (captain 硬要求)。"""
    d = _compiled()
    d["maps"][0]["interactables"][0]["x"] = 150.0   # r1 的 rect 是 x:0..100
    with pytest.raises(CompiledError) as ei:
        hc.validate_compiled(d)
    assert ei.value.code == "COMPILED_INTERACTABLE_OUT_OF_ROOM"
    assert ei.value.detail["room"] == "r1"


def test_interactable_missing_room_anchor_or_actions_rejected():
    for field, code in (("room", "COMPILED_INTERACTABLE_ROOM_UNKNOWN"),
                        ("anchor", "COMPILED_INTERACTABLE_ANCHOR_MISSING"),
                        ("actions", "COMPILED_INTERACTABLE_ACTIONS_MISSING")):
        d = _compiled()
        d["maps"][0]["interactables"][0][field] = "" if field != "actions" else []
        with pytest.raises(CompiledError) as ei:
            hc.validate_compiled(d)
        assert ei.value.code == code, field


def test_interactable_unknown_action_rejected():
    d = _compiled()
    d["maps"][0]["interactables"][0]["actions"] = ["inspect", "teleport"]
    with pytest.raises(CompiledError) as ei:
        hc.validate_compiled(d)
    assert ei.value.code == "COMPILED_INTERACTABLE_ACTION_UNKNOWN"


def test_dangling_edge_and_bad_initial_scene_rejected():
    d = _compiled()
    d["event_graph"]["edges"] = [{"id": "e1", "from": "n1", "to": "n_missing"}]
    with pytest.raises(CompiledError) as ei:
        hc.validate_compiled(d)
    assert ei.value.code == "COMPILED_GRAPH_DANGLING_EDGE"
    d2 = _compiled()
    d2["event_graph"]["initial_scene"] = "nope"
    with pytest.raises(CompiledError) as ei2:
        hc.validate_compiled(d2)
    assert ei2.value.code == "COMPILED_GRAPH_INITIAL_INVALID"


def test_load_compiled_missing_and_invalid_json(tmp_path: Path):
    with pytest.raises(CompiledError) as ei:
        hc.load_compiled(tmp_path / "nope.json")
    assert ei.value.code == "COMPILED_FILE_MISSING"
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(CompiledError) as ei2:
        hc.load_compiled(bad)
    assert ei2.value.code == "COMPILED_INVALID_JSON"


# ------------------------------------------------------------- 确定性

def test_canonical_digest_is_key_order_independent():
    a = _compiled()
    b = json.loads(json.dumps(a))
    b["npcs"] = list(reversed(b["npcs"]))
    assert hc.canonical_digest(a) == hc.canonical_digest(b)


def test_second_import_diff_is_empty():
    """二次导入 diff 必须为空 (确定性判据)。"""
    a = _compiled()
    assert diff_states(hc.normalize(a), hc.normalize(json.loads(json.dumps(a)))) == []
    assert diff_states(None, hc.normalize(a)) != []          # 首次导入非空


def test_diff_is_deterministic_across_calls():
    old = hc.normalize(_compiled())
    d = _compiled()
    d["maps"][0]["interactables"][0]["x"] = 60.0
    d["clues"].append({"id": "c2", "kind": "mark", "location": "n2"})
    new = hc.normalize(d)
    r1 = diff_states(old, new)
    r2 = diff_states(old, new)
    assert r1 == r2
    assert changes_digest(r1) == changes_digest(r2)
    kinds = [c["type"] for c in r1]
    assert "MAP_UPDATED" in kinds and "CLUE_GRANTED" in kinds


def test_diff_only_uses_existing_frozen_event_types():
    """铁律: 变更规格只能使用既有 EVENT_TYPES, 不新增事件类型。"""
    old = hc.normalize(_compiled())
    d = _compiled()
    d["maps"][0]["rooms"].append({"id": "r3", "name": "后仓",
                                  "rect": {"x": 400, "y": 0, "w": 100, "h": 100}})
    d["maps"][0]["interactables"].append({"id": "it2", "name": "货箱", "room": "r3",
                                          "anchor": "a3", "x": 450.0, "y": 50.0,
                                          "actions": ["search"]})
    d["event_graph"]["nodes"].append({"id": "n3", "label": "新节点"})
    d["event_graph"]["edges"].append({"id": "e2", "from": "n2", "to": "n3"})
    d["clues"].append({"id": "c2", "kind": "mark", "location": "n3"})
    d["npcs"].append({"id": "npc2", "name": "汉克", "role": "司机"})
    changes = diff_states(old, hc.normalize(d))
    assert changes
    for c in changes:
        assert c["type"] in EVENT_TYPES, c["type"]
    assert {c["type"] for c in changes} <= {"MAP_UPDATED", "EVENT_INJECTED",
                                            "CLUE_GRANTED", "TABLE_CONFIG_UPDATED"}


def test_map_op_is_one_of_existing_map_ops():
    """MAP_UPDATED 的 op 必须取自既有 MAP_OPS, 不得自造。"""
    from app.web.rest import MAP_OPS

    old = hc.normalize(_compiled())
    d = _compiled()
    d["maps"][0]["interactables"][0]["x"] = 70.0
    d["maps"][0]["interactables"].append({"id": "it9", "name": "新物", "room": "r1",
                                          "anchor": "a9", "x": 10.0, "y": 10.0,
                                          "actions": ["inspect"]})
    for c in diff_states(old, hc.normalize(d)):
        if c["type"] == "MAP_UPDATED":
            assert c["op"] in MAP_OPS, c["op"]


# ------------------------------------------------------------- 帧复用

@pytest.mark.asyncio
async def test_all_change_types_map_to_frozen_server_frames():
    """R27 铁律: 变更落到 WS 时必须复用冻结的 8 帧, 不新增帧类型。"""
    from app.web import ws_bridge
    from app.web.ws_protocol import SERVER_KINDS

    old = hc.normalize(_compiled())
    d = _compiled()
    d["maps"][0]["interactables"][0]["x"] = 70.0
    d["event_graph"]["nodes"].append({"id": "n3", "label": "新节点"})
    d["clues"].append({"id": "c2", "kind": "mark", "location": "n3"})
    d["npcs"].append({"id": "npc2", "name": "汉克", "role": "司机"})
    changes = diff_states(old, hc.normalize(d))
    assert changes
    for c in changes:
        payload = hrw._PAYLOAD_BUILDERS[c["type"]]("camp", c)
        ev = make_event(seq=1, campaign_id="camp", type=c["type"], payload=payload,
                        actor="system", ts="2026-09-27T00:00:00+00:00")
        frame = await ws_bridge.build_frame("camp", ev)
        assert frame is not None
        assert frame.kind in SERVER_KINDS, frame.kind


def test_payload_builders_cover_every_change_type():
    """任何 diff 产出的类型都必须有 payload 构造器, 否则会被静默丢弃。"""
    old = hc.normalize(_compiled())
    d = _compiled()
    d["maps"][0]["rooms"].append({"id": "r3", "name": "后仓",
                                  "rect": {"x": 400, "y": 0, "w": 100, "h": 100}})
    d["maps"][0]["interactables"].append({"id": "it2", "name": "货箱", "room": "r3",
                                          "anchor": "a3", "x": 450.0, "y": 50.0,
                                          "actions": ["search"]})
    d["event_graph"]["nodes"].append({"id": "n3", "label": "新节点"})
    d["clues"].append({"id": "c2", "kind": "mark", "location": "n3"})
    d["npcs"].append({"id": "npc2", "name": "汉克", "role": "司机"})
    for c in diff_states(old, hc.normalize(d)):
        assert c["type"] in hrw._PAYLOAD_BUILDERS, c["type"]


def test_no_new_ws_frame_kind_was_introduced():
    """ws_protocol.py 是冻结契约: 下行帧必须仍恰好是 8 类。"""
    from app.web.ws_protocol import SERVER_KINDS

    assert len(SERVER_KINDS) == 8
    assert SERVER_KINDS == ("STATE_DELTA", "TURN_UPDATED", "NARRATION_PENDING",
                            "NARRATION_APPROVED", "WHISPER", "INFO_REVEALED",
                            "BRANCH_TAKEN", "JOB_STATUS")


def test_event_types_still_40():  # T6 (M3 additive) + T2 (SCENE_UPDATED)
    assert len(EVENT_TYPES) == 53  # +T13: PHASE_UPDATED


# ------------------------------------------------------------- watcher

@pytest.mark.asyncio
async def test_watcher_bind_apply_idempotent_and_rollback(tmp_path: Path):
    w = hrw.HotReloadWatcher()
    save = tmp_path / "save_state.json"
    state = _compiled()
    save.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    w.bind("camp1", "dead_light", save, initial=state)

    r1 = await w.apply_state("camp1", state)
    assert r1["change_count"] == 0 and r1["idempotent"] is True
    assert r1["seqs"] == []

    moved = json.loads(json.dumps(state))
    moved["maps"][0]["interactables"][0]["x"] = 70.0
    r2 = await w.apply_state("camp1", moved)
    assert r2["change_count"] >= 1
    assert r2["idempotent"] is False
    assert len(r2["seqs"]) == r2["change_count"]

    r3 = await w.apply_state("camp1", moved)
    assert r3["change_count"] == 0, "同一状态重复应用必须零事件"

    rb = await w.rollback("camp1")
    assert rb["rolled_back_steps"] == 1
    assert any(c["type"] == "SNAPSHOT_LOADED" for c in rb["changes"])


@pytest.mark.asyncio
async def test_watcher_unbound_raises_explicit_code(tmp_path: Path):
    w = hrw.HotReloadWatcher()
    with pytest.raises(CompiledError) as ei:
        await w.apply_state("nope", _compiled())
    assert ei.value.code == "HOTRELOAD_NOT_BOUND"
    with pytest.raises(CompiledError) as ei2:
        await w.rollback("nope")
    assert ei2.value.code == "HOTRELOAD_NOT_BOUND"


@pytest.mark.asyncio
async def test_rollback_without_history_raises_explicit_code(tmp_path: Path):
    w = hrw.HotReloadWatcher()
    save = tmp_path / "s.json"
    save.write_text("{}", encoding="utf-8")
    w.bind("c", "m", save, initial=_compiled())
    with pytest.raises(CompiledError) as ei:
        await w.rollback("c")
    assert ei.value.code == "HOTRELOAD_NO_HISTORY"


@pytest.mark.asyncio
async def test_poll_once_detects_mtime_and_sha_change(tmp_path: Path):
    w = hrw.HotReloadWatcher()
    save = tmp_path / "save_state.json"
    state = _compiled()
    save.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    w.bind("c", "m", save, initial=state)

    out = await w.poll_once()
    assert out["fired_count"] == 0, "未变更时不得触发"

    moved = json.loads(json.dumps(state))
    moved["maps"][0]["interactables"][0]["y"] = 20.0
    save.write_text(json.dumps(moved, ensure_ascii=False), encoding="utf-8")
    import os
    os.utime(save, (save.stat().st_atime, save.stat().st_mtime + 2))

    out2 = await w.poll_once()
    assert out2["fired_count"] == 1
    assert out2["fired"][0]["change_count"] >= 1
