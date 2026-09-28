"""galaxy-decision 裁决子模块 — W-C2 implementation (DESIGN §1.5/§2.5).

Subroutine of loop S3: hit a KP preset decision point -> structured ruling
slip (dict, §2.5 schema). Read-only over scene/rule sources, never writes
the world book; uncertain cases are marked kp_needed.

Frozen schema keys: decision_id/trigger/context/ruling/dice/broadcast/replay_ptr.
Hard constraints (enforced, ValueError on violation):
  * ruling.type=kp_needed  -> broadcast MUST start with "需 KP 拍板："
  * dice.needed=true       -> rolled/outcome are filled BEFORE broadcast text
    is composed (dice always precede narration, §2.2 global invariant).
Python 3.12 compatible, stdlib only.
"""
from __future__ import annotations

import copy
import json
import random
from pathlib import Path
from typing import Any

RULING_TYPES: tuple[str, ...] = (
    "auto_success",
    "check",
    "opposed",
    "branch_lock",
    "kp_needed",
)

# Ruling types that require a dice roll before narration.
_DICE_TYPES: tuple[str, ...] = ("check", "opposed")

KP_PREFIX = "需 KP 拍板："

_seq_counter = 0


def _next_seq() -> int:
    global _seq_counter
    _seq_counter += 1
    return _seq_counter


def _resolve_log_path() -> Path:
    """Workspace log: <ws>/trpg_agent/research/galaxy_decision_log.md.

    Walk up from this file until a directory containing trpg_agent/ is
    found (dev mirror lives at <ws>/trpg_run/dev/trpg). Fallback to the
    repo-local var/ dir so decide() never fails for lack of a log home.
    """
    here = Path(__file__).resolve()
    for parent in (here.parent, *here.parents):
        cand = parent / "trpg_agent" / "research"
        if cand.is_dir():
            return cand / "galaxy_decision_log.md"
        if (parent / "trpg_agent").is_dir():
            d = parent / "trpg_agent" / "research"
            d.mkdir(parents=True, exist_ok=True)
            return d / "galaxy_decision_log.md"
    fallback = here.parents[2] / "var"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback / "galaxy_decision_log.md"


def _roll_d100(seed: Any = None, rng: Any = None) -> int:
    if rng is not None:
        return rng.randint(1, 100)
    if seed is not None:
        return random.Random(seed).randint(1, 100)
    return random.randint(1, 100)


def _outcome(rolled: int, target: int) -> str:
    if rolled == 1:
        return "critical_success"
    if rolled == 100:
        return "fumble"
    return "success" if rolled <= target else "fail"


def decide(
    point: Any = None,
    scene: Any = None,
    declaration: str = "",
    *,
    point_id: str | None = None,
    context: dict[str, Any] | None = None,
    round_no: int | None = None,
    seq: int | None = None,
    seed: Any = None,
    rng: Any = None,
    log_path: Any = "auto",
) -> dict[str, Any]:
    """Hit a KP decision point -> structured ruling slip (§2.5 schema).

    New signature: decide(point, scene, declaration).
      point: dict{point_id|id, matched|trigger, round, ruling{type, skill,
        difficulty, cost, fail_result}, dice{needed, expr, target},
        broadcast?, replay_ptr?} or a bare point_id string.
      scene: dict{scene_id, round} or a bare scene_id string.
      declaration: PC action declaration string.
    Old stub signature decide(point_id, context) is still accepted:
      decide("p1", {...}) maps to point="p1", scene-as-context.
    """
    # -- backward compat: decide(point_id_str, context_dict) -----------------
    ctx: dict[str, Any] = dict(context) if isinstance(context, dict) else {}
    if isinstance(scene, dict) and point is not None and not isinstance(point, dict):
        # Old shape: decide("p1", {...}) -> scene slot holds the context.
        ctx = {**scene, **ctx}
        scene = None
    if isinstance(point, str):
        point = {"point_id": point}
    point = dict(point) if isinstance(point, dict) else {}
    if point_id is not None:
        point.setdefault("point_id", point_id)

    scene_d: dict[str, Any] = {}
    if isinstance(scene, dict):
        scene_d = scene
    elif isinstance(scene, str):
        scene_d = {"scene_id": scene}

    pc = str(point.get("pc") or scene_d.get("pc") or ctx.get("pc") or "")
    decl = str(declaration or point.get("declaration")
               or scene_d.get("declaration") or ctx.get("declaration") or "")
    scene_id = str(point.get("scene_id") or scene_d.get("scene_id")
                   or ctx.get("scene_id") or "")
    rnd = round_no
    if rnd is None:
        rnd = point.get("round", scene_d.get("round", ctx.get("round", 0)))
    try:
        rnd = int(rnd)
    except (TypeError, ValueError):
        rnd = 0

    # -- ruling ----------------------------------------------------------------
    raw_ruling = point.get("ruling")
    ruling_d = dict(raw_ruling) if isinstance(raw_ruling, dict) else {}
    rtype = str(point.get("type") or ruling_d.get("type") or "kp_needed")
    if rtype not in RULING_TYPES:
        raise ValueError(f"unknown ruling type: {rtype!r} (want one of {list(RULING_TYPES)})")
    skill = ruling_d.get("skill")
    difficulty = ruling_d.get("difficulty")
    cost = ruling_d.get("cost")
    fail_result = str(ruling_d.get("fail_result")
                      or point.get("fail_result") or "")

    # -- dice (rolled BEFORE broadcast is composed) -----------------------------
    raw_dice = point.get("dice")
    dice_d = dict(raw_dice) if isinstance(raw_dice, dict) else {}
    needed = dice_d.get("needed")
    if needed is None:
        needed = rtype in _DICE_TYPES
    needed = bool(needed)
    expr = str(dice_d.get("expr") or "1d100")
    target = dice_d.get("target", point.get("target", 50))
    try:
        target = int(target)
    except (TypeError, ValueError):
        target = 50
    rolled: Any = None
    outcome: Any = None
    if needed:
        if dice_d.get("rolled") is not None and dice_d.get("outcome"):
            rolled, outcome = int(dice_d["rolled"]), str(dice_d["outcome"])
        else:
            rolled = _roll_d100(seed=seed, rng=rng)
            outcome = _outcome(rolled, target)

    # -- broadcast (dice already known here: 骰先行) ------------------------------
    matched = str(point.get("matched") or point.get("trigger") or "")
    template = point.get("broadcast")
    if template is not None:
        broadcast = str(template)
    elif rtype == "auto_success":
        broadcast = f"【自动成功】{decl}——无需检定，直接成功。"
    elif rtype == "check":
        skill_txt = skill or "检定"
        broadcast = (f"【检定】{skill_txt}（目标{target}）：掷出{rolled}，{outcome}。"
                     f"{decl}")
    elif rtype == "opposed":
        skill_txt = skill or "对抗"
        broadcast = (f"【对抗】{skill_txt}（目标{target}）：掷出{rolled}，{outcome}。"
                     f"{decl}")
    elif rtype == "branch_lock":
        broadcast = f"【分支锁定】{matched or decl}——剧情分支已锁定，按锁定线推进。"
    else:  # kp_needed
        reason = matched or decl or "情况超出预设，无法自动裁定"
        broadcast = f"{KP_PREFIX}{reason}，请 KP 定夺。"
    if rtype == "kp_needed" and not broadcast.startswith(KP_PREFIX):
        broadcast = f"{KP_PREFIX}{broadcast}"

    seq_no = seq if seq is not None else _next_seq()
    decision_id = f"gd-{rnd}-{seq_no}"
    slip: dict[str, Any] = {
        "decision_id": decision_id,
        "trigger": {
            "point_id": str(point.get("point_id") or point.get("id") or ""),
            "matched": matched,
            "round": rnd,
        },
        "context": {"scene_id": scene_id, "pc": pc, "declaration": decl},
        "ruling": {
            "type": rtype,
            "skill": skill,
            "difficulty": difficulty,
            "cost": cost,
            "fail_result": fail_result,
        },
        "dice": {
            "needed": needed,
            "expr": expr,
            "target": target,
            "rolled": rolled,
            "outcome": outcome,
        },
        "broadcast": broadcast,
        "replay_ptr": str(point.get("replay_ptr") or f"ruling:{decision_id}"),
    }
    _validate(slip)

    # -- append-only log (JSONL, one line per ruling) -----------------------------
    if log_path != "skip":
        path = Path(log_path) if isinstance(log_path, (str, Path)) and log_path != "auto" else _resolve_log_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(slip, ensure_ascii=False) + "\n")
        except OSError:
            pass  # best-effort: a ruling must never fail for lack of a log
    return copy.deepcopy(slip)


def _validate(slip: dict[str, Any]) -> None:
    """Enforce frozen §2.5 hard constraints; raise ValueError on violation."""
    for key in ("decision_id", "trigger", "context", "ruling",
                "dice", "broadcast", "replay_ptr"):
        if key not in slip:
            raise ValueError(f"ruling slip missing key: {key}")
    rtype = slip["ruling"].get("type")
    if rtype not in RULING_TYPES:
        raise ValueError(f"unknown ruling type: {rtype!r}")
    if rtype == "kp_needed" and not str(slip["broadcast"]).startswith(KP_PREFIX):
        raise ValueError("kp_needed broadcast must start with '需 KP 拍板：'")
    dice = slip["dice"]
    if dice.get("needed"):
        rolled, outcome = dice.get("rolled"), dice.get("outcome")
        if not isinstance(rolled, int) or not 1 <= rolled <= 100:
            raise ValueError("dice.needed=true requires rolled in 1..100")
        if not isinstance(outcome, str) or not outcome:
            raise ValueError("dice.needed=true requires non-empty outcome")


def validate(slip: dict[str, Any]) -> bool:
    """Public validator: True iff the slip satisfies §2.5 constraints."""
    _validate(slip)
    return True
