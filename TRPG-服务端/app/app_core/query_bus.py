"""Query bus: read-only views over the server projection (MIT).

Never touches the store directly for writes; every answer is derived
from SessionState + visibility filtering. Python 3.12 compatible.
"""
from __future__ import annotations

from typing import Any

from app.domain.model import SessionState
from app.domain.visibility import filter_state_for, visible_infos


class QueryBus:
    def __init__(self, state: SessionState) -> None:
        self._state = state

    @property
    def state(self) -> SessionState:
        return self._state

    def ask(self, name: str, viewer: str = "kp",
            is_kp: bool = False, **kwargs: Any) -> Any:
        handler = getattr(self, "q_" + name, None)
        if handler is None:
            raise KeyError("unknown query: %r" % name)
        return handler(viewer=viewer, is_kp=is_kp, **kwargs)

    # -- queries --

    def q_session_state(self, viewer: str, is_kp: bool = False) -> dict:
        return filter_state_for(self._state, viewer, is_kp)

    def q_turn(self, viewer: str, is_kp: bool = False) -> dict:
        t = self._state.turn
        if t is None:
            return {"state": "IDLE", "turn_no": 0}
        return {"state": t.state, "turn_no": t.turn_no,
                "submitted": len(t.submitted), "order": list(t.order),
                "cursor": t.cursor,
                "countdown_end_ts": t.countdown_end_ts}

    def q_infos(self, viewer: str, is_kp: bool = False) -> dict:
        return visible_infos(self._state, viewer, is_kp)

    def q_approvals(self, viewer: str, is_kp: bool = False) -> dict:
        if not is_kp:
            return {}
        return {k: v.model_dump(mode="json")
                for k, v in self._state.approvals.items()
                if v.status == "pending"}

    def q_checks(self, viewer: str, is_kp: bool = False) -> list:
        return list(self._state.checks)
