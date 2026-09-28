"""TRPG MCP auth - FROZEN (MIT).

Source: docs/contracts/security-sync.md v1.0 §1/§2 (t4 frozen).
Server entry guards _require_kp / _require_actor.
R2 (R30/R31): npc_act is gated by NPC_GATE_OPEN —— 默认 open，
TRPG_NPC_GATE=locked 可逐字恢复旧 403 语义（npc_forbidden）。
契约变更已登记于 docs/R2-NPC-CONTRACT-CHANGE.md。Python 3.12 compatible.
"""
from __future__ import annotations

import hmac
import os
import secrets
from typing import Any

TOKENS: dict[str, str] = {}  # table_id -> table_token (server-side only)

NPC_GATE_OPEN = (os.environ.get("TRPG_NPC_GATE", "open").strip().lower()
                 != "locked")  # R2: 默认 open; "locked" 恢复旧 403


class AuthError(ValueError):
    def __init__(self, error: str) -> None:
        super().__init__(error)
        self.error = error


def register_table_token(table_id: str, token: str = "") -> str:
    tok = token or ("tt_" + secrets.token_hex(12))
    TOKENS[table_id] = tok
    return tok


def actor_of(args: dict[str, Any]) -> dict[str, Any]:
    actor = args.get("actor")
    if not isinstance(actor, dict) or not str(actor.get("id", "")).strip():
        raise AuthError("actor_required")
    return actor


def _require_actor(args: dict[str, Any]) -> dict[str, Any]:
    return actor_of(args)


def _require_kp(args: dict[str, Any], table_id: str = "") -> dict[str, Any]:
    actor = actor_of(args)
    if actor.get("id") != "kp":
        raise AuthError("actor_required")
    token = str(actor.get("token") or "")
    if not token:
        raise AuthError("kp_token_required")
    if table_id and table_id in TOKENS:
        if not hmac.compare_digest(token, TOKENS[table_id]):
            raise AuthError("kp_token_required")
    return actor


# ---- 13x3 permission matrix (security-sync §2) ----
# value: "kp" (KP+token) | "actor" (any authed actor) | "public" (no token)
TOOL_ACCESS: dict[str, str] = {
    "character_create": "actor",
    "roll_check": "kp",
    "roll_preview": "public",
    "event_inject": "kp",
    "narration_propose": "actor",
    "narration_approve": "kp",
    "info_distribute": "kp",
    "transcribe_audio": "kp",
    "image_generate": "actor",
    "map_command": "mixed",  # op=get public-ish; writes kp (checked in tool)
    "summarize_session": "kp",
    "session_state": "public",
    "job_get_status": "actor",
    # R2 (R30): 门开时按 actor 放行（候选仍必须先过主持人）；门关时下方
    # gate 分支抛 npc_forbidden，与改造前 403 语义逐字一致。
    "npc_act": "actor",
}


def check_tool_access(raw: str, args: dict[str, Any],
                      table_id: str = "") -> dict[str, Any] | None:
    """Enforce the matrix. Returns authed actor or None for public tools.
    Raises AuthError -> 403 {error}."""
    # R2: 原实现是恒真式（raw == "npc_act" or (gate is False and raw == "npc_act")），
    # 导致无论开关如何都 403。现改为真正的开关判定。
    if raw == "npc_act" and not NPC_GATE_OPEN:
        raise AuthError("npc_forbidden")
    access = TOOL_ACCESS.get(raw)
    if access is None:
        raise AuthError("unknown_tool")
    if access == "public":
        return None
    if access == "kp":
        return _require_kp(args, table_id)
    if access == "actor":
        return _require_actor(args)
    if access == "mixed":
        return None  # tool-level: reads open, writes require kp
    raise AuthError("unknown_tool")


def is_kp(args: dict[str, Any], table_id: str = "") -> bool:
    try:
        _require_kp(args, table_id)
        return True
    except AuthError:
        return False
