"""Extension registry — hot-load implementation (DESIGN §2.7, W-B3).

Frozen interface (unchanged signatures): register_skill / register_module /
register_rulepack / load / unload / list.

Semantics:
- Registration validates ``needs_allow ⊆ ALLOW`` where ALLOW is the frozen
  allow id set from ``trpg/agent/allowlist.yml`` (DESIGN §2.6 v1). Anything
  else (DENY ids such as ``read_secrets``, or unknown ids) is rejected with
  ``PermissionDeniedError`` and an audit record.
- Hot-load without loop restart: ``load()`` resolves the entry handler but it
  becomes effective on the *next* round (``advance_round()``), i.e. S0 semantics.
- ``dispatch(event_kind, event)`` fans an event out to loaded handlers whose
  manifest subscribes to that kind and whose effective round has arrived.
- Audit trail is kept in memory (``audit_log``); every register success,
  permission rejection, load and unload appends a record.
"""
from __future__ import annotations

import copy
import importlib
from dataclasses import dataclass, field
from typing import Any, Callable

from .events import FROZEN_KINDS

# Frozen ALLOW id set — mirrors trpg/agent/allowlist.yml v1 (DESIGN §2.6).
# extends only with captain approval; W-B3 must not change it.
ALLOW_IDS: frozenset[str] = frozenset({
    "health_check",
    "log_collect",
    "service_control",
    "file_rw",
    "run_sim",
})

# Frozen DENY id set — for explicit audit detail on越权 attempts.
DENY_IDS: frozenset[str] = frozenset({
    "read_secrets",
    "edit_llm_config",
    "write_outside_sysdrive",
    "schedtask_registry",
    "egress",
    "priv_esc_raw_ps",
})

_VALID_KINDS = ("skill", "module", "rulepack")


class PermissionDeniedError(PermissionError):
    """Raised when a manifest's needs_allow exceeds the frozen ALLOW set."""


@dataclass(frozen=True)
class SkillManifest:
    """SkillManifest{skill_id, name, version, entry, events_subscribed[], needs_allow[]}."""

    skill_id: str
    name: str
    version: str
    entry: Any  # callable or "module:attr" import path
    events_subscribed: tuple[str, ...] = ()
    needs_allow: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModuleManifest:
    """Module (剧本) manifest."""

    module_id: str
    name: str
    version: str
    entry: Any = None
    events_subscribed: tuple[str, ...] = ()
    needs_allow: tuple[str, ...] = ()


@dataclass(frozen=True)
class RulepackManifest:
    """Rulepack (规则包) manifest."""

    rulepack_id: str
    name: str
    version: str
    entry: Any = None
    events_subscribed: tuple[str, ...] = ()
    needs_allow: tuple[str, ...] = ()


@dataclass
class Extension:
    """A hot-loaded extension handle returned by load()."""

    ext_id: str
    kind: str  # skill | module | rulepack
    manifest: Any
    handler: Any = None
    effective_round: int = 0


@dataclass
class _Loaded:
    manifest: Any
    kind: str
    handler: Any
    effective_round: int


def _manifest_id(kind: str, manifest: Any) -> str:
    attr = {"skill": "skill_id", "module": "module_id",
            "rulepack": "rulepack_id"}[kind]
    if isinstance(manifest, dict):
        return manifest.get(attr, "")
    return getattr(manifest, attr, "")


def _manifest_field(manifest: Any, name: str, default: Any = None) -> Any:
    if isinstance(manifest, dict):
        return manifest.get(name, default)
    return getattr(manifest, name, default)


def _normalize(kind: str, manifest: Any) -> Any:
    """Normalize dict / namespace manifests to frozen dataclasses."""
    cls = {"skill": SkillManifest, "module": ModuleManifest,
           "rulepack": RulepackManifest}[kind]
    if isinstance(manifest, cls):
        return manifest
    if isinstance(manifest, dict):
        data = dict(manifest)
        for key in ("events_subscribed", "needs_allow"):
            val = data.get(key, ())
            data[key] = tuple(val) if not isinstance(val, tuple) else val
        try:
            return cls(**data)
        except TypeError as exc:
            raise ValueError(f"invalid {kind} manifest fields: {exc}") from exc
    # generic namespace object -> dict
    data: dict[str, Any] = {}
    fields = ("skill_id", "module_id", "rulepack_id", "name", "version",
              "entry", "events_subscribed", "needs_allow")
    for f in fields:
        if hasattr(manifest, f):
            data[f] = getattr(manifest, f)
    try:
        kwargs = {k: v for k, v in data.items()
                  if k in cls.__dataclass_fields__}
        for key in ("events_subscribed", "needs_allow"):
            if key in kwargs and not isinstance(kwargs[key], tuple):
                kwargs[key] = tuple(kwargs[key])
        return cls(**kwargs)
    except TypeError as exc:
        raise ValueError(f"invalid {kind} manifest fields: {exc}") from exc


def _resolve_entry(entry: Any) -> Any:
    """Resolve an entry to a handler: callable passes through, 'mod:attr' is imported."""
    if entry is None:
        return None
    if callable(entry):
        return entry
    if isinstance(entry, str) and ":" in entry:
        mod_name, _, attr = entry.partition(":")
        try:
            mod = importlib.import_module(mod_name)
        except ImportError as exc:
            raise ValueError(f"entry module not importable: {mod_name}") from exc
        try:
            fn = getattr(mod, attr)
        except AttributeError as exc:
            raise ValueError(f"entry attr missing: {entry}") from exc
        if not callable(fn):
            raise ValueError(f"entry not callable: {entry}")
        return fn
    raise ValueError(f"entry must be a callable or 'module:attr' path, got {entry!r}")


class ExtensionRegistry:
    """Hot-load registry for skills / modules / rulepacks (W-B3 implementation)."""

    def __init__(self, allow: frozenset[str] | set[str] | None = None) -> None:
        self._allow: frozenset[str] = frozenset(allow) if allow is not None else ALLOW_IDS
        self._skills: dict[str, Any] = {}
        self._modules: dict[str, Any] = {}
        self._rulepacks: dict[str, Any] = {}
        self._loaded: dict[str, _Loaded] = {}
        self._audit: list[dict[str, Any]] = []
        self._round: int = 0

    # -- introspection ----------------------------------------------------
    @property
    def current_round(self) -> int:
        """Current loop round (S0 counter; load() takes effect next round)."""
        return self._round

    def advance_round(self) -> int:
        """Advance one loop round; pending hot-loads become effective. Returns new round."""
        self._round += 1
        self._audit.append({"action": "advance_round", "round": self._round})
        return self._round

    @property
    def audit_log(self) -> list[dict[str, Any]]:
        """Copy of the audit trail (register/load/unload/reject records)."""
        return [dict(r) for r in self._audit]

    # -- registration -----------------------------------------------------
    def _register(self, kind: str, manifest: Any) -> str:
        norm = _normalize(kind, manifest)
        ext_id = _manifest_id(kind, norm)
        if not ext_id or not str(ext_id).strip():
            raise ValueError(f"{kind} manifest needs a non-empty id")
        if not _manifest_field(norm, "name") or not _manifest_field(norm, "version"):
            raise ValueError(f"{kind} manifest needs non-empty name/version")
        events = tuple(_manifest_field(norm, "events_subscribed", ()) or ())
        bad_events = [e for e in events if e not in FROZEN_KINDS]
        if bad_events:
            raise ValueError(f"{kind} manifest subscribes to unknown events: {bad_events}")
        needs = tuple(_manifest_field(norm, "needs_allow", ()) or ())
        over = [n for n in needs if n not in self._allow]
        if over:
            deny_hit = [n for n in over if n in DENY_IDS]
            self._audit.append({
                "action": "register_rejected",
                "kind": kind,
                "ext_id": ext_id,
                "needs_allow": list(needs),
                "over_privilege": list(over),
                "deny_hit": list(deny_hit),
            })
            raise PermissionDeniedError(
                f"{kind} {ext_id!r} needs_allow exceeds ALLOW: {over}")
        store = {"skill": self._skills, "module": self._modules,
                 "rulepack": self._rulepacks}[kind]
        if ext_id in store:
            raise ValueError(f"{kind} already registered: {ext_id!r}")
        store[ext_id] = norm
        self._audit.append({"action": "register", "kind": kind,
                            "ext_id": ext_id,
                            "needs_allow": list(needs)})
        return ext_id

    def register_skill(self, manifest: Any) -> str:
        """Register a skill manifest -> skill_id."""
        return self._register("skill", manifest)

    def register_module(self, manifest: Any) -> str:
        """Register a module manifest -> module_id."""
        return self._register("module", manifest)

    def register_rulepack(self, manifest: Any) -> str:
        """Register a rulepack manifest -> rulepack_id."""
        return self._register("rulepack", manifest)

    # -- hot load ---------------------------------------------------------
    def load(self, ext_id: str) -> Extension:
        """Hot-load an extension -> Extension (effective next round, no loop restart)."""
        for kind, store in (("skill", self._skills),
                            ("module", self._modules),
                            ("rulepack", self._rulepacks)):
            if ext_id in store:
                manifest = store[ext_id]
                handler = _resolve_entry(_manifest_field(manifest, "entry", None))
                effective = self._round + 1
                self._loaded[ext_id] = _Loaded(manifest=manifest, kind=kind,
                                              handler=handler,
                                              effective_round=effective)
                self._audit.append({"action": "load", "kind": kind,
                                    "ext_id": ext_id,
                                    "effective_round": effective})
                return Extension(ext_id=ext_id, kind=kind, manifest=manifest,
                                 handler=handler, effective_round=effective)
        raise KeyError(f"extension not registered: {ext_id!r}")

    def unload(self, ext_id: str) -> None:
        """Unload an extension (registration kept; dispatch stops)."""
        if ext_id not in self._loaded:
            raise KeyError(f"extension not loaded: {ext_id!r}")
        kind = self._loaded.pop(ext_id).kind
        self._audit.append({"action": "unload", "kind": kind, "ext_id": ext_id})

    def list(self, kind: str = "all") -> list[Any]:
        """List manifests (kind: skill | module | rulepack | all)."""
        if kind == "all":
            items = list(self._skills.values()) + list(self._modules.values()) + list(
                self._rulepacks.values())
            return copy.deepcopy(items)
        if kind == "skill":
            return copy.deepcopy(list(self._skills.values()))
        if kind == "module":
            return copy.deepcopy(list(self._modules.values()))
        if kind == "rulepack":
            return copy.deepcopy(list(self._rulepacks.values()))
        raise ValueError(f"unknown kind: {kind!r} (skill|module|rulepack|all)")

    # -- event fan-out ----------------------------------------------------
    def dispatch(self, event_kind: str, event: Any) -> list[Any]:
        """Fan an event out to effective loaded handlers subscribed to event_kind.

        Returns per-handler outputs in load order. Handlers whose effective
        round has not arrived yet (loaded this round) are skipped — hot-load
        takes effect next round without restarting the loop.
        """
        out: list[Any] = []
        for ext_id, loaded in self._loaded.items():
            if self._round < loaded.effective_round:
                continue
            subs = tuple(_manifest_field(loaded.manifest, "events_subscribed", ()) or ())
            if event_kind not in subs:
                continue
            if loaded.handler is None:
                continue
            out.append(loaded.handler(event))
        return out

    # -- sample skill -----------------------------------------------------
    def register_dice_blessing(self) -> str:
        """Register the W-B3 sample skill (dice blessing on roll events)."""
        from .skills.dice_blessing import SKILL_MANIFEST
        return self.register_skill(dict(SKILL_MANIFEST))
