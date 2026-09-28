"""Branch guard: idempotency + loop-guard + conflict rollback (MIT).

- Idempotency: every command carries an idempotency key; a repeated key
  returns the original receipt without emitting new events.
- Loop-guard: causal chains longer than max_depth, or a node revisited
  more than max_visits within one causal chain, are rejected before any
  write (prevents EventGraph cascade loops).
- Conflict: same-window concurrent submissions for the same player with
  different payloads are detected; the second submit is rejected and the
  caller must withdraw-then-resubmit (rollback semantics = withdraw).
Python 3.12 compatible.
"""
from __future__ import annotations

import copy
import json
from typing import Any


class BranchViolation(ValueError):
    """Raised when the branch guard blocks a command."""


class DuplicateCommand(ValueError):
    """Raised when the idempotency key was already consumed with the SAME
    payload (treated as success-replay by command_bus; this error type lets
    callers distinguish it from a payload conflict)."""


class ConflictError(ValueError):
    """Same idempotency key reused with a DIFFERENT payload, or a
    same-window concurrent submit conflict."""


def _canon_key(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


class BranchGuard:
    def __init__(self, max_depth: int = 8, max_visits: int = 2) -> None:
        self.max_depth = max_depth
        self.max_visits = max_visits
        self._keys: dict[str, dict[str, Any]] = {}

    # -- idempotency --

    def check_key(self, key: str, payload: dict[str, Any]) -> None:
        """Raise DuplicateCommand (same payload) or ConflictError (changed).

        Comparison is on the canonical JSON (sorted keys): key order,
        dict aliasing, or later caller mutation can never fork the result.
        """
        if key in self._keys:
            if self._keys[key].get("_canon") == _canon_key(payload):
                raise DuplicateCommand("duplicate key %r: replay" % key)
            raise ConflictError("idempotency key %r reused with new payload" % key)

    def record_key(self, key: str, payload: dict[str, Any],
                   receipt: dict[str, Any]) -> None:
        stored = copy.deepcopy(dict(payload))
        stored["_receipt"] = copy.deepcopy(dict(receipt))
        stored["_canon"] = _canon_key(payload)
        self._keys[key] = stored

    def receipt_for(self, key: str) -> dict[str, Any] | None:
        entry = self._keys.get(key)
        if entry is None:
            return None
        rec = entry.get("_receipt")
        if not isinstance(rec, dict):
            return {}
        return dict(rec)

    # -- loop guard --

    def check_causal(self, causal: list[str], node_id: str | None = None) -> None:
        chain = list(causal or [])
        if node_id is not None:
            chain = chain + [node_id]
        if len(chain) > self.max_depth:
            raise BranchViolation(
                "causal chain too deep (%d > %d)" % (len(chain), self.max_depth))
        seen: dict[str, int] = {}
        for node in chain:
            seen[node] = seen.get(node, 0) + 1
            if seen[node] > self.max_visits:
                raise BranchViolation("loop detected at node %r" % node)

    # -- same-window submit conflict --

    @staticmethod
    def check_submit_conflict(submitted: dict[str, Any], player_id: str,
                              new_action: dict[str, Any]) -> None:
        """A second *different* action in the same open window conflicts.

        Same action resubmitted is harmless (idempotent) and passes.
        """
        cur = submitted.get(player_id)
        if cur is None:
            return
        old = cur.get("action", {}) if isinstance(cur, dict) else cur
        if old != new_action:
            raise ConflictError(
                "player %r already submitted this window; withdraw first" % player_id)

    def reset(self) -> None:
        self._keys.clear()
