"""TRPG AgentSlot — one in-flight proposal at a time (MIT).

Flow: ``draft`` (gateway text -> NARRATION_PROPOSED event object, NOT
persisted) -> KP ``decide`` via approvals -> ``settle`` (slot freed).
The slot never writes to the EventStore itself; the caller persists the
returned event objects through CommandBus/EventStore. LLM text is data,
never a state mutation.

Fault policy: gateway "fault" -> GatewayError propagates and the slot
stays empty (caller may retry); "degraded" template text still becomes
a proposal (clearly marked by the gateway) so the table can proceed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from app.agent import approvals as AP
from app.agent.gateway import GatewayError, GatewayResult, LLMGateway
from app.domain import events as E

__all__ = ["AgentSlot", "SlotBusyError", "SlotEmptyError"]


class SlotBusyError(RuntimeError):
    """A proposal is already in flight; settle it before drafting again."""


class SlotEmptyError(RuntimeError):
    """No proposal in flight to settle."""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentSlot:
    """Single-proposal scheduler around an LLMGateway."""

    def __init__(self, gateway: LLMGateway) -> None:
        if not hasattr(gateway, "complete"):
            raise TypeError("gateway must expose complete()")
        self.gateway = gateway
        self._pending: dict | None = None

    @property
    def has_pending(self) -> bool:
        return self._pending is not None

    @property
    def pending(self) -> dict | None:
        return dict(self._pending) if self._pending is not None else None

    def draft(
        self,
        campaign_id: str,
        messages: Sequence[Mapping[str, Any]],
        proposal_id: str,
        source: str = "agent",
        intention: str | None = None,
        seq: int = 0,
    ) -> Any:
        """Ask the gateway for text and wrap it as NARRATION_PROPOSED.

        Raises SlotBusyError when a proposal is in flight; GatewayError
        on gateway fault (slot stays empty).
        """
        if self._pending is not None:
            raise SlotBusyError("one proposal already in flight")
        if not campaign_id or not isinstance(campaign_id, str):
            raise ValueError("campaign_id must be a non-empty string")
        if not proposal_id or not isinstance(proposal_id, str):
            raise ValueError("proposal_id must be a non-empty string")
        result: GatewayResult = self.gateway.complete(messages)
        payload = {
            "campaign_id": campaign_id,
            "proposal_id": proposal_id,
            "text": result.text,
            "intention": intention,
            "reasoning": f"gateway={self.gateway.name} mode={result.mode}",
            "source": source,
        }
        event = E.make_event(seq, campaign_id, "NARRATION_PROPOSED", payload, "agent", _utcnow())
        self._pending = {
            "proposal_id": proposal_id, "campaign_id": campaign_id,
            "text": result.text, "mode": result.mode,
        }
        return event

    def settle(
        self,
        decision: str,
        actor: Mapping[str, Any] | str | None,
        edited_text: str | None = None,
        seq: int = 0,
    ) -> Any:
        """Apply a KP decision to the in-flight proposal -> result event.

        Frees the slot. Raises SlotEmptyError when nothing is pending;
        ApprovalDenied/ApprovalError propagate (slot stays occupied so
        the KP can retry with a corrected decision).
        """
        if self._pending is None:
            raise SlotEmptyError("no proposal in flight")
        event = AP.decide(self._pending, decision, actor, edited_text, seq=seq)
        self._pending = None
        return event
