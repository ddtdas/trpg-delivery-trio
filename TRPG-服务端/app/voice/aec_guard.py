"""TRPG AEC guard — broadcast-period self-echo suppression (MIT).

Pure policy: while the table is broadcasting TTS (``broadcasting`` is
True), inbound mic chunks from table speakers are dropped (they are
likely self-echo); explicit player up-links (``is_uplink``) always pass.
Every decision is returned as data with a reason — no silent drops.

Python 3.12 compatible.
"""
from __future__ import annotations

from typing import Any, Mapping

__all__ = ["AECDecision", "aec_should_drop", "AEC_REASONS"]

AEC_REASONS = (
    "pass: uplink always passes",
    "pass: not broadcasting",
    "drop: broadcast self-echo suppression",
    "drop: vad suppressed during broadcast",
)


def aec_should_drop(
    chunk: Mapping[str, Any],
    broadcasting: bool,
    vad_speech: bool = True,
) -> dict:
    """Decide drop/pass for one inbound chunk. Pure function."""
    if not isinstance(chunk, Mapping):
        raise TypeError("chunk must be a mapping")
    if not isinstance(broadcasting, bool):
        raise TypeError("broadcasting must be bool")
    if not isinstance(vad_speech, bool):
        raise TypeError("vad_speech must be bool")
    is_uplink = bool(chunk.get("is_uplink", False))
    if is_uplink:
        return {"drop": False, "reason": AEC_REASONS[0]}
    if not broadcasting:
        return {"drop": False, "reason": AEC_REASONS[1]}
    if not vad_speech:
        return {"drop": True, "reason": AEC_REASONS[3]}
    return {"drop": True, "reason": AEC_REASONS[2]}


class AECDecision:
    """Small stateful guard: tracks broadcast windows for the pipeline."""

    def __init__(self) -> None:
        self.broadcasting = False

    def set_broadcast(self, on: bool) -> None:
        if not isinstance(on, bool):
            raise TypeError("on must be bool")
        self.broadcasting = on

    def filter(self, chunk: Mapping[str, Any], vad_speech: bool = True) -> dict:
        return aec_should_drop(chunk, self.broadcasting, vad_speech)
