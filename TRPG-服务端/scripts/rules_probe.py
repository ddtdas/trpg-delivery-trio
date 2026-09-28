"""R23 acceptance probe -- rulepack multi-version + auto-binding.

Read-only diagnostic. Run from the server root:

    python scripts/rules_probe.py

Sections:
  1  rulepack catalogue (packaged vs planned)
  2  repository scan / index
  3  v1 backward compatibility (app.rules.arbiter still loads all three)
  4  opening fields per ruleset
  5  SAME module opened as coc7 vs dnd5e -> field/formula diff
  6  unknown ruleset -> explicit error code
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

from app.rules import binding as binding_mod  # noqa: E402
from app.rules import resolver as resolver_mod  # noqa: E402
from app.rules.rulepack_schema import catalog  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REPO = binding_mod.RulepackRepository(ROOT / "rulepacks")


def rule(title: str) -> None:
    print("")
    print("=" * 72)
    print(title)
    print("=" * 72)


def jdump(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False))


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


def main() -> int:
    rule("1. RULEPACK CATALOGUE")
    jdump(catalog())

    rule("2. REPOSITORY SCAN")
    entries = REPO.scan()
    print("available() -> %s" % (REPO.available(),))
    print("")
    jdump(REPO.build_index())

    rule("3. V1 BACKWARD COMPATIBILITY (app.rules.arbiter)")
    from app.rules.arbiter import load_rulepack, build_arbiter
    for rid in ("coc7", "coc6", "dnd5e"):
        path = ROOT / "rulepacks" / rid / "rulepack.yaml"
        rp = load_rulepack(path)
        arb = build_arbiter(rp)
        print("  %-6s v1 load OK  rulepack_id=%s  skills=%d  attrs=%d"
              % (rid, arb.rulepack_id, len(rp["skills"]), len(rp["attrs"])))

    rule("4. OPENING FIELDS PER RULESET")
    for rid, card in (("coc7", COC7_CARD), ("coc6", COC7_CARD), ("dnd5e", DND_CARD)):
        _, rulepack, _ = REPO.resolve(rid)
        fields = resolver_mod.opening_fields(rulepack, card)
        print("")
        print("--- %s ---" % rid)
        jdump(fields)

    rule("5. SAME MODULE, TWO RULESETS (modules/sample_coc)")
    manifest_path = ROOT / "modules" / "sample_coc" / "module.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    print("manifest ruleset declared as: %r" % (manifest.get("ruleset"),))

    out = {}
    for rid, card in (("coc7", COC7_CARD), ("dnd5e", DND_CARD)):
        out[rid] = binding_mod.open_table(manifest, card, repo=REPO, ruleset_override=rid)

    for rid in ("coc7", "dnd5e"):
        block = out[rid]
        print("")
        print("--- module=%s ruleset=%s model=%s ---"
              % (block["module_id"], block["ruleset"], block["resolution_model"]))
        print("  requested=%r alias=%r" % (block["requested_ruleset"], block["alias_applied"]))
        f = block["opening_fields"]
        print("  attr names  : %s" % [a["name"] for a in f["attr_schema"]])
        print("  attr range  : %s" % sorted({(a["min"], a["max"]) for a in f["attr_schema"]}))
        print("  skill count : %d" % len(f["skill_schema"]))
        print("  difficulties: %s" % f["difficulties"])
        print("  growth model: %s" % f["growth"].get("model"))
        print("  formulas    : %s" % json.dumps(f["formulas"], ensure_ascii=False))

    rule("5b. CHECK RESOLUTION PER MODEL (same intent, different maths)")
    _, coc7_rp, _ = REPO.resolve("coc7")
    _, dnd_rp, _ = REPO.resolve("dnd5e")
    print("")
    print("coc7  spot_hidden roll=12 :")
    jdump(resolver_mod.resolve_check(coc7_rp, COC7_CARD, "spot_hidden", rolled=12))
    print("")
    print("dnd5e perception roll=12 dc=medium :")
    jdump(resolver_mod.resolve_check(dnd_rp, DND_CARD, "perception", difficulty="medium", rolled=12))

    rule("6. UNKNOWN RULESET -> EXPLICIT ERROR")
    for bad in ("pathfinder3", "coc9", "nope"):
        try:
            REPO.resolve(bad)
        except binding_mod.RulesetBindingError as exc:
            print("")
            print("resolve(%r) raised:" % bad)
            jdump(exc.to_dict())
        else:
            print("!! %r unexpectedly resolved" % bad)
            return 1

    rule("6b. MODULE MANIFEST WITH UNKNOWN RULESET")
    bad_manifest = {**manifest, "ruleset": "gurps4e"}
    try:
        REPO.bind_manifest(bad_manifest)
    except binding_mod.RulesetBindingError as exc:
        jdump(exc.to_dict())
    else:
        print("!! unknown ruleset did NOT raise")
        return 1

    rule("7. DECLARED ALIAS IS ECHOED, NEVER SILENT")
    bound = REPO.bind_manifest({**manifest, "ruleset": "dnd"})
    print("requested=%r -> ruleset=%r alias_applied=%r"
          % (bound["requested_ruleset"], bound["ruleset"], bound["alias_applied"]))

    print("")
    print("PROBE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
