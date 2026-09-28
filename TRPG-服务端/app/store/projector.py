"""TRPG projector: events -> SessionState (MIT).

Deterministic pure reduce: same stream always yields the same state.
Python 3.12 compatible.
"""
from __future__ import annotations

import copy
from typing import Any

from app.domain.events import GameEvent
from app.domain.model import ApprovalItem, SessionState, new_session


def _turn(state: SessionState, campaign_id: str):
    return state.ensure_turn(campaign_id)


def _set_approval(state: SessionState, pid: str, status: str) -> None:
    cur = state.approvals.get(pid)
    if cur is None:
        return
    state.approvals[pid] = ApprovalItem(
        proposal_id=cur.proposal_id, campaign_id=cur.campaign_id,
        text=cur.text, intention=cur.intention, source=cur.source,
        status=status)


def reduce(state: SessionState, ev: GameEvent) -> SessionState:
    t = ev.type
    p: dict[str, Any] = ev.payload
    if t == "CAMPAIGN_STARTED":
        state.table_id = p.get("table_id", state.table_id)
    elif t == "WORLD_INTRO_SET":
        state.world_intro = p.get("text", "")
    elif t == "CHARACTER_CREATED":
        card = dict(p.get("card", {}))
        card.update({"card_id": p["card_id"], "player_id": p["player_id"],
                     "ruleset": p["ruleset"]})
        state.characters[p["card_id"]] = card
    elif t == "CARD_FINALIZED":
        if p["card_id"] not in state.finalized_cards:
            state.finalized_cards.append(p["card_id"])
    elif t == "CARD_REVERTED":
        pass  # history-preserving marker; wizard state machine consumes it
    elif t == "PORTRAIT_READY":
        card = state.characters.get(p["card_id"], {"card_id": p["card_id"]})
        card["portrait"] = p.get("image_ref", {})
        state.characters[p["card_id"]] = card
    elif t == "TURN_STARTED":
        tw = _turn(state, ev.campaign_id)
        tw.turn_no = p["turn_no"]
        tw.state = "COLLECTING"
        tw.submitted = {}
        tw.order = []
        tw.countdown_end_ts = p.get("countdown_end_ts", "")
        tw.cursor = "turn:%d:collecting" % p["turn_no"]
    elif t == "ACTION_SUBMITTED":
        tw = _turn(state, ev.campaign_id)
        tw.submitted[p["player_id"]] = {"action": p.get("action", {}),
                                        "intent": p.get("intent_summary", "")}
    elif t == "ACTION_WITHDRAWN":
        tw = _turn(state, ev.campaign_id)
        tw.submitted.pop(p["player_id"], None)
    elif t == "TURN_CLOSED":
        tw = _turn(state, ev.campaign_id)
        tw.state = "CLOSED"
        tw.order = list(p.get("order", []))
    elif t == "TURN_CHECKPOINT":
        tw = _turn(state, ev.campaign_id)
        tw.cursor = p.get("cursor", tw.cursor)
        tw.state = "RESOLVING"
    elif t == "ACT_ADVANCED":
        state.act_no = p.get("act_no", state.act_no)
    elif t == "CHECK_RESOLVED":
        state.checks.append({"seq": ev.seq, "card_id": p.get("card_id"),
                             "target": p.get("target"), "total": p.get("total"),
                             "level": p.get("level"), "seed": p.get("seed")})
    elif t == "NARRATION_PROPOSED":
        pid = p["proposal_id"]
        state.narrations[pid] = {"text": p.get("text", ""), "status": "pending"}
        state.approvals[pid] = ApprovalItem(
            proposal_id=pid, campaign_id=ev.campaign_id,
            text=p.get("text", ""), intention=p.get("intention"),
            source=p.get("source", "agent"), status="pending")
    elif t == "NARRATION_APPROVED":
        n = state.narrations.get(p["proposal_id"], {"text": ""})
        n.update({"text": p.get("text", n.get("text", "")), "status": "approved"})
        state.narrations[p["proposal_id"]] = n
        _set_approval(state, p["proposal_id"], "approved")
    elif t == "NARRATION_EDITED":
        n = state.narrations.get(p["proposal_id"], {"text": ""})
        n.update({"text": p.get("text", n.get("text", "")), "status": "edited",
                  "diff": p.get("diff", {})})
        state.narrations[p["proposal_id"]] = n
        _set_approval(state, p["proposal_id"], "edited")
    elif t == "NARRATION_REJECTED":
        n = state.narrations.get(p["proposal_id"], {"text": ""})
        n.update({"status": "rejected", "reason": p.get("reason", "")})
        state.narrations[p["proposal_id"]] = n
        _set_approval(state, p["proposal_id"], "rejected")
    elif t == "INFO_REVEALED":
        state.infos[p["info_id"]] = {"scope": p.get("scope"),
                                     "targets": list(p.get("targets", [])),
                                     "body_ref": p.get("body_ref")}
    elif t == "CLUE_GRANTED":
        state.clues[p["clue_id"]] = {"ref": p.get("ref"),
                                     "condition_met": p.get("condition_met")}
    elif t == "BRANCH_TAKEN":
        state.branches.append({"node_id": p.get("node_id"),
                               "edge_id": p.get("edge_id"),
                               "label": p.get("label"),
                               "consequences": list(p.get("consequences", []))})
    elif t == "BRANCH_OVERRIDDEN":
        state.branches.append({"node_id": p.get("node_id"),
                               "overridden": True,
                               "reason": p.get("reason", "")})
    elif t == "EVENT_INJECTED":
        state.branches.append({"node_id": p.get("node_id"), "injected": True,
                               "payload": p.get("payload", {})})
    elif t == "TRANSCRIPT_APPENDED":
        state.transcripts.append({"seg": p.get("seg", {}),
                                  "source": p.get("source")})
    elif t == "TRANSCRIPT_READY":
        state.transcript_ready = True
    elif t == "SESSION_SUMMARIZED":
        state.summaries.append({"summary_ref": p.get("summary_ref"),
                                "hooks": list(p.get("hooks", [])),
                                "next_preview": p.get("next_preview", "")})
    elif t == "SNAPSHOT_SAVED":
        pass  # snapshot bookkeeping lives in app.store.snapshot
    elif t == "SNAPSHOT_LOADED":
        tw = _turn(state, ev.campaign_id)
        tw.cursor = p.get("resume_cursor", tw.cursor)
    elif t == "ROLE_ASSIGNED":
        state.roles[p["player_id"]] = {"role_ref": p.get("role_ref"),
                                       "secret_ref": p.get("secret_ref")}
    elif t == "EVIDENCE_DEALT":
        state.clues[p["clue_id"]] = {"act_no": p.get("act_no"),
                                     "location": p.get("location"),
                                     "scope": p.get("scope")}
    elif t == "VOTE_CAST":
        state.votes.append({"player_id": p.get("player_id"),
                            "target": p.get("target_player_id")})
    elif t == "TRUTH_REVEALED":
        state.truth = {"truth_tree_ref": p.get("truth_tree_ref"),
                       "timeline_ref": p.get("timeline_ref")}
    elif t == "NPC_ACT_PROPOSED":
        pass  # pending line candidates; approval event carries the final
    elif t == "NPC_ACT_APPROVED":
        state.npc_lines[p["npc_id"]] = p.get("line", "")
    elif t == "SCENE_UPDATED":
        state.current_scene = p.get("scene_id", "")
        state.scene_trace.append({
            "seq": ev.seq,
            "scene_id": p.get("scene_id", ""),
            "prev_scene_id": p.get("prev_scene_id"),
            "edge_id": p.get("edge_id"),
            "map_id": p.get("map_id"),
            "reason": p.get("reason", "")})
    elif t == "MAP_UPDATED":
        m = state.maps.get(p["map_id"], {"ops": []})
        m["ops"].append({"op": p.get("op"), "target": p.get("target"),
                         "delta": p.get("delta", {})})
        state.maps[p["map_id"]] = m
    elif t in ("CHAT_POLICY_UPDATED", "CHAT_MODE_SET"):
        state.chat_mode = p.get("mode", state.chat_mode)
    elif t == "PRIVATE_MSG":
        state.chats.append({"seq": ev.seq, "from_player": p.get("from_player"),
                           "to_players": list(p.get("to_players") or []),
                           "text": p.get("text", ""),
                           "room_ref": p.get("room_ref")})
    elif t == "NPC_TENDENCY_UPDATED":
        npc_id = p.get("npc_id", "")
        tend = dict(p.get("tendency") or {})
        tend.update({"source": p.get("source", "ai"),
                     "status": "pending" if p.get("source", "ai") == "ai" else "active",
                     "updated_at": ev.ts})
        state.npc_tendencies[npc_id] = tend
    elif t == "NPC_TENDENCY_APPROVED":
        npc_id = p.get("npc_id", "")
        if npc_id in state.npc_tendencies:
            state.npc_tendencies[npc_id]["status"] = "approved"
            state.npc_tendencies[npc_id]["approved_by"] = p.get("approved_by", "")
        else:
            state.npc_tendencies[npc_id] = dict(p.get("tendency") or {})
            state.npc_tendencies[npc_id]["status"] = "approved"
    elif t == "COMBAT_STARTED":
        state.combat = {"combat_id": p.get("combat_id", ""),
                        "status": "running",
                        "round": 0,
                        "participants": list(p.get("participants") or []),
                        "turn_order": [],
                        "pending_resolutions": [],
                        "rounds": {},
                        "rejected_rounds": [],
                        "start_seq": p.get("start_seq", ev.seq),
                        "end_seq": None}
    elif t == "COMBAT_ROUND_PROPOSED":
        c = dict(state.combat)
        c["pending_resolutions"] = list(p.get("resolutions") or [])
        c["round"] = p.get("round", c.get("round", 0))
        c["status"] = "awaiting_approval"
        state.combat = c
    elif t == "COMBAT_ROUND_APPROVED":
        c = dict(state.combat)
        rounds = dict(c.get("rounds") or {})
        rounds[str(p.get("round"))] = list(p.get("resolutions") or [])
        c["rounds"] = rounds
        c["pending_resolutions"] = []
        c["status"] = "running"
        state.combat = c
    elif t == "COMBAT_ROUND_REJECTED":
        c = dict(state.combat)
        rej = list(c.get("rejected_rounds") or [])
        rej.append({"round": p.get("round"), "reason": p.get("reason", "")})
        c["rejected_rounds"] = rej
        c["pending_resolutions"] = []
        c["status"] = "running"
        state.combat = c
    elif t == "COMBAT_ENDED":
        c = dict(state.combat)
        c["status"] = "ended"
        c["end_seq"] = p.get("end_seq", ev.seq)
        state.combat = c
    elif t == "SNAPSHOT_CREATED":
        sid = p.get("snapshot_id", "")
        state.checkpoints[sid] = {"kind": p.get("kind", "auto"),
                                  "seq": p.get("seq", ev.seq),
                                  "label": p.get("label", ""),
                                  "reason": p.get("reason", "")}
    elif t == "CHECKPOINT_TAKEN":
        cid = p.get("checkpoint_id", "")
        state.checkpoints[cid] = {"kind": p.get("kind", "auto"),
                                  "seq": p.get("seq", ev.seq),
                                  "label": p.get("label", ""),
                                  "reason": p.get("reason", ""),
                                  "auto": bool(p.get("auto", False))}
    elif t == "TIMELINE_ROLLBACK":
        state.timeline_branches.append({"target_seq": p.get("target_seq"),
                                        "branch_mark": p.get("branch_mark", ""),
                                        "reason": p.get("reason", ""),
                                        "actor": p.get("actor", "")})
    elif t == "NPC_INFO_GENERATED":
        state.npc_public_infos[p.get("player_id", "")] = list(p.get("public_infos") or [])
    elif t == "PHASE_UPDATED":
        state.phase = p.get("phase", state.phase)
        if p.get("started_seq") is not None:
            state.started_seq = p.get("started_seq")
    elif t in ("TABLE_CREATED", "TABLE_CONFIG_UPDATED", "CAMPAIGN_ARCHIVED"):
        pass  # registry-level; no session mutation
    else:
        raise ValueError("projector: unhandled event type %r" % t)
    state.last_seq = ev.seq
    return state


def project(events: list[GameEvent], campaign_id: str) -> SessionState:
    state = new_session(campaign_id)
    for ev in events:
        reduce(state, ev)
    return state


def states_equal(a: SessionState, b: SessionState) -> bool:
    return a.model_dump(mode="json") == b.model_dump(mode="json")


def state_fingerprint(state: SessionState) -> str:
    import hashlib
    import json

    raw = json.dumps(state.model_dump(mode="json"), sort_keys=True,
                     ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def clone(state: SessionState) -> SessionState:
    return SessionState.model_validate(copy.deepcopy(state.model_dump(mode="json")))