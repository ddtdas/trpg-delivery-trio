"""测试用模组包构造器: 一个「合法包」+ 可注入 5 类坏包缺陷。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def build_module(root: Path, **kw: Any) -> dict[str, Any]:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    mid = kw.get("mid", "t_mod")
    n = int(kw.get("nodes", 3))
    n_npc = int(kw.get("npcs", 1))
    n_clue = int(kw.get("clues", 1))
    n_room = int(kw.get("rooms", 2))

    node_ids = ["n%d" % (i + 1) for i in range(n)]
    npc_ids = ["npc_%d" % (i + 1) for i in range(n_npc)]
    clue_ids = ["c%d" % (i + 1) for i in range(n_clue)]
    rooms = [{"id": "r%d" % (i + 1), "name": "房间%d" % (i + 1),
              "x": 20 + i * 220, "y": 20, "w": 200, "h": 140} for i in range(n_room)]

    graph_nodes: list[dict[str, Any]] = []
    for i, nid in enumerate(node_ids):
        node: dict[str, Any] = {"id": nid, "title": "节点%d" % (i + 1), "actions": ["观察"]}
        if i == 0:
            node["clue_refs"] = clue_ids[:1]
            node["npc_refs"] = npc_ids[:1]
            node["map_ref"] = "map_test"
        graph_nodes.append(node)

    edges = kw.get("edges")
    if edges is None:
        edges = [{"from": node_ids[i], "to": node_ids[i + 1], "condition": {}, "label": "next"}
                 for i in range(len(node_ids) - 1)]
    if kw.get("dangling"):
        edges = list(edges) + [{"from": node_ids[-1], "to": "n_missing", "condition": {}}]

    clues = {"clues": [{"id": c, "kind": "物证", "location": node_ids[0],
                        "points_to": node_ids[-1], "scope": "public", "text": "线索"} for c in clue_ids]}
    manifest: dict[str, Any] = {
        "id": mid, "name": kw.get("name", "测试模组"),
        "ruleset": kw.get("ruleset", "coc7"), "version": kw.get("version", "1.0.0"),
        "initial_scene": kw.get("initial_scene") or node_ids[0],
        "files": {"event_graph": "event_graph.yaml", "clues": "clues.yaml",
                  "npcs": ["npcs/%s.yaml" % x for x in npc_ids],
                  "maps": ["maps/map_test.json"]},
    }
    if kw.get("schema_version") is not None:
        manifest["schema_version"] = kw["schema_version"]
    if kw.get("min_engine_version") is not None:
        manifest["min_engine_version"] = kw["min_engine_version"]
    if kw.get("declared_counts") is not None:
        manifest["counts"] = kw["declared_counts"]
    if kw.get("extra_manifest"):
        manifest.update(kw["extra_manifest"])
    if kw.get("omit_id"):
        manifest.pop("id", None)

    if not kw.get("omit_manifest"):
        (root / "module.yaml").write_text(
            yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (root / "event_graph.yaml").write_text(
        yaml.safe_dump({"nodes": graph_nodes, "edges": edges}, allow_unicode=True, sort_keys=False),
        encoding="utf-8")
    (root / "clues.yaml").write_text(
        yaml.safe_dump(clues, allow_unicode=True, sort_keys=False), encoding="utf-8")

    if not kw.get("omit_npc_files"):
        (root / "npcs").mkdir(parents=True, exist_ok=True)
        for i, nid in enumerate(npc_ids):
            (root / "npcs" / ("%s.yaml" % nid)).write_text(
                yaml.safe_dump({"id": nid, "name": "NPC%d" % (i + 1), "role": "角色",
                                "lines": ["台词1", "台词2"], "traits": {"trust": 50}},
                               allow_unicode=True, sort_keys=False), encoding="utf-8")

    (root / "maps").mkdir(parents=True, exist_ok=True)
    (root / "maps" / "map_test.json").write_text(json.dumps(
        {"id": "map_test", "name": "测试地图", "rooms": rooms,
         "doors": [], "tokens_start": []}, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"root": root, "manifest": manifest, "node_ids": node_ids,
            "npc_ids": npc_ids, "clue_ids": clue_ids, "rooms": rooms,
            "counts": {"scenes": n_room, "rooms": n_room, "areas": 1,
                       "event_nodes": n, "event_edges": len(edges),
                       "npcs": n_npc, "clues": n_clue}}


def bad_packages(base: Path) -> dict[str, Path]:
    """R13 五类坏包, 各自只注入一种缺陷。"""
    base = Path(base)
    out: dict[str, Path] = {}
    out["missing_manifest"] = build_module(base / "missing_manifest", omit_manifest=True)["root"]
    out["missing_id"] = build_module(base / "missing_id", omit_id=True)["root"]
    out["dangling_edge"] = build_module(base / "dangling_edge", dangling=True)["root"]
    out["missing_referenced_file"] = build_module(base / "missing_ref", omit_npc_files=True)["root"]
    out["version_incompatible"] = build_module(base / "bad_version", schema_version="99")["root"]
    return out
