# -*- coding: utf-8 -*-
"""D-03 R9 负例夹具 · 三方对照检查器（REST 路径）

用法: python scripts/_t7_fixture_check.py [--base http://127.0.0.1:9211]
输出: KP / 玩家 / 无 token 三种身份下，5 个隐藏关键字的命中计数。
判据:
  ① GM 端 5 个关键字全部可见
  ② 玩家端 5 个关键字命中数全为 0
  ③ 无 token 命中数全为 0（fail-closed）
  ④ **对抗用例**：DARKROLL_NPC_CARD_DELTA（actor="kp" 但 card_id="npc_butler"）
     在玩家侧同样必须 0 命中 —— 这条用于卡住「判据退化成 card_id == "kp"」，
     并会打印反事实计数：KP 视图里 `actor=="kp" 且 card_id != "kp"` 的 CHECK_RESOLVED
     条数（>0 即证明本夹具具备判别力，弱判据必然在此泄露）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CAMPAIGN = "fixture_r9"
LITERALS = ["HIDDEN_ROOM_ALPHA", "SECRET_CLUE_BETA", "NPC_TRUE_OMEGA", "DARKROLL_GAMMA",
            "DARKROLL_NPC_CARD_DELTA"]
ADVERSARIAL = "DARKROLL_NPC_CARD_DELTA"   # actor=kp 但 card_id != "kp" 的对抗用例


def tokens() -> tuple[str, str]:
    """读 configs/access_config.yaml 的 ends.{mobile,webapp}.token。"""
    cfg = yaml.safe_load((ROOT / "configs" / "access_config.yaml").read_text("utf-8"))
    ends = cfg.get("ends") or {}
    mob = str(((ends.get("mobile") or {}).get("token")) or "")
    web = str(((ends.get("webapp") or {}).get("token")) or "")
    if not mob or not web:
        raise SystemExit("access_config.yaml 缺少 ends.mobile.token / ends.webapp.token")
    return mob, web


def fetch(base: str, params: dict) -> tuple[int, dict]:
    r = httpx.get("%s/api/campaigns/%s/events" % (base, CAMPAIGN),
                  params=params, timeout=20)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"raw": r.text[:200]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:9211")
    a = ap.parse_args()
    base = a.base.rstrip("/")
    mobile, webapp = tokens()
    print("== D-03 R9 夹具三方对照（REST）==  campaign=%s base=%s" % (CAMPAIGN, base))
    print("token: player(mobile)=%s  kp(webapp)=%s" % (mobile, webapp))

    views = [
        ("KP(webapp)", {"since": -1, "limit": 1000, "token": webapp, "viewer": "kp"}),
        ("PLAYER(mobile)", {"since": -1, "limit": 1000, "token": mobile,
                            "viewer": "pl_fixture"}),
        ("NO-TOKEN", {"since": -1, "limit": 1000}),
    ]
    results = {}
    for name, params in views:
        code, body = fetch(base, params)
        blob = json.dumps(body, ensure_ascii=False)
        evs = body.get("events") or []
        hits = {lit: blob.count(lit) for lit in LITERALS}
        results[name] = (code, len(evs), hits)
        print("%-16s HTTP %s events=%-3d scope=%-7s filtered=%-5s hits=%s"
              % (name, code, len(evs), body.get("scope"), body.get("filtered"), hits))

    ok = all(v == 0 for v in results["PLAYER(mobile)"][2].values())
    ok2 = all(v == 0 for v in results["NO-TOKEN"][2].values())
    kp_ok = all(v > 0 for v in results["KP(webapp)"][2].values())
    adv_pl = results["PLAYER(mobile)"][2].get(ADVERSARIAL, 0)
    adv_nt = results["NO-TOKEN"][2].get(ADVERSARIAL, 0)
    adv_kp = results["KP(webapp)"][2].get(ADVERSARIAL, 0)
    ok4 = (adv_pl == 0 and adv_nt == 0 and adv_kp > 0)

    # 反事实证据：KP 视图里「actor==kp 但 card_id != kp」的 CHECK_RESOLVED 条数。
    # >0 说明本夹具确实包含弱判据（card_id == "kp"）会漏裁的事件。
    code, kp_body = fetch(base, views[0][1])
    weak_leaks = [
        e for e in (kp_body.get("events") or [])
        if e.get("type") == "CHECK_RESOLVED"
        and str(e.get("actor")) == "kp"
        and str((e.get("payload") or {}).get("card_id")) != "kp"
    ]
    print()
    print("判据① GM 端 %d 个关键字全部可见      : %s" % (len(LITERALS), "PASS" if kp_ok else "FAIL"))
    print("判据② 玩家端 %d 个关键字命中数全为 0  : %s" % (len(LITERALS), "PASS" if ok else "FAIL"))
    print("判据③ 无 token 命中数全为 0（fail-closed）: %s" % ("PASS" if ok2 else "FAIL"))
    print("判据④ 对抗用例 actor=kp/card_id!=kp 玩家与无 token 均 0 命中: %s" % ("PASS" if ok4 else "FAIL"))
    print("   [反事实] KP 视图 actor=kp 且 card_id!=kp 的 CHECK_RESOLVED 条数 = %d"
          % len(weak_leaks))
    print("      -> card_id 的取值: %s"
          % sorted({str((e.get("payload") or {}).get("card_id")) for e in weak_leaks}))
    print("      -> 若实现退化为 card_id == \"kp\" 判据，上述 %d 条会原样出现在玩家视图（判据④ FAIL）"
          % len(weak_leaks))
    if not ok:
        leak = [k for k, v in results["PLAYER(mobile)"][2].items() if v]
        print("泄露字面量: %s" % leak)
        print("玩家可拉取的原始事件流（截断 1200 字）:")
        code, body = fetch(base, views[1][1])
        print(json.dumps(body, ensure_ascii=False)[:1200])
    return 0 if (ok and ok2 and ok4) else 2


if __name__ == "__main__":
    raise SystemExit(main())
