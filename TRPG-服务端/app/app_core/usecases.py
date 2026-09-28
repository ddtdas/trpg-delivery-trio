"""TRPG use-cases: map chain + module wiring (MIT).

T26 M9-A incremental layer over command_bus/scheduler: no frozen file
touched, no new event types. Pure validation + delegation.
Python 3.12 compatible.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.app_core.command_bus import CommandBus, CommandError
from app.domain.visibility import can_see_map

__all__ = [
    "MapChainError",
    "submit_map_op",
    "load_module",
    "validate_module",
    "graph_neighbors",
]

MAP_OPS = ("move", "add_token", "set_fog", "set_status", "set_light")
APPROVAL_OPS = ("set_fog", "set_light")


class MapChainError(ValueError):
    """Map chain refused: bad op / missing approval / backend denies."""


async def submit_map_op(bus: CommandBus, map_id: str, op: str, target: str,
                        actor: str = "kp",
                        delta: dict[str, Any] | None = None,
                        approved: bool = False,
                        key: str | None = None) -> dict[str, Any]:
    """Map op via command_bus (single write point); fog/light need approval."""
    if op not in MAP_OPS:
        raise MapChainError("bad op %r" % op)
    if not map_id.strip() or not target.strip():
        raise MapChainError("map_id/target required")
    if op in APPROVAL_OPS and not approved:
        raise MapChainError("map op %r requires approval" % op)
    try:
        return await bus.dispatch(
            "map_update",
            {"map_id": map_id, "op": op, "target": target,
             "delta": dict(delta or {})},
            actor=actor or "kp", key=key)
    except ValueError as exc:
        raise MapChainError(str(exc)) from exc


def submit_map_op_sync(*a: Any, **k: Any) -> dict[str, Any]:  # test helper
    import asyncio

    return asyncio.run(submit_map_op(*a, **k))


def _read_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise MapChainError("missing file: %s" % path)
    except yaml.YAMLError as exc:
        raise MapChainError("bad yaml %s: %s" % (path, exc))


def load_module(module_dir: str | Path) -> dict[str, Any]:
    """Load + cross-check modules/sample_coc manifest vs files on disk."""
    root = Path(module_dir)
    manifest = _read_yaml(root / "module.yaml")
    if not isinstance(manifest, dict) or "id" not in manifest:
        raise MapChainError("module.yaml: id required")
    files = manifest.get("files", {}) if isinstance(manifest, dict) else {}
    graph_p = root / files.get("event_graph", "event_graph.yaml")
    graph = _read_yaml(graph_p)
    nodes = {n.get("id") for n in graph.get("nodes", [])} if isinstance(graph, dict) else set()
    edges = graph.get("edges", []) if isinstance(graph, dict) else []
    for e in edges:
        if e.get("from") not in nodes or e.get("to") not in nodes:
            raise MapChainError("edge %r dangles" % e)
    for rel in list(files.get("npcs", [])) + list(files.get("maps", [])) + [
            files.get("clues", "clues.yaml")]:
        if rel and not (root / rel).is_file():
            raise MapChainError("module file missing: %s" % rel)
    return {"manifest": manifest, "graph": graph,
            "nodes": sorted(n for n in nodes if n),
            "edges": list(edges)}


def validate_module(module_dir: str | Path) -> dict[str, Any]:
    """Strict gate used by e2e: manifest + DAG edges + starting node."""
    loaded = load_module(module_dir)
    manifest, graph = loaded["manifest"], loaded["graph"]
    for key in ("id", "ruleset", "initial_scene"):
        if not manifest.get(key):
            raise MapChainError("module.yaml: %s required" % key)
    if manifest["initial_scene"] not in loaded["nodes"]:
        raise MapChainError("initial_scene not in graph nodes")
    if not isinstance(graph.get("nodes"), list) or not graph["nodes"]:
        raise MapChainError("event_graph: nodes[] required")
    return {"ok": True, "id": manifest["id"], "nodes": len(loaded["nodes"]),
            "edges": len(loaded["edges"])}


def graph_neighbors(graph: dict[str, Any], node_id: str) -> list[str]:
    """Event-graph navigation query: outgoing neighbors of node_id."""
    out = []
    for e in graph.get("edges", []) or []:
        if isinstance(e, dict) and e.get("from") == node_id:
            out.append(e.get("to"))
    return out


__all__ += ["can_see_map"]
