"""T7 (additive): P1a -- 8 步 COC7 向导 REST 入口 (MIT).

Sessions are in-memory (same as CharWizard design). This API lets a player
walk the full COC7 flow over HTTP without touching WS:

  POST /api/wizard/start             -> session
  POST /api/wizard/{card}/fill       -> session state
  GET  /api/wizard/{card}            -> current wizard state
  POST /api/wizard/{card}/back       -> move back
  POST /api/wizard/{card}/finalize   -> finalize card (host-gated)

All write steps append CHARACTER_CREATED/CARD_FINALIZED through the store
(same as CharWizard.finalize).
Python 3.12 compatible.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.app_core.char_wizard import CharWizard, WizardError
from app.web.access import _require_kp_end, _require_player_end

router = APIRouter()

# In-memory wizard sessions keyed by campaign (single process).
_WIZARDS: dict[str, CharWizard] = {}


def _wizard(campaign: str, actor: str = "kp") -> CharWizard:
    w = _WIZARDS.get(campaign)
    if w is None:
        w = CharWizard(None, campaign, actor=actor)
        _WIZARDS[campaign] = w
    return w


def _session_dto(sess: Any) -> dict[str, Any]:
    return {"card_id": sess.card_id, "player_id": sess.player_id,
            "ruleset": sess.ruleset, "step": sess.step,
            "name": sess.name, "age": sess.age,
            "attrs": dict(sess.attrs), "derived": dict(sess.derived),
            "occupation": sess.occupation,
            "occupation_points": sess.occupation_points,
            "interest_points": sess.interest_points,
            "skills": dict(sess.skills),
            "skill_points": {k: dict(v) for k, v in sess.skill_points.items()},
            "background": sess.background,
            "background_details": dict(sess.background_details),
            "san_current": sess.san_current, "idea": sess.idea,
            "history": list(sess.history)}


@router.post("/api/wizard/start", status_code=201)
async def wizard_start(body: dict[str, Any],
                       entry: dict[str, Any] = Depends(_require_player_end)) -> dict[str, Any]:
    # Start a wizard session (player endpoint; finalize is host-gated).
    campaign = str((body or {}).get("campaign_id") or "").strip()
    player_id = str((body or {}).get("player_id") or "").strip()
    if not campaign or not player_id:
        raise HTTPException(status_code=422, detail="campaign_id and player_id required")
    ruleset = str((body or {}).get("ruleset") or "coc7")
    sess = _wizard(campaign).start(player_id, ruleset, (body or {}).get("card_id"))
    return {"ok": True, "session": _session_dto(sess)}


@router.post("/api/wizard/{card_id}/fill")
async def wizard_fill(card_id: str, body: dict[str, Any],
                      entry: dict[str, Any] = Depends(_require_player_end)) -> dict[str, Any]:
    campaign = str((body or {}).get("campaign_id") or "").strip()
    if not campaign:
        raise HTTPException(status_code=422, detail="campaign_id required")
    step = str((body or {}).get("step") or "").strip()
    data = (body or {}).get("data") or {}
    if not step or not isinstance(data, dict):
        raise HTTPException(status_code=422, detail="step + data required")
    try:
        sess = _wizard(campaign).fill(card_id, step, data)
    except WizardError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "session": _session_dto(sess)}


@router.get("/api/wizard/{card_id}")
async def wizard_get(card_id: str, campaign: str = "",
                     entry: dict[str, Any] = Depends(_require_player_end)) -> dict[str, Any]:
    campaign = str(campaign or "").strip()
    if not campaign:
        raise HTTPException(status_code=422, detail="campaign required (query)")
    try:
        sess = _wizard(campaign).get(card_id)
    except WizardError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "session": _session_dto(sess)}


@router.post("/api/wizard/{card_id}/back")
async def wizard_back(card_id: str, body: dict[str, Any],
                      entry: dict[str, Any] = Depends(_require_player_end)) -> dict[str, Any]:
    campaign = str((body or {}).get("campaign_id") or "").strip()
    to_step = str((body or {}).get("to_step") or "").strip()
    if not campaign or not to_step:
        raise HTTPException(status_code=422, detail="campaign_id and to_step required")
    try:
        sess = _wizard(campaign).back(card_id, to_step)
    except WizardError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "session": _session_dto(sess)}


@router.post("/api/wizard/{card_id}/finalize", status_code=201)
async def wizard_finalize(card_id: str, body: dict[str, Any],
                          entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    # Host-gated finalize: full validate_card hard gate + events.
    from app.web import rest as rest_mod
    campaign = str((body or {}).get("campaign_id") or "").strip()
    if not campaign:
        raise HTTPException(status_code=422, detail="campaign_id required")
    w = _wizard(campaign)
    store = rest_mod._store()
    await store.init()
    w.store = store
    w.campaign_id = campaign
    w.actor = "kp"
    try:
        card = await w.finalize(card_id)
    except WizardError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "card_id": card.card_id,
            "card": card.model_dump(mode="json")}
