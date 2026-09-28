"""R2 delivery invariant verifier -- READ ONLY.

Implements acceptance rule 4: assert RECOMPUTABILITY, never a recorded value.

Every check here recomputes a derived value from the bytes on disk and compares
it against what the artifact claims. Nothing is asserted against a hard-coded
hash, so the checks survive both rebuilds and content changes.

Invariants checked
  I1  index self-consistency : stored fingerprint == fingerprint(entries)
  I2  index freshness        : entry sha256 == sha256_dir(<dir>) recomputed
  I3  same for both kinds    : rulepacks/ and modules/
  I4  mirror byte-identity   : player-web/ <-> TRPG-Web客户端/client/
  I5  string-table parity    : the three client ends expose the same key set
  I6  miniprogram self-consistency : strings.js and strings.json agree on
       keys AND values (the package ships no tests/ to guard this itself)

Exit code 0 iff every invariant holds. Read-only: never writes anything.

Usage:
    python scripts/r2_verify_invariants.py [--json]
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
from pathlib import Path

# --- reference implementations, copied from app/repository/index.py ----------
# Kept identical on purpose: an independent check is only meaningful if it
# recomputes with the SAME documented algorithm from the raw bytes.


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dir_files(root: Path) -> list[Path]:
    out = [p for p in root.rglob("*") if p.is_file()]
    out.sort(key=lambda p: p.relative_to(root).as_posix())
    return out


def sha256_dir(root: Path) -> tuple[str, int, int]:
    h = hashlib.sha256()
    total = 0
    files = dir_files(root)
    for p in files:
        rel = p.relative_to(root).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\x00")
        h.update(sha256_file(p).encode("ascii"))
        h.update(b"\n")
        total += p.stat().st_size
    return h.hexdigest(), total, len(files)


def fingerprint(entries: list) -> str:
    canon = json.dumps(entries, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


# --- check harness ----------------------------------------------------------

RESULTS: list[dict] = []
OBSERVATIONS: dict = {}


def check(cid: str, name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append({"id": cid, "name": name, "ok": bool(ok), "detail": detail})


def kind_dir(server: Path, kind: str) -> Path:
    return server / ("rulepacks" if kind == "rulepacks" else "modules")


def check_index(server: Path, kind: str) -> None:
    root = kind_dir(server, kind)
    idx = root / "index.json"
    if not idx.is_file():
        check(kind + ".index", kind + " index.json present", False, "missing: %s" % idx)
        return

    data = load_json_checked(idx, kind + ".index_parses", kind + " index.json")
    if data is None:
        return
    entries = data.get("entries", [])

    # I1 -- self-consistency: the fingerprint must equal the hash of the entries
    # it claims to describe. Immune to rebuilds and to content changes.
    recomputed_fp = fingerprint(entries)
    stored_fp = data.get("fingerprint")
    check(kind + ".fingerprint_selfconsistent",
          kind + " fingerprint is self-consistent (stored == recomputed)",
          stored_fp == recomputed_fp,
          "stored=%s recomputed=%s" % (str(stored_fp)[:16], recomputed_fp[:16]))

    # I2 -- freshness: each entry's digest must match the directory on disk.
    # This is what detects silent staleness after someone edits content.
    stale = []
    for e in entries:
        eid = e.get("id")
        # G2 (tester): the directory on disk is named by `dir`; `id` comes from
        # the manifest and may legitimately differ. Prefer `dir` so a future
        # id/dir split cannot make this silently hash the wrong tree.
        d = root / str(e.get("dir") or eid)
        if not d.is_dir():
            stale.append("%s(dir-missing)" % eid)
            continue
        digest, size, nfiles = sha256_dir(d)
        if digest != e.get("sha256"):
            stale.append("%s(digest)" % eid)
        elif e.get("size") is not None and size != e.get("size"):
            stale.append("%s(size %s!=%s)" % (eid, e.get("size"), size))
    check(kind + ".fresh",
          kind + " index is fresh (every entry digest reproduces from disk)",
          not stale,
          "entries=%d stale=%s" % (len(entries), stale if stale else "none"))

    # G4a (tester) -- non-vacuity. An empty `entries` list makes I1 and I2 pass
    # trivially (fingerprint([]) is well defined and the freshness loop never
    # runs), so a wiped index would look green. Require at least one entry.
    check(kind + ".nonvacuous",
          kind + " index lists at least one entry (no vacuous pass)",
          len(entries) > 0,
          "entries=%d" % len(entries))

    # G4a (tester) -- the index's own summary counts must match its entries.
    dead = sum(1 for e in entries if e.get("deleted"))
    bad_counts = []
    if data.get("count") != len(entries):
        bad_counts.append("count=%s != len(entries)=%s"
                          % (data.get("count"), len(entries)))
    if data.get("deleted_count") != dead:
        bad_counts.append("deleted_count=%s != %s"
                          % (data.get("deleted_count"), dead))
    check(kind + ".counts_selfconsistent",
          kind + " index summary counts agree with its entries",
          not bad_counts,
          "entries=%d deleted=%d %s"
          % (len(entries), dead, "; ".join(bad_counts) if bad_counts else "ok"))

    # G4b (tester) -- teeth control. Mutate a deep copy and require the digest
    # to change. This proves the check above is not a constant that always
    # agrees; it is an in-memory control and never touches disk.
    tampered = copy.deepcopy(entries)
    if tampered:
        tampered[0]["sha256"] = "0" * 64
        check(kind + ".teeth",
              kind + " fingerprint check has teeth (tamper control differs)",
              fingerprint(tampered) != recomputed_fp,
              "untampered=%s tampered=%s"
              % (recomputed_fp[:16], fingerprint(tampered)[:16]))

    OBSERVATIONS[kind + "_fingerprint"] = stored_fp
    OBSERVATIONS[kind + "_count"] = len(entries)


def check_mirror(server: Path, pkg: Path) -> None:
    """I4 -- full-set mirror comparison (G3, tester).

    The first version compared a fixed six-name list, so a seventh file added
    on one side only would have gone unnoticed. Compare the complete
    relative-path sets of both trees, then byte-compare every common file.
    """
    a = server / "player-web"
    b = pkg / "TRPG-Web客户端" / "client"
    if not (a.is_dir() and b.is_dir()):
        check("mirror.dirs", "mirror directories present", False,
              "A=%s B=%s" % (a.is_dir(), b.is_dir()))
        return
    rel_a = {p.relative_to(a).as_posix() for p in a.rglob("*") if p.is_file()}
    rel_b = {p.relative_to(b).as_posix() for p in b.rglob("*") if p.is_file()}
    only_a = sorted(rel_a - rel_b)
    only_b = sorted(rel_b - rel_a)
    differing = sorted(r for r in (rel_a & rel_b)
                       if sha256_file(a / r) != sha256_file(b / r))
    check("mirror.byte_identical",
          "player-web/ <-> client/ are byte-identical (full set, %d files)"
          % len(rel_a),
          not only_a and not only_b and not differing,
          "A=%d B=%d only_in_A=%s only_in_B=%s differing=%s"
          % (len(rel_a), len(rel_b), only_a or "none", only_b or "none",
             differing or "none"))
    OBSERVATIONS["mirror_files"] = len(rel_a)


def load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def load_json_checked(p: Path, cid: str, what: str):
    """Parse JSON, degrading to a FAIL judgement instead of a traceback.

    tester hit this: a mutation wrote malformed JSON, the gate raised, and it
    exited rc=1 with a stack trace and NO verdict line. Both are "red", but in a
    report they mean opposite things -- "the gate found a defect" versus "the
    gate could not run". A gate must never crash without a verdict.
    """
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        check(cid, what + " parses as JSON", False,
              "%s: %s" % (type(e).__name__, str(e)[:140]))
        return None


def check_strings(server: Path, pkg: Path) -> None:
    a = server / "player-web" / "strings.json"
    b = pkg / "TRPG-Web客户端" / "client" / "strings.json"
    c = pkg / "TRPG-微信小程序客户端" / "strings.json"
    present = [(n, p) for n, p in (("player-web", a), ("client", b),
                                   ("miniprogram", c)) if p.is_file()]
    if len(present) < 3:
        check("strings.all_present", "all three string tables present", False,
              "found=%s" % [n for n, _ in present])
        return
    tables = {}
    for n, p in present:
        t = load_json_checked(p, "strings.parses", "%s strings.json" % n)
        if t is None:
            return
        tables[n] = t
    sets = {n: set(t) for n, t in tables.items()}
    union = set()
    for s in sets.values():
        union |= s
    missing = {n: sorted(union - s) for n, s in sets.items() if union - s}
    check("strings.key_parity",
          "the three client ends expose the same key set",
          not missing,
          "union=%d missing=%s" % (len(union), missing if missing else "none"))
    OBSERVATIONS["strings_union_keys"] = len(union)

    # H4 (fixed): key parity alone cannot see "same keys, different values".
    # Compare every shared value across each pair of ends.
    names = sorted(tables)
    drift = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            x, y = names[i], names[j]
            diff = sorted(k for k in set(tables[x]) & set(tables[y])
                          if tables[x][k] != tables[y][k])
            if diff:
                drift.append("%s!=%s:%s" % (x, y, diff))
    check("strings.value_parity",
          "the three client ends agree on every shared value",
          not drift,
          "pairs=%d falling_out=%s"
          % (len(names) * (len(names) - 1) // 2, drift if drift else "none"))

    # The miniprogram keeps a second hand-maintained copy in strings.js, guarded
    # by its own contract test. Report it, but do not fail the run on it here:
    # that end is owned by another workstream.
    js = pkg / "TRPG-微信小程序客户端" / "strings.js"
    if js.is_file():
        text = js.read_text(encoding="utf-8", errors="replace")
        absent = sorted(k for k in (union - sets["miniprogram"]) if k not in text)
        OBSERVATIONS["miniprogram_strings_js_missing"] = absent


# --- I6: miniprogram strings.js <-> strings.json -----------------------------
# strings.js line 5 claims "must be value-identical to strings.json --
# tests/contract.test.js asserts this". That guard is NOT in the delivery
# package (no tests/, no package.json, no node test env), so the claim is
# unenforced in the artifact. This is the equivalent assertion.

_JS_PAIR = re.compile(r'"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"')


def parse_js_strings(path: Path) -> tuple[dict, list]:
    """Parse a module.exports = { "k": "v", ... } table. Returns (pairs, dups)."""
    text = path.read_text(encoding="utf-8")
    # Start after the leading block comment so its prose cannot be read as data.
    idx = text.find("module.exports")
    body = text[idx:] if idx >= 0 else text
    out: dict = {}
    dups: list = []
    for m in _JS_PAIR.finditer(body):
        try:
            k = json.loads('"' + m.group(1) + '"')
            v = json.loads('"' + m.group(2) + '"')
        except ValueError:
            continue
        if k in out:
            dups.append(k)
        out[k] = v
    return out, dups


def check_miniprogram_strings(pkg: Path) -> None:
    mp = pkg / "TRPG-微信小程序客户端"
    js, jn = mp / "strings.js", mp / "strings.json"
    if not (js.is_file() and jn.is_file()):
        check("I6.files", "miniprogram strings.js + strings.json present", False,
              "js=%s json=%s" % (js.is_file(), jn.is_file()))
        return

    data = json.loads(jn.read_text(encoding="utf-8"))
    pairs, dups = parse_js_strings(js)

    # I6a -- same key set in both files
    only_json = sorted(set(data) - set(pairs))
    only_js = sorted(set(pairs) - set(data))
    check("I6.keys",
          "miniprogram strings.js and strings.json have the same key set",
          not only_json and not only_js,
          "json=%d js=%d only_json=%s only_js=%s"
          % (len(data), len(pairs), only_json or "none", only_js or "none"))

    # I6b -- same value for every shared key
    bad = [k for k in set(data) & set(pairs) if data[k] != pairs[k]]
    check("I6.values",
          "miniprogram strings.js and strings.json agree on every shared value",
          not bad,
          "shared=%d differing=%s" % (len(set(data) & set(pairs)), bad or "none"))

    # I6c -- no duplicate keys (a later literal would silently win)
    check("I6.no_duplicates", "miniprogram strings.js declares no duplicate keys",
          not dups, "duplicates=%s" % (dups or "none"))

    OBSERVATIONS["miniprogram_strings_js_keys"] = len(pairs)


def resolve_ref(base: Path, ref: str):
    if not ref:
        return None
    for c in (base / ref, base / Path(ref).name):
        if c.is_file():
            return c
    return None


def check_manifest(server: Path) -> None:
    """I16 (captain): a package must not lie about its own bytes.

    app/repository/pkg.py hashed the LF text BEFORE writing, so every newline
    became CRLF on disk and the recorded digest described bytes that never
    shipped -- that is DEFECT-004. The index checks above CANNOT see this: they
    recompute their digests FROM disk, so they stay green while the artifact
    fails its own self-check. That blind spot was H6.
    """
    manifests = sorted(set(list(server.glob("*/compiled/compiled.manifest.json"))
                           + list(server.glob("*/*/compiled/compiled.manifest.json"))
                           + list(server.glob("*/*/*/compiled/compiled.manifest.json"))))
    OBSERVATIONS["manifests_found"] = len(manifests)
    if not manifests:
        check("manifest.recorded_equals_shipped",
              "at least one compiled manifest exists (no vacuous pass)", False,
              "no */compiled/compiled.manifest.json under %s" % server.name)
        return
    for mf in manifests:
        rel = mf.relative_to(server).as_posix()
        try:
            j = json.loads(mf.read_text(encoding="utf-8"))
        except Exception as e:
            check("manifest.recorded_equals_shipped", rel + " parses", False,
                  "%s: %s" % (type(e).__name__, e))
            continue
        pairs = [("compiled_sha256", "compiled_ref"),
                 ("save_sha256", "save_ref"),
                 ("source_sha256", "source_ref")]
        checked_any = False
        for key, refkey in pairs:
            recorded = j.get(key)
            if not recorded:
                continue
            target = resolve_ref(mf.parent, j.get(refkey) or "")
            if target is None:
                target = resolve_ref(mf.parent.parent, j.get(refkey) or "")
            if target is None:
                check("manifest.recorded_equals_shipped",
                      "%s: %s resolves to a real file" % (rel, refkey), False,
                      "ref=%r not found" % (j.get(refkey),))
                checked_any = True
                continue
            checked_any = True
            raw = target.read_bytes()
            asis = sha256_file(target)
            lfonly = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
            ok = asis == recorded
            detail = ("%s recorded=%s as-is=%s lf-norm=%s crlf=%d"
                      % (rel, recorded[:16], asis[:16], lfonly[:16],
                         raw.count(b"\r\n")))
            if not ok and lfonly == recorded:
                detail += ("  <-- recorded digest is of the LF TEXT, not the"
                           " shipped bytes (write_text newline bug)")
            check("manifest.recorded_equals_shipped",
                  "%s: %s == sha256 of the shipped bytes" % (rel, key), ok, detail)
        if not checked_any:
            check("manifest.recorded_equals_shipped",
                  "%s declares no digest field to verify" % rel, False,
                  "keys=%s" % sorted(j))

def check_pack_lf(server: Path) -> None:
    """I17 (tester): no CRLF in modules/ + rulepacks/ -- DECLARED SCOPE.

    DEFECT-004 was exactly this. The index checks CANNOT see it when it lands
    in a TOP-LEVEL pack file (a sibling of index.json): they only hash *entry
    subdirectories*, so such a file stayed invisible while the gate printed
    17/17 PASS. tester demonstrated that with the two .tombstones.json files:
    blind spot H2 made concrete. By captain's own ruling -- the reason I16 was
    ordered into the gate -- such a gap belongs here, not in a separate script
    a reviewer may never run.

    SCOPE (captain ruling, R2): this invariant asserts ONLY that no file under
    modules/ + rulepacks/ contains CRLF. It is deliberately NOT a whole-package
    EOL policy check. Files elsewhere (e.g. app/*.py, web/src-manifest.txt) fall
    under .gitattributes policy and are tracked as a KNOWN P2 HYGIENE ITEM,
    not by this gate. Declaring the scope here removes the previous
    docstring/implementation mismatch (docstring said "anywhere a reader
    will open it"; the loop below only walks modules/ + rulepacks/).
    """
    offenders = []
    scanned = 0
    for kind in ("modules", "rulepacks"):
        base = server / kind
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file() or "__pycache__" in p.parts:
                continue
            scanned += 1
            try:
                raw = p.read_bytes()
            except Exception:
                continue
            if b"\r\n" in raw:
                offenders.append("%s (%dB, %d CRLF)"
                                  % (p.relative_to(server).as_posix(),
                                     len(raw), raw.count(b"\r\n")))
    OBSERVATIONS["pack_files_scanned"] = scanned
    check("pack.content_is_lf",
          "no CRLF in modules/ + rulepacks/ (including top-level files)",
          scanned > 0 and not offenders,
          "scanned=%d crlf_files=%s" % (scanned, offenders if offenders else "none"))

def main() -> int:
    # P3 (tester): on a cp936 console the --json payload was emitted in the
    # console codepage, so a UTF-8 consumer saw mojibake in non-ASCII paths.
    # Force UTF-8; ASCII-only judgments are unaffected either way.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    server = Path(__file__).resolve().parent.parent
    pkg = server.parent

    # Each check degrades to a judged FAIL on bad input (never a traceback), and
    # this net guarantees a verdict line even if one still escapes: a gate that
    # dies silently is worse than a gate that reports a failure.
    for fn, args in ((check_index, (server, "rulepacks")),
                     (check_index, (server, "modules")),
                     (check_mirror, (server, pkg)),
                     (check_strings, (server, pkg)),
                     (check_miniprogram_strings, (pkg,)),
                     (check_manifest, (server,)),
                     (check_pack_lf, (server,))):
        try:
            fn(*args)
        except Exception as e:
            check("%s.crashed" % getattr(fn, "__name__", "check"),
                  "check completed without raising", False,
                  "%s: %s" % (type(e).__name__, str(e)[:140]))

    failed = [r for r in RESULTS if not r["ok"]]
    payload = {
        "server_root": str(server),
        "package_root": str(pkg),
        "invariants": RESULTS,
        "observations": OBSERVATIONS,
        "invariants_passed": len(RESULTS) - len(failed),
        "invariants_total": len(RESULTS),
        "ok": not failed,
    }

    if "--json" in sys.argv:
        print(json.dumps(payload, ensure_ascii=False, indent=1))
    else:
        print("=" * 74)
        print("R2 DELIVERY INVARIANTS  (recomputed from disk -- no recorded values asserted)")
        print("=" * 74)
        for r in RESULTS:
            print("  [%s] %s" % ("PASS" if r["ok"] else "FAIL", r["name"]))
            if r["detail"]:
                print("         %s" % r["detail"])
        print("")
        print("  INVARIANTS: %d/%d passed" % (len(RESULTS) - len(failed), len(RESULTS)))
        print("")
        print("  TIME-POINT OBSERVATIONS (recorded, NOT asserted):")
        for k, v in OBSERVATIONS.items():
            print("    %-34s %s" % (k, v))
        print("")
        if failed:
            print("  RESULT: FAIL -- %d invariant(s) violated" % len(failed))
        else:
            print("  RESULT: OK -- all invariants hold")
        print("=" * 74)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
