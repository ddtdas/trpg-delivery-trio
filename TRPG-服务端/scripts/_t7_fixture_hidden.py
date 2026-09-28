# -*- coding: utf-8 -*-
"""D-03 R9 负例夹具战役：含 GM 私有内容的专用战役（t7 交付）。

四个唯一可检索字面量（REST 与 WS 两条路径都能驱动）:
  HIDDEN_ROOM_ALPHA   未揭示房间（KP 定向 INFO_REVEALED）
  SECRET_CLUE_BETA    私有线索草稿（NARRATION_PROPOSED -> KP-only 帧）
  NPC_TRUE_OMEGA      NPC 真身（NPC_ACT_PROPOSED -> KP-only 帧）
  DARKROLL_GAMMA      暗骰结果（CHECK_RESOLVED, actor="kp", card_id="kp"）
  DARKROLL_NPC_CARD_DELTA  **对抗用例**：同样由 KP 掷出（actor="kp"）的暗骰，
                      但 card_id 故意不等于 "kp"（= "npc_butler"）。
                      它存在的唯一目的：证明判据**必须**是「骰主是 KP」(actor)，
                      而不能退化成 card_id == "kp" —— 后者会因为这个 card_id 而漏裁。

R9 门禁：五个字面量在玩家侧（REST + WS）命中数都必须是 0。
  * INFO_REVEALED(whisper->kp) / NARRATION_PROPOSED / NPC_ACT_PROPOSED 已由
    visibility.KP_ONLY_EVENT_TYPES + whisper targets 裁剪覆盖；
  * CHECK_RESOLVED 的暗骰判据必须锚在**事件 actor**上（actor == "kp"，即骰主是 KP），
    而**不是** card_id == "kp" —— 见 LITERALS 里的 DARKROLL_NPC_CARD_DELTA 对抗用例：
    用 card_id 判据会漏裁「KP 用 NPC 卡掷的暗骰」，那类事件同样会泄露 target/rolled/level。
另加 1 条公开事件（TURN_STARTED）作对照，保证玩家侧不是空集。

运行（默认打运行中的 9211；可指定隔离实例）:
    python scripts/_t7_fixture_hidden.py
    python scripts/_t7_fixture_hidden.py --base http://127.0.0.1:9317
幂等：字面量已存在则跳过写入；--force 可强制补写。
重建：--reset 会先备份 data/trpg.db 为 data/trpg.db.r9bak，再删除本夹具战役的
      全部事件（保证不残留早期版本写入的、card_id 不符的暗骰事件），然后重写
      标准 5 条事件。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import websockets
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CAMPAIGN = "fixture_r9"
TABLE = "fixture_r9_table"
LITERALS = ("HIDDEN_ROOM_ALPHA", "SECRET_CLUE_BETA",
            "NPC_TRUE_OMEGA", "DARKROLL_GAMMA", "DARKROLL_NPC_CARD_DELTA")

_cfg = yaml.safe_load((ROOT / "configs" / "access_config.yaml").read_text(encoding="utf-8"))
MOBILE = str(_cfg["ends"]["mobile"]["token"])
WEBAPP = str(_cfg["ends"]["webapp"]["token"])


def _events(base: str) -> list[dict]:
    r = httpx.get("%s/api/campaigns/%s/events" % (base, CAMPAIGN),
                  params={"since": -1, "limit": 1000}, timeout=20)
    return r.json().get("events", []) if r.status_code == 200 else []


def _fixture_events() -> list[tuple[str, dict, str, str | None]]:
    """(type, payload, actor, literal) —— literal=None 表示"仅当战役为空时写入"。

    payload 必须严格匹配冻结模型（StrictModel, extra=forbid）:
      InfoRevealed     = campaign_id/info_id/scope/targets/body_ref
      NarrationProposed= campaign_id/proposal_id/text/intention/reasoning/source
      NpcActProposed   = campaign_id/npc_id/lines[]/context_ref
      CheckResolved    = campaign_id/turn_no/card_id/target/difficulty/rolled/total/level/seed/summary
    """
    end = (datetime.now(timezone.utc) + timedelta(seconds=600)).isoformat()
    return [
        ("TURN_STARTED",
         {"campaign_id": CAMPAIGN, "turn_no": 1, "window_sec": 600,
          "countdown_end_ts": end},
         "kp", None),
        ("INFO_REVEALED",
         {"campaign_id": CAMPAIGN, "info_id": "info:fixture:hidden-room",
          "scope": "whisper", "targets": ["kp"],
          "body_ref": "HIDDEN_ROOM_ALPHA：未揭示房间「地下酒窖暗门」（KP 私有）"},
         "kp", "HIDDEN_ROOM_ALPHA"),
        ("NARRATION_PROPOSED",
         {"campaign_id": CAMPAIGN, "proposal_id": "fixture-secret-clue",
          "text": "SECRET_CLUE_BETA：管家袖口沾着新泥（KP 私有线索）",
          "intention": "", "reasoning": "R9 夹具", "source": "agent"},
         "agent", "SECRET_CLUE_BETA"),
        ("NPC_ACT_PROPOSED",
         {"campaign_id": CAMPAIGN, "npc_id": "npc_butler",
          "lines": ["NPC_TRUE_OMEGA：管家其实是已死的少东家（KP 私有真身）"],
          "context_ref": "fixture_r9"},
         "agent", "NPC_TRUE_OMEGA"),
        # 暗骰：CHECK_RESOLVED 是冻结模型（无 scope 字段），玩家侧要隐藏只能靠
        # 「骰主是 KP」这一约定（事件 actor == "kp"）。R9 的 clip_event 需要增加
        # 该规则，否则本字面量对玩家可见 —— 这正是本夹具要卡住的门禁。
        ("CHECK_RESOLVED",
         {"campaign_id": CAMPAIGN, "turn_no": 1, "card_id": "kp",
          "target": "DARKROLL_GAMMA", "difficulty": 3, "rolled": [13],
          "total": 13, "level": "extreme", "seed": "fixture-dark",
          "summary": "暗骰（KP 私有）"},
         "kp", "DARKROLL_GAMMA"),
        # ★ 对抗用例（防判据退化）：同样 actor="kp"（骰主是 KP），但 card_id 故意
        #   不等于 "kp" —— KP 用 NPC 卡（npc_butler）掷的暗骰。若实现只按
        #   card_id == "kp" 裁剪，本事件就会原样出现在玩家视图里（判据②直接 FAIL）。
        ("CHECK_RESOLVED",
         {"campaign_id": CAMPAIGN, "turn_no": 1, "card_id": "npc_butler",
          "target": "DARKROLL_NPC_CARD_DELTA", "difficulty": 4, "rolled": [7],
          "total": 7, "level": "hard", "seed": "fixture-dark-npccard",
          "summary": "暗骰（KP 用 NPC 卡掷，KP 私有）"},
         "kp", "DARKROLL_NPC_CARD_DELTA"),
    ]


def _reset_campaign(db: Path) -> int:
    """备份 + 清空本夹具战役的事件（D5 快照纪律：先备份再写）。"""
    if not db.is_file():
        return 0
    bak = db.with_suffix(db.suffix + ".r9bak")
    if not bak.exists():
        shutil.copy2(db, bak)
    con = sqlite3.connect(str(db))
    try:
        n = con.execute("select count(*) from events where campaign_id=?",
                        (CAMPAIGN,)).fetchone()[0]
        con.execute("delete from events where campaign_id=?", (CAMPAIGN,))
        con.commit()
    finally:
        con.close()
    return int(n)


async def _ws_probe(base: str, viewer: str, token: str, role: str,
                    sink: list) -> object:
    url = "%s?table=%s&viewer=%s&role=%s&token=%s" % (
        base.replace("http://", "ws://") + "/ws", TABLE, viewer, role, token)
    ws = await websockets.connect(url)

    async def reader():
        try:
            async for raw in ws:
                sink.append(json.loads(raw))
        except Exception:  # noqa: BLE001
            return
    asyncio.create_task(reader())
    return ws


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:9211")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--reset", action="store_true",
                    help="重建夹具：备份 trpg.db 后清空本战役事件，再写标准 5 条")
    ap.add_argument("--db", default=str(ROOT / "data" / "trpg.db"),
                    help="--reset 用的库文件")
    ap.add_argument("--probe", action="store_true",
                    help="WS 负例专用: 在两条 WS 都连上后，追加一组带同名字面量的"
                         "探针事件（唯一 id），使 WS 路径当场可见帧")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    print("== D-03 R9 负例夹具战役 ==")
    print("base=%s campaign=%s table=%s" % (base, CAMPAIGN, TABLE))

    with httpx.Client(timeout=20) as c:
        r = c.post(base + "/access/host/table", params={"token": WEBAPP},
                   json={"table_id": TABLE, "campaign_id": CAMPAIGN,
                         "ruleset": "coc7", "name": "R9 负例夹具"})
        print("[开桌] HTTP %s %s" % (r.status_code,
                                     json.dumps(r.json(), ensure_ascii=False)))

    if args.reset:
        n = _reset_campaign(Path(args.db))
        print("[重建] 已备份 %s -> %s.r9bak, 删除旧事件 %d 条"
              % (args.db, args.db, n))
        args.force = True

    existing = _events(base)
    have = {lit for lit in LITERALS
            if any(lit in json.dumps(e, ensure_ascii=False) for e in existing)}
    print("[现状] 已有事件 %d 条, 已含字面量 %s" % (len(existing), sorted(have)))

    kp_frames: list = []
    pl_frames: list = []
    ws_kp = await _ws_probe(base, "kp", WEBAPP, "kp", kp_frames)
    ws_pl = await _ws_probe(base, "pl_fixture", MOBILE, "pl", pl_frames)
    await asyncio.sleep(0.5)

    with httpx.Client(timeout=20) as c:
        for etype, payload, actor, literal in _fixture_events():
            if literal is None and existing:
                print("[跳过] %-20s (战役非空, 公开对照事件已存在)" % etype)
                continue
            if literal and literal in have and not args.force:
                print("[跳过] %-20s (%s 已存在, 幂等)" % (etype, literal))
                continue
            r = c.post("%s/api/campaigns/%s/events" % (base, CAMPAIGN),
                       json={"type": etype, "payload": payload, "actor": actor})
            print("[写入] %-20s HTTP %s %s" % (
                etype, r.status_code,
                json.dumps(r.json(), ensure_ascii=False)
                if r.status_code < 300 else r.text.replace("\n", " ")))
    await asyncio.sleep(0.6)

    if args.probe:
        stamp = int(datetime.now(timezone.utc).timestamp())
        probes = [
            ("INFO_REVEALED",
             {"campaign_id": CAMPAIGN,
              "info_id": "info:fixture:hidden-room:probe%d" % stamp,
              "scope": "whisper", "targets": ["kp"],
              "body_ref": "HIDDEN_ROOM_ALPHA：未揭示房间探针（KP 私有）"}, "kp"),
            ("NARRATION_PROPOSED",
             {"campaign_id": CAMPAIGN,
              "proposal_id": "fixture-secret-clue-probe%d" % stamp,
              "text": "SECRET_CLUE_BETA：私有线索探针（KP 私有）",
              "intention": "", "reasoning": "R9 夹具探针", "source": "agent"},
             "agent"),
            ("NPC_ACT_PROPOSED",
             {"campaign_id": CAMPAIGN, "npc_id": "npc_butler",
              "lines": ["NPC_TRUE_OMEGA：真身探针（KP 私有）"],
              "context_ref": "fixture_r9_probe%d" % stamp}, "agent"),
            ("CHECK_RESOLVED",
             {"campaign_id": CAMPAIGN, "turn_no": 1, "card_id": "kp",
              "target": "DARKROLL_GAMMA", "difficulty": 3, "rolled": [13],
              "total": 13, "level": "extreme", "seed": "fixture-dark-%d" % stamp,
              "summary": "暗骰探针（KP 私有）"}, "kp"),
            # 对抗探针：actor=kp 但 card_id != "kp"（弱判据会漏裁的那一类）
            ("CHECK_RESOLVED",
             {"campaign_id": CAMPAIGN, "turn_no": 1, "card_id": "npc_butler",
              "target": "DARKROLL_NPC_CARD_DELTA", "difficulty": 4, "rolled": [7],
              "total": 7, "level": "hard",
              "seed": "fixture-dark-npccard-%d" % stamp,
              "summary": "暗骰对抗探针（KP 用 NPC 卡掷，KP 私有）"}, "kp"),
        ]
        with httpx.Client(timeout=20) as c:
            for etype, payload, actor in probes:
                r = c.post("%s/api/campaigns/%s/events" % (base, CAMPAIGN),
                           json={"type": etype, "payload": payload, "actor": actor})
                print("[探针] %-20s HTTP %s" % (etype, r.status_code))
        await asyncio.sleep(0.8)

    await ws_kp.close()
    await ws_pl.close()

    print("\n[WS] KP 端收到的帧 (%d):" % len(kp_frames))
    print(json.dumps(kp_frames, ensure_ascii=False, indent=2)[:3000])
    print("\n[WS] 玩家端收到的帧 (%d):" % len(pl_frames))
    print(json.dumps(pl_frames, ensure_ascii=False, indent=2)[:3000])

    pl_blob = json.dumps(pl_frames, ensure_ascii=False)
    kp_blob = json.dumps(kp_frames, ensure_ascii=False)
    print("\n[自检] WS 关键字命中数（player 必须全 0；kp 仅作对照）:")
    for lit in LITERALS:
        print("   %-18s player=%d  kp=%d" % (lit, pl_blob.count(lit), kp_blob.count(lit)))

    dump = json.dumps(_events(base), ensure_ascii=False)
    print("[自检] 玩家可拉取的 REST 事件流关键字命中数（R9 未修前=每个字面量>0，修后应为 0）:")
    total = 0
    for lit in LITERALS:
        n = dump.count(lit)
        total += n
        print("   %-18s %d" % (lit, n))
    print("[结论] REST 命中合计=%d（R9 判据：玩家侧应为 0）" % total)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
