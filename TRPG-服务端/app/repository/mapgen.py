"""Rule-based module-text -> MapDefinition generator (MIT, additive).

T1 §3: the recommended (a) path -- deterministic, offline, unit-testable.
It parses module prose (markdown / plain text / .modpkg source) into:
  * maps/*.json  (same shape the importer consumes: rooms/doors/tokens_start)
  * an event_graph (nodes/edges/initial_scene) derived from the same prose
so the output can be fed straight into app.repository.importer and becomes
visible via GET /api/modules/{id}/prepared.

Design:
  * section detection: headings + keywords 地点/场所/房间/区域/场景/地图/章节.
  * edge lines: "通往 X -> Y" (explicit arrow) or "^通往 X" (starts with the
    keyword) connect nodes; lines that merely *contain* an edge keyword are
    treated as room descriptions, never as edges (keeps prose safe).
  * rooms without coordinates get a deterministic greedy grid layout.
  * duplicate-named nodes are merged (edge targets often precede their
    headings); scene_nodes are rebuilt from the final room list so every
    room is a scene node and refs stay consistent.
  * quality report: every unparsed line is collected (T1 §3.6 手工标注兜底).
Python 3.12 compatible.
"""
from __future__ import annotations

import re
from typing import Any

_KW_LOC = ("地点", "场所", "房间", "区域", "场景", "地图", "章节", "位置", "区域图")
_EDGE_KW_RE = re.compile(r"(?:通往|连接|出口|通道|门)[\s：:]*([^\s，。；>\-→]+)")
_ARROW_RE = re.compile(r"\s*[→>]\s*")
_HEADING_RE = re.compile(r"^#{1,6}\s+")
_INIT_RE = re.compile(r"^initial_scene:\s*([^\s，。；>\-→]+)")


def _norm(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        lines.append(line)
    return lines


def _slug(name: str, used: set[str]) -> str:
    base = re.sub(r"[^\w]+", "_", name).strip("_") or "node"
    cand = base
    i = 1
    while cand in used:
        i += 1
        cand = "%s_%d" % (base, i)
    used.add(cand)
    return cand


def _extract_edge(line: str) -> tuple[str | None, str | None] | None:
    """Two-phase edge extraction (conservative -- desc lines stay desc).

      "- 通往 X -> Y" (list marker + arrow) -> (X, Y)
      "- 通往 X" (list marker, no arrow)   -> (None, X)  meaning cur -> X
      "^通往 X"                            -> (None, X)
      otherwise                            -> None

    P2 (T3): list-style lines ("- 通往 X") are now detected by stripping a
    leading bullet/marker before keyword matching; arrow edges whose target
    equals the source are dropped (no self-loop phantom nodes).
    """
    probe = re.sub(r"^[\s]*[-*•·>»]+[\s]*", "", line)
    has_arrow = _ARROW_RE.search(probe) is not None
    starts_kw = re.match(r"^(通往|连接|出口|通道|门)[\s：:]*", probe) is not None
    if not has_arrow and not starts_kw:
        return None
    if has_arrow:
        parts = _ARROW_RE.split(probe)
        if len(parts) >= 2:
            a = parts[0]
            b = parts[-1].strip()
            m = _EDGE_KW_RE.search(a)
            a_final = (m.group(1).strip() if m else a.strip())
            a_final = a_final.strip("。，；· ")
            b = b.strip("。，；· ")
            if a_final and b and a_final != b:
                return a_final, b
            return None
    m = _EDGE_KW_RE.search(probe)
    if m:
        return None, m.group(1).strip().strip("。，；· ")
    return None


def parse_module_text(text: str, *, module_id: str = "generated",
                      map_id: str = "m_generated",
                      map_title: str = "生成地图") -> dict[str, Any]:
    """Parse module prose into a MapDefinition (T1 §3.3) + event graph."""
    lines = _norm(text)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    used: set[str] = set()
    unparsed: list[str] = []
    initial_scene: str = ""
    cur: dict[str, Any] | None = None
    grid_x, grid_y, cell_w, cell_h = 20, 20, 380, 240
    grid = {"col": 0, "row": 0}

    def _add_node(name: str) -> str:
        """Add a room node, returning its id."""
        nid = _slug(name, used)
        nodes.append({"id": nid, "name": name,
                      "x": grid_x + grid["col"] * cell_w,
                      "y": grid_y + grid["row"] * cell_h,
                      "w": cell_w, "h": cell_h, "desc": ""})
        grid["col"] = (grid["col"] + 1) % 2
        grid["row"] = grid["row"] + (1 if grid["col"] == 0 else 0)
        return nid

    for line in lines:
        low = line
        m_init = _INIT_RE.search(low)
        if m_init:
            initial_scene = m_init.group(1).strip()
            continue
        if re.match(r"^(nodes|edges):\s*$", low):
            continue  # embedded YAML block headers
        edge = _extract_edge(low)
        if edge is not None:
            a, b = edge
            ids = {n["id"] for n in nodes}
            # Resolve names already known; otherwise create the node.
            def _resolve(name: str) -> str:
                if not name:
                    return ""
                for n in nodes:
                    if str(n.get("name") or "") == name or str(n.get("id") or "") == name:
                        return str(n["id"])
                return _add_node(name)
            if a is None and b is not None:
                # cur -> b
                if cur is None:
                    continue
                src = str(cur["id"])
                dst = _resolve(b)
            elif a is not None and b is not None:
                src = _resolve(a)
                dst = _resolve(b)
            else:
                continue
            if src and dst and src != dst:
                edges.append({"id": "e%d" % (len(edges) + 1),
                              "from": src, "to": dst, "label": low[:40]})
            continue
        if _HEADING_RE.match(low) or any(k in low for k in _KW_LOC):
            title = _HEADING_RE.sub("", low).strip()
            nid = _add_node(title)
            cur = nodes[-1]
            continue
        if cur is not None and not re.match(r"^[#-]", low):
            cur["desc"] = (cur.get("desc", "") + " " + low).strip()
            continue
        unparsed.append(line)

    if not nodes:
        raise ValueError("mapgen: no locations parsed from text")

    # ---- merge duplicate-named nodes ----
    # Edge targets often precede their headings ("通往 X" before "## X"):
    # the edge creates a bare stub node, then the heading creates _2. Collapse
    # all nodes sharing a name into one id (the first created), carrying the
    # longest desc, and remap edges + initial_scene onto the kept id.
    id_to_keep: dict[str, str] = {}
    seen_names: dict[str, str] = {}      # name -> kept node id
    merged_nodes: list[dict[str, Any]] = []
    for n in nodes:
        nm = str(n.get("name") or "")
        if nm in seen_names:
            keep = seen_names[nm]
            id_to_keep[str(n["id"])] = keep
            # absorb desc into the kept node
            for m in merged_nodes:
                if str(m["id"]) == keep:
                    d1 = str(m.get("desc") or "")
                    d2 = str(n.get("desc") or "")
                    if len(d2) > len(d1):
                        m["desc"] = d2
                    break
            continue
        seen_names[nm] = str(n["id"])
        merged_nodes.append(n)
    nodes = merged_nodes

    def _remap(ref: str) -> str:
        if not ref:
            return ref
        return id_to_keep.get(ref, ref)

    edges = [{"id": e.get("id"), "from": _remap(str(e.get("from") or "")),
              "to": _remap(str(e.get("to") or "")), "label": e.get("label")}
             for e in edges]

    # Rebuild scene_nodes from the final room list (every room is a scene).
    scene_nodes = [{"id": n["id"], "label": n["name"],
                    "map_ref": map_id, "room_ref": n["id"]} for n in nodes]

    # Normalize initial_scene to a real node id (by name or id).
    if not initial_scene:
        initial_scene = scene_nodes[0]["id"]
    else:
        hit = next((n["id"] for n in nodes
                    if str(n.get("name") or "") == initial_scene
                    or str(n.get("id") or "") == initial_scene), None)
        if hit:
            initial_scene = hit
        else:
            raise ValueError("mapgen: initial_scene %r not a node" % initial_scene)

    # Drop any dangling edges (defensive; _resolve already prevents them).
    ids = {n["id"] for n in nodes}
    edges = [e for e in edges if e["from"] in ids and e["to"] in ids and e["from"] != e["to"]]

    doors = [{"id": "d_%s_%s" % (e["from"], e["to"]), "from": e["from"],
              "to": e["to"]} for e in edges]

    map_def = {
        "schema": "trpg.map.v1",
        "map_id": map_id,
        "module_id": module_id,
        "title": map_title,
        "w": 20 + (cell_w + 20) * 2,
        "h": 20 + (cell_h + 20) * (grid["row"] + 1),
        "rooms": nodes,
        "doors": doors,
        "tokens_start": [{"id": "pc1", "room": initial_scene,
                          "x": nodes[0]["x"] + 40, "y": nodes[0]["y"] + 40}]
                          if nodes else [],
        "meta": {"source_ref": "module.md", "generated_by": "rule",
                 "status": "draft", "confidence": 0.7},
    }
    event_graph = {
        "initial_scene": initial_scene,
        "nodes": scene_nodes,
        "edges": edges,
    }
    return {
        "schema": "trpg.mapgen.v1",
        "module_id": module_id,
        "map_id": map_id,
        "map": map_def,
        "event_graph": event_graph,
        "scene_count": len(scene_nodes),
        "room_count": len(nodes),
        "edge_count": len(edges),
        "quality": {
            "unparsed_lines": unparsed,
            "unparsed_count": len(unparsed),
            "confidence": 0.7,
        },
    }
