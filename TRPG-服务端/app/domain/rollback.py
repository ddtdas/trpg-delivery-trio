"""Rollback-aware projection (P1-4, T10) -- MIT additive.

After a TIMELINE_ROLLBACK, the server-authoritative projected state must be
the state at the rollback target (not the full stream). This module scans
the event stream for the LAST TIMELINE_ROLLBACK and truncates the events
list to its target_seq, then projects the truncated list.

Writes after the rollback still land in the stream (append-only, alternate
branch semantics per T5 design); consumers using project_with_rollback see
the rolled-back authoritative state, matching what the rollback response's
projected_state shows.
"""
from __future__ import annotations

from typing import Any

from app.store.projector import project


def rollback_target(events: list[Any]) -> int | None:
    """Seq of the latest TIMELINE_ROLLBACK target (None if none)."""
    target: int | None = None
    for ev in events:
        if str(getattr(ev, "type", "")) == "TIMELINE_ROLLBACK":
            target = int((getattr(ev, "payload", {}) or {}).get("target_seq", -1))
    return target


def project_with_rollback(events: list[Any], campaign_id: str) -> Any:
    """Project the stream truncated at the latest rollback target (if any).

    Events after the rollback belong to the alternate branch and are
    excluded from the authoritative projection (they remain in the stream
    for audit/recovery).
    """
    target = rollback_target(events)
    if target is None:
        return project(events, campaign_id)
    truncated = [e for e in events if int(getattr(e, "seq", -1)) <= target]
    return project(truncated, campaign_id)
