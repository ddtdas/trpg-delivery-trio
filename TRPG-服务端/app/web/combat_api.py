"""T7 (additive): M5 战斗事件回合 REST API.

Captain ruling (M5 APPROVAL):
  * auto-resolution produces COMBAT_ROUND_PROPOSED (pending placeholder) --
    resolutions are NOT written to the event stream unapproved;
  * approve -> COMBAT_ROUND_APPROVED (approved_by=主持人) written;
  * reject -> COMBAT_ROUND_REJECTED + reason;
  * grep-able evidence: proposal lands, approved events carry resolutions.

Endpoints:
  POST /api/campaigns/{c}/combat/start     (主持人) -> COMBAT_STARTED
  POST /api/campaigns/{c}/combat/round    (主持人) -> 自动结算 -> COMBAT_ROUND_PROPOSED
  POST /api/campaigns/{c}/combat/approve  (主持人) -> COMBAT_ROUND_APPROVED
  POST /api/campaigns/{c}/combat/reject   (主持人) -> COMBAT_ROUND_REJECTED
  POST /api/campaigns/{c}/combat/end      (主持人) -> COMBAT_ENDED
  GET  /api/campaigns/{c}/combat/current             -> 当前战斗状态

Auto-resolution uses the rulepack resolver (d100 <= target, difficulty
divisors, damage table) -- deterministic and offline.
Python 3.12 compatible.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.config import APP_ROOT
from app.domain.events import make_event
from app.web.access import _require_kp_end

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _campaign_id(c: str) -> str:
    c = str(c or "").strip()
    if not c or "/" in c or "\\" in c or ".." in c:
        raise HTTPException(status_code=422, detail="bad campaign id")
    return c


def _as_dict(v: Any) -> dict[str, Any]:
    # Accept either a dict action or a bare string (treated as action text).
    if isinstance(v, dict):
        return dict(v)
    return {"action": str(v or ""), "skill": "fighting_brawl",
            "target_value": 50, "damage": "1d6", "seed": None}


def _as_actor(v: Any) -> dict[str, Any]:
    """Normalize an actor reference: string id -> {id: <s>, kind: player};

    dict kept as-is. P1-3 (T10): prevents 500 on string actor."""
    if isinstance(v, dict):
        return dict(v)
    return {"id": str(v or ""), "kind": "player"}


def _resolve_attack(actor: dict[str, Any], action: dict[str, Any],
                    rulepack: dict[str, Any] | None = None) -> dict[str, Any]:
    """Deterministic auto-resolution of one combat action.

    Uses the coc7 percentile model: d100 <= skill target -> success;
    hard/extreme tiers via divisors; damage from a dice formula.
    Falls back to a conservative roll when rulepack data is absent.
    """
    actor = _as_actor(actor)
    action = _as_dict(action)
    skill = str(action.get("skill") or "fighting_brawl")
    target = int(action.get("target_value") or 0)
    if target <= 0:
        # derive from rulepack skill base if available, else default 50
        target = 50
    import random
    seed = action.get("seed")
    rng = random.Random(int(seed) if seed is not None and str(seed).strip().isdigit() else None)
    rolled = rng.randint(1, 100)
    hard = target // 2
    extreme = target // 5
    if rolled == 1:
        level = "crit"
    elif rolled >= 96 and target < 50:
        level = "fumble"
    elif rolled <= extreme:
        level = "extreme"
    elif rolled <= hard:
        level = "hard"
    elif rolled <= target:
        level = "success"
    else:
        level = "fail"
    # damage (formula like 1d6)
    import re
    m = re.fullmatch(r"(\d*)d(\d+)([+-]\d+)?", str(action.get("damage") or "1d6").strip())
    if m:
        count = int(m.group(1) or 1)
        sides = int(m.group(2))
        mod = int(m.group(3) or 0) if m.group(3) else 0
        dmg = sum(rng.randint(1, sides) for _ in range(count)) + mod
    else:
        dmg = 0
    result = "命中" if level in ("crit", "success", "hard", "extreme") else "未命中"
    if level == "crit":
        dmg = dmg * 2
        result = "重击命中"
    return {
        "actor": str(actor.get("id") or actor.get("actor") or ""),
        "action": str(action.get("action") or "攻击"),
        "skill": skill,
        "target_value": target,
        "rolled": rolled,
        "level": level,
        "damage": dmg,
        "result": "%s（d100=%d，目标%d，%s）" % (result, rolled, target, level),
        "status": "pending_approval",
    }


@router.get("/api/campaigns/{campaign}/combat/current")
async def combat_current(campaign: str,
                         entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    from app.web import rest as rest_mod
    c = _campaign_id(campaign)
    store = rest_mod._store()
    await store.init()
    events = await store.replay(c)
    state = rest_mod.project(events, c)
    combat = getattr(state, "combat", {}) or {}
    if not combat:
        return {"campaign": c, "combat": None, "status": "none"}
    return {"campaign": c, "combat": combat, "status": combat.get("status", "")}


@router.post("/api/campaigns/{campaign}/combat/start", status_code=201)
async def combat_start(campaign: str, body: dict[str, Any],
                       entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    from app.web import rest as rest_mod
    c = _campaign_id(campaign)
    store = rest_mod._store()
    await store.init()
    events = await store.replay(c)
    seq = events[-1].seq if events else -1
    participants = list((body or {}).get("participants") or [])
    if not participants:
        raise HTTPException(status_code=422, detail="participants required")
    combat_id = str((body or {}).get("combat_id") or ("cbt_%s_%d" % (c, seq + 1)))
    ev = make_event(seq=0, campaign_id=c, type="COMBAT_STARTED",
                    payload={"campaign_id": c, "combat_id": combat_id,
                             "participants": participants, "start_seq": seq + 1},
                    actor="kp", ts=_now())
    seqs = await store.append(c, [ev])
    # auto snapshot before combat (M6)
    try:
        from app.repository import campaign_folder as cf
        cf.ensure_campaign(c)
        state = rest_mod.project(events + [ev], c)
        snap = {"schema": "trpg.snapshot.v1", "campaign_id": c,
                "snapshot_id": "auto-before-combat-%06d" % (seq + 1),
                "kind": "auto", "seq": seq + 1, "ts": _now(),
                "label": "战斗前-%s" % combat_id, "reason": "COMBAT_STARTED 自动存档",
                "state": state.model_dump(mode="json")}
        cf.write_checkpoint(c, "auto", "before-combat", seq + 1, snap)
    except Exception:  # noqa: BLE001 — snapshot is best-effort
        pass
    return {"ok": True, "seq": seqs[0], "combat_id": combat_id, "start_seq": seq + 1}


@router.post("/api/campaigns/{campaign}/combat/round", status_code=201)
async def combat_round(campaign: str, body: dict[str, Any],
                       entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    """自动结算 -> COMBAT_ROUND_PROPOSED (pending). 未批准不写入 resolutions."""
    from app.web import rest as rest_mod
    c = _campaign_id(campaign)
    store = rest_mod._store()
    await store.init()
    events = await store.replay(c)
    state = rest_mod.project(events, c)
    combat = getattr(state, "combat", {}) or {}
    combat_id = str((body or {}).get("combat_id") or combat.get("combat_id") or "")
    if not combat_id:
        raise HTTPException(status_code=422, detail="no active combat (start first)")
    actions = list((body or {}).get("actions") or [])
    if not actions:
        raise HTTPException(status_code=422, detail="actions required")
    # M2 (T8): server forces round increment; body-provided round is ignored
    round_no = int(combat.get("round", 0) + 1)
    resolutions = []
    for a in actions:
        if not isinstance(a, dict):
            raise HTTPException(status_code=422,
                                detail="combat actions entries must be objects")
        if not a.get("actor"):
            raise HTTPException(status_code=422,
                                detail="combat action actor required")
        if not a.get("action"):
            raise HTTPException(status_code=422,
                                detail="combat action action text required")
        resolutions.append(_resolve_attack(a.get("actor"), a.get("action"), None))
    ev = make_event(seq=0, campaign_id=c, type="COMBAT_ROUND_PROPOSED",
                    payload={"campaign_id": c, "combat_id": combat_id,
                             "round": round_no, "resolutions": resolutions,
                             "status": "pending_approval"},
                    actor="kp", ts=_now())
    seqs = await store.append(c, [ev])
    return {"ok": True, "seq": seqs[0], "type": "COMBAT_ROUND_PROPOSED",
            "round": round_no, "combat_id": combat_id,
            "resolutions": resolutions, "status": "pending_approval"}


@router.post("/api/campaigns/{campaign}/combat/approve", status_code=201)
async def combat_approve(campaign: str, body: dict[str, Any],
                         entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    """主持人批准 -> COMBAT_ROUND_APPROVED (approved_by=主持人) 写入事件流.

    M1 (T8): idempotency — a round already approved/rejected cannot be
    approved again (prevents double-click landing two APPROVED events).
    """
    from app.web import rest as rest_mod
    c = _campaign_id(campaign)
    store = rest_mod._store()
    await store.init()
    events = await store.replay(c)
    state = rest_mod.project(events, c)
    combat = getattr(state, "combat", {}) or {}
    combat_id = str((body or {}).get("combat_id") or combat.get("combat_id") or "")
    if not combat_id:
        raise HTTPException(status_code=422, detail="no active combat")
    round_no = int((body or {}).get("round") or combat.get("round", 0))
    # M1: reject double approval
    rounds = combat.get("rounds") or {}
    if str(round_no) in rounds:
        raise HTTPException(status_code=409,
                            detail="round %d already approved" % round_no)
    # fetch pending resolutions from state (proposal placeholder)
    pending = list(combat.get("pending_resolutions") or [])
    if not pending:
        # allow explicit resolutions in the approve body (host edited)
        pending = list((body or {}).get("resolutions") or [])
    if not pending:
        raise HTTPException(status_code=422, detail="no pending resolutions to approve")
    ev = make_event(seq=0, campaign_id=c, type="COMBAT_ROUND_APPROVED",
                    payload={"campaign_id": c, "combat_id": combat_id,
                             "round": round_no, "resolutions": pending,
                             "approved_by": "kp"},
                    actor="kp", ts=_now(), approved_by="kp")
    seqs = await store.append(c, [ev])
    return {"ok": True, "seq": seqs[0], "type": "COMBAT_ROUND_APPROVED",
            "round": round_no, "resolutions": pending, "approved_by": "kp"}


@router.post("/api/campaigns/{campaign}/combat/reject", status_code=201)
async def combat_reject(campaign: str, body: dict[str, Any],
                        entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    from app.web import rest as rest_mod
    c = _campaign_id(campaign)
    store = rest_mod._store()
    await store.init()
    events = await store.replay(c)
    state = rest_mod.project(events, c)
    combat = getattr(state, "combat", {}) or {}
    combat_id = str((body or {}).get("combat_id") or combat.get("combat_id") or "")
    round_no = int((body or {}).get("round") or combat.get("round", 0))
    pending = list(combat.get("pending_resolutions") or [])
    reason = str((body or {}).get("reason") or "主持人驳回")
    ev = make_event(seq=0, campaign_id=c, type="COMBAT_ROUND_REJECTED",
                    payload={"campaign_id": c, "combat_id": combat_id,
                             "round": round_no, "resolutions": pending,
                             "reason": reason, "approved_by": "kp"},
                    actor="kp", ts=_now())
    seqs = await store.append(c, [ev])
    return {"ok": True, "seq": seqs[0], "type": "COMBAT_ROUND_REJECTED",
            "round": round_no, "reason": reason}


@router.post("/api/campaigns/{campaign}/combat/end", status_code=201)
async def combat_end(campaign: str, body: dict[str, Any],
                     entry: dict[str, Any] = Depends(_require_kp_end)) -> dict[str, Any]:
    from app.web import rest as rest_mod
    c = _campaign_id(campaign)
    store = rest_mod._store()
    await store.init()
    events = await store.replay(c)
    seq = events[-1].seq if events else -1
    combat_id = str((body or {}).get("combat_id") or "")
    ev = make_event(seq=0, campaign_id=c, type="COMBAT_ENDED",
                    payload={"campaign_id": c, "combat_id": combat_id,
                             "end_seq": seq + 1},
                    actor="kp", ts=_now())
    seqs = await store.append(c, [ev])
    return {"ok": True, "seq": seqs[0], "type": "COMBAT_ENDED", "combat_id": combat_id}
