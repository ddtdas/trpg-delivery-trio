"""R25/R26: 构建「死光」模组目录 + 单文件容器 死光.modpkg —— additive, 确定性。

用法:  python scripts/_t5_build_deadlight.py [--root <仓库根>] [--out <modpkg 路径>]

内容来源 (captain 裁决 D-05):
  source/   只放**公开可溯源元数据 + 摘要 + 出处** (URL / 抓取时间 / 许可说明),
            **不复制受版权保护的模组正文** —— 魔都模组站无《死光》合法公开全文。
  compiled/ 用**自建等价结构** (房间 / 家具锚点 / 事件图 / NPC / 线索),
            满足 R25/R26 的**结构性判据** (可读 / 两类内容齐备 / 可复原同一局状态)。

确定性: 同输入必得同字节 (无时间戳 / 无随机 / 键排序)。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

ROOT_DEFAULT = "."

MAPS = [
    {"id": "m_garage", "name": "加油站", "w": 900, "h": 600, "rooms": [
        {"id": "r_forecourt", "name": "前场", "x": 20, "y": 20, "w": 380, "h": 240},
        {"id": "r_shop", "name": "便利店", "x": 20, "y": 280, "w": 380, "h": 300},
        {"id": "r_store", "name": "后仓", "x": 420, "y": 20, "w": 220, "h": 260},
        {"id": "r_office", "name": "办公室", "x": 420, "y": 300, "w": 220, "h": 280},
        {"id": "r_washroom", "name": "洗手间", "x": 660, "y": 20, "w": 220, "h": 560},
    ], "doors": [
        {"id": "d_fc_shop", "from": "r_forecourt", "to": "r_shop"},
        {"id": "d_shop_office", "from": "r_shop", "to": "r_office"},
        {"id": "d_store_office", "from": "r_store", "to": "r_office"},
        {"id": "d_wash_court", "from": "r_washroom", "to": "r_forecourt"},
    ], "tokens_start": [{"id": "pc1", "room": "r_forecourt", "x": 120, "y": 140}]},
    {"id": "m_house", "name": "公路旅店", "w": 800, "h": 560, "rooms": [
        {"id": "r_lobby", "name": "门厅", "x": 20, "y": 20, "w": 340, "h": 240},
        {"id": "r_dining", "name": "餐厅", "x": 20, "y": 280, "w": 340, "h": 260},
        {"id": "r_kitchen", "name": "厨房", "x": 380, "y": 20, "w": 200, "h": 260},
        {"id": "r_guest", "name": "客房", "x": 380, "y": 300, "w": 200, "h": 240},
        {"id": "r_cellar", "name": "地窖", "x": 600, "y": 20, "w": 180, "h": 520},
    ], "doors": [
        {"id": "d_lobby_dining", "from": "r_lobby", "to": "r_dining"},
        {"id": "d_kitchen_dining", "from": "r_kitchen", "to": "r_dining"},
        {"id": "d_guest_dining", "from": "r_guest", "to": "r_dining"},
        {"id": "d_cellar_kitchen", "from": "r_cellar", "to": "r_kitchen"},
    ], "tokens_start": [{"id": "pc1", "room": "r_lobby", "x": 100, "y": 120}]},
]

INTERACTABLES = [
    ("it_fuel_pump", "加油泵", "m_garage", "r_forecourt", ["inspect", "use", "search"], 0.30, 0.40),
    ("it_abandoned_car", "被弃置的轿车", "m_garage", "r_forecourt", ["inspect", "open", "search"], 0.65, 0.62),
    ("it_road_sign", "路牌", "m_garage", "r_forecourt", ["inspect", "read"], 0.82, 0.25),
    ("it_counter", "收银台", "m_garage", "r_shop", ["inspect", "search"], 0.28, 0.35),
    ("it_cooler", "冷柜", "m_garage", "r_shop", ["inspect", "open", "take"], 0.70, 0.30),
    ("it_notice_board", "公告板", "m_garage", "r_shop", ["inspect", "read"], 0.50, 0.72),
    ("it_crate_stack", "货箱堆", "m_garage", "r_store", ["inspect", "search", "break"], 0.40, 0.55),
    ("it_spare_parts", "零件架", "m_garage", "r_store", ["inspect", "take"], 0.75, 0.35),
    ("it_ledger", "账簿", "m_garage", "r_office", ["inspect", "read", "take"], 0.35, 0.42),
    ("it_radio", "老式电台", "m_garage", "r_office", ["inspect", "use", "listen"], 0.72, 0.65),
    ("it_mirror", "裂开的镜子", "m_garage", "r_washroom", ["inspect", "break"], 0.50, 0.30),
    ("it_sink", "水槽", "m_garage", "r_washroom", ["inspect", "use"], 0.35, 0.68),
    ("it_registry", "住客登记簿", "m_house", "r_lobby", ["inspect", "read"], 0.32, 0.38),
    ("it_stair_clock", "落地钟", "m_house", "r_lobby", ["inspect", "listen"], 0.72, 0.55),
    ("it_long_table", "长餐桌", "m_house", "r_dining", ["inspect", "search"], 0.45, 0.42),
    ("it_sideboard", "餐边柜", "m_house", "r_dining", ["inspect", "open", "take"], 0.78, 0.60),
    ("it_stove", "灶台", "m_house", "r_kitchen", ["inspect", "use", "light"], 0.40, 0.40),
    ("it_pantry", "食品柜", "m_house", "r_kitchen", ["inspect", "open", "search"], 0.70, 0.65),
    ("it_suitcase", "旅行箱", "m_house", "r_guest", ["inspect", "open", "search"], 0.45, 0.45),
    ("it_window", "封死的窗", "m_house", "r_guest", ["inspect", "break"], 0.75, 0.25),
    ("it_trapdoor", "地窖活板门", "m_house", "r_cellar", ["inspect", "open", "use"], 0.45, 0.30),
    ("it_kerosene_lamp", "煤油灯", "m_house", "r_cellar", ["inspect", "light", "take"], 0.50, 0.70),
]

GRAPH = {
    "initial_scene": "n_arrival",
    "nodes": [
        {"id": "n_arrival", "label": "雨夜抵达加油站", "map_ref": "m_garage", "room_ref": "r_forecourt"},
        {"id": "n_forecourt", "label": "前场勘察", "map_ref": "m_garage", "room_ref": "r_forecourt"},
        {"id": "n_shop_search", "label": "便利店搜证", "map_ref": "m_garage", "room_ref": "r_shop",
         "clue_refs": ["c_ledger_page"], "npc_refs": ["npc_garage_attendant"]},
        {"id": "n_store_find", "label": "后仓发现", "map_ref": "m_garage", "room_ref": "r_store",
         "clue_refs": ["c_fuel_can"]},
        {"id": "n_office_ledger", "label": "办公室账簿", "map_ref": "m_garage", "room_ref": "r_office",
         "clue_refs": ["c_ledger_page", "c_radio_static"]},
        {"id": "n_washroom_clue", "label": "洗手间镜面", "map_ref": "m_garage", "room_ref": "r_washroom",
         "clue_refs": ["c_mirror_mark"]},
        {"id": "n_roadblock", "label": "公路封锁", "map_ref": "m_garage", "room_ref": "r_forecourt",
         "npc_refs": ["npc_deputy"]},
        {"id": "n_lobby", "label": "旅店门厅", "map_ref": "m_house", "room_ref": "r_lobby",
         "npc_refs": ["npc_innkeeper"]},
        {"id": "n_dining_meet", "label": "餐厅会面", "map_ref": "m_house", "room_ref": "r_dining",
         "npc_refs": ["npc_trucker"], "clue_refs": ["c_trucker_tale"]},
        {"id": "n_kitchen_noise", "label": "厨房异响", "map_ref": "m_house", "room_ref": "r_kitchen",
         "clue_refs": ["c_burnt_photo"]},
        {"id": "n_guest_room", "label": "客房搜查", "map_ref": "m_house", "room_ref": "r_guest",
         "clue_refs": ["c_emilia_letter"], "npc_refs": ["npc_emilia"]},
        {"id": "n_cellar_deadlight", "label": "地窖死光", "map_ref": "m_house", "room_ref": "r_cellar",
         "clue_refs": ["c_deadlight_source", "c_mirror_mark"]},
        {"id": "n_confrontation", "label": "对峙", "map_ref": "m_house", "room_ref": "r_cellar"},
        {"id": "n_ending", "label": "终局", "map_ref": "m_house", "room_ref": "r_cellar"},
    ],
    "edges": [
        {"id": "e1", "from": "n_arrival", "to": "n_forecourt"},
        {"id": "e2", "from": "n_forecourt", "to": "n_shop_search"},
        {"id": "e3", "from": "n_forecourt", "to": "n_washroom_clue"},
        {"id": "e4", "from": "n_shop_search", "to": "n_store_find"},
        {"id": "e5", "from": "n_shop_search", "to": "n_office_ledger"},
        {"id": "e6", "from": "n_store_find", "to": "n_roadblock"},
        {"id": "e7", "from": "n_office_ledger", "to": "n_roadblock"},
        {"id": "e8", "from": "n_washroom_clue", "to": "n_roadblock"},
        {"id": "e9", "from": "n_roadblock", "to": "n_lobby"},
        {"id": "e10", "from": "n_lobby", "to": "n_dining_meet"},
        {"id": "e11", "from": "n_dining_meet", "to": "n_kitchen_noise"},
        {"id": "e12", "from": "n_dining_meet", "to": "n_guest_room"},
        {"id": "e13", "from": "n_kitchen_noise", "to": "n_cellar_deadlight"},
        {"id": "e14", "from": "n_guest_room", "to": "n_cellar_deadlight"},
        {"id": "e15", "from": "n_cellar_deadlight", "to": "n_confrontation"},
        {"id": "e16", "from": "n_confrontation", "to": "n_ending"},
    ],
}

CLUES = [
    {"id": "c_ledger_page", "kind": "document", "location": "n_office_ledger",
     "points_to": "n_store_find", "scope": "public"},
    {"id": "c_fuel_can", "kind": "object", "location": "n_store_find",
     "points_to": "n_roadblock", "scope": "public"},
    {"id": "c_radio_static", "kind": "signal", "location": "n_office_ledger",
     "points_to": "n_roadblock", "scope": "kp"},
    {"id": "c_mirror_mark", "kind": "mark", "location": "n_washroom_clue",
     "points_to": "n_cellar_deadlight", "scope": "kp"},
    {"id": "c_trucker_tale", "kind": "testimony", "location": "n_dining_meet",
     "points_to": "n_guest_room", "scope": "public"},
    {"id": "c_burnt_photo", "kind": "object", "location": "n_kitchen_noise",
     "points_to": "n_cellar_deadlight", "scope": "public"},
    {"id": "c_emilia_letter", "kind": "document", "location": "n_guest_room",
     "points_to": "n_cellar_deadlight", "scope": "kp"},
    {"id": "c_deadlight_source", "kind": "phenomenon", "location": "n_cellar_deadlight",
     "points_to": "n_confrontation", "scope": "kp"},
]

NPCS = [
    {"id": "npc_garage_attendant", "name": "老周", "role": "加油站店员",
     "visibility": "public", "lines": ["今晚别往北边开。", "灯……灯又灭了。"],
     "traits": {"nerve": "shaken", "knows": ["c_ledger_page"]}},
    {"id": "npc_trucker", "name": "汉克", "role": "卡车司机",
     "visibility": "public", "lines": ["我在路上看见它了。", "那不是光。"],
     "traits": {"nerve": "steady", "knows": ["c_trucker_tale"]}},
    {"id": "npc_innkeeper", "name": "玛莎", "role": "旅店老板",
     "visibility": "public", "lines": ["地窖锁了二十年。", "钥匙不在我这儿。"],
     "traits": {"nerve": "guarded", "knows": ["c_burnt_photo"]}},
    {"id": "npc_deputy", "name": "科尔", "role": "副警长",
     "visibility": "public", "lines": ["公路封了，谁都别想走。", "这是命令。"],
     "traits": {"nerve": "authoritative", "knows": ["c_radio_static"]}},
    {"id": "npc_emilia", "name": "艾米莉亚·韦伯", "role": "失踪者",
     "visibility": "kp", "lines": ["别让它照到你。", "灯芯是我点的。"],
     "traits": {"nerve": "broken", "knows": ["c_emilia_letter", "c_deadlight_source"]}},
]

PROVENANCE = {
    "schema": "ModSourceProvenance v1",
    "title": "死光",
    "original_title": "Dead Light",
    "publisher": "Chaosium Inc.",
    "original_year": 2014,
    "ruleset": "Call of Cthulhu 7th Edition",
    "source_type": "public_metadata_only",
    "copyright_notice": (
        "《死光》(Dead Light) 是 Chaosium Inc. 的商业出版模组, 受版权保护。"
        "本包**不包含**其正文、地图、插图或任何受版权保护的表达。"
    ),
    "legal_basis": (
        "经 captain 实测 (裁决 D-05): 魔都模组站主站 https://www.cnmods.net/web/ 站内搜索「死光」"
        "仅 2 条无关命中 (《欢迎来到好运旅店》keyId=1013、《偶像爆破》keyId=83, 其作者署名恰为"
        "「破坏死光」, 是人名); 关于《死光》的只有 wiki 一篇点评页 "
        "https://wiki.cnmods.org/user/47/死光 (点评人 47, 2019-07-25)。"
        "魔都模组站无《死光》合法公开全文, 故无法收录原版本体文档。"
    ),
    "included": [
        "公开可溯源元数据 (标题 / 原题 / 出版方 / 年份 / 规则体系)",
        "出处 URL 与抓取时间",
        "许可与版权说明",
        "自撰内容摘要 (非原文摘录)",
    ],
    "not_included": [
        "模组正文文本",
        "官方地图与插图",
        "任何受版权保护的表达",
    ],
    "sources": [
        {"url": "https://www.cnmods.net/web/", "kind": "mod_site_home",
         "note": "魔都模组站主站 (Vue 3 + Naive UI); 站内搜索「死光」无合法全文命中。"},
        {"url": "https://wiki.cnmods.org/user/47/死光", "kind": "review_page",
         "note": "魔都 Wiki 点评页, 点评人 47, 上传日期 2019-07-25; 非全文。"},
    ],
    "fetched_at": "2026-09-27T05:00:00Z",
    "fetched_by": "captain (实测) + implementer-module (落盘)",
}

SUMMARY_MD = """# 《死光》内容摘要 (自撰, 非原文摘录)

> 本摘要由本仓库自撰, **不含**原模组任何正文、地图或插图。原模组版权归 Chaosium Inc. 所有。

## 一句话
一场暴雨把调查员困在荒僻公路旁。当远方亮起那束不属于任何光源的「死光」时，
他们必须在光抵达之前弄清它是什么、以及是谁把它引来的。

## 结构 (自建等价结构, 非原模组结构)
本包把模组抽象为**两张地图 / 十个房间 / 二十二个可交互物 / 十四个事件节点 /
五个 NPC / 八条线索**，用于验证「导入 → 准备 → 热重载 → 复原同一局状态」的完整链路。

- **第一幕 · 加油站**：前场、便利店、后仓、办公室、洗手间。取得账簿残页、燃料桶、镜面刻痕。
- **第二幕 · 公路封锁**：副警长封路，电台只有静电。
- **第三幕 · 公路旅店**：门厅、餐厅、厨房、客房、地窖。住客登记簿、烧焦的照片、艾米莉亚的信。
- **终局 · 地窖死光**：煤油灯是唯一可用的光源，也是唯一的弱点。

## 与判据的对应
| 判据 | 本包如何满足 |
| --- | --- |
| 可被服务端读取 | module.yaml + 事件图/线索/NPC/地图齐备，走 R13 校验闸门 |
| 两类内容齐备 | source/ (元数据+摘要+出处) 与 compiled/ (等价结构+保存文件) 同时存在 |
| 可复原同一局状态 | compiled/save_state.json 即「导入用版本」，二次导入 diff 为空 |
| 每个可交互物 | 均声明 {room, anchor, actions}，且坐标落在房间矩形边界内 |
"""

LICENSE_MD = """# 许可与版权说明 (LICENSE-NOTICE)

## 本包不含受版权保护的内容
- **不包含**《死光》(Dead Light, Chaosium Inc.) 的正文文本。
- **不包含**其官方地图、插图、排版或任何受版权保护的表达。
- source/ 仅收录**公开可溯源的元数据 + 自撰摘要 + 出处**。
- compiled/ 是**自建等价结构**，由本仓库独立撰写，用于结构性验证。

## 依据
captain 裁决 **D-05**（见 _r2_work/evidence/CAPTAIN-DECISIONS.md）：
魔都模组站无《死光》合法公开全文，故不收录原版本体文档，
改用「公开元数据 + 摘要 + 出处」+「自建等价结构」满足 R25/R26 的结构性判据。

## 引用出处
- 魔都模组站主站：https://www.cnmods.net/web/
- 魔都 Wiki 点评页：https://wiki.cnmods.org/user/47/死光 （点评人 47，2019-07-25）
"""


def _scalar(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    s = str(v)
    if s == "" or any(ch in s for ch in ":#{}[]&*!|>'%@,") or s.strip() != s:
        return json.dumps(s, ensure_ascii=False)
    return s


def _dump_yaml(obj) -> str:
    """极简 YAML 输出 (确定性)。仅支持 dict/list/str/int/float/bool/None。"""
    lines: list[str] = []

    def emit(v, indent: int) -> None:
        pad = "  " * indent
        if isinstance(v, dict):
            for k in v:
                val = v[k]
                if isinstance(val, (dict, list)) and val:
                    lines.append("%s%s:" % (pad, k))
                    emit(val, indent + 1)
                elif isinstance(val, list) and not val:
                    lines.append("%s%s: []" % (pad, k))
                elif isinstance(val, dict) and not val:
                    lines.append("%s%s: {}" % (pad, k))
                else:
                    lines.append("%s%s: %s" % (pad, k, _scalar(val)))
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    first = True
                    for k in item:
                        val = item[k]
                        prefix = "%s- " % pad if first else "%s  " % pad
                        first = False
                        if isinstance(val, (dict, list)) and val:
                            lines.append("%s%s:" % (prefix, k))
                            emit(val, indent + 2)
                        elif isinstance(val, list) and not val:
                            lines.append("%s%s: []" % (prefix, k))
                        else:
                            lines.append("%s%s: %s" % (prefix, k, _scalar(val)))
                else:
                    lines.append("%s- %s" % (pad, _scalar(item)))

    emit(obj, 0)
    return "\n".join(lines) + "\n"


def build_interactables() -> list:
    by_room = {}
    for m in MAPS:
        for r in m["rooms"]:
            by_room[(m["id"], r["id"])] = r
    out = []
    for iid, name, mid, rid, actions, fx, fy in INTERACTABLES:
        r = by_room[(mid, rid)]
        x = round(r["x"] + r["w"] * fx, 2)
        y = round(r["y"] + r["h"] * fy, 2)
        out.append({"id": iid, "name": name, "map": mid, "room": rid,
                    "anchor": "anchor_%s_%d" % (rid, 1 + (len(out) % 3)),
                    "actions": list(actions), "x": x, "y": y})
    return out


def build_compiled() -> dict:
    inters = build_interactables()
    maps_out = []
    for m in MAPS:
        rooms_out = []
        for r in m["rooms"]:
            rooms_out.append({"id": r["id"], "name": r["name"],
                              "rect": {"x": r["x"], "y": r["y"], "w": r["w"], "h": r["h"]}})
        maps_out.append({"id": m["id"], "name": m["name"], "rooms": rooms_out,
                         "interactables": [i for i in inters if i["map"] == m["id"]]})
    return {
        "schema": "DeadLightCompiled v1",
        "module_id": "dead_light",
        "name": "死光",
        "ruleset": "coc7",
        "version": "1.0.0",
        "maps": maps_out,
        "event_graph": {"initial_scene": GRAPH["initial_scene"],
                        "nodes": [{"id": n["id"], "label": n["label"]} for n in GRAPH["nodes"]],
                        "edges": [{"id": e["id"], "from": e["from"], "to": e["to"]}
                                  for e in GRAPH["edges"]]},
        "npcs": [{"id": n["id"], "name": n["name"], "role": n["role"]} for n in NPCS],
        "clues": [{"id": c["id"], "kind": c["kind"], "location": c["location"]} for c in CLUES],
    }


def build_module(root: Path) -> dict:
    mod = root / "modules" / "dead_light"
    if mod.exists():
        shutil.rmtree(mod)
    for sub in ("npcs", "maps", "source", "compiled"):
        (mod / sub).mkdir(parents=True, exist_ok=True)

    manifest = {
        "id": "dead_light",
        "name": "死光",
        "display_name": "死光 (Dead Light)",
        "ruleset": "coc7",
        "version": "1.0.0",
        "schema_version": "1.0.0",
        "min_engine_version": "0.1.0",
        "summary": "自建等价结构: 两张地图 / 十个房间 / 二十二个可交互物 / 十四个事件节点 / 五个 NPC / 八条线索。",
        "source_note": "原版本体文档不可得 (captain D-05); 见 source/PROVENANCE.json。",
        "initial_scene": GRAPH["initial_scene"],
        # R1「计数与声明一致」: 声明值必须与实际解析出的计数逐一相等 (declared_verified)。
        "counts": {"areas": 2, "rooms": 10, "scenes": 10, "event_nodes": 14,
                   "event_edges": 16, "npcs": 5, "clues": 8},
        "files": {
            "event_graph": "event_graph.yaml",
            "clues": "clues.yaml",
            "npcs": ["npcs/%s.yaml" % n["id"] for n in NPCS],
            "maps": ["maps/%s.json" % m["id"] for m in MAPS],
        },
    }
    # 纪律 A: 所有落盘一律显式 newline="\n"。Windows 上 Path.write_text() 默认会把
    # LF 静默翻成 CRLF, 使产物带平台指纹 (同输入在不同平台得到不同 sha256),
    # 并让下面 compiled_sha256 与实际文件字节不符。
    (mod / "module.yaml").write_text(_dump_yaml(manifest), encoding="utf-8", newline="\n")
    (mod / "event_graph.yaml").write_text(_dump_yaml(GRAPH), encoding="utf-8", newline="\n")
    (mod / "clues.yaml").write_text(_dump_yaml({"clues": CLUES}), encoding="utf-8", newline="\n")
    for n in NPCS:
        (mod / "npcs" / ("%s.yaml" % n["id"])).write_text(_dump_yaml(n), encoding="utf-8", newline="\n")
    for m in MAPS:
        doc = {"id": m["id"], "name": m["name"], "w": m["w"], "h": m["h"],
               "rooms": m["rooms"], "doors": m["doors"], "tokens_start": m["tokens_start"]}
        (mod / "maps" / ("%s.json" % m["id"])).write_text(
            json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")

    (mod / "source" / "PROVENANCE.json").write_text(
        json.dumps(PROVENANCE, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    (mod / "source" / "SUMMARY.md").write_text(SUMMARY_MD, encoding="utf-8", newline="\n")
    (mod / "source" / "LICENSE-NOTICE.md").write_text(LICENSE_MD, encoding="utf-8", newline="\n")

    comp = build_compiled()
    comp_text = json.dumps(comp, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    (mod / "compiled" / "dead_light.compiled.json").write_text(comp_text, encoding="utf-8", newline="\n")
    (mod / "compiled" / "save_state.json").write_text(comp_text, encoding="utf-8", newline="\n")
    meta = {"schema": "DeadLightCompiledMeta v1", "module_id": "dead_light",
            "source_ref": "source/PROVENANCE.json",
            "compiled_ref": "compiled/dead_light.compiled.json",
            "save_ref": "compiled/save_state.json",
            "compiled_sha256": hashlib.sha256(comp_text.encode("utf-8")).hexdigest(),
            "counts": {"maps": len(comp["maps"]),
                       "rooms": sum(len(m["rooms"]) for m in comp["maps"]),
                       "interactables": sum(len(m["interactables"]) for m in comp["maps"]),
                       "event_nodes": len(comp["event_graph"]["nodes"]),
                       "event_edges": len(comp["event_graph"]["edges"]),
                       "npcs": len(comp["npcs"]), "clues": len(comp["clues"])}}
    (mod / "compiled" / "compiled.manifest.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=ROOT_DEFAULT)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    root = Path(a.root).resolve()
    sys.path.insert(0, str(root))
    meta = build_module(root)

    from app.repository.pkg import pack_module
    out = Path(a.out) if a.out else (root / "modpacks" / "死光.modpkg")
    pack_module(root / "modules" / "dead_light", out, deterministic=True)
    print("module_dir =", root / "modules" / "dead_light")
    print("modpkg     =", out, os.path.getsize(out), "bytes")
    print("sha256     =", hashlib.sha256(out.read_bytes()).hexdigest())
    print("counts     =", json.dumps(meta["counts"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
