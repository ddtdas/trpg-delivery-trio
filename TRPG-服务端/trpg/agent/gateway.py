"""Execution gateway — allowlist enforcement + audit (DESIGN §2.6, W-C3).

Driven by ``trpg/agent/allowlist.yml`` (frozen v1): every operation first
consults the table — ALLOW passes with an audit row, DENY refuses with an
audit trace. Denial messages are redacted (never echo secrets or key paths).

Frozen-contract note: this module only *reads* allowlist.yml / events /
registry contracts; it changes no frozen signatures.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

ALLOWLIST_FILE = Path(__file__).resolve().parent / "allowlist.yml"

# Frozen id sets — mirror allowlist.yml v1 (DESIGN §2.6). Kept as a closed
# fallback; the live table is loaded from the yml file.
ALLOW_IDS: frozenset[str] = frozenset({
    "health_check",
    "log_collect",
    "service_control",
    "file_rw",
    "run_sim",
})
DENY_IDS: frozenset[str] = frozenset({
    "read_secrets",
    "edit_llm_config",
    "write_outside_sysdrive",
    "schedtask_registry",
    "egress",
    "priv_esc_raw_ps",
})

# -- operation functions -------------------------------------------------
HEALTH_TARGETS: frozenset[str] = frozenset({
    "http://127.0.0.1:9210/health",
    "/app",
})
SERVICE_COMMANDS: dict[str, str] = {
    "start": "start.bat",
    "stop": "stop.bat",
}
SANDBOX_DIRS: tuple[str, ...] = ("data", "var", "modules")
LOG_DIR_NAME = "var"
LOG_SUFFIX = ".log"
SIM_DIR_NAME = "scripts/sim"
_SECRET_NAME_RE = re.compile(r"(key|secret|token)", re.IGNORECASE)
_SECRET_VALUE_RE = re.compile(r"sk-[A-Za-z0-9\-_]+")
_ABS_WIN_PATH_RE = re.compile(r"[A-Za-z]:\\[^\s\"']*")
_ARG_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_\-=.]*\Z")
_SIM_BASE_RE = re.compile(r"[A-Za-z0-9_]+\Z")
_MAX_SIM_ARGS = 20
_MAX_LOG_LINES = 500


class DeniedError(PermissionError):
    """Raised when the allowlist denies an operation (message is redacted)."""


class GatewayConfigError(RuntimeError):
    """Raised when allowlist.yml cannot be loaded/validated."""


def redact(text: str) -> str:
    """Scrub secrets and key paths from a message/audit detail string."""
    s = _SECRET_VALUE_RE.sub("<set>", text)
    s = _ABS_WIN_PATH_RE.sub(
        lambda m: "<redacted-path>" if _SECRET_NAME_RE.search(m.group(0))
        else m.group(0), s)
    # KEY=/SECRET=/TOKEN= assignments: mask the value, keep the name.
    s = re.sub(r"(?i)\b(api[_-]?key|secret|token)\b\s*[:=]\s*\S+",
               r"\1=<redacted>", s)
    return s


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AllowTable:
    """Parsed allow/deny table from allowlist.yml."""

    allow: dict[str, dict[str, Any]] = field(default_factory=dict)
    deny: dict[str, dict[str, Any]] = field(default_factory=dict)
    version: Any = None

    @classmethod
    def load(cls, path: str | os.PathLike[str] = ALLOWLIST_FILE) -> "AllowTable":
        p = Path(path)
        if not p.is_file():
            raise GatewayConfigError(f"allowlist file missing: {p.name}")
        if yaml is None:
            raise GatewayConfigError("pyyaml unavailable; cannot load allowlist")
        try:
            doc = yaml.safe_load(p.read_text(encoding="utf-8"))
        except Exception as exc:
            raise GatewayConfigError(f"allowlist file unparseable: {p.name}") from exc
        if not isinstance(doc, dict):
            raise GatewayConfigError("allowlist root must be a mapping")
        allow, deny = {}, {}
        for key, store in (("allow", allow), ("deny", deny)):
            rows = doc.get(key, [])
            if not isinstance(rows, list):
                raise GatewayConfigError(f"allowlist[{key}] must be a list")
            for row in rows:
                if not isinstance(row, dict) or not row.get("id"):
                    raise GatewayConfigError(
                        f"allowlist[{key}] row needs a non-empty id")
                store[str(row["id"])] = dict(row)
        missing_allow = set(ALLOW_IDS) - set(allow)
        missing_deny = set(DENY_IDS) - set(deny)
        if missing_allow or missing_deny:
            raise GatewayConfigError(
                "allowlist ids drift from frozen v1: "
                f"allow_missing={sorted(missing_allow)} "
                f"deny_missing={sorted(missing_deny)}")
        return cls(allow=allow, deny=deny, version=doc.get("version"))


class ExecGateway:
    """Allowlist-driven execution gateway with an audit trail.

    ``root`` is the repo sandbox root (``trpg/data|var|modules`` live under
    it). Every op method validates its own parameter whitelist (defense in
    depth); :meth:`request` adds the allow/deny table lookup plus audit.
    """

    def __init__(self, root: str | os.PathLike[str] | None = None,
                 allowlist: str | os.PathLike[str] = ALLOWLIST_FILE) -> None:
        if root is None:
            # trpg/agent/gateway.py -> parents: agent, trpg, repo-root
            root = Path(__file__).resolve().parent.parent.parent
        self._root = Path(root).resolve()
        self._table = AllowTable.load(allowlist)
        self._audit: list[dict[str, Any]] = []
        self._seq = 0

    # -- audit -----------------------------------------------------------
    @property
    def audit_log(self) -> list[dict[str, Any]]:
        """Copy of the audit trail (allow + deny rows)."""
        return [dict(r) for r in self._audit]

    def audit_decisions(self, decision: str) -> list[dict[str, Any]]:
        """Filter audit rows by decision ('allow' | 'deny')."""
        return [r for r in self.audit_log if r.get("decision") == decision]

    def _record(self, op: str, decision: str, rule: str, detail: str) -> dict:
        self._seq += 1
        row = {"seq": self._seq, "ts": _utcnow(), "op": op,
               "decision": decision, "rule": rule,
               "detail": redact(detail)}
        self._audit.append(row)
        return dict(row)

    def _deny(self, op: str, rule: str, reason: str) -> DeniedError:
        # Never echo caller input: only the rule id + generic reason.
        self._record(op, "deny", rule, f"denied by rule {rule}: {reason}")
        return DeniedError(f"denied by rule {rule}: {reason}")

    # -- ALLOW op 1: health check ----------------------------------------
    def health_check(self, target: str = "http://127.0.0.1:9210/health") -> dict:
        """Validate a health-check target (GET only, no side effects).

        Allowed: ``GET http://127.0.0.1:9210/health`` and ``GET /app``.
        Anything else (other hosts/URLs = egress) is denied.
        """
        op = "health_check"
        if not isinstance(target, str) or target not in HEALTH_TARGETS:
            raise self._deny(op, "egress", "target not in health whitelist")
        self._record(op, "allow", "health_check",
                     f"GET {target} validated (no probe executed)")
        return {"allowed": True, "method": "GET", "target": target}

    # -- ALLOW op 2: log tail --------------------------------------------
    def log_tail(self, name: str, lines: int = 50) -> dict:
        """Tail a ``trpg/var/*.log`` file (read-only, key files excluded)."""
        op = "log_collect"
        if (not isinstance(name, str) or "/" in name or "\\" in name
                or not name.endswith(LOG_SUFFIX) or not name[: -len(LOG_SUFFIX)]
                or _SECRET_NAME_RE.search(name)):
            raise self._deny(op, "read_secrets",
                             "log name not in var/*.log whitelist")
        if not isinstance(lines, int) or isinstance(lines, bool) \
                or not (1 <= lines <= _MAX_LOG_LINES):
            raise self._deny(op, "log_collect",
                             "lines out of range 1..500")
        path = (self._root / LOG_DIR_NAME / name).resolve()
        if path.parent != (self._root / LOG_DIR_NAME).resolve():
            raise self._deny(op, "write_outside_sysdrive",
                             "log path escapes sandbox")
        content: list[str] = []
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                raise self._deny(op, "log_collect", "log unreadable") from None
            content = text.splitlines()[-lines:]
        self._record(op, "allow", "log_collect",
                     f"tail var/{name} last {lines} lines")
        return {"allowed": True, "file": f"var/{name}", "lines": content}

    # -- ALLOW op 3: service start/stop ----------------------------------
    def service_control(self, action: str) -> dict:
        """Return the exact whitelisted service command (never executes here).

        Only ``start`` -> ``start.bat`` and ``stop`` -> ``stop.bat``.
        Raw/parameterized commands are denied (must use this wrapper).
        """
        op = "service_control"
        if not isinstance(action, str) or action not in SERVICE_COMMANDS:
            raise self._deny(op, "priv_esc_raw_ps",
                             "only exact start/stop actions allowed")
        cmd = SERVICE_COMMANDS[action]
        self._record(op, "allow", "service_control",
                     f"action {action} -> {cmd} (not executed by gateway)")
        return {"allowed": True, "action": action, "command": cmd,
                "executed": False}

    # -- ALLOW op 4: sandbox file read/write ------------------------------
    def _sandbox_path(self, rel: str) -> Path:
        if not isinstance(rel, str) or not rel.strip():
            raise self._deny("file_rw", "file_rw", "empty path")
        norm = rel.replace("\\", "/").strip()
        if norm.startswith("/") or ".." in norm.split("/") \
                or re.match(r"(?i)^[a-z]:", norm):
            raise self._deny("file_rw", "write_outside_sysdrive",
                             "absolute or escaping path")
        parts = norm.split("/")
        if parts[0] not in SANDBOX_DIRS:
            if parts[0] == "configs" or _SECRET_NAME_RE.search(norm):
                raise self._deny("file_rw", "read_secrets",
                                 "secret/config path blocked")
            raise self._deny("file_rw", "write_outside_sysdrive",
                             "path outside data/var/modules sandbox")
        if _SECRET_NAME_RE.search(parts[-1]):
            raise self._deny("file_rw", "read_secrets",
                             "secret-like filename blocked")
        full = (self._root / Path(*parts)).resolve()
        sandbox_roots = [(self._root / d).resolve() for d in SANDBOX_DIRS]
        if not any(full == r or r in full.parents for r in sandbox_roots):
            raise self._deny("file_rw", "write_outside_sysdrive",
                             "resolved path escapes sandbox")
        if os.name == "nt" and full.drive.lower() != self._root.drive.lower():
            raise self._deny("file_rw", "write_outside_sysdrive",
                             "cross-drive write blocked")
        return full

    def file_read(self, path: str) -> dict:
        """Read a sandbox file (data/var/modules; key/config paths denied)."""
        op = "file_rw"
        full = self._sandbox_path(path)
        if not full.is_file():
            raise self._deny(op, "file_rw", "target is not a readable file")
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            raise self._deny(op, "file_rw", "target unreadable") from None
        rel = full.relative_to(self._root).as_posix()
        self._record(op, "allow", "file_rw", f"read {rel}")
        return {"allowed": True, "path": rel, "content": text}

    def file_write(self, path: str, content: str) -> dict:
        """Write a sandbox file (audit row is recorded *before* writing)."""
        op = "file_rw"
        if not isinstance(content, str):
            raise self._deny(op, "file_rw", "content must be text")
        full = self._sandbox_path(path)
        rel = full.relative_to(self._root).as_posix()
        # Write ops are audited before they take effect (DESIGN §2.6).
        self._record(op, "allow", "file_rw",
                     f"write {rel} bytes={len(content)} (pre-write audit)")
        try:
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")
        except OSError:
            raise self._deny(op, "file_rw", "target unwritable") from None
        return {"allowed": True, "path": rel, "bytes": len(content)}

    # -- ALLOW op 5: sim runner (dry-run plan) -----------------------------
    def run_sim(self, script: str, args: list[str] | tuple[str, ...] = ()) -> dict:
        """Validate a sim invocation; returns the exact argv (never executes).

        Script must live under ``scripts/sim/`` with a safe basename;
        args must pass the parameter whitelist (no shell metachars).
        """
        op = "run_sim"
        if not isinstance(script, str):
            raise self._deny(op, "run_sim", "script must be text")
        norm = script.replace("\\", "/").strip()
        segs = norm.split("/")
        base = segs[-1]
        stem, dot, ext = base.partition(".")
        if not (dot and ext in ("py", "yaml") and _SIM_BASE_RE.fullmatch(stem)):
            raise self._deny(op, "run_sim", "script name not whitelisted")
        if not (len(segs) >= 2 and segs[-2] == "sim" and "scripts" in segs):
            raise self._deny(op, "run_sim", "script outside scripts/sim")
        if ".." in segs or _SECRET_NAME_RE.search(base):
            raise self._deny(op, "read_secrets",
                             "secret-like sim script blocked")
        if not isinstance(args, (list, tuple)) or len(args) > _MAX_SIM_ARGS:
            raise self._deny(op, "run_sim", "arg list invalid or too long")
        for a in args:
            if not isinstance(a, str) or not _ARG_RE.fullmatch(a):
                raise self._deny(op, "run_sim",
                                 "sim arg not in parameter whitelist")
        argv = [f"scripts/sim/{base}", *list(args)]
        self._record(op, "allow", "run_sim",
                     f"sim plan {' '.join(argv)} (not executed by gateway)")
        return {"allowed": True, "argv": argv, "executed": False}

    # -- dispatcher: table lookup first ------------------------------------
    def request(self, op: str, **params: Any) -> dict:
        """Dispatch one operation through the allow/deny table.

        ALLOW ids route to the op function; DENY ids (or unknown ops, the
        default-deny) refuse with an audit trace.
        """
        if not isinstance(op, str) or not op:
            self._record("unknown", "deny", "default_deny", "empty op refused")
            raise DeniedError("denied by rule default_deny: empty op")
        if op in self._table.deny or op in DENY_IDS:
            rule = op if op in self._table.deny else "default_deny"
            self._record(op, "deny", rule,
                         f"deny-table hit for {rule} (params redacted)")
            raise DeniedError(f"denied by rule {rule}: deny-table hit")
        if op in self._table.allow or op in ALLOW_IDS:
            try:
                if op == "health_check":
                    return self.health_check(params.get(
                        "target", "http://127.0.0.1:9210/health"))
                if op == "log_collect":
                    return self.log_tail(params.get("name", ""),
                                         params.get("lines", 50))
                if op == "service_control":
                    return self.service_control(params.get("action", ""))
                if op == "file_rw":
                    if params.get("action", "read") == "write":
                        return self.file_write(params.get("path", ""),
                                               params.get("content", ""))
                    return self.file_read(params.get("path", ""))
                if op == "run_sim":
                    return self.run_sim(params.get("script", ""),
                                        params.get("args", []))
            except DeniedError:
                raise
            except Exception as exc:  # fail closed on unexpected errors
                raise self._deny(op, "default_deny",
                                 "op failed closed") from exc
        self._record(op, "deny", "default_deny", "unknown op refused")
        raise DeniedError("denied by rule default_deny: unknown op")
