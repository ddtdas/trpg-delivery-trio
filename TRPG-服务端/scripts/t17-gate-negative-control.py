
"""Negative control for r2_verify_invariants.py -- proves the gate has teeth.

Builds a synthetic package that satisfies every invariant, then applies one
mutation at a time and records which checks go red. A check that never fires
is a check that proves nothing.

Read-only w.r.t. the real delivery tree: everything happens in a temp dir.
"""
import importlib.util, json, shutil, subprocess, sys, tempfile
from pathlib import Path

if len(sys.argv) < 2:
    sys.stderr.write(
        "usage: python %s <path to r2_verify_invariants.py>\n"
        "\n"
        "Runs the gate against a synthetic package and applies one mutation at a\n"
        "time, reporting which checks go red. A check that never fires proves\n"
        "nothing, so this is the evidence that the gate has teeth.\n"
        "\n"
        "Read-only w.r.t. the real delivery tree: everything happens under a\n"
        "tempfile.mkdtemp() directory.\n"
        "\n"
        "Example:\n"
        "  python scripts/t17-gate-negative-control.py \\\n"
        "         scripts/r2_verify_invariants.py\n"
        % Path(sys.argv[0]).name)
    raise SystemExit(2)

VERIFIER = Path(sys.argv[1]).resolve()
if not VERIFIER.is_file():
    sys.stderr.write("error: no such verifier: %s\n" % VERIFIER)
    raise SystemExit(2)
SIX = ("app.js", "app.css", "tokens.json", "strings.json", "index.html", "README.md")


def load_verifier():
    spec = importlib.util.spec_from_file_location("ver", VERIFIER)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def build(root: Path, ver):
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copy2(VERIFIER, root / "scripts" / "r2_verify_invariants.py")

    for kind, ids in (("rulepacks", ["rp1"]), ("modules", ["m1"])):
        entries = []
        for i in ids:
            d = root / kind / i
            d.mkdir(parents=True, exist_ok=True)
            fname = "rulepack.yaml" if kind == "rulepacks" else "module.yaml"
            (d / fname).write_bytes(("id: %s\n" % i).encode("utf-8"))
            if kind == "modules":
                # I16 fixture: a manifest that HONESTLY describes shipped bytes.
                comp = d / "compiled"
                comp.mkdir(parents=True, exist_ok=True)
                art = comp / ("%s.compiled.json" % i)
                # MUST contain newlines: the DEFECT-004 mutation converts LF->CRLF,
                # and on a newline-free payload that replace() is a silent no-op
                # (caught by the negative control reporting "NOTHING FIRED").
                art.write_bytes(("{\n  \"id\": \"%s\"\n}\n" % i).encode("utf-8"))
                (comp / "compiled.manifest.json").write_bytes(json.dumps({
                    "schema": 1, "module_id": i,
                    "compiled_ref": "compiled/%s.compiled.json" % i,
                    "compiled_sha256": ver.sha256_file(art),
                }, ensure_ascii=False).encode("utf-8"))
            dg, size, nf = ver.sha256_dir(d)
            entries.append({"id": i, "dir": i, "name": i, "deleted": False,
                            "path": "%s/%s" % (kind, i), "sha256": dg,
                            "size": size, "files": nf, "ruleset": i,
                            "schema_version": "2.0.0", "version": "2.0.0"})
        idx = {"kind": kind, "schema": 2, "count": len(entries),
               "deleted_count": 0, "entries": entries,
               "fingerprint": ver.fingerprint(entries),
               "generated_at": "2026-01-01T00:00:00+00:00", "root": kind}
        (root / kind / "index.json").write_text(
            json.dumps(idx, ensure_ascii=False), encoding="utf-8")

    strings = json.dumps({"a": "1", "b": "2"}, ensure_ascii=False)
    # The verifier derives pkg = server.parent, so mirror the real nesting:
    # <tmp>/TRPG-服务端/  and  <tmp>/TRPG-Web客户端/, <tmp>/TRPG-微信小程序客户端/
    a = root / "player-web"
    b = root.parent / "TRPG-Web客户端" / "client"
    mp = root.parent / "TRPG-微信小程序客户端"
    for d in (a, b, mp):
        d.mkdir(parents=True, exist_ok=True)
    for n in SIX:
        payload = strings if n == "strings.json" else ("x" * 10)
        (a / n).write_bytes(payload.encode("utf-8"))
        (b / n).write_bytes(payload.encode("utf-8"))
    (mp / "strings.json").write_bytes(strings.encode("utf-8"))
    (mp / "strings.js").write_bytes(
        ("module.exports = {\n  \"a\": \"1\",\n  \"b\": \"2\"\n};\n").encode("utf-8"))


def run(root: Path):
    p = subprocess.run([sys.executable,
                        str(root / "scripts" / "r2_verify_invariants.py"), "--json"],
                       capture_output=True, text=True, encoding="utf-8")
    try:
        return json.loads(p.stdout), p.returncode
    except Exception:
        return {"invariants": [], "ok": None, "raw": p.stdout[:300]}, p.returncode


def failed_ids(payload):
    return sorted(r["id"] for r in payload.get("invariants", []) if not r["ok"])


MUTATIONS = []


def mutation(name):
    def deco(fn):
        MUTATIONS.append((name, fn))
        return fn
    return deco


@mutation("wipe rulepacks entries -> []")
def _(root):
    p = root / "rulepacks" / "index.json"
    j = json.loads(p.read_text(encoding="utf-8"))
    j["entries"] = []
    j["count"] = 0
    p.write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")


@mutation("corrupt count")
def _(root):
    p = root / "rulepacks" / "index.json"
    j = json.loads(p.read_text(encoding="utf-8"))
    j["count"] = 99
    p.write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")


@mutation("edit pack file (stale digest)")
def _(root):
    (root / "rulepacks" / "rp1" / "rulepack.yaml").write_bytes(b"id: rp1\nextra: 1\n")


@mutation("tamper stored fingerprint")
def _(root):
    p = root / "rulepacks" / "index.json"
    j = json.loads(p.read_text(encoding="utf-8"))
    j["fingerprint"] = "0" * 64
    p.write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")


@mutation("add 7th file to player-web only")
def _(root):
    (root / "player-web" / "extra.js").write_bytes(b"x")


@mutation("drop a key from miniprogram strings.json")
def _(root):
    p = root.parent / "TRPG-微信小程序客户端" / "strings.json"
    p.write_text(json.dumps({"a": "1"}, ensure_ascii=False), encoding="utf-8")


@mutation("change a value in strings.js")
def _(root):
    p = root.parent / "TRPG-微信小程序客户端" / "strings.js"
    p.write_text('module.exports = {\n  "a": "CHANGED",\n  "b": "2"\n};\n',
                 encoding="utf-8")


@mutation("cross-end VALUE drift (keys unchanged)")
def _(root):
    # keys stay identical, only a value differs -> only value_parity can see it
    p = root.parent / "TRPG-微信小程序客户端" / "strings.json"
    j = json.loads(p.read_text(encoding="utf-8"))
    j["a"] = "DIFFERENT"
    p.write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")


@mutation("tamper compiled_sha256 in manifest (I16)")
def _(root):
    p = root / "modules" / "m1" / "compiled" / "compiled.manifest.json"
    j = json.loads(p.read_text(encoding="utf-8"))
    j["compiled_sha256"] = "0" * 64
    p.write_bytes(json.dumps(j, ensure_ascii=False).encode("utf-8"))


@mutation("manifest records LF digest but the file ships CRLF (DEFECT-004 shape)")
def _(root):
    # Exactly how DEFECT-004 arose: the digest was computed over LF text, then the
    # write turned every \n into \r\n, so the recorded value describes bytes that
    # never shipped. The index checks stay green; only I16 can see this.
    art = root / "modules" / "m1" / "compiled" / "m1.compiled.json"
    art.write_bytes(art.read_bytes().replace(b"\n", b"\r\n"))


@mutation("malformed JSON in rulepacks index (must judge, not crash)")
def _(root):
    # tester's finding: this used to raise, exit rc=1 with a stack trace and NO
    # verdict line -- indistinguishable from a real judgement failure in a report.
    (root / "rulepacks" / "index.json").write_text("{not json", encoding="utf-8")


@mutation("malformed JSON in player-web strings.json (must judge, not crash)")
def _(root):
    (root / "player-web" / "strings.json").write_text("[[[", encoding="utf-8")


@mutation("duplicate key in strings.js")
def _(root):
    p = root.parent / "TRPG-微信小程序客户端" / "strings.js"
    p.write_text('module.exports = {\n  "a": "1",\n  "a": "1",\n  "b": "2"\n};\n',
                 encoding="utf-8")


@mutation("CRLF in a TOP-LEVEL pack file (invisible to the index checks)")
def _(root):
    # tester's H2 instance: a sibling of index.json is inside no indexed entry,
    # so dir-digest checking never looks at it.
    (root / "modules" / ".tombstones.json").write_bytes(
        b'{\r\n  "entries": {},\r\n  "schema": "RepoTombstones v1"\r\n}')


def main():
    ver = load_verifier()
    tmp = Path(tempfile.mkdtemp(prefix="gate_neg_"))
    root = tmp / "TRPG-服务端"
    root.mkdir(parents=True)
    build(root, ver)

    payload, rc = run(root)
    print("BASELINE (valid synthetic package)")
    print("  failed = %s   exit = %d" % (failed_ids(payload) or "none", rc))
    print("  total invariants = %d" % len(payload.get("invariants", [])))
    baseline_ok = not failed_ids(payload) and rc == 0
    print("  BASELINE_OK = %s" % baseline_ok)
    print("")

    # Snapshot the WHOLE temp tree. Mutations that touch the client/miniprogram
    # dirs live in root.parent, so restoring only `root` would leak state from
    # one mutation into the next and silently contaminate the results.
    snap = Path(tempfile.mkdtemp(prefix="gate_snap_"))
    shutil.rmtree(snap, ignore_errors=True)
    shutil.copytree(tmp, snap)

    print("%-42s %s" % ("MUTATION", "CHECKS THAT WENT RED"))
    print("-" * 88)
    all_teeth = True
    for name, fn in MUTATIONS:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.copytree(snap, tmp)
        fn(root)
        payload, rc = run(root)
        ids = failed_ids(payload)
        if not ids:
            all_teeth = False
        print("%-42s %s" % (name, ", ".join(ids) if ids else "*** NOTHING FIRED ***"))
    print("-" * 88)
    print("EVERY_MUTATION_CAUGHT = %s" % all_teeth)
    print("BASELINE_OK = %s" % baseline_ok)
    print("VERDICT = %s" % ("GATE HAS TEETH" if (all_teeth and baseline_ok)
                            else "GATE IS BLIND SOMEWHERE"))
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(snap, ignore_errors=True)


main()
