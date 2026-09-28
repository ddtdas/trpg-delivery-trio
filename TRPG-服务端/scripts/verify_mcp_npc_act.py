# -*- coding: utf-8 -*-
"""T14 验收：MCP npc_act 不再恒 403，且与 REST/WS 同源（同一门、同一导演、同一审批总线）。

判据：
  1) tools/list 仍注册 mcp__trpg__npc_act（注册面不变）
  2) 门开：/mcp/tools/call 返回 200 + NPC_ACT_PROPOSED + proposal_id，且**不回显候选台词**
  3) 同一存储：候选出现在 GET /npc/proposals（GM 待审队列）
  4) 同一条审批总线：POST /approvals 拍板 -> NPC_ACT_APPROVED
  5) 批准后才对玩家可见：GET /npc/lines
  6) 缺 actor -> 403 actor_required（既有语义不变）
  7) 缺 campaign_id -> 422 campaign_id_required
  8) 门关（TRPG_NPC_GATE=locked 语义）：check_tool_access 抛 npc_forbidden
  9) describe(): 门开 reserved_403=[] / npc_gate=open；门关 reserved_403 含 npc_act
 10) 冻结面不变：FROZEN_NAMES=13、ALL_NAMES=14、events.py sha256 未变
"""
from __future__ import annotations
import hashlib, json, os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TRPG_BASE", "http://127.0.0.1:9211")
import httpx, yaml

BASE = os.environ["TRPG_BASE"]
LOG = ROOT / "run" / "verify_mcp_npc_act.txt"
LOG.parent.mkdir(parents=True, exist_ok=True)
_buf: list[str] = []


def emit(line: str = "") -> None:
    print(line)
    _buf.append(line)


RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    emit("%-5s %-34s %s" % ("PASS" if ok else "FAIL", name, detail))


CFG = yaml.safe_load((ROOT / "configs" / "access_config.yaml").read_text(encoding="utf-8"))
KP = {"Authorization": "Bearer " + str((CFG.get("ends") or {}).get("webapp", {}).get("token") or "")}
STAMP = time.strftime("%m%d%H%M%S", time.gmtime())
CAMPAIGN = "c_mcpnpc_" + STAMP
NPC = "npc_clerk"
c = httpx.Client(base_url=BASE, timeout=30.0)

emit("=" * 70)
emit("T14 MCP npc_act 验收  campaign=%s  base=%s" % (CAMPAIGN, BASE))
emit("=" * 70)

# 1) 注册面
tl = c.post("/mcp/tools/list", json={}, headers=KP)   # tools/list 有 token 鉴权(EX-MCP)
names = [t["name"] for t in tl.json().get("tools", [])]
check("MCP-tools-list-needs-token", c.post("/mcp/tools/list", json={}).status_code == 401,
      "无 token -> 401 (EX-MCP 既有语义不变)")
check("MCP-npc_act-registered", "mcp__trpg__npc_act" in names,
      "tools/list 含 npc_act（共 %d 项）" % len(names))

# 2) 门开：调用
body = {"name": "mcp__trpg__npc_act",
        "arguments": {"actor": {"id": "pl-001"}, "campaign_id": CAMPAIGN,
                      "npc_id": NPC, "trigger": "玩家询问闭馆那晚"}}
r = c.post("/mcp/tools/call", json=body)
emit(">>> POST /mcp/tools/call npc_act -> %d" % r.status_code)
emit(json.dumps(r.json(), ensure_ascii=False, indent=2))
j = r.json() if r.status_code < 400 else {}
pid = str(j.get("proposal_id") or "")
check("MCP-npc_act-not-hardlocked", r.status_code == 200 and j.get("type") == "NPC_ACT_PROPOSED",
      "status=%d type=%s" % (r.status_code, j.get("type")))
check("MCP-npc_act-no-line-echo", "line" not in j and "lines" not in j,
      "响应键=%s（不回显候选台词）" % sorted(j.keys()))

# 3) 同一存储
pr = c.get("/api/campaigns/%s/npc/proposals" % CAMPAIGN, headers=KP)
ids = [p.get("proposal_id") for p in (pr.json().get("proposals") or [])]
check("MCP-same-store", bool(pid) and pid in ids,
      "候选进入同一 npc_proposal 存储: %s" % ids)
cand = ""
for p in (pr.json().get("proposals") or []):
    if p.get("proposal_id") == pid:
        cand = str(p.get("line") or "")

# 4) 同一条审批总线
ap = c.post("/api/campaigns/%s/approvals" % CAMPAIGN, headers=KP,
            json={"proposal_id": pid, "decision": "approve"})
emit(">>> POST /approvals -> %d" % ap.status_code)
emit(json.dumps(ap.json(), ensure_ascii=False, indent=2))
check("MCP-single-approval-bus",
      ap.status_code == 201 and ap.json().get("type") == "NPC_ACT_APPROVED",
      "经既有唯一审批总线拍板 -> %s" % ap.json().get("type"))

# 5) 批准后才对玩家可见
ln = c.get("/api/campaigns/%s/npc/lines" % CAMPAIGN)
texts = json.dumps(ln.json(), ensure_ascii=False)
check("MCP-player-visible-after-approval", bool(cand) and cand in texts,
      "玩家端 lines 含批准后的台词")

# 6) 缺 actor
r6 = c.post("/mcp/tools/call", json={"name": "mcp__trpg__npc_act",
                                     "arguments": {"campaign_id": CAMPAIGN, "npc_id": NPC}})
check("MCP-actor-required-kept", r6.status_code == 403 and
      (r6.json().get("detail") or {}).get("error") == "actor_required",
      "%d %s" % (r6.status_code, r6.json()))

# 7) 缺 campaign_id
r7 = c.post("/mcp/tools/call", json={"name": "mcp__trpg__npc_act",
                                     "arguments": {"actor": {"id": "kp"}, "npc_id": NPC}})
check("MCP-campaign-required", r7.status_code == 422 and
      (r7.json().get("detail") or {}).get("error") == "campaign_id_required",
      "%d %s" % (r7.status_code, r7.json()))

# 8/9) 门关 + describe
from app.mcp import auth as mcp_auth
from app.mcp import server as mcp_server
from app.mcp.schemas import ALL_NAMES, FROZEN_NAMES

d_open = mcp_server.describe()
check("MCP-describe-gate-open",
      d_open.get("npc_gate") == "open" and d_open.get("reserved_403") == [],
      "npc_gate=%s reserved_403=%s" % (d_open.get("npc_gate"), d_open.get("reserved_403")))

saved = mcp_auth.NPC_GATE_OPEN
try:
    mcp_auth.NPC_GATE_OPEN = False
    try:
        mcp_auth.check_tool_access("npc_act", {"actor": {"id": "pl-001"}})
        locked_err = "no-error"
    except mcp_auth.AuthError as exc:
        locked_err = exc.error
    d_locked = mcp_server.describe()
    check("MCP-lock-switch", locked_err == "npc_forbidden" and
          d_locked.get("reserved_403") == ["mcp__trpg__npc_act"],
          "门关 -> %s ; reserved_403=%s" % (locked_err, d_locked.get("reserved_403")))
finally:
    mcp_auth.NPC_GATE_OPEN = saved

check("MCP-tautology-gone",
      'if raw == "npc_act" and not NPC_GATE_OPEN' in
      (ROOT / "app" / "mcp" / "auth.py").read_text(encoding="utf-8"),
      "auth.py 已是真开关判定（非恒真式）")

# 10) 冻结面
ev = ROOT / "trpg" / "agent" / "events.py"
# 验收规范第 4 条：断言可复算性，不断言观测值。
# 冻结文件的 sha256 由 docs/CROSS-END-CONTRACT.md 第 1.5 节**声明** —— 断言
# 「声明值 == 现算值」，而不是硬编码某个观测值（契约升版时自动跟随）。
import re as _re
_contract = (ROOT / "docs" / "CROSS-END-CONTRACT.md").read_text(encoding="utf-8")
_declared = {m.group(1).strip(): m.group(2).upper()
             for m in _re.finditer(r"^\|\s*\d+\s*\|\s*([^|]+?)\s*\|\s*([0-9A-Fa-f]{64})\s*\|\s*$",
                                   _contract, _re.M)}
_ev_rel = "trpg/agent/events.py"
_ev_now = hashlib.sha256(ev.read_bytes()).hexdigest().upper()
check("MCP-frozen-surface",
      len(FROZEN_NAMES) == 13 and len(ALL_NAMES) == 14 and _declared.get(_ev_rel) == _ev_now,
      "FROZEN_NAMES=%d ALL_NAMES=%d | %s 声明=%s 现算=%s 一致=%s"
      % (len(FROZEN_NAMES), len(ALL_NAMES), _ev_rel,
         (_declared.get(_ev_rel) or "?")[:16], _ev_now[:16], _declared.get(_ev_rel) == _ev_now))

emit("")
emit("=" * 70)
emit("SUMMARY")
emit("=" * 70)
bad = [r for r in RESULTS if not r[1]]
for name, ok, detail in RESULTS:
    emit("%-5s %s" % ("PASS" if ok else "FAIL", name))
emit("")
emit("checks=%d failed=%d" % (len(RESULTS), len(bad)))
emit("VERIFY_RESULT=%s" % ("PASS" if not bad else "FAIL"))
LOG.write_text("\n".join(_buf) + "\n", encoding="utf-8")
emit("evidence file: %s" % LOG)
sys.exit(0 if not bad else 1)
