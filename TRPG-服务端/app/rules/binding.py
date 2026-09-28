"""TRPG ruleset auto-binding (MIT, additive layer) -- R23.

A module manifest declares its ruleset (modules/<id>/module.yaml carries
"ruleset: coc7"). Until this round nothing read that field: a table opened
with ruleset "dnd5e" was indistinguishable from one opened with "coc7",
and a typo silently fell back to the CoC7 kernel.

This module closes both halves of R23:

* auto-binding -- the manifest's ruleset string is resolved against the
  rulepacks/ repository and the resulting rulepack is bound to the table,
* explicit failure -- an unknown ruleset raises RulesetBindingError with
  code RULEPACK_UNKNOWN_RULESET, listing what IS available. There is no
  fallback path: the caller either gets a bound rulepack or an error.

Aliases (dnd -> dnd5e) are declared in app.rules.rulepack_schema and are
echoed back in the binding result, so a shorthand is never a silent
substitution.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any, Mapping

import yaml

from app.rules import resolver as resolver_mod
from app.rules.rulepack_schema import (
    PACKAGED_RULESETS,
    PLANNED_RULESETS,
    RULESET_ALIASES,
    RULESET_CATALOG,
    SCHEMA_VERSION,
    RulepackSchemaError,
    validate_rulepack_v2,
)

__all__ = [
    "RulesetBindingError",
    "RulepackEntry",
    "RulepackRepository",
    "default_repository",
    "bind_manifest",
    "open_table",
]

# --------------------------------------------------------------------------
# Error codes -- R13's table (app/repository/errors.py) is the SINGLE source
# of truth. This module keeps finer-grained INTERNAL codes for diagnostics
# and maps them onto that table, so a caller only ever routes on one system.
# --------------------------------------------------------------------------
ERR_UNKNOWN_RULESET = "RULEPACK_UNKNOWN_RULESET"            # internal
ERR_INVALID = "RULEPACK_INVALID"                            # internal
ERR_MANIFEST_INVALID = "RULEPACK_MANIFEST_INVALID"          # internal
ERR_NO_RULESET_DECLARED = "RULEPACK_NO_RULESET_DECLARED"    # internal
ERR_SCHEMA_UNSUPPORTED = "RULEPACK_SCHEMA_UNSUPPORTED"      # internal

try:
    from app.repository.errors import ERROR_TABLE as _R13_TABLE
except Exception:  # noqa: BLE001 -- the rules layer stays usable standalone
    _R13_TABLE = {}

#: internal code -> R13 code (for the cases where origin does not matter)
_INTERNAL_TO_R13 = {
    ERR_INVALID: "RULEPACK_MANIFEST_INVALID",
    ERR_MANIFEST_INVALID: "MODULE_MANIFEST_INVALID",
    ERR_NO_RULESET_DECLARED: "MODULE_RULESET_MISSING",
    ERR_SCHEMA_UNSUPPORTED: "RULEPACK_VERSION_INCOMPATIBLE",
}


def r13_code(internal: str, origin: str = "direct") -> str:
    """Map an internal binding code onto the R13 table.

    An unknown ruleset reached through a module manifest is
    MODULE_RULESET_UNKNOWN (R13 owns that judgement); the same miss asked
    for directly is RULEPACK_ENTRY_NOT_FOUND. Both are client errors.
    """
    if internal == ERR_UNKNOWN_RULESET:
        return "MODULE_RULESET_UNKNOWN" if origin == "manifest" else "RULEPACK_ENTRY_NOT_FOUND"
    return _INTERNAL_TO_R13.get(internal, internal)


def r13_status(code: str, fallback: int = 422) -> int:
    """HTTP status declared by the R13 table for this code."""
    entry = _R13_TABLE.get(code)
    return entry[0] if entry else fallback


class RulesetBindingError(ValueError):
    """Raised when a manifest's ruleset cannot be bound to a rulepack.

    Never raised for a *valid* ruleset: the repository either returns a
    bound rulepack or this error. The code attribute is the R13 table code;
    internal_code keeps the finer-grained reason for diagnostics.
    """

    def __init__(
        self,
        code: str,
        message: str,
        ruleset: str | None = None,
        available: tuple[str, ...] = (),
        detail: Mapping[str, Any] | None = None,
        origin: str = "direct",
    ) -> None:
        self.internal_code = code
        self.code = r13_code(code, origin)
        self.http_status = r13_status(self.code)
        self.origin = origin
        self.ruleset = ruleset
        self.available = tuple(available)
        self.detail = {**dict(detail or {}), "rulepack_code": code}
        super().__init__("[%s] %s" % (self.code, message))

    def to_dict(self) -> dict:
        return {
            "ok": False,
            "error_code": self.code,
            "code": self.code,
            "internal_code": self.internal_code,
            "http_status": self.http_status,
            "ruleset": self.ruleset,
            "message": str(self),
            "available_rulesets": list(self.available),
            "planned_rulesets": list(PLANNED_RULESETS),
            "detail": self.detail,
        }


class RulepackEntry(dict):
    """One indexed rulepack (dict subclass so it JSON-serializes directly)."""


class RulepackRepository:
    """Read-only view over a rulepacks/ directory.

    Layout: rulepacks/<ruleset_id>/rulepack.yaml. Scanning is cheap and
    idempotent; loaded rulepacks are cached per instance so a request path
    does not re-parse YAML.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self._loaded: dict[str, dict] = {}
        self._entries: dict[str, RulepackEntry] | None = None

    # -- scanning ---------------------------------------------------------
    def scan(self) -> dict[str, RulepackEntry]:
        """Index every rulepacks/*/rulepack.yaml. Never raises on bad files."""
        entries: dict[str, RulepackEntry] = {}
        if not self.root.is_dir():
            self._entries = entries
            return entries
        for child in sorted(self.root.iterdir()):
            if not child.is_dir():
                continue
            yaml_path = child / "rulepack.yaml"
            if not yaml_path.is_file():
                yml_path = child / "rulepack.yml"
                if not yml_path.is_file():
                    continue
                yaml_path = yml_path
            raw = yaml_path.read_bytes()
            entry = RulepackEntry(
                id=child.name,
                path=str(yaml_path),
                rel_path="%s/%s" % (child.name, yaml_path.name),
                size=len(raw),
                sha256=hashlib.sha256(raw).hexdigest(),
                valid=False,
                error=None,
            )
            try:
                data = yaml.safe_load(raw.decode("utf-8"))
                data = validate_rulepack_v2(data)
            except RulepackSchemaError as exc:
                entry["error"] = exc.to_dict()
            except Exception as exc:  # noqa: BLE001 -- indexing must not abort
                entry["error"] = {"code": ERR_INVALID, "message": str(exc)}
            else:
                entry.update(
                    declared_id=data["id"],
                    version=data["version"],
                    display_name=data.get("display_name", data["id"]),
                    schema=data.get("schema", 1),
                    family=(data.get("ruleset") or {}).get("family"),
                    edition=(data.get("ruleset") or {}).get("edition"),
                    dice=(data.get("ruleset") or {}).get("dice"),
                    resolution_model=resolver_mod.resolution_model(data),
                    valid=True,
                )
                if data["id"] != child.name:
                    # The directory name is the id manifests refer to; a pack
                    # that disagrees with its own folder must not silently win.
                    entry["valid"] = False
                    entry["error"] = {
                        "code": ERR_INVALID,
                        "message": "directory %r declares rulepack id %r (they must match)"
                                   % (child.name, data["id"]),
                        "path": "id",
                    }
                else:
                    self._loaded[data["id"]] = data
            entries[entry["id"]] = entry
        self._entries = entries
        return entries

    def entries(self) -> dict[str, RulepackEntry]:
        if self._entries is None:
            self.scan()
        return self._entries or {}

    def available(self) -> tuple[str, ...]:
        """Ids of rulepacks that actually load and validate."""
        return tuple(sorted(k for k, v in self.entries().items() if v.get("valid")))

    def build_index(self) -> dict:
        """rulepacks/index.json payload (T1 owns writing the file)."""
        items = []
        for rid in sorted(self.entries()):
            entry = self.entries()[rid]
            item = {
                "id": entry.get("id"),
                "name": entry.get("display_name", entry.get("id")),
                "ruleset": entry.get("family") or entry.get("id"),
                "version": entry.get("version"),
                "schema": entry.get("schema"),
                "resolution_model": entry.get("resolution_model"),
                "sha256": entry.get("sha256"),
                "size": entry.get("size"),
                "path": entry.get("rel_path"),
                "valid": bool(entry.get("valid")),
            }
            if entry.get("error"):
                item["error"] = entry["error"]
            items.append(item)
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_by": "app.rules.binding.RulepackRepository.build_index",
            "count": len(items),
            "packaged_rulesets": list(PACKAGED_RULESETS),
            "planned_rulesets": list(PLANNED_RULESETS),
            "items": items,
        }

    # -- resolution -------------------------------------------------------
    def canonical_id(self, requested: str, origin: str = "direct") -> str:
        """Map a requested ruleset string to a canonical id (alias-aware)."""
        if not isinstance(requested, str) or not requested.strip():
            raise RulesetBindingError(
                ERR_NO_RULESET_DECLARED,
                "manifest declares no ruleset (expected a non-empty string)",
                ruleset=requested,
                available=self.available(),
                origin=origin,
            )
        key = requested.strip()
        lowered = key.lower()
        if lowered in RULESET_ALIASES:
            return RULESET_ALIASES[lowered]
        return lowered

    def resolve(self, requested: str, origin: str = "direct") -> tuple[str, dict, str | None]:
        """Return (canonical_id, rulepack, alias_used).

        Raises RulesetBindingError(ERR_UNKNOWN_RULESET) when the ruleset is
        neither a packaged rulepack nor a declared alias.
        """
        canonical = self.canonical_id(requested, origin=origin)
        alias = canonical if canonical != (requested or "").strip().lower() else None
        entries = self.entries()
        entry = entries.get(canonical)
        if entry is None:
            raise RulesetBindingError(
                ERR_UNKNOWN_RULESET,
                "unknown ruleset %r; no rulepacks/%s/rulepack.yaml in the repository"
                % (requested, canonical),
                ruleset=requested,
                available=self.available(),
                detail={
                    "canonical_id": canonical,
                    "planned": canonical in PLANNED_RULESETS,
                    "catalog_known": canonical in RULESET_CATALOG,
                },
                origin=origin,
            )
        if not entry.get("valid"):
            raise RulesetBindingError(
                ERR_INVALID,
                "rulepack %r exists but is invalid: %s"
                % (canonical, (entry.get("error") or {}).get("message", "unknown")),
                ruleset=requested,
                available=self.available(),
                detail={"inner": entry.get("error")},
            )
        rulepack = self._loaded.get(canonical)
        if rulepack is None:
            rulepack = self._load(canonical, Path(entry["path"]))
        # Hand out a copy: callers must not be able to mutate the cache
        # through the returned mapping.
        return canonical, copy.deepcopy(rulepack), alias

    def _load(self, rid: str, path: Path) -> dict:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        validated = validate_rulepack_v2(data)
        if validated["id"] != rid:
            raise RulesetBindingError(
                ERR_INVALID,
                "directory %r declares rulepack id %r (they must match)" % (rid, validated["id"]),
                ruleset=rid,
                available=self.available(),
            )
        self._loaded[rid] = validated
        return validated

    # -- binding ----------------------------------------------------------
    def bind_manifest(self, manifest: Mapping[str, Any]) -> dict:
        """Auto-bind a module manifest's declared ruleset.

        This is the R23 entry point: the manifest is the single source of
        truth, and a bad ruleset fails loudly instead of defaulting.
        """
        if not isinstance(manifest, Mapping):
            raise RulesetBindingError(
                ERR_MANIFEST_INVALID,
                "manifest must be a mapping, got %s" % type(manifest).__name__,
            )
        requested = manifest.get("ruleset")
        canonical, rulepack, alias = self.resolve(requested, origin="manifest")
        return {
            "ok": True,
            "module_id": manifest.get("id"),
            "requested_ruleset": requested,
            "ruleset": canonical,
            "alias_applied": alias,
            "rulepack_id": rulepack["id"],
            "rulepack_version": rulepack["version"],
            "resolution_model": resolver_mod.resolution_model(rulepack),
            "rulepack": rulepack,
        }


_DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "rulepacks"
_REPO: RulepackRepository | None = None


def default_repository() -> RulepackRepository:
    """Process-wide repository rooted at <package root>/rulepacks."""
    global _REPO
    if _REPO is None:
        _REPO = RulepackRepository(_DEFAULT_ROOT)
    return _REPO


def bind_manifest(manifest: Mapping[str, Any], repo: RulepackRepository | None = None) -> dict:
    """Module-level convenience wrapper around RulepackRepository.bind_manifest."""
    return (repo or default_repository()).bind_manifest(manifest)


def open_table(
    manifest: Mapping[str, Any],
    card: Mapping[str, Any],
    repo: RulepackRepository | None = None,
    ruleset_override: str | None = None,
) -> dict:
    """Open a table from a module manifest and return the bound opening payload.

    The ruleset_override argument exists so the acceptance run can open the
    SAME module under two rulesets and diff the resulting fields and formulas.
    """
    repository = repo or default_repository()
    target: dict[str, Any] = dict(manifest)
    if ruleset_override is not None:
        target = {**target, "ruleset": ruleset_override}
    bound = repository.bind_manifest(target)
    rulepack = bound.pop("rulepack")
    fields = resolver_mod.opening_fields(rulepack, card)
    return {**bound, "opening_fields": fields}
