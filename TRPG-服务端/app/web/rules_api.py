"""Additive REST surface for rulepack binding (R23).

Namespace note: T1 owns /api/rulepacks (the rulepack *repository*: list,
read, write, soft-delete, index). This module owns /api/rules (the
*resolution* side: which ruleset a table binds to and what the opening
payload looks like). The two namespaces do not overlap.

Every failure path returns a machine-readable code with a 4xx status --
never a 500 and never a silent fallback to CoC7.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.rules import binding as binding_mod
from app.rules import resolver as resolver_mod
from app.rules.rulepack_schema import catalog as rulepack_catalog

router = APIRouter(prefix="/api/rules", tags=["rules"])

_ROOT = Path(__file__).resolve().parents[2]
_MODULES = _ROOT / "modules"

#: Status used for a ruleset that does not exist -- a client error, not a
#: server fault, so the R13 error table can distinguish it from a 500.
_UNPROCESSABLE = 422


def _repo() -> binding_mod.RulepackRepository:
    return binding_mod.default_repository()


def _err(exc: binding_mod.RulesetBindingError) -> JSONResponse:
    """Render a binding failure with the status the R13 table declares.

    Never 500: an unknown ruleset is a client error (404/422 depending on
    the code the table assigns), and the body always carries the code.
    """
    return JSONResponse(status_code=exc.http_status, content=exc.to_dict())


def _load_manifest(module_id: str) -> dict:
    """Read modules/<id>/module.yaml, refusing to escape the modules root."""
    if not isinstance(module_id, str) or not module_id:
        raise binding_mod.RulesetBindingError(
            binding_mod.ERR_MANIFEST_INVALID, "module_id must be a non-empty string"
        )
    if any(part in module_id for part in ("/", "\\", "..", ":")):
        raise binding_mod.RulesetBindingError(
            binding_mod.ERR_MANIFEST_INVALID,
            "module_id must be a bare identifier, got %r" % (module_id,),
        )
    path = _MODULES / module_id / "module.yaml"
    if not path.is_file():
        raise binding_mod.RulesetBindingError(
            binding_mod.ERR_MANIFEST_INVALID, "no module manifest at %s" % (path,)
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise binding_mod.RulesetBindingError(
            binding_mod.ERR_MANIFEST_INVALID, "manifest root must be a mapping"
        )
    return data


@router.get("/catalog")
def rules_catalog() -> dict:
    """Packaged rulesets, schema-ready-but-planned rulesets, aliases."""
    return rulepack_catalog()


@router.get("/rulesets")
def list_rulesets() -> dict:
    """Repository view: what actually loads, plus the planned backlog."""
    repo = _repo()
    return {
        "available": list(repo.available()),
        "index": repo.build_index(),
        "catalog": rulepack_catalog(),
    }


@router.get("/rulesets/{ruleset}")
def get_ruleset(ruleset: str) -> Any:
    """One rulepack's declared fields, formulas, combat and growth blocks."""
    try:
        canonical, rulepack, alias = _repo().resolve(ruleset)
    except binding_mod.RulesetBindingError as exc:
        return _err(exc)
    return {
        "ok": True,
        "requested_ruleset": ruleset,
        "ruleset": canonical,
        "alias_applied": alias,
        "resolution_model": resolver_mod.resolution_model(rulepack),
        "difficulties": list(resolver_mod.check_difficulties(rulepack)),
        "rulepack": rulepack,
    }


@router.post("/bind")
def bind(body: dict) -> Any:
    """Auto-bind a ruleset (optionally via a module manifest)."""
    body = body or {}
    try:
        if body.get("module_id"):
            manifest = _load_manifest(body["module_id"])
            if body.get("ruleset"):
                manifest = {**manifest, "ruleset": body["ruleset"]}
        else:
            manifest = {"id": body.get("module_id"), "ruleset": body.get("ruleset")}
        bound = _repo().bind_manifest(manifest)
    except binding_mod.RulesetBindingError as exc:
        return _err(exc)
    bound.pop("rulepack", None)
    return bound


@router.post("/open")
def open_table(body: dict) -> Any:
    """Open a table and return the bound opening payload.

    Same module + different ruleset must yield different field names and
    different derived formulas -- that is the R23 acceptance surface.
    """
    body = body or {}
    try:
        manifest = _load_manifest(body.get("module_id") or "")
        card = body.get("card") or {"attrs": {}, "skills": {}}
        return binding_mod.open_table(
            manifest, card, repo=_repo(), ruleset_override=body.get("ruleset")
        )
    except binding_mod.RulesetBindingError as exc:
        return _err(exc)
    except resolver_mod.ResolutionError as exc:
        return JSONResponse(status_code=_UNPROCESSABLE, content={"ok": False, **exc.to_dict()})
    except Exception as exc:  # noqa: BLE001 -- formula/card problems are client errors
        return JSONResponse(
            status_code=_UNPROCESSABLE,
            content={"ok": False, "code": "RULEPACK_CARD_INVALID", "message": str(exc)},
        )
