
"""R2 manifest self-consistency verifier -- READ ONLY.

Closes the blind spot the invariant gate cannot see (H6, found via DEFECT-004):
app/repository/pkg.py hashes the LF text BEFORE writing, then the write turns
every \n into \r\n, so the digest recorded in compiled.manifest.json describes
bytes that never reached disk. A consumer that recomputes the digest over the
file as shipped gets a mismatch.

The invariant gate recomputes DIRECTORY digests from disk, so it stays green
even when this is broken -- which is exactly how DEFECT-004 slipped past it.
Kept as a SEPARATE script on purpose: it is additive and does not change the
already-accepted gate artifact.

Exit code 0 iff every referenced digest matches the file as shipped.

Usage:
    python scripts/r2_verify_manifest.py [--json]
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append({"id": name, "ok": bool(ok), "detail": detail})


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def resolve(module_dir: Path, manifest_dir: Path, ref: str):
    """Resolve a manifest ref to a real file, trying the usual locations."""
    if not ref:
        return None
    cands = [module_dir / ref, manifest_dir / ref, module_dir / Path(ref).name,
             manifest_dir / Path(ref).name]
    for c in cands:
        if c.is_file():
            return c
    return None


def check_module(module_dir: Path) -> None:
    mids = module_dir.name
    manifests = sorted(module_dir.rglob("compiled.manifest.json"))
    if not manifests:
        return
    for mf in manifests:
        try:
            j = json.loads(mf.read_text(encoding="utf-8"))
        except Exception as e:
            check("%s.manifest_parse" % mids, False, "%s: %s" % (mf, e))
            continue
        for key, refkey in (("compiled_sha256", "compiled_ref"),
                            ("save_sha256", "save_ref"),
                            ("source_sha256", "source_ref")):
            recorded = j.get(key)
            if not recorded:
                continue
            target = resolve(module_dir, mf.parent, j.get(refkey) or "")
            if target is None:
                check("%s.%s" % (mids, key), False,
                      "ref %r not resolvable from %s" % (j.get(refkey), mf.parent))
                continue
            raw = target.read_bytes()
            asis = sha256_bytes(raw)
            lfonly = sha256_bytes(raw.replace(b"\r\n", b"\n"))
            crlf = raw.count(b"\r\n")
            # The assertion that matters: the digest must describe the SHIPPED bytes.
            detail = ("file=%s recorded=%s as-is=%s lf-norm=%s crlf=%d"
                      % (target.relative_to(module_dir).as_posix(),
                         recorded[:16], asis[:16], lfonly[:16], crlf))
            if asis == recorded:
                check("%s.%s" % (mids, key), True, detail)
            elif lfonly == recorded:
                check("%s.%s" % (mids, key), False,
                      detail + "  <-- recorded digest is of the LF TEXT, "
                               "not the shipped bytes (write_text newline bug)")
            else:
                check("%s.%s" % (mids, key), False, detail + "  <-- neither matches")


def check_crlf(server: Path) -> None:
    bad = []
    for kind in ("modules", "rulepacks"):
        root = server / kind
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if p.is_file() and b"\r" in p.read_bytes():
                bad.append(p.relative_to(server).as_posix())
    check("pack.content_is_lf", not bad,
          "no CRLF in module/rulepack content; crlf_files=%s"
          % (bad if bad else "none"))


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    server = Path(__file__).resolve().parent.parent

    mods = server / "modules"
    if mods.is_dir():
        for d in sorted(p for p in mods.iterdir() if p.is_dir()):
            check_module(d)
    check_crlf(server)

    failed = [r for r in RESULTS if not r["ok"]]
    payload = {"invariants": RESULTS,
               "passed": len(RESULTS) - len(failed), "total": len(RESULTS),
               "ok": not failed}
    if "--json" in sys.argv:
        print(json.dumps(payload, ensure_ascii=False, indent=1))
    else:
        print("=" * 74)
        print("R2 MANIFEST SELF-CONSISTENCY  (digest vs shipped bytes)")
        print("=" * 74)
        for r in RESULTS:
            print("  [%s] %s" % ("PASS" if r["ok"] else "FAIL", r["id"]))
            if r["detail"]:
                print("         %s" % r["detail"])
        print("")
        print("  CHECKS: %d/%d passed" % (len(RESULTS) - len(failed), len(RESULTS)))
        print("  RESULT: %s" % ("OK" if not failed else "FAIL (%d)" % len(failed)))
        print("=" * 74)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
