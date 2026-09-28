"""TRPG MCP table/session tools (MIT): character/session/map-read/narrate.

character_create validates via the shared hard gate and appends
CHARACTER_CREATED; narration_propose queues NARRATION_PROPOSED;
narration_approve lands the APPROVED/EDITED/REJECTED event;
info_distribute lands INFO_REVEALED; map reads are direct, map writes
go through the event chain (MAP_UPDATED, KP-approved upstream).
Python 3.12 compatible.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.domain.character import CharacterCard, validate_card
from app.domain.events import GameEvent, make_event
from app.mcp.auth import AuthError, is_kp
from app.store.event_store import EventStore
from app.store.projector import project

PENDING: dict[str, dict[str, Any]] = {}  # proposal_id -> proposal (KP queue)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_events(events: list[GameEvent]) -> str:
    canon = json.dumps([{"seq": e.seq, "type": e.type,
                         "payload": e.payload} for e in events],
                       sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


async def do_character_create(args: dict[str, Any],
                              store: EventStore) -> dict[str, Any]:
    actor = args.get("actor", {})
    card_in = dict(args.get("card", {}))
    card_in.setdefault("card_id", "card_" + uuid.uuid4().hex[:8])
    card_in.setdefault("player_id", str(actor.get("id", "")))
    card_in.setdefault("ruleset", str(args.get("ruleset", "coc7")))
    try:
        card = CharacterCard(**card_in)
    except Exception as exc:
        raise ValueError("illegal card: %s" % exc) from exc
    report = validate_card(card)
    if not report.ok:
        raise ValueError("illegal card: %s" % "; ".join(report.errors))
    campaign = str(args.get("campaign_id", card.player_id or "c1"))
    ev = make_event(seq=0, campaign_id=campaign, type="CHARACTER_CREATED",
                    payload={"card_id": card.card_id,
                             "player_id": card.player_id,
                             "ruleset": card.ruleset,
                             "card": card.model_dump(mode="json")},
                    actor=str(actor.get("id", "")), ts=_now())
    await store.init()
    await store.append(campaign, [ev])
    return {"ok": True, "card_id": card.card_id,
            "validation_report": {"ok": True, "errors": []}}


async def do_session_state(args: dict[str, Any],
                           store: EventStore) -> dict[str, Any]:
    campaign = str(args.get("campaign_id", ""))
    if not campaign:
        raise ValueError("campaign_id required")
    await store.init()
    events = await store.replay(campaign)
    state = project(events, campaign)
    cursor = ""
    if state.turn is not None:
        cursor = state.turn.cursor
    pending = [p for p in PENDING.values()
               if p.get("campaign_id") == campaign]
    return {"campaign_id": campaign,
            "event_seq": events[-1].seq if events else -1,
            "projected_hash": _hash_events(events),
            "pending_approvals": [{"proposal_id": p["proposal_id"],
                                   "text": p["text"]} for p in pending],
            "turn_cursor": cursor}


async def do_narration_propose(args: dict[str, Any],
                               store: EventStore) -> dict[str, Any]:
    for f in ("campaign_id", "text", "reasoning"):
        if not args.get(f):
            raise ValueError("missing param: %s" % f)
    if str(args.get("source", "agent")) not in ("agent", "dsh"):
        raise ValueError("source must be agent|dsh")
    pid = "prop_" + uuid.uuid4().hex[:8]
    PENDING[pid] = {"proposal_id": pid, "campaign_id": str(args["campaign_id"]),
                    "text": str(args["text"]),
                    "intention": args.get("intention"),
                    "reasoning": str(args["reasoning"]),
                    "source": str(args.get("source", "agent"))}
    ev = make_event(seq=0, campaign_id=str(args["campaign_id"]),
                    type="NARRATION_PROPOSED",
                    payload={"campaign_id": str(args["campaign_id"]),
                             "proposal_id": pid, "text": str(args["text"]),
                             "reasoning": str(args["reasoning"]),
                             "source": str(args.get("source", "agent")),
                             **({"intention": args["intention"]}
                                if args.get("intention") else {})},
                    actor=str(args.get("actor", {}).get("id", "")),
                    ts=_now())
    await store.init()
    await store.append(str(args["campaign_id"]), [ev])
    return {"ok": True, "proposal_id": pid}


async def do_narration_approve(args: dict[str, Any],
                               store: EventStore) -> dict[str, Any]:
    pid = str(args.get("proposal_id", ""))
    decision = str(args.get("decision", ""))
    if decision not in ("approve", "edit", "reject"):
        raise ValueError("decision must be approve|edit|reject")
    if decision == "edit" and not args.get("edited_text"):
        raise ValueError("edited_text required for edit")
    prop = PENDING.get(pid, {"text": args.get("edited_text") or ""})
    text = str(args.get("edited_text") or prop.get("text") or "")
    campaign = str(args.get("campaign_id")
                     or prop.get("campaign_id") or "c1")
    if decision == "approve":
        etype, payload = "NARRATION_APPROVED", {"proposal_id": pid,
                                                "text": text}
    elif decision == "edit":
        etype, payload = "NARRATION_EDITED", {"proposal_id": pid,
                                              "text": text, "diff": {}}
    else:
        etype, payload = "NARRATION_REJECTED", {
            "proposal_id": pid, "reason": str(args.get("reason", "rejected"))}
    ev = GameEvent(seq=0, campaign_id=campaign, type=etype, payload=payload,
                   actor="kp", approved_by="kp", ts=_now())
    await store.init()
    seqs = await store.append(campaign, [ev])
    PENDING.pop(pid, None)
    return {"ok": True, "events": [{"seq": seqs[0], "type": etype}]}


async def do_info_distribute(args: dict[str, Any],
                             store: EventStore) -> dict[str, Any]:
    for f in ("campaign_id", "info_id", "scope", "body_ref"):
        if f not in args:
            raise ValueError("missing param: %s" % f)
    if str(args["scope"]) not in ("public", "whisper", "condition"):
        raise ValueError("bad scope")
    ev = make_event(seq=0, campaign_id=str(args["campaign_id"]),
                    type="INFO_REVEALED",
                    payload={"campaign_id": str(args["campaign_id"]),
                             "info_id": str(args["info_id"]),
                             "scope": str(args["scope"]),
                             "targets": list(args.get("targets", [])),
                             "body_ref": str(args["body_ref"])},
                    actor="kp", ts=_now())
    await store.init()
    seqs = await store.append(str(args["campaign_id"]), [ev])
    return {"ok": True, "events": [{"seq": seqs[0], "type": "INFO_REVEALED"}]}


async def do_event_inject(args: dict[str, Any],
                          store: EventStore) -> dict[str, Any]:
    for f in ("campaign_id", "node_id"):
        if f not in args:
            raise ValueError("missing param: %s" % f)
    if args.get("dry_run"):
        return {"dry_run_result": {"node_id": str(args["node_id"]),
                                   "would_emit": "EVENT_INJECTED",
                                   "payload_keys": sorted(
                                       list(dict(args.get("payload", {})).keys()))}}
    allowed = set(args.get("whitelist", ["library", "hospital", "chapel"]))
    if str(args["node_id"]) not in allowed:
        raise AuthError("actor_required")  # not whitelisted: deny w/o oracle
    ev = make_event(seq=0, campaign_id=str(args["campaign_id"]),
                    type="EVENT_INJECTED",
                    payload={"campaign_id": str(args["campaign_id"]),
                             "node_id": str(args["node_id"]),
                             "payload": dict(args.get("payload", {})),
                             "dry_run_result": {"approved": True}},
                    actor="kp", ts=_now())
    await store.init()
    seqs = await store.append(str(args["campaign_id"]), [ev])
    return {"ok": True, "events": [{"seq": seqs[0], "type": "EVENT_INJECTED"}]}


async def do_map_command(args: dict[str, Any], store: EventStore,
                         actor: dict[str, Any] | None = None) -> dict[str, Any]:
    op = str(args.get("op", "get"))
    if op == "get":
        return {"ok": True, "result": {"map_id": str(args.get("map_id", "")),
                                       "tokens": [], "fog": {}}}
    if not is_kp({"actor": (actor or {})}, "") and not is_kp(args, ""):
        raise AuthError("kp_token_required")
    if op not in ("move", "add_token", "set_fog", "set_status", "set_light"):
        raise ValueError("bad op")
    ev = make_event(seq=0, campaign_id=str(args["campaign_id"]),
                    type="MAP_UPDATED",
                    payload={"campaign_id": str(args["campaign_id"]),
                             "map_id": str(args.get("map_id", "")),
                             "op": op, "target": str(args.get("target", "")),
                             "delta": dict(args.get("delta", {}))},
                    actor="kp", ts=_now())
    await store.init()
    seqs = await store.append(str(args["campaign_id"]), [ev])
    return {"ok": True, "events": [{"seq": seqs[0], "type": "MAP_UPDATED"}]}
