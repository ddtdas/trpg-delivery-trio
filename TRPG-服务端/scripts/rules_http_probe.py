"""R23 HTTP acceptance probe -- real ASGI app, in-process.

Uses fastapi.testclient so the ACTUAL app.main:app routing table is
exercised (no stub, no second server, no interference with the live
instance on 9211).

    python scripts/rules_http_probe.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)

COC7_CARD = {
    "name": "Investigator A",
    "attrs": {"STR": 50, "CON": 60, "SIZ": 70, "DEX": 55, "APP": 45,
              "INT": 65, "POW": 70, "EDU": 80, "LUCK": 50},
    "skills": {"spot_hidden": 45, "library_use": 60, "dodge": 27},
}

DND_CARD = {
    "name": "Adventurer A",
    "attrs": {"STR": 16, "DEX": 14, "CON": 15, "INT": 12, "WIS": 13,
              "CHA": 10, "LEVEL": 3},
    "skills": {},
}


def show(method: str, url: str, **kw) -> dict:
    resp = client.request(method, url, **kw)
    print("")
    print("%s %s  ->  HTTP %d" % (method, url, resp.status_code))
    try:
        body = resp.json()
    except Exception:
        print(resp.text[:400])
        return {}
    print(json.dumps(body, ensure_ascii=False, indent=2)[:2600])
    return body


def rule(title: str) -> None:
    print("")
    print("=" * 72)
    print(title)
    print("=" * 72)


def main() -> int:
    rule("0. ROUTES PRESENT IN /openapi.json")
    spec = client.get("/openapi.json").json()
    rules_paths = sorted(p for p in spec["paths"] if p.startswith("/api/rules"))
    for p in rules_paths:
        print("  " + p)
    if len(rules_paths) < 4:
        print("!! /api/rules/* not fully mounted")
        return 1

    rule("1. GET /api/rules/catalog")
    cat = show("GET", "/api/rules/catalog")
    packaged = [row["id"] for row in cat.get("packaged", [])]
    print("")
    print("packaged: %s" % packaged)
    print("planned : %s" % [row["id"] for row in cat.get("planned", [])])

    rule("2. GET /api/rules/rulesets")
    idx = show("GET", "/api/rules/rulesets")
    print("")
    print("available: %s" % idx.get("available"))

    rule("3. SAME MODULE OPENED AS coc7 vs dnd5e")
    coc7 = show("POST", "/api/rules/open",
                json={"module_id": "sample_coc", "ruleset": "coc7", "card": COC7_CARD})
    dnd = show("POST", "/api/rules/open",
               json={"module_id": "sample_coc", "ruleset": "dnd5e", "card": DND_CARD})

    rule("3b. FIELD / FORMULA DIFF (the R23 acceptance surface)")
    fa = coc7.get("opening_fields", {})
    fb = dnd.get("opening_fields", {})
    print("module_id          : %r vs %r" % (coc7.get("module_id"), dnd.get("module_id")))
    print("resolution_model   : %r vs %r" % (coc7.get("resolution_model"), dnd.get("resolution_model")))
    print("attr names         : %s" % [a["name"] for a in fa.get("attr_schema", [])])
    print("                   : %s" % [a["name"] for a in fb.get("attr_schema", [])])
    print("attr ranges        : %s" % sorted({(a["min"], a["max"]) for a in fa.get("attr_schema", [])}))
    print("                   : %s" % sorted({(a["min"], a["max"]) for a in fb.get("attr_schema", [])}))
    print("skill count        : %d vs %d" % (len(fa.get("skill_schema", {})), len(fb.get("skill_schema", {}))))
    print("difficulties       : %s" % fa.get("difficulties"))
    print("                   : %s" % fb.get("difficulties"))
    print("growth model       : %r vs %r" % (fa.get("growth", {}).get("model"), fb.get("growth", {}).get("model")))
    print("formula keys       : %s" % sorted(fa.get("formulas", {})))
    print("                   : %s" % sorted(fb.get("formulas", {})))
    print("coc7 formulas      : %s" % json.dumps(fa.get("formulas", {}), ensure_ascii=False))
    print("dnd5e formulas     : %s" % json.dumps(fb.get("formulas", {}), ensure_ascii=False))

    if sorted(fa.get("formulas", {})) == sorted(fb.get("formulas", {})):
        print("!! formulas identical -- rulesets are NOT actually distinguished")
        return 1

    rule("4. UNKNOWN RULESET OVER HTTP")
    bad = show("POST", "/api/rules/open",
               json={"module_id": "sample_coc", "ruleset": "gurps4e", "card": COC7_CARD})
    if bad.get("code") != "MODULE_RULESET_UNKNOWN":
        print("!! expected R13 code MODULE_RULESET_UNKNOWN, got %r" % (bad.get("code"),))
        return 1
    print("")
    print("R13 code=%r internal=%r http_status=%r"
          % (bad.get("code"), bad.get("internal_code"), bad.get("http_status")))

    rule("4b. UNKNOWN RULESET VIA GET")
    show("GET", "/api/rules/rulesets/pathfinder3")

    rule("4c. PLANNED RULESET IS DISTINGUISHED FROM UNKNOWN")
    show("GET", "/api/rules/rulesets/pf2e")

    rule("5. DECLARED ALIAS IS ECHOED")
    alias = show("POST", "/api/rules/bind", json={"module_id": "sample_coc", "ruleset": "dnd"})
    if alias.get("alias_applied") != "dnd5e":
        print("!! alias not echoed")
        return 1

    rule("6. MODULE MANIFEST DRIVES BINDING WHEN NO OVERRIDE IS GIVEN")
    show("POST", "/api/rules/bind", json={"module_id": "sample_coc"})

    print("")
    print("HTTP PROBE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
