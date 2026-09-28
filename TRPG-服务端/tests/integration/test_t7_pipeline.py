# -*- coding: utf-8 -*-
"""T7 单元 + 集成测试 (R10 R11 R17 R18 R19)。

运行（在 TRPG-服务端 根目录）:
    python -m pytest tests/test_t7_pipeline.py -q

隔离: 事件库/快照/待审登记表/桌注册表全部重定向到 tmp_path，
      不触碰交付包的 data/trpg.db 与 data/tables_registry.json。
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

CAMPAIGN = "t7c1"
TABLE = "t7t1"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    from app.app_core import pipeline_store
    from app.web import access as access_mod
    from app.web import rest as rest_mod

    monkeypatch.setattr(rest_mod, "DEFAULT_DB", tmp_path / "t7.db")
    monkeypatch.setattr(rest_mod, "SNAP_BASE", tmp_path / "snapshots")
    monkeypatch.setattr(pipeline_store, "STORE_DIR", tmp_path / "pipeline")
    monkeypatch.setattr(access_mod, "_registry_path", lambda: tmp_path / "tables_registry.json")
    monkeypatch.setattr(access_mod, "_save_tables_registry", lambda: None)
    monkeypatch.setattr(access_mod, "persist_tables", lambda: None)
    rest_mod.TABLES.clear()
    pipeline_store.reset()
    from app.main import app
    with TestClient(app) as client:
        yield client
    rest_mod.TABLES.clear()
    pipeline_store.reset()


def tokens() -> tuple[str, str]:
    """(mobile=玩家, webapp=主持人) —— 读既有 configs/access_config.yaml。"""
    from app.web import access as access_mod
    cfg = access_mod._load_config()
    ends = cfg["ends"]
    return str(ends["mobile"]["token"]), str(ends["webapp"]["token"])


def make_table(client: TestClient, campaign: str = CAMPAIGN,
               table: str = TABLE, module: str = "sample_coc") -> None:
    r = client.post("/api/tables",
                    json={"table_id": table, "campaign_id": campaign,
                          "ruleset": "coc7", "config": {"module": module}})
    assert r.status_code == 201, r.text


def events_of(client: TestClient, campaign: str = CAMPAIGN,
              token: str | None = None) -> list[dict]:
    """原始事件流。默认用 KP(webapp) token —— R9 生效后无 token 会 fail-closed
    裁剪成玩家视图，看不到 KP-only 事件（本用例要断言的是"原始流里也没有
    隐藏正文"，所以必须走 KP 通道）。"""
    if token is None:
        token = tokens()[1]
    r = client.get("/api/campaigns/%s/events" % campaign,
                   params={"since": -1, "limit": 1000, "token": token,
                           "viewer": "kp"})
    assert r.status_code == 200, r.text
    return r.json()["events"]


def infos_of(client: TestClient, campaign: str = CAMPAIGN) -> list[dict]:
    return [e for e in events_of(client, campaign) if e["type"] == "INFO_REVEALED"]


def interactives(client: TestClient, token: str, campaign: str = CAMPAIGN) -> dict:
    r = client.get("/api/campaigns/%s/interactives" % campaign,
                   params={"token": token})
    assert r.status_code == 200, r.text
    return r.json()


# ---- R10: 地点可交互 ------------------------------------------------------

def test_r10_interactives_expose_action_set(env):
    mobile, _kp = tokens()
    make_table(env)
    data = interactives(env, mobile)
    assert data["count"] > 0
    by_kind = {o["kind"]: o for o in data["objects"]}
    assert "cabinet" in by_kind, data["objects"]
    acts = {a["action"]: a for a in by_kind["cabinet"]["actions"]}
    assert acts["search"]["label"] == "搜索"
    assert acts["search"]["sensitive"] is False
    assert acts["pick_lock"]["sensitive"] is True
    assert all(o["anchor"]["x"] >= 0 for o in data["objects"])


def test_r10_search_enters_event_stream_and_is_targeted(env):
    mobile, _kp = tokens()
    make_table(env)
    obj = interactives(env, mobile)["objects"][0]
    r = env.post("/api/campaigns/%s/interact" % CAMPAIGN, params={"token": mobile},
                 json={"player_id": "pl_a", "object_id": obj["id"],
                       "action": "search"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["result"]["level"] in ("crit", "success", "hard", "extreme",
                                       "fail", "fumble", "critical")
    assert isinstance(body["result"]["rolled"], int)
    ev = events_of(env)
    assert "EVENT_INJECTED" in [e["type"] for e in ev]
    inj = [e for e in ev if e["type"] == "EVENT_INJECTED"][-1]
    assert inj["payload"]["payload"]["object_id"] == obj["id"]
    assert inj["payload"]["dry_run_result"]["text"] == body["result"]["text"]
    infos = infos_of(env)
    assert infos and infos[-1]["payload"]["scope"] == "whisper"
    assert infos[-1]["payload"]["targets"] == ["pl_a"]
    # 服务端权威裁剪: 同一条定向信息对别的玩家不可见
    from app.domain.events import GameEvent
    from app.domain.visibility import visible_infos
    from app.store.projector import project
    st = project([GameEvent(**e) for e in ev], CAMPAIGN)
    assert len(visible_infos(st, "pl_a")) >= 1
    assert len(visible_infos(st, "pl_b")) == 0


# ---- R11: 敏感交互过主持人 ------------------------------------------------

def test_r11_sensitive_interaction_reports_to_gm_queue(env):
    mobile, kp = tokens()
    make_table(env)
    obj = [o for o in interactives(env, mobile)["objects"]
           if o["kind"] == "cabinet"][0]
    r = env.post("/api/campaigns/%s/interact" % CAMPAIGN, params={"token": mobile},
                 json={"player_id": "pl_a", "object_id": obj["id"],
                       "action": "pick_lock"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "pending_approval"
    assert body["state"] == "已上报待主持人"
    pid = body["proposal_id"]
    # 玩家 token 读不到待审队列（端隔离，复用既有 _require_kp_end）
    assert env.get("/api/campaigns/%s/approvals" % CAMPAIGN,
                   params={"token": mobile}).status_code == 403
    # 玩家自己的状态回显
    mine = env.get("/api/campaigns/%s/pipeline/mine" % CAMPAIGN,
                   params={"token": mobile, "player_id": "pl_a"}).json()
    assert mine["items"][0]["state"] == "已上报待主持人"
    # GM 待审队列：真实正文只在 KP 通道
    q = env.get("/api/campaigns/%s/approvals" % CAMPAIGN, params={"token": kp}).json()
    assert q["count"] == 1
    item = q["pending"][0]
    assert item["proposal_id"] == pid
    assert item["kind"] == "interaction" and item["targets"] == ["pl_a"]
    assert item["label"].startswith("【待审·撬锁】")
    real_text = item["text"]
    assert real_text and real_text != item["label"]
    # 负例: 真实正文不在事件流里（玩家能拉到的事件流里搜不到）
    dump = json.dumps(events_of(env), ensure_ascii=False)
    assert real_text not in dump


def test_r11_approve_delivers_and_edit_is_not_broadcast(env):
    mobile, kp = tokens()
    make_table(env)
    obj = [o for o in interactives(env, mobile)["objects"]
           if o["kind"] == "cabinet"][0]
    pid = env.post("/api/campaigns/%s/interact" % CAMPAIGN, params={"token": mobile},
                   json={"player_id": "pl_a", "object_id": obj["id"],
                         "action": "pick_lock"}).json()["proposal_id"]
    edited = "锁开了，里面是一叠发黄的信纸。"
    r = env.post("/api/campaigns/%s/approvals" % CAMPAIGN,
                 json={"proposal_id": pid, "decision": "edit",
                       "edited_text": edited})
    assert r.status_code == 201, r.text
    assert r.json()["delivery"]["status"] == "delivered"
    assert r.json()["delivery"]["targets"] == ["pl_a"]
    # GM 改写版经 whisper 定向下发
    infos = infos_of(env)
    mine = [i for i in infos if i["payload"]["info_id"] == "info:%s" % pid]
    assert mine and mine[-1]["payload"]["body_ref"] == edited
    assert mine[-1]["payload"]["targets"] == ["pl_a"]
    # 决定事件正文脱敏 —— 公开帧（NARRATION_EDITED -> NARRATION_APPROVED public）不带定向内容
    dec = [e for e in events_of(env)
           if e["type"] == "NARRATION_EDITED" and e["payload"]["proposal_id"] == pid]
    assert dec and dec[-1]["payload"]["text"] == ""
    # 效果事件只在批准后落库
    inj = [e for e in events_of(env) if e["type"] == "EVENT_INJECTED"]
    assert inj and inj[-1]["payload"]["payload"]["approved"] is True


def test_r11_reject_gives_neutral_feedback(env):
    mobile, kp = tokens()
    make_table(env)
    obj = [o for o in interactives(env, mobile)["objects"]
           if o["kind"] == "cabinet"][0]
    pid = env.post("/api/campaigns/%s/interact" % CAMPAIGN, params={"token": mobile},
                   json={"player_id": "pl_a", "object_id": obj["id"],
                         "action": "take"}).json()["proposal_id"]
    q = env.get("/api/campaigns/%s/approvals" % CAMPAIGN, params={"token": kp}).json()
    hidden = [i["text"] for i in q["pending"] if i["proposal_id"] == pid][0]
    r = env.post("/api/campaigns/%s/approvals" % CAMPAIGN,
                 json={"proposal_id": pid, "decision": "reject",
                       "reason": "锁太结实"})
    assert r.status_code == 201, r.text
    assert r.json()["delivery"]["status"] == "rejected"
    infos = infos_of(env)
    mine = [i for i in infos if i["payload"]["info_id"] == "info:%s" % pid]
    assert mine and mine[-1]["payload"]["body_ref"] == "主持人暂未允许该动作。"
    assert hidden not in json.dumps(mine, ensure_ascii=False)


# ---- R17: 同时行动流水线 --------------------------------------------------

def _open_window(env, kp: str, campaign: str = CAMPAIGN) -> int:
    r = env.post("/access/host/turn", params={"token": kp},
                 json={"campaign": campaign, "window_sec": 60, "table_id": TABLE})
    assert r.status_code == 200 and r.json()["ok"], r.text
    return int(r.json()["data"]["turn_no"])


def _submit(env, mobile: str, player: str, text: str, turn_no: int,
            campaign: str = CAMPAIGN) -> None:
    r = env.post("/access/mobile/action", params={"token": mobile},
                 json={"campaign": campaign, "turn_no": turn_no,
                       "player_id": player, "action": {"text": text},
                       "intent_summary": "test"})
    assert r.status_code == 200 and r.json()["ok"], r.text


def test_r17_gm_sends_before_player_receives_nothing(env):
    mobile, kp = tokens()
    make_table(env)
    turn_no = _open_window(env, kp)
    _submit(env, mobile, "pl_a", "搜索书桌", turn_no)
    _submit(env, mobile, "pl_b", "撬开柜子", turn_no)
    r = env.post("/api/campaigns/%s/pipeline/resolve" % CAMPAIGN,
                 params={"token": kp}, json={"close_window": True})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["closed_window"] is True
    assert body["count"] == 2
    pids = [c["proposal_id"] for c in body["candidates"]]
    assert len(set(pids)) == 2
    # 负例①: 服务端批量计算结果不在玩家可拉取的事件流里
    dump = json.dumps(events_of(env), ensure_ascii=False)
    assert "尝试：" not in dump
    assert "d100=" not in dump
    # 负例②: 玩家侧没有任何定向下发
    assert infos_of(env) == []
    # GM 待审队列里两条都在
    q = env.get("/api/campaigns/%s/approvals" % CAMPAIGN, params={"token": kp}).json()
    assert q["count"] == 2
    cand = {i["proposal_id"]: i for i in q["pending"]}
    assert set(cand) == set(pids)
    assert "尝试：" in cand[pids[0]]["text"]
    # GM 改写其中一条并发送
    target_pid = [c["proposal_id"] for c in body["candidates"]
                  if c["player_id"] == "pl_a"][0]
    edited = "你翻开书桌抽屉，找到一枚铜钥匙。"
    r = env.post("/api/campaigns/%s/approvals" % CAMPAIGN,
                 json={"proposal_id": target_pid, "decision": "edit",
                       "edited_text": edited})
    assert r.json()["delivery"]["status"] == "delivered"
    # 改写版只到 pl_a
    infos = infos_of(env)
    assert len(infos) == 1
    assert infos[0]["payload"]["body_ref"] == edited
    assert infos[0]["payload"]["targets"] == ["pl_a"]
    # pl_b 的结果仍未发送 -> 仍然收不到
    assert "尝试：" not in json.dumps(infos, ensure_ascii=False)
    other = [i for i in q["pending"] if i["proposal_id"] != target_pid][0]
    assert other["targets"] == ["pl_b"]


def test_r17_resolve_is_idempotent(env):
    mobile, kp = tokens()
    make_table(env)
    turn_no = _open_window(env, kp)
    _submit(env, mobile, "pl_a", "观察四周", turn_no)
    first = env.post("/api/campaigns/%s/pipeline/resolve" % CAMPAIGN,
                     params={"token": kp}, json={"close_window": True}).json()
    second = env.post("/api/campaigns/%s/pipeline/resolve" % CAMPAIGN,
                      params={"token": kp}, json={"close_window": False}).json()
    assert first["count"] == 1
    assert second["count"] == 1 and second["candidates"][0]["duplicate"] is True
    assert second["closed_window"] is False


# ---- R18 / R19: 感知回显 + 检定通知 --------------------------------------

def _seed_for(env, want_success: bool, player: str, room: str) -> int:
    from app.app_core import perception
    for s in range(1, 400):
        chk = perception.resolve_perception(skill=50, difficulty="regular", seed=s)
        if chk["success"] is want_success:
            return s
    raise AssertionError("no seed found")


def test_r18_subtitle_is_targeted_and_reviewed(env):
    mobile, kp = tokens()
    make_table(env)
    a = env.post("/api/campaigns/%s/perception/enter" % CAMPAIGN,
                 params={"token": mobile},
                 json={"player_id": "pl_a", "room": "r_reading"})
    assert a.status_code == 201 and a.json()["status"] == "pending_approval"
    pid_a = a.json()["proposal_id"]
    b = env.post("/api/campaigns/%s/perception/enter" % CAMPAIGN,
                 params={"token": mobile},
                 json={"player_id": "pl_b", "room": "r_reading"})
    pid_b = b.json()["proposal_id"]
    assert "pl_a" in b.json()["others"]
    q = env.get("/api/campaigns/%s/approvals" % CAMPAIGN, params={"token": kp}).json()
    cand = {i["proposal_id"]: i for i in q["pending"]}
    assert "pl_a" in cand[pid_b]["text"] and "你进入了" in cand[pid_b]["text"]
    assert "pl_b" not in cand[pid_a]["text"]
    # GM 审核后才下发 B 的字幕
    assert infos_of(env) == []
    env.post("/api/campaigns/%s/approvals" % CAMPAIGN,
             json={"proposal_id": pid_b, "decision": "approve"})
    infos = infos_of(env)
    assert len(infos) == 1 and infos[0]["payload"]["targets"] == ["pl_b"]
    # A 未察觉: A 的**可见集**里既没有 B 的定向字幕，也没有任何 B 的信息
    from app.domain.events import GameEvent
    from app.domain.visibility import visible_infos
    from app.store.projector import project
    st = project([GameEvent(**e) for e in events_of(env)], CAMPAIGN)
    seen_a = visible_infos(st, "pl_a")
    assert seen_a == {}, seen_a
    assert "pl_b" not in json.dumps(seen_a, ensure_ascii=False)
    assert "pl_b" not in cand[pid_a]["text"]


def test_r19_perception_check_gates_neutral_notice(env):
    mobile, kp = tokens()
    make_table(env)
    env.post("/api/campaigns/%s/perception/enter" % CAMPAIGN,
             params={"token": mobile}, json={"player_id": "pl_a", "room": "r_reading"})
    env.post("/api/campaigns/%s/perception/enter" % CAMPAIGN,
             params={"token": mobile}, json={"player_id": "pl_b", "room": "r_reading"})
    before = len(infos_of(env))
    # 失败 -> 收不到
    fail = _seed_for(env, False, "pl_a", "r_reading")
    r = env.post("/api/campaigns/%s/perception/check" % CAMPAIGN,
                 params={"token": mobile},
                 json={"player_id": "pl_a", "room": "r_reading", "skill": 50,
                       "difficulty": "regular", "seed": fail})
    assert r.status_code == 201, r.text
    assert r.json()["success"] is False and r.json()["delivered"] is False
    assert len(infos_of(env)) == before
    # 成功 -> 收到中性通知，且不泄露 B 身份
    ok = _seed_for(env, True, "pl_a", "r_reading")
    r = env.post("/api/campaigns/%s/perception/check" % CAMPAIGN,
                 params={"token": mobile},
                 json={"player_id": "pl_a", "room": "r_reading", "skill": 50,
                       "difficulty": "regular", "seed": ok})
    body = r.json()
    assert body["success"] is True and body["delivered"] is True
    assert body["text"] == "你感觉你的房间多进来了一个人。"
    assert "pl_b" not in body["text"]
    infos = infos_of(env)
    assert len(infos) == before + 1
    assert infos[-1]["payload"]["targets"] == ["pl_a"]
    # 检定记录可追溯（骰值/技能值/难度/成败）
    checks = [e for e in events_of(env) if e["type"] == "CHECK_RESOLVED"]
    assert len(checks) == 2
    last = checks[-1]["payload"]
    assert last["rolled"] and last["level"] and last["seed"]
    assert "skill=50" in last["summary"] and "success=True" in last["summary"]




# ---- 端隔离：T7 端点不能被跨端绕过 ---------------------------------------

def test_t7_endpoints_enforce_end_isolation(env):
    """GM 通道（待审队列/流水线结算）玩家 token 一律 403；玩家通道 KP token 403；
    无 token 401。保证 R17「GM 发送前玩家收不到」无法从 API 绕过。"""
    mobile, kp = tokens()
    make_table(env)
    C = CAMPAIGN
    kp_only = [("get", "/api/campaigns/%s/approvals" % C),
               ("get", "/api/campaigns/%s/pipeline/queue" % C),
               ("post", "/api/campaigns/%s/pipeline/resolve" % C)]
    for method, path in kp_only:
        call = (env.get if method == "get" else env.post)
        r = (call(path, params={"token": mobile}) if method == "get"
             else call(path, params={"token": mobile}, json={}))
        assert r.status_code == 403, "%s %s -> %s" % (method, path, r.status_code)
    player_only = [("get", "/api/campaigns/%s/interactives" % C, None),
                   ("get", "/api/campaigns/%s/pipeline/mine" % C, {"player_id": "pl_a"}),
                   ("post", "/api/campaigns/%s/perception/enter" % C,
                    {"player_id": "pl_a", "room": "r_reading"})]
    for method, path, body in player_only:
        call = (env.get if method == "get" else env.post)
        assert (call(path, params={}) if method == "get"
                else call(path, params={}, json=body or {})).status_code == 401, path
        r = (call(path, params={"token": kp}) if method == "get"
             else call(path, params={"token": kp}, json=body or {}))
        assert r.status_code == 403, "%s %s -> %s" % (method, path, r.status_code)
    # 敏感动作的结果不能从玩家通道被"预读"：待审期间 /pipeline/mine 只有状态，没有正文
    obj = [o for o in interactives(env, mobile)["objects"] if o["kind"] == "cabinet"][0]
    pid = env.post("/api/campaigns/%s/interact" % C, params={"token": mobile},
                   json={"player_id": "pl_a", "object_id": obj["id"],
                         "action": "pick_lock"}).json()["proposal_id"]
    q = env.get("/api/campaigns/%s/approvals" % C, params={"token": kp}).json()
    real = [i["text"] for i in q["pending"] if i["proposal_id"] == pid][0]
    mine = env.get("/api/campaigns/%s/pipeline/mine" % C,
                   params={"token": mobile, "player_id": "pl_a"}).json()
    assert real not in json.dumps(mine, ensure_ascii=False)

# ---- 回归: 既有链路不受影响 + 公开帧不泄露身份 ---------------------------

def test_existing_agent_narration_unchanged(env):
    """无 T7 投递规格的候选（既有 agent 叙事链路）行为与改造前一致。"""
    import asyncio

    _mobile, _kp = tokens()
    make_table(env)
    from app.app_core.command_bus import CommandBus
    from app.web import access as access_mod
    from app.web import rest as rest_mod

    async def _propose():
        store = rest_mod._store()
        await store.init()
        bus = CommandBus(store, CAMPAIGN, guard=access_mod._guard_for(CAMPAIGN))
        return await bus.dispatch("propose_narration",
                                  {"campaign_id": CAMPAIGN,
                                   "proposal_id": "agent-1",
                                   "text": "KP 叙事草稿",
                                   "reasoning": "既有 agent 链路"},
                                  actor="agent")

    asyncio.run(_propose())
    r = env.post("/api/campaigns/%s/approvals" % CAMPAIGN,
                 json={"proposal_id": "agent-1", "decision": "approve",
                       "edited_text": "最终叙事文本"})
    assert r.status_code == 201, r.text
    assert "delivery" not in r.json()          # 无规格 -> 响应形状不变
    dec = [e for e in events_of(env) if e["type"] == "NARRATION_APPROVED"]
    assert dec and dec[-1]["payload"]["text"] == "最终叙事文本"  # 正文不脱敏


def test_proposal_ids_are_opaque(env):
    """公开帧（NARRATION_APPROVED 是 public）不得携带玩家/房间/物件身份。

    实测泄露点: 早期 id 形如 "s:t7e2e:r_reading:pl_b:19"，公开帧一广播
    就把「谁在哪个房间」告诉了全桌（R18 判据 A 未察觉即被破坏）。
    """
    mobile, kp = tokens()
    make_table(env)
    obj = [o for o in interactives(env, mobile)["objects"]
           if o["kind"] == "cabinet"][0]
    pid_i = env.post("/api/campaigns/%s/interact" % CAMPAIGN,
                     params={"token": mobile},
                     json={"player_id": "pl_a", "object_id": obj["id"],
                           "action": "pick_lock"}).json()["proposal_id"]
    pid_s = env.post("/api/campaigns/%s/perception/enter" % CAMPAIGN,
                     params={"token": mobile},
                     json={"player_id": "pl_a", "room": "r_reading"}
                     ).json()["proposal_id"]
    turn_no = _open_window(env, kp)
    _submit(env, mobile, "pl_a", "搜索书桌", turn_no)
    pid_p = env.post("/api/campaigns/%s/pipeline/resolve" % CAMPAIGN,
                     params={"token": kp}, json={"close_window": True}
                     ).json()["candidates"][0]["proposal_id"]
    for pid in (pid_i, pid_s, pid_p):
        for needle in ("pl_a", "pl_b", "r_reading", "cabinet", "t7t1"):
            assert needle not in pid, "%s 泄露身份 %s" % (pid, needle)
        assert pid.count(":") == 2 and len(pid.split(":")[-1]) == 12, pid

# ---- 单元: 领域层 ---------------------------------------------------------

def test_unit_interactions_deterministic():
    from app.app_core import interactions as I
    d = I.load_interactives("sample_coc")   # 裸模组 id 也能解析（不依赖 cwd）
    assert d["objects"]
    obj = d["objects"][0]
    a = I.resolve_action("c1", obj, "search", seed=7)
    b = I.resolve_action("c1", obj, "search", seed=7)
    assert a == b
    assert a["sensitive"] is False
    assert I.resolve_action("c1", obj, "look")["level"] == "auto"
    with pytest.raises(I.InteractionError):
        I.resolve_action("c1", obj, "teleport")


def test_unit_pipeline_deterministic():
    from app.app_core import action_pipeline as P
    from app.domain.model import TurnWindowState
    tw = TurnWindowState(campaign_id="c1", turn_no=2, state="CLOSED",
                         submitted={"pl_a": {"action": {"text": "搜索书桌"},
                                             "intent": "找线索"},
                                    "pl_b": {"action": {"text": "守住门口"},
                                             "intent": ""}},
                         order=["pl_b", "pl_a"])
    one = P.resolve_window("c1", tw)
    two = P.resolve_window("c1", tw)
    assert one == two
    assert [c["player_id"] for c in one] == ["pl_b", "pl_a"]
    assert one[1]["check"] and one[1]["check"]["verb"] == "搜索"
    assert one[0]["check"] is None


def test_unit_store_roundtrip(tmp_path, monkeypatch):
    from app.app_core import pipeline_store as S
    monkeypatch.setattr(S, "STORE_DIR", tmp_path / "p")
    S.reset()
    S.register("c1", "p1", {"kind": "subtitle", "targets": ["pl_a"], "text": "x"})
    S.set_status("c1", "p1", S.DELIVERED, delivered_text="y")
    S.reset()
    assert S.get("c1", "p1")["delivered_text"] == "y"
    assert S.for_actor("c1", "pl_a")[0]["status"] == S.DELIVERED
