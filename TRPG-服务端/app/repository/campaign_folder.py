"""Campaign folder (M6) -- additive, pure-path + JSON (MIT).

Implements the master-plan section-3 layout:

    campaigns/<campaign_id>/
      campaign.json              metadata (name/ruleset/module/current_checkpoint/last_seq)
      players/<player_id>/card.json + state.json
      npcs/<npc_id>/profile.json + tendency.json + state.json
      story/events.jsonl         append-only event stream (rollback truth source)
      story/scenes.json          scene definitions + branches
      story/maps.json            MapDefinition list
      story/relations.json       relations (player<->npc<->scene)
      checkpoints/auto/<ts>-<seq>.snapshot
      checkpoints/manual/<name>-<seq>.snapshot
      .dsh/loop_state.json + suggestions/ + approvals/

Everything is deterministic and path-guarded: campaign_id is validated
(strict identifier), no path traversal, and all writes are UTF-8 JSON.
Python 3.12 compatible.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.config import APP_ROOT

CAMPAIGNS_ROOT = APP_ROOT / "campaigns"

_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


class FolderError(ValueError):
    """Invalid campaign/player/npc id or unsafe path."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check_id(value: str, label: str) -> str:
    v = str(value or "").strip()
    if not _ID_RE.match(v):
        raise FolderError("invalid %s id: %r" % (label, value))
    return v


def campaign_dir(campaign_id: str, *, root: Path | None = None) -> Path:
    """campaigns/<campaign_id> (not created)."""
    cid = _check_id(campaign_id, "campaign")
    base = Path(root) if root is not None else CAMPAIGNS_ROOT
    return base / cid


def ensure_campaign(campaign_id: str, *, root: Path | None = None) -> Path:
    """Create the full folder tree if missing; returns the campaign dir."""
    d = campaign_dir(campaign_id, root=root)
    for sub in ("players", "npcs", "story", "checkpoints/auto", "checkpoints/manual",
                ".dsh/suggestions", ".dsh/approvals"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    meta = d / "campaign.json"
    if not meta.is_file():
        write_campaign_meta(campaign_id, d)
    return d


def list_active_campaigns(*, root: Path | None = None) -> list[str]:
    """campaigns/ 目录下所有带 campaign.json 的活跃团（S2 用于启动 DSH loop）。"""
    base = Path(root) if root is not None else CAMPAIGNS_ROOT
    if not base.is_dir():
        return []
    out = []
    for d in sorted(base.iterdir()):
        if d.is_dir() and (d / "campaign.json").is_file():
            out.append(d.name)
    return out


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8", newline="\n")


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


# ---- campaign.json ----

def write_campaign_meta(campaign_id: str, d: Path | None = None, *, root: Path | None = None, **extra: Any) -> dict[str, Any]:
    d = Path(d) if d is not None else campaign_dir(campaign_id, root=root)
    d.mkdir(parents=True, exist_ok=True)
    meta = {
        "schema": "trpg.campaign.v1",
        "campaign_id": campaign_id,
        "name": extra.get("name", campaign_id),
        "ruleset": extra.get("ruleset", "coc7"),
        "module_id": extra.get("module_id", ""),
        "created_at": extra.get("created_at", _now()),
        "current_checkpoint": extra.get("current_checkpoint", ""),
        "last_seq": int(extra.get("last_seq", -1)),
        "phase": extra.get("phase", "lobby"),
        "started_seq": extra.get("started_seq"),
        "last_started_at": extra.get("last_started_at", ""),
    }
    _write_json(d / "campaign.json", meta)
    return meta


def read_campaign_meta(campaign_id: str, *, root: Path | None = None) -> dict[str, Any]:
    d = campaign_dir(campaign_id, root=root)
    return _read_json(d / "campaign.json", {}) or {}


def update_campaign_meta(campaign_id: str, **fields: Any) -> dict[str, Any]:
    meta = read_campaign_meta(campaign_id)
    meta.update(fields)
    _write_json(campaign_dir(campaign_id) / "campaign.json", meta)
    return meta


# ---- story/events.jsonl (append-only) ----

def append_event(campaign_id: str, event: dict[str, Any], *,
                 root: Path | None = None) -> None:
    """Append one GameEvent dict as a single JSON line (append-only truth)."""
    d = campaign_dir(campaign_id, root=root)
    (d / "story").mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, ensure_ascii=False, sort_keys=True)
    with (d / "story" / "events.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(line + "\n")


def read_events(campaign_id: str, *, upto: int | None = None,
                root: Path | None = None) -> list[dict[str, Any]]:
    """All events, optionally only those with seq <= upto (rollback replay)."""
    p = campaign_dir(campaign_id, root=root) / "story" / "events.jsonl"
    if not p.is_file():
        return []
    out: list[dict[str, Any]] = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            ev = json.loads(raw)
        except ValueError:
            continue
        seq = int(ev.get("seq", -1))
        if upto is not None and seq > upto:
            continue
        out.append(ev)
    return out


# ---- players / npcs ----

def write_player(campaign_id: str, player_id: str, *, card: Any = None,
                 state: Any = None, root: Path | None = None) -> Path:
    pid = _check_id(player_id, "player")
    d = campaign_dir(campaign_id, root=root) / "players" / pid
    d.mkdir(parents=True, exist_ok=True)
    if card is not None:
        _write_json(d / "card.json", card)
    if state is not None:
        _write_json(d / "state.json", state)
    return d


def read_player_state(campaign_id: str, player_id: str, *,
                      root: Path | None = None) -> dict[str, Any]:
    pid = _check_id(player_id, "player")
    return _read_json(campaign_dir(campaign_id, root=root) / "players" / pid / "state.json", {}) or {}


def write_npc(campaign_id: str, npc_id: str, *, profile: Any = None,
              tendency: Any = None, state: Any = None,
              root: Path | None = None) -> Path:
    nid = _check_id(npc_id, "npc")
    d = campaign_dir(campaign_id, root=root) / "npcs" / nid
    d.mkdir(parents=True, exist_ok=True)
    if profile is not None:
        _write_json(d / "profile.json", profile)
    if tendency is not None:
        _write_json(d / "tendency.json", tendency)
    if state is not None:
        _write_json(d / "state.json", state)
    return d


def list_players(campaign_id: str, *, root: Path | None = None) -> list[str]:
    d = campaign_dir(campaign_id, root=root) / "players"
    return sorted(p.name for p in d.iterdir() if p.is_dir()) if d.is_dir() else []


def list_npcs(campaign_id: str, *, root: Path | None = None) -> list[str]:
    d = campaign_dir(campaign_id, root=root) / "npcs"
    return sorted(p.name for p in d.iterdir() if p.is_dir()) if d.is_dir() else []


# ---- story/scenes.json + maps.json + relations.json ----

def write_scenes(campaign_id: str, scenes: Any, *, root: Path | None = None) -> None:
    _write_json(campaign_dir(campaign_id, root=root) / "story" / "scenes.json", scenes)


def write_maps(campaign_id: str, maps: Any, *, root: Path | None = None) -> None:
    _write_json(campaign_dir(campaign_id, root=root) / "story" / "maps.json", maps)


def append_relation(campaign_id: str, rel: dict[str, Any], *,
                    root: Path | None = None) -> None:
    p = campaign_dir(campaign_id, root=root) / "story" / "relations.json"
    data = _read_json(p, []) or []
    data.append(dict(rel))
    _write_json(p, data)


def read_relations(campaign_id: str, *, root: Path | None = None) -> list[dict[str, Any]]:
    return _read_json(campaign_dir(campaign_id, root=root) / "story" / "relations.json", []) or []


# ---- checkpoints (snapshots) ----

def _slug_name(name: str) -> str:
    """File-safe slug from a human label (Chinese OK): keep word chars,
    collapse runs of non-alphanumerics to a single dash, cap length."""
    import re
    n = re.sub(r"[^\w\u4e00-\u9fff]+", "-", str(name or "")).strip("-")
    if not n:
        n = "ckpt"
    return n[:64]


def checkpoint_path(campaign_id: str, kind: str, name: str, seq: int, *,
                    root: Path | None = None) -> Path:
    if kind not in ("auto", "manual"):
        raise FolderError("checkpoint kind must be auto|manual")
    n = _slug_name(name)
    d = campaign_dir(campaign_id, root=root) / "checkpoints" / kind
    d.mkdir(parents=True, exist_ok=True)
    return d / ("%s-%06d.snapshot" % (n, int(seq)))


def write_checkpoint(campaign_id: str, kind: str, name: str, seq: int,
                     snapshot: dict[str, Any], *,
                     root: Path | None = None) -> Path:
    p = checkpoint_path(campaign_id, kind, name, seq, root=root)
    _write_json(p, snapshot)
    return p


def list_checkpoints(campaign_id: str, *, root: Path | None = None) -> list[dict[str, Any]]:
    """All checkpoints (auto+manual) sorted by seq asc."""
    base = campaign_dir(campaign_id, root=root) / "checkpoints"
    out: list[dict[str, Any]] = []
    if not base.is_dir():
        return out
    for kind in ("auto", "manual"):
        kd = base / kind
        if not kd.is_dir():
            continue
        for f in sorted(kd.glob("*.snapshot")):
            data = _read_json(f, {}) or {}
            out.append({"kind": kind, "file": f.name, "path": f.as_posix(),
                        "seq": int(data.get("seq", -1)),
                        "snapshot_id": str(data.get("snapshot_id", "")),
                        "label": str(data.get("label", "")),
                        "reason": str(data.get("reason", ""))})
    out.sort(key=lambda r: (r["seq"], r["kind"]))
    return out


def latest_checkpoint_at_or_before(campaign_id: str, target_seq: int, *,
                                    root: Path | None = None) -> dict[str, Any] | None:
    """The newest checkpoint with seq <= target_seq (manual preferred on tie)."""
    cands = [c for c in list_checkpoints(campaign_id, root=root) if c["seq"] <= int(target_seq)]
    if not cands:
        return None
    cands.sort(key=lambda r: (r["seq"], 1 if r["kind"] == "manual" else 0))
    return cands[-1]


def read_checkpoint(campaign_id: str, kind: str, file_name: str, *,
                    root: Path | None = None) -> dict[str, Any]:
    base = campaign_dir(campaign_id, root=root) / "checkpoints" / kind
    name = Path(file_name).name  # guard: never accept a path
    data = _read_json(base / name, {}) or {}
    return data


# ---- .dsh workspace ----

def write_dsh_state(campaign_id: str, data: dict[str, Any], *,
                    root: Path | None = None) -> Path:
    p = campaign_dir(campaign_id, root=root) / ".dsh" / "loop_state.json"
    _write_json(p, data)
    return p


def read_dsh_state(campaign_id: str, *, root: Path | None = None) -> dict[str, Any]:
    return _read_json(campaign_dir(campaign_id, root=root) / ".dsh" / "loop_state.json", {}) or {}


def write_dsh_record(campaign_id: str, bucket: str, name: str, data: Any, *,
                     root: Path | None = None) -> Path:
    if bucket not in ("suggestions", "approvals"):
        raise FolderError("dsh bucket must be suggestions|approvals")
    n = _check_id(name, "dsh record")
    p = campaign_dir(campaign_id, root=root) / ".dsh" / bucket / (n + ".json")
    _write_json(p, data)
    return p


# ---- custom scenes (P1b: real persistence for create/update/delete) ----

def read_custom_scenes(campaign_id: str, *, root: Path | None = None) -> dict[str, dict[str, Any]]:
    """Player-created (non-graph) scenes: {scene_id: {..}}. JSON file."""
    return _read_json(campaign_dir(campaign_id, root=root) / "story" / "custom_scenes.json", {}) or {}


def write_custom_scene(campaign_id: str, scene: dict[str, Any], *,
                       root: Path | None = None) -> None:
    scenes = read_custom_scenes(campaign_id, root=root)
    scenes[str(scene.get("scene_id") or "")] = dict(scene)
    _write_json(campaign_dir(campaign_id, root=root) / "story" / "custom_scenes.json", scenes)


def delete_custom_scene(campaign_id: str, scene_id: str, *,
                        root: Path | None = None) -> bool:
    scenes = read_custom_scenes(campaign_id, root=root)
    if scene_id in scenes:
        del scenes[scene_id]
        _write_json(campaign_dir(campaign_id, root=root) / "story" / "custom_scenes.json", scenes)
        return True
    return False
