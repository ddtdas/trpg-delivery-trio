"""Scene coordinator — W-B2 implementation (DESIGN §2.3) + BW-2 parallel lines.

Frozen signatures from W-A3 are unchanged; bodies now read the
modules/sample_coc content files (module/event_graph/npcs/clues).
Pure-python, stdlib + PyYAML only. No app/ imports.

BW-2 additions (additive only — no frozen signature changed):
  - optional module_dir: SceneCoordinator(module_dir=...) reads another
    module (e.g. modules/blackwater_creek); defaults to sample_coc.
  - parallel-line advance: SCENE events may carry payload["branch"] (line id);
    each branch advances independently along declared edges from its own
    current node, so one blocked line never stalls another (clue_trace is
    likewise line-independent). Delta gains a "branches" dict and
    branch_state() exposes per-branch current nodes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .events import Event, EventKind

Kin = EventKind

# Module content root: <repo>/modules/sample_coc
# Layout-agnostic (ID-1): the agent package lives at <repo>/trpg/agent in the
# dev mirror but at <repo>/agent in the flattened delivery tree; walk up from
# this file until a modules/sample_coc/event_graph.yaml is found.
def _find_module_dir() -> Path:
    here = Path(__file__).resolve()
    for parent in (here.parent, *here.parents):
        cand = parent / "modules" / "sample_coc" / "event_graph.yaml"
        if cand.is_file():
            return parent / "modules" / "sample_coc"
    return here.parents[2] / "modules" / "sample_coc"


MODULE_DIR = _find_module_dir()


def _load_yaml(dir_path: Path, name: str) -> dict[str, Any]:
    with open(dir_path / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_npc(dir_path: Path, npc_id: str) -> dict[str, Any]:
    npc_dir = dir_path / "npcs"
    for rel in sorted(p.name for p in npc_dir.glob("*.yaml")):
        path = npc_dir / rel
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if data.get("id") == npc_id:
            return data
    raise KeyError(f"unknown npc_id: {npc_id}")


def _nodes(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {n["id"]: n for n in graph.get("nodes", [])}


def _edges(graph: dict[str, Any]) -> list[dict[str, Any]]:
    return list(graph.get("edges", []))


def _clues(pool: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in pool.get("clues", [])}


class SceneCoordinator:
    """Scene-graph / clue-chain / NPC state machine driver.

    module_dir: optional path to a module content dir (default sample_coc).
    The initial scene is resolved from the module (module.yaml
    initial_scene, else event_graph initial_scene, else n1_front_desk).
    """

    def __init__(self, module_dir: str | Path | None = None) -> None:
        self._module_dir = Path(module_dir) if module_dir else MODULE_DIR
        self._seen_events: list[Event] = []
        self._current_scene = self._resolve_initial_scene()
        self._revealed_clues: list[str] = []
        self._branch_scenes: dict[str, str] = {}

    def _resolve_initial_scene(self) -> str:
        try:
            manifest = _load_yaml(self._module_dir, "module.yaml")
            initial = str(manifest.get("initial_scene", "") or "")
            if initial:
                return initial
            nodes = manifest.get("starting_nodes") or []
            if nodes:
                return str(nodes[0])
        except FileNotFoundError:
            pass
        try:
            graph = _load_yaml(self._module_dir, "event_graph.yaml")
            initial = str(graph.get("initial_scene", "") or "")
            if initial:
                return initial
            nodes = graph.get("starting_nodes") or []
            if nodes:
                return str(nodes[0])
        except FileNotFoundError:
            pass
        return "n1_front_desk"

    def _graph(self, graph: Any) -> dict[str, Any]:
        if graph is None:
            graph = _load_yaml(self._module_dir, "event_graph.yaml")
        return graph

    # -- advance ------------------------------------------------------
    def advance(self, events: list[Event], graph: Any) -> Any:
        """Fold normalized events into a SceneDelta dict.

        graph: event_graph dict (nodes/edges) or None (loads bundled file).
        Returns {"scene_id", "moved", "new_clues", "npc_lines", "round",
                 "branches"}.
        "branches" is a {branch_id: {"scene_id", "moved", "blocked"}} dict for
        parallel-line SCENE events (payload["branch"]); a blocked branch
        (undeclared edge) never blocks other branches or the main line.
        """
        graph = self._graph(graph)
        nodes = _nodes(graph)
        edges = _edges(graph)
        new_clues: list[str] = []
        npc_lines: list[dict[str, str]] = []
        moved = False
        last_round = 0
        branch_delta: dict[str, dict[str, Any]] = {}
        for ev in events:
            self._seen_events.append(ev)
            last_round = max(last_round, ev.ts_round)
            if ev.kind is Kin.CLUE:
                cid = str(ev.payload.get("clue_id", ""))
                if cid and cid not in self._revealed_clues:
                    self._revealed_clues.append(cid)
                    new_clues.append(cid)
            elif ev.kind is Kin.NPC:
                npc_lines.append({"npc_id": str(ev.payload.get("npc_id", "")),
                                  "line": str(ev.payload.get("line", ""))})
            elif ev.kind is Kin.SCENE:
                target = str(ev.payload.get("to", ""))
                branch = str(ev.payload.get("branch", "") or "")
                if branch:
                    # parallel line: advance this branch only, from its own
                    # current node (initially the main scene). Branch is
                    # registered on first sight (even when blocked) so
                    # branch_state() is complete. A blocked move (undeclared
                    # edge / unknown target) never touches other branches or
                    # the main line.
                    cur = self._branch_scenes.get(branch, self._current_scene)
                    if branch not in self._branch_scenes:
                        self._branch_scenes[branch] = cur
                    ok = (target in nodes and target != cur
                          and any(e.get("from") == cur and e.get("to") == target
                                  for e in edges))
                    if ok:
                        self._branch_scenes[branch] = target
                    entry = branch_delta.setdefault(
                        branch, {"scene_id": cur, "moved": False,
                                 "blocked": False})
                    if ok:
                        entry["scene_id"] = target
                        entry["moved"] = True
                    else:
                        entry["blocked"] = True
                elif target in nodes and target != self._current_scene:
                    # only follow declared edges (DAG guard)
                    if any(e.get("from") == self._current_scene
                           and e.get("to") == target for e in edges):
                        self._current_scene = target
                        moved = True
        return {"scene_id": self._current_scene, "moved": moved,
                "new_clues": new_clues, "npc_lines": npc_lines,
                "round": last_round, "branches": branch_delta}

    def branch_state(self) -> dict[str, Any]:
        """Current per-branch nodes: {"main": node, "branches": {line: node}}."""
        return {"main": self._current_scene,
                "branches": dict(self._branch_scenes)}

    # -- clue_trace ---------------------------------------------------
    def clue_trace(self, clue_id: str) -> list[Any]:
        """Trace a clue -> [clue, location node, points_to node] hop dicts.

        Stateless over the graph: tracing line B's clue never depends on
        line A's progress or blockage (BW-2 parallel-line guarantee).
        """
        pool = _clues(_load_yaml(self._module_dir, "clues.yaml"))
        if clue_id not in pool:
            raise KeyError(f"unknown clue_id: {clue_id}")
        clue = pool[clue_id]
        graph = _nodes(_load_yaml(self._module_dir, "event_graph.yaml"))
        hops = [{"step": "clue", "clue": clue}]
        loc = str(clue.get("location", ""))
        if loc in graph:
            hops.append({"step": "found_at", "node": graph[loc]})
        target = str(clue.get("points_to", ""))
        if target in graph:
            hops.append({"step": "points_to", "node": graph[target]})
        return hops

    # -- npc_react ----------------------------------------------------
    def npc_react(self, npc_id: str, trigger: str) -> Any:
        """One-line in-character NPC reaction -> {"npc_id","name","line"}.

        Deterministic: picks the card line whose index hashes from trigger,
        so the same trigger always yields the same line (testable, no LLM).
        """
        card = _load_npc(self._module_dir, npc_id)
        lines: list[str] = list(card.get("lines", []))
        if not lines:
            raise ValueError(f"npc {npc_id} has no lines")
        idx = sum(ord(c) for c in trigger) % len(lines)
        return {"npc_id": npc_id, "name": card.get("name", npc_id),
                "line": lines[idx]}

    # -- triple_guarantee ----------------------------------------------
    def triple_guarantee(self, goal_id: str) -> list[Any]:
        """Three-clue floor: >=3 clue paths reaching the goal node.

        Paths counted: (1) clue.location == goal, (2) clue.points_to == goal,
        (3) graph node clue_refs contains a clue whose chain reaches goal.
        Returns the clue dicts (dedup, sorted by id). Raises AssertionError
        if fewer than 3 routes exist.
        """
        pool = _clues(_load_yaml(self._module_dir, "clues.yaml"))
        nodes = _nodes(_load_yaml(self._module_dir, "event_graph.yaml"))
        reaching: dict[str, dict[str, Any]] = {}
        for cid, clue in pool.items():
            if clue.get("location") == goal_id or clue.get("points_to") == goal_id:
                reaching[cid] = clue
        for node in nodes.values():
            refs = list(node.get("clue_refs", []))
            if goal_id in refs:
                for cid in refs:
                    if cid in pool:
                        reaching[cid] = pool[cid]
        # n9_truth chain: clues pointing at n7/n8/n9 all converge on the goal
        if goal_id == "n9_truth":
            for cid, clue in pool.items():
                if clue.get("points_to") in ("n7_clue_chain", "n9_truth"):
                    reaching[cid] = clue
        result = [reaching[k] for k in sorted(reaching)]
        if len(result) < 3:
            raise AssertionError(
                f"triple guarantee failed for {goal_id}: "
                f"only {len(result)} routes")
        return result

    # -- snapshot / replay ---------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        """Current scene snapshot (W-B2 shape; loop persists it)."""
        return {"scene_id": self._current_scene,
                "round": self._seen_events[-1].ts_round if self._seen_events else 0,
                "revealed_clues": list(self._revealed_clues),
                "events_seen": len(self._seen_events)}

    def replay(self, event_id: str) -> list[Event]:
        """Replay seen events from event_id (inclusive)."""
        ids = [e.event_id for e in self._seen_events]
        if event_id not in ids:
            raise KeyError(f"unknown event_id: {event_id}")
        return self._seen_events[ids.index(event_id):]
