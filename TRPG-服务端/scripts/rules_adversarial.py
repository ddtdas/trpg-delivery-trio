"""R23 adversarial probe -- attempts to FALSIFY the R23 claims.

This is the material an independent reviewer (t9) should run. Every case
here is an attempt to make the rules layer misbehave: silent fallback,
path escape, expression injection, cache poisoning. A PASS means the
layer refused cleanly instead of degrading quietly.

Read-only: nothing is written, no server is started.

    python scripts/rules_adversarial.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rules import binding as binding_mod
from app.rules import formulas as formulas_mod
from app.rules import resolver as resolver_mod

REPO = binding_mod.default_repository()
FAILURES: list[str] = []
CHECKS = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    print("  [%s] %s%s" % ("PASS" if ok else "FAIL", label, ("  <- " + detail) if detail else ""))
    if not ok:
        FAILURES.append(label)


def must_error(label: str, fn) -> None:
    """The call must raise a typed error -- not return, not fall back."""
    try:
        got = fn()
    except (binding_mod.RulesetBindingError, resolver_mod.ResolutionError,
            formulas_mod.FormulaError) as exc:
        code = getattr(exc, "code", type(exc).__name__)
        check(label, True, "refused with %s" % code)
    except Exception as exc:  # noqa: BLE001
        check(label, False, "raised unexpected %r" % (exc,))
    else:
        check(label, False, "NO ERROR -- returned %r (silent degradation!)" % (got,))


def section(title: str) -> None:
    print("")
    print("-" * 70)
    print(title)
    print("-" * 70)


print("=" * 70)
print("R23 ADVERSARIAL PROBE -- trying to break the rulepack layer")
print("=" * 70)

# ---------------------------------------------------------------- A: ids
section("A. ruleset id abuse -- must never silently pick a different pack")

for bad in ("", "   ", None, 123, [], {}, "coc7x", "coc9", "coc 7",
            "GURPS", "not-a-ruleset"):
    must_error("resolve(%r) refused" % (bad,), lambda b=bad: REPO.resolve(b))

section("A2. path traversal -- must not read outside rulepacks/")
for evil in ("../../../etc/passwd",
             "..\\..\\..\\windows\\win.ini",
             "coc7/../coc6",
             "coc7/../../rulepacks/coc6",
             "/etc/passwd",
             "C:\\Windows\\win.ini",
             "coc7\0coc6"):
    must_error("resolve(%r) refused" % (evil,), lambda e=evil: REPO.resolve(e))

section("A3. case / whitespace handling must be explicit, never accidental")
for variant in ("COC7", "Coc7", " coc7 ", "\tcoc7"):
    try:
        canonical, _pack, alias = REPO.resolve(variant)
        ok = canonical in ("coc7", "coc6", "dnd5e", "custom")
        check("resolve(%r) -> %r (alias=%r)" % (variant, canonical, alias), ok,
              "resolved to a real packaged ruleset")
    except binding_mod.RulesetBindingError as exc:
        check("resolve(%r) refused cleanly" % (variant,), True, exc.code)

# ------------------------------------------------------------ B: formulas
section("B. formula safety -- YAML must never become code")

must_error("expression string rejected",
           lambda: formulas_mod.resolve_one({"fn": "half", "args": {"of": "DEX / 2"}}, {}))
must_error("dunder ref rejected",
           lambda: formulas_mod.resolve_one({"fn": "half", "args": {"of": "$__import__"}}, {}))
must_error("os.system fn rejected",
           lambda: formulas_mod.resolve_one({"fn": "os_system", "args": {}}, {}))
must_error("eval fn rejected",
           lambda: formulas_mod.resolve_one({"fn": "eval", "args": {}}, {}))
must_error("exec fn rejected",
           lambda: formulas_mod.resolve_one({"fn": "exec", "args": {}}, {}))
must_error("extra key beyond fn/args rejected",
           lambda: formulas_mod.resolve_one({"fn": "half", "args": {"of": 10}, "x": 1}, {}))
must_error("bool in numeric slot rejected",
           lambda: formulas_mod.resolve_one({"fn": "half", "args": {"of": True}}, {}))
must_error("missing required arg rejected",
           lambda: formulas_mod.resolve_one({"fn": "half", "args": {}}, {}))
must_error("self-referential ref rejected",
           lambda: formulas_mod.resolve_formulas(
               {"formulas": {"a": {"fn": "half", "args": {"of": "$a"}}}}, {}))

# ------------------------------------------------------- C: cache isolation
section("C. repository cache isolation -- callers must not poison it")
try:
    _, pack1, _ = REPO.resolve("coc7")
    before = sorted(pack1.get("formulas", {}))
    pack1["formulas"]["__INJECTED__"] = {"fn": "const", "args": {"value": 666}}
    pack1["skills"]["__INJECTED__"] = 99
    # DEEP poisoning: mutate nested containers IN PLACE. A key-count
    # comparison would not catch this -- method adopted from the t9
    # independent review, which found the original check too weak.
    deep_targets = 0
    for key in ("formulas", "skills", "attrs"):
        node = pack1.get(key)
        if isinstance(node, dict):
            for sub in node.values():
                if isinstance(sub, dict):
                    sub["__T9_POISON__"] = "poison"
                    deep_targets += 1
                elif isinstance(sub, list):
                    sub.append("__T9_POISON__")
                    deep_targets += 1

    _, pack2, _ = REPO.resolve("coc7")
    after = sorted(pack2.get("formulas", {}))
    blob = repr(pack2)
    check("mutating a returned rulepack does not poison the cache (shallow)",
          after == before and "__INJECTED__" not in pack2.get("skills", {}),
          "before=%d keys after=%d keys" % (len(before), len(after)))
    check("nested in-place mutation does not poison the cache (deep)",
          "__T9_POISON__" not in blob and "__INJECTED__" not in blob,
          "deep targets mutated=%d  poison leaked=%s"
          % (deep_targets, "__T9_POISON__" in blob))
except Exception as exc:  # noqa: BLE001
    check("cache isolation", False, repr(exc))

# ------------------------------------------------------------- D: manifests
section("D. malformed manifests -- typed errors, never a crash")
must_error("manifest ruleset is a list",
           lambda: REPO.bind_manifest({"id": "x", "ruleset": ["coc7"]}))
must_error("manifest ruleset is a dict",
           lambda: REPO.bind_manifest({"id": "x", "ruleset": {"name": "coc7"}}))
must_error("manifest ruleset is a bool",
           lambda: REPO.bind_manifest({"id": "x", "ruleset": True}))
must_error("manifest ruleset is an int",
           lambda: REPO.bind_manifest({"id": "x", "ruleset": 7}))

# ---------------------------------------------- E: genuine differentiation
section("E. differentiation is real -- coc7 and dnd5e must not coincide")
try:
    _, c7, _ = REPO.resolve("coc7")
    _, d5, _ = REPO.resolve("dnd5e")
    f7 = set(c7.get("formulas", {}))
    f5 = set(d5.get("formulas", {}))
    shared = f7 & f5
    # Honest bar: the sets need not be disjoint (hp_max exists in both), but
    # they must be substantially different AND every shared name must still
    # compute to a different value -- otherwise it is a relabelled copy.
    check("formula key sets are substantially different",
          len(shared) <= 1 and len(f7) + len(f5) - 2 * len(shared) >= 30,
          "coc7=%d dnd5e=%d shared=%s" % (len(f7), len(f5), sorted(shared)))
    card7 = {"attrs": {"STR": 50, "CON": 60, "SIZ": 70, "DEX": 55, "APP": 45,
                       "INT": 65, "POW": 70, "EDU": 80, "LUCK": 50},
             "skills": {"spot_hidden": 45, "dodge": 27}}
    card5 = {"attrs": {"STR": 16, "DEX": 14, "CON": 15, "INT": 12, "WIS": 13,
                       "CHA": 10, "LEVEL": 3}, "skills": {}}
    v7 = resolver_mod.opening_fields(c7, card7)["formulas"]
    v5 = resolver_mod.opening_fields(d5, card5)["formulas"]
    for k in sorted(shared):
        check("shared formula %r computes to different values" % k,
              v7.get(k) != v5.get(k), "coc7=%r vs dnd5e=%r" % (v7.get(k), v5.get(k)))
    check("resolution models differ",
          resolver_mod.resolution_model(c7) != resolver_mod.resolution_model(d5),
          "%s vs %s" % (resolver_mod.resolution_model(c7), resolver_mod.resolution_model(d5)))
    check("attr name lists differ",
          [a["name"] for a in c7.get("attrs", [])] != [a["name"] for a in d5.get("attrs", [])])
except Exception as exc:  # noqa: BLE001
    check("differentiation", False, repr(exc))

# ------------------------------------------------------ F: no silent default
section("F. no silent default ruleset")
try:
    _, pack, _ = REPO.resolve("coc7")
    check("resolve returns the requested pack, not a default",
          pack.get("id") == "coc7", "got id=%r" % (pack.get("id"),))
    _, pack6, _ = REPO.resolve("coc6")
    check("coc6 resolves to coc6 (not to coc7)",
          pack6.get("id") == "coc6", "got id=%r" % (pack6.get("id"),))
except Exception as exc:  # noqa: BLE001
    check("no silent default", False, repr(exc))

print("")
print("=" * 70)
print("CHECKS RUN: %d   FAILURES: %d" % (CHECKS, len(FAILURES)))
for f in FAILURES:
    print("  FAILED: %s" % f)
print("ADVERSARIAL PROBE %s" % ("OK -- nothing degraded silently" if not FAILURES else "FAILED"))
print("=" * 70)
raise SystemExit(1 if FAILURES else 0)
