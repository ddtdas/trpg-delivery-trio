"""TRPG MCP schemas - FROZEN (MIT).

Source: docs/contracts/mcp-contract.md v1.0 (t4 frozen) §3.
13 tool names + input/output skeletons. Any change requires a contract
change (merge back + broadcast). Python 3.12 compatible.
"""
from __future__ import annotations

from typing import Any, Literal

SERVER_NAME = "trpg"
MCP_PATH = "/mcp"

RAW_NAMES: tuple[str, ...] = (
    "character_create",
    "roll_check",
    "roll_preview",
    "event_inject",
    "narration_propose",
    "narration_approve",
    "info_distribute",
    "transcribe_audio",
    "image_generate",
    "map_command",
    "summarize_session",
    "session_state",
    "job_get_status",
)

FROZEN_NAMES: tuple[str, ...] = tuple("mcp__trpg__%s" % n for n in RAW_NAMES)

NPC_ACT_NAME = "mcp__trpg__npc_act"  # R2 (R30): 门开时可用; TRPG_NPC_GATE=locked 回锁 403

ALL_NAMES: tuple[str, ...] = FROZEN_NAMES + (NPC_ACT_NAME,)

NARRATION_DECISION = ("approve", "edit", "reject")
INFO_SCOPES = ("public", "whisper", "hidden", "condition")
MAP_OPS = ("get", "move", "add_token", "set_fog", "set_status", "set_light")
COMMAND_TYPES = ("roll_check", "map", "quick")
JOB_STATUSES = ("queued", "running", "done", "failed")

# Input skeletons per mcp-contract §3 (required keys; ? = optional).
INPUT_SKELETONS: dict[str, dict[str, Any]] = {
    "character_create": {"actor": {"id": "str", "token?": "str"},
                         "ruleset": "str",
                         "card": {"attrs": "{}", "skills": "{}",
                                  "background": "str", "secret_ref?": "str"}},
    "roll_check": {"actor": {"id": "kp", "token": "str"},
                   "campaign_id": "str", "turn_no": "int", "card_id": "str",
                   "target": "str", "difficulty": "int",
                   "bonus?": "int", "penalty?": "int", "seed": "str"},
    "roll_preview": {"campaign_id": "str", "card_id": "str", "target": "str",
                     "difficulty": "int", "bonus?": "int", "penalty?": "int"},
    "event_inject": {"actor": {"id": "kp", "token": "str"},
                     "campaign_id": "str", "node_id": "str",
                     "payload": "{}", "dry_run": "bool"},
    "narration_propose": {"actor": {"id": "str"}, "campaign_id": "str",
                          "text": "str", "intention?": "str",
                          "reasoning": "str", "source": "agent|dsh"},
    "narration_approve": {"actor": {"id": "kp", "token": "str"},
                          "proposal_id": "str",
                          "decision": "approve|edit|reject",
                          "edited_text?": "str", "diff?": "{}"},
    "info_distribute": {"actor": {"id": "kp", "token": "str"},
                        "campaign_id": "str", "info_id": "str",
                        "scope": "public|whisper|condition",
                        "targets": "[]", "body_ref": "str"},
    "transcribe_audio": {"actor": {"id": "kp", "token": "str"},
                         "campaign_id": "str", "audio_ref": "str",
                         "speaker?": "str"},
    "image_generate": {"actor": {"id": "str", "token?": "str"},
                       "card_id?": "str", "prompt": "str",
                       "style?": "str", "engine?": "str"},
    "map_command": {"actor": {"id": "str", "token?": "str"},
                    "campaign_id": "str", "map_id": "str",
                    "op": "get|move|add_token|set_fog|set_status|set_light",
                    "target?": "str", "delta?": "{}"},
    "summarize_session": {"actor": {"id": "kp", "token": "str"},
                          "campaign_id": "str", "anonymize?": "bool"},
    "session_state": {"campaign_id": "str"},
    "job_get_status": {"actor": {"id": "str"}, "job_id": "str"},
    "npc_act": {"actor": {"id": "str"}, "campaign_id": "str",
                "npc_id": "str", "lines?": "[]"},
}

# Output skeletons per mcp-contract §3.
OUTPUT_SKELETONS: dict[str, dict[str, Any]] = {
    "character_create": {"ok": True, "card_id": "str",
                         "validation_report": {"ok": "bool", "errors": "[]"}},
    "roll_check": {"ok": True, "rolled": "[]", "total": "int",
                   "level": "str", "seed": "str"},
    "roll_preview": {"total": "int", "level": "str",
                     "note": "preview-only"},
    "event_inject": {"ok?": True, "dry_run_result?": "{}",
                     "events?": "[{seq,type}]"},
    "narration_propose": {"ok": True, "proposal_id": "str"},
    "narration_approve": {"ok": True, "events": "[{seq,type}]"},
    "info_distribute": {"ok": True, "events": "[{seq,type}]"},
    "transcribe_audio": {"ok": True, "job_id": "str"},
    "image_generate": {"ok": True, "job_id": "str"},
    "map_command": {"ok": True, "result?": "{}", "events?": "[{seq,type}]"},
    "summarize_session": {"ok": True, "job_id": "str"},
    "session_state": {"campaign_id": "str", "event_seq": "int",
                      "projected_hash": "str", "pending_approvals": "[]",
                      "turn_cursor": "str"},
    "job_get_status": {"job_id": "str",
                       "status": "queued|running|done|failed",
                       "result_ref?": "str"},
    # R2 (R30/R31): 成功体 = 候选入主持人待审队列（不回显候选台词）。
    # 门关闭时仍为 403 {"error": "npc_forbidden"}。
    "npc_act": {"seq": "int", "type": "NPC_ACT_PROPOSED",
                "proposal_id": "str", "npc_id": "str",
                "status": "pending", "visible_to_players": False,
                "note": "str"},
}

# Write tools per security-sync §2 (public-read / player-write / kp-write).
WRITE_TOOLS: frozenset[str] = frozenset({
    "character_create", "roll_check", "event_inject", "narration_propose",
    "narration_approve", "info_distribute", "transcribe_audio",
    "image_generate", "summarize_session",
})

KP_TOOLS: frozenset[str] = frozenset({
    "roll_check", "event_inject", "narration_approve", "info_distribute",
    "transcribe_audio", "map_command_write", "summarize_session",
})

Role = Literal["kp", "pl", "spectator"]


def frozen_name(raw: str) -> str:
    return "mcp__trpg__%s" % raw


def tool_spec(raw: str) -> dict[str, Any]:
    """Full tool descriptor for tools/list."""
    return {"name": frozen_name(raw),
            "description": OUTPUT_SKELETONS.get(raw, {}).get("note", raw),
            "inputSchema": {"type": "object",
                            "properties": INPUT_SKELETONS[raw]},
            "outputSchema": {"type": "object",
                             "properties": OUTPUT_SKELETONS[raw]}}
