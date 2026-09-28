"""TRPG approvals chain (MIT).

KP approve / reject / edit for narration proposals. Pure domain logic:
this module builds the *result events* — persistence stays with the
caller (CommandBus/EventStore). Permission checks follow
docs/contracts/security-sync.md: only KP (holder of table token) may
approve; everyone else gets 403-style denial data, never an exception
that leaks whether the proposal exists.

Decisions: "approve" -> NARRATION_APPROVED, "edit" -> NARRATION_EDITED
(with diff), "reject" -> NARRATION_REJECTED.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Mapping

from app.domain import events as E

Decision = Literal["approve", "edit", "reject"]

KP_ACTOR = "kp"

__all__ = [
    "ApprovalDenied",
    "ApprovalError",
    "require_kp",
    "decide",
    "KP_ACTOR",
]


class ApprovalDenied(ValueError):
    """Raised when a non-KP actor attempts approval (maps to 403)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code  # "kp_token_required" | "actor_required"


class ApprovalError(ValueError):
    """Raised on malformed approval inputs (decision unknown, empty text...)."""


def require_kp(actor: Mapping[str, Any] | str | None) -> str:
    """Validate the approver is KP. Returns the kp actor id.

    ``actor`` may be "kp", {"id": "kp", "token": ...} (token presence
    checked, value never inspected here — server compares it), or None.
    Anything else raises ApprovalDenied (403 surface).
    """
    if actor is None:
        raise ApprovalDenied("actor_required")
    ident = actor if isinstance(actor, str) else actor.get("id")
    token = None if isinstance(actor, str) else actor.get("token")
    if ident != KP_ACTOR:
        raise ApprovalDenied("actor_required")
    if isinstance(actor, Mapping) and not token:
        raise ApprovalDenied("kp_token_required")
    return KP_ACTOR


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def decide(
    proposal: Mapping[str, Any],
    decision: str,
    actor: Mapping[str, Any] | str | None,
    edited_text: str | None = None,
    seq: int = 0,
) -> Any:
    """Apply a KP decision to a proposal dict -> result GameEvent.

    ``proposal`` must carry proposal_id + campaign_id (+ text for edits).
    Never mutates ``proposal``. Non-KP actors -> ApprovalDenied.
    Unknown decisions / empty edits -> ApprovalError.
    """
    kp = require_kp(actor)
    if not isinstance(proposal, Mapping):
        raise ApprovalError("proposal must be a mapping")
    proposal_id = proposal.get("proposal_id")
    campaign_id = proposal.get("campaign_id")
    if not proposal_id or not isinstance(proposal_id, str):
        raise ApprovalError("proposal missing proposal_id")
    if not campaign_id or not isinstance(campaign_id, str):
        raise ApprovalError("proposal missing campaign_id")
    if decision == "approve":
        payload = {"proposal_id": proposal_id, "text": proposal.get("text", "")}
        if not isinstance(payload["text"], str) or not payload["text"].strip():
            raise ApprovalError("proposal text empty: cannot approve")
        return E.make_event(seq, campaign_id, "NARRATION_APPROVED", payload, kp, _utcnow(), approved_by=kp)
    if decision == "edit":
        if not isinstance(edited_text, str) or not edited_text.strip():
            raise ApprovalError("edited_text must be non-empty for edit")
        old = str(proposal.get("text", ""))
        payload = {
            "proposal_id": proposal_id,
            "text": edited_text.strip(),
            "diff": {"from": old, "to": edited_text.strip()},
        }
        return E.make_event(seq, campaign_id, "NARRATION_EDITED", payload, kp, _utcnow(), approved_by=kp)
    if decision == "reject":
        reason = edited_text if isinstance(edited_text, str) and edited_text.strip() else "rejected by host"
        payload = {"proposal_id": proposal_id, "reason": reason}
        return E.make_event(seq, campaign_id, "NARRATION_REJECTED", payload, kp, _utcnow(), approved_by=kp)
    raise ApprovalError(f"unknown decision: {decision!r}")