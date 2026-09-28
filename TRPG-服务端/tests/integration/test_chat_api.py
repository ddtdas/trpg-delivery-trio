# -*- coding: utf-8 -*-
"""M3 (T6): 私聊系统测试 —— 四态调控 + 同场景私聊 + 公共频道 + 服务端权威门控。

运行（在 TRPG-服务端 根目录）:
    python -m pytest tests/test_chat_api.py -q

隔离: 事件库/桌注册表全部重定向到 tmp_path，不触碰交付包 data/trpg.db。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

CAMPAIGN = "chatc1"
TABLE = "chatt1"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    from app.web import access as access_mod
    from app.web import rest as rest_mod

    monkeypatch.setattr(rest_mod, "DEFAULT_DB", tmp_path / "chat.db")
    monkeypatch.setattr(rest_mod, "SNAP_BASE", tmp_path / "snapshots")
    monkeypatch.setattr(access_mod, "_registry_path", lambda: tmp_path / "tables_registry.json")
    monkeypatch.setattr(access_mod, "_save_tables_registry", lambda: None)
    monkeypatch.setattr(access_mod, "persist_tables", lambda: None)
    rest_mod.TABLES.clear()
    from app.main import app
    with TestClient(app) as client:
        yield client
    rest_mod.TABLES.clear()


def tokens() -> tuple[str, str]:
    """(mobile=玩家, webapp=主持人)。"""
    from app.web import access as access_mod
    cfg = access_mod._load_config()
    ends = cfg["ends"]
    return str(ends["mobile"]["token"]), str(ends["webapp"]["token"])


def make_table(client: TestClient, campaign: str = CAMPAIGN,
               table: str = TABLE) -> None:
    r = client.post("/api/tables",
                    json={"table_id": table, "campaign_id": campaign,
                          "ruleset": "coc7", "config": {"module": "sample_coc"}})
    assert r.status_code == 201, r.text


def post_char(client: TestClient, player: str, campaign: str = CAMPAIGN) -> None:
    """建一张角色卡（让玩家出现在 chat/status 的 players 列表）。"""
    r = client.post("/api/campaigns/%s/events" % campaign,
                    params={"token": tokens()[1]},
                    json={"type": "CHARACTER_CREATED",
                          "payload": {"card_id": "card_" + player,
                                      "player_id": player, "ruleset": "coc7",
                                      "card": {"name": player}},
                          "actor": player})
    assert r.status_code == 201, r.text


# ---- 四态调控 --------------------------------------------------------------

def test_chat_status_default_enabled(env):
    mobile, kp = tokens()
    make_table(env)
    post_char(env, "p1")
    r = env.get("/api/campaigns/%s/chat/status" % CAMPAIGN,
                params={"token": mobile})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["mode"] == "chat_enabled"
    assert d["private_allowed"] is True
    assert d["public_allowed"] is True
    assert any(p["id"] == "p1" for p in d["players"])


def test_chat_mode_set_and_roundtrip(env):
    mobile, kp = tokens()
    make_table(env)
    for mode in ("chat_disabled", "public_only", "all_disabled", "chat_enabled"):
        r = env.post("/api/campaigns/%s/chat/mode" % CAMPAIGN,
                     params={"token": kp},
                     json={"mode": mode, "scope": "campaign"})
        assert r.status_code == 201, r.text
        assert r.json()["mode"] == mode
        s = env.get("/api/campaigns/%s/chat/status" % CAMPAIGN,
                    params={"token": mobile}).json()
        assert s["mode"] == mode
        assert s["private_allowed"] == (mode == "chat_enabled")
        assert s["public_allowed"] == (mode != "all_disabled")


def test_chat_mode_requires_kp(env):
    mobile, kp = tokens()
    make_table(env)
    r = env.post("/api/campaigns/%s/chat/mode" % CAMPAIGN,
                 params={"token": mobile},
                 json={"mode": "all_disabled"})
    assert r.status_code == 403, r.text  # mobile token 不能调控（kp_only）


def test_chat_mode_invalid_value(env):
    mobile, kp = tokens()
    make_table(env)
    r = env.post("/api/campaigns/%s/chat/mode" % CAMPAIGN,
                 params={"token": kp},
                 json={"mode": "bogus"})
    assert r.status_code in (403, 422), r.text


# ---- 私聊门控 --------------------------------------------------------------

def test_private_msg_ok_same_scene(env):
    mobile, kp = tokens()
    make_table(env)
    post_char(env, "p1")
    post_char(env, "p2")
    # 主持人先开放私聊
    env.post("/api/campaigns/%s/chat/mode" % CAMPAIGN,
             params={"token": kp}, json={"mode": "chat_enabled"})
    r = env.post("/api/campaigns/%s/chat/private" % CAMPAIGN,
                 params={"token": mobile},
                 json={"player_id": "p1", "to_players": ["p2"],
                       "text": "你好，p2！"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["type"] == "PRIVATE_MSG"
    assert body["to_players"] == ["p2"]
    # 事件落库
    ev = env.get("/api/campaigns/%s/events" % CAMPAIGN,
                 params={"token": kp, "limit": 1000}).json()["events"]
    priv = [e for e in ev if e["type"] == "PRIVATE_MSG"]
    assert priv and priv[-1]["payload"]["text"] == "你好，p2！"


def test_private_msg_blocked_when_disabled(env):
    mobile, kp = tokens()
    make_table(env)
    post_char(env, "p1")
    post_char(env, "p2")
    env.post("/api/campaigns/%s/chat/mode" % CAMPAIGN,
             params={"token": kp}, json={"mode": "chat_disabled"})
    r = env.post("/api/campaigns/%s/chat/private" % CAMPAIGN,
                 params={"token": mobile},
                 json={"player_id": "p1", "to_players": ["p2"], "text": "hi"})
    assert r.status_code == 403, r.text
    assert "私聊已关闭" in r.json().get("detail", "")


def test_private_msg_cross_scene_rejected(env):
    mobile, kp = tokens()
    make_table(env)
    post_char(env, "p1")
    post_char(env, "p2")
    # 制造 MAP_UPDATED: p1 在 r_a, p2 在 r_b（不同房间）
    env.post("/api/campaigns/%s/map" % CAMPAIGN, params={"token": kp},
             json={"map_id": "m1", "op": "add_token", "target": "p1",
                   "delta": {"room": "r_a"}})
    env.post("/api/campaigns/%s/map" % CAMPAIGN, params={"token": kp},
             json={"map_id": "m1", "op": "add_token", "target": "p2",
                   "delta": {"room": "r_b"}})
    r = env.post("/api/campaigns/%s/chat/private" % CAMPAIGN,
                 params={"token": mobile},
                 json={"player_id": "p1", "to_players": ["p2"], "text": "hi"})
    assert r.status_code == 422, r.text
    assert "不在同一场景" in r.json().get("detail", "")


# ---- 公共频道 --------------------------------------------------------------

def test_public_chat_allowed_and_blocked(env):
    mobile, kp = tokens()
    make_table(env)
    post_char(env, "p1")
    post_char(env, "p2")
    # chat_disabled: 公共放行
    env.post("/api/campaigns/%s/chat/mode" % CAMPAIGN,
             params={"token": kp}, json={"mode": "chat_disabled"})
    r = env.post("/api/campaigns/%s/chat/private" % CAMPAIGN,
                 params={"token": mobile},
                 json={"player_id": "p1", "to_players": ["_public_"],
                       "text": "大家好"})
    assert r.status_code == 201, r.text
    # all_disabled: 公共拒绝
    env.post("/api/campaigns/%s/chat/mode" % CAMPAIGN,
             params={"token": kp}, json={"mode": "all_disabled"})
    r = env.post("/api/campaigns/%s/chat/private" % CAMPAIGN,
                 params={"token": mobile},
                 json={"player_id": "p1", "to_players": ["_public_"],
                       "text": "大家好"})
    assert r.status_code == 403, r.text


# ---- 可见性: 私聊只达参与方 ------------------------------------------------

def test_private_msg_visibility_participants_only(env):
    mobile, kp = tokens()
    make_table(env)
    post_char(env, "p1")
    post_char(env, "p2")
    post_char(env, "p3")
    env.post("/api/campaigns/%s/chat/private" % CAMPAIGN,
             params={"token": mobile},
             json={"player_id": "p1", "to_players": ["p2"], "text": "秘密消息"})
    # p3 视角（mobile token, viewer=p3）不得看到该私聊正文
    r3 = env.get("/api/campaigns/%s/events" % CAMPAIGN,
                 params={"token": mobile, "viewer": "p3", "limit": 1000})
    ev3 = [e for e in r3.json()["events"] if e["type"] == "PRIVATE_MSG"]
    for e in ev3:
        assert e["payload"].get("text") != "秘密消息"
        assert "秘密消息" not in str(e)