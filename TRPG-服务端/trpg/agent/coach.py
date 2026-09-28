"""KP coach — W-C1 (DESIGN §2.4 K1–K8, frozen outline).

New module (non-frozen): K1–K8 chapter content + on_event trigger
interface (S1/S2/S3 → reminders). Does NOT modify frozen contracts
(events.py / allowlist.yml / registry / coordinators).
Python 3.12 compatible.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

CASES_DIR = Path(__file__).resolve().parent / "cases"

CHAPTERS: dict[str, dict[str, Any]] = {
    "K1": {
        "title": "开团前通读：一页速查＋房规公示",
        "pain_ref": "P1 规则现查打断节奏",
        "cheatsheet": (
            "【战斗】先攻=DEX顺序；命中=技能检定；伤害=武器骰+加值；闪避/格挡二选一\n"
            "【技能】1d100≤技能值成功；≤1/5困难；≤1/2普通；大失败=96-100\n"
            "【SAN】见怪先过SAN；失败扣骰面值，成功扣1或0；不定性疯狂=5轮内失5点\n"
            "【成功等级】大成功(01)＞极难＞困难＞成功＞失败＞大失败(00/96+)\n"
            "【fumble·crit】01恒大成功；00恒大失败；96+按规则为失败\n"
            "【房规】争议先快判后复盘；骰先于叙述；KP终审"
        ),
        "house_rule_template_ref": "wizard.get_house_rule_template",
        "bookmark_pages": "战斗章/技能检定章/SAN章各贴一便签，开团前能30秒翻到",
        "trigger": "开团向导入口强制过一遍；争议时一键弹速查",
    },
    "K2": {
        "title": "模组精读：二遍法",
        "pain_ref": "P2 漏线索/逻辑矛盾",
        "two_pass": [
            "第一遍：通读剧情线，用三色标出 关键线索/分支/结局条件",
            "第二遍：统一NPC名＋动机表；场景描述提炼三感官关键词",
        ],
        "npc_table_columns": ["姓名", "身份", "动机", "掌握线索", "口头禅/动作"],
        "trigger": "开团前checklist；S1漏线索风险预警（clue.at_risk）",
    },
    "K3": {
        "title": "选模组：分级推荐",
        "pain_ref": "P3 首开翻车",
        "rule": "首车仅开放短经典白名单；毒汤/常暗之箱锁死并给一句话理由",
        "whitelist_ref": "wizard.list_modules",
        "duration_label": "每个模组必须标注诚实时长（准备时长＋单局时长）",
        "trigger": "选模组页只列白名单，锁死项给理由",
    },
    "K4": {
        "title": "框架内自由：否决转暗示话术20例",
        "pain_ref": "P4 否决式引导（模组没写/不能去）",
        "rule": "绝不说模组没写；三选一改写：环境暗示 / NPC反应 / 气氛营造；绝不替PC宣言意图",
        "rewrites_ref": "VETO_REWRITES（20例）",
        "trigger": "S3检测到否决式措辞→实时改写建议",
    },
    "K5": {
        "title": "边界与目标：显性目标＋三级提醒",
        "pain_ref": "P5 放飞失控",
        "boundary_template": "开场即声明：本幕目标是X；超出Y范围的行动KP会提示拉回",
        "escalation": ["L1 环境暗示", "L2 NPC拉回", "L3 KP明示（不扣乐趣、只给方向）"],
        "trigger": "S2 check_pace偏离→按级提醒",
    },
    "K6": {
        "title": "节奏与计时：分幕计时＋三线索保底",
        "pain_ref": "P6 调查冗长/战斗拖沓/超时",
        "rules": [
            "分幕计时：调查幕≤60min，超时KP给快进话术",
            "先攻预计算：开战前先排DEX序",
            "三线索保底：关键线索至少三条独立可达路径",
            "单房间调查上限：20分钟无进展→NPC/环境送线索",
        ],
        "fast_forward_lines": ["你们把房间翻了个底朝天，就在要放弃时——", "时间不多，KP提示一个方向："],
        "trigger": "S2超时→提醒＋快进话术",
    },
    "K7": {
        "title": "快判与房规：先快判后复盘＋判例库",
        "pain_ref": "P7 骰子争议",
        "flow": "争议→KP 10秒快判（继续玩）→记复盘项→团后对照判例库裁定",
        "cases_ref": "cases/（按规则条款索引：combat/skill/san/grade/fumble_crit/opposed/growth）",
        "trigger": "S3规则冲突→快判＋记复盘项",
    },
    "K8": {
        "title": "聚光灯与信息：轮流点名＋多路可达",
        "pain_ref": "P8 偏袒/冷场/信息差",
        "rules": [
            "轮流点名：每15分钟确认每人都有行动机会",
            "线索多路可达：同一关键信息≥2人可获",
            "私聊转桌面摘要：私聊信息必须转一条桌面可公开摘要",
        ],
        "summary_template": "【桌面摘要】{pc}得知：{public_part}（细节保密）",
        "trigger": "S2 spotlight_next＋S1私聊信息摘要提醒",
    },
}

# --- K4: veto patterns + 20 rewrites ---------------------------------------

VETO_PATTERNS: tuple[str, ...] = (
    "模组上没写",
    "模组没写",
    "规则没写",
    "不能去",
    "不可以去",
    "你不能",
    "不允许",
    "说了不行",
    "就是不行",
    "没这个选项",
)

VETO_REWRITES: list[dict[str, str]] = [
    {"bad": "模组上没写，不能去。", "good": "通往码头的路被巡警封锁了，警灯闪着——你们要硬闯还是换条路？", "why": "环境暗示代替否决"},
    {"bad": "模组没写这个NPC，你不能问他。", "good": "店主摆摆手：这事别问我，不过码头老陈昨晚好像看见了什么。", "why": "NPC反应转交线索"},
    {"bad": "现在不能去那里。", "good": "夜雾里传来不祥的声响，直觉告诉你们现在过去不明智——先查完旅馆？", "why": "气氛营造给选择"},
    {"bad": "规则没写，就按我说的来。", "good": "这条规则KP先快判一次，记下来团后复盘，继续跑不耽误节奏。", "why": "先快判后复盘"},
    {"bad": "你不能这么做。", "good": "你可以试，但KP提醒难度极高——确定要赌这一把吗？", "why": "把否决变知情选择"},
    {"bad": "不允许分头行动。", "good": "分头可以，但KP会轮流给每人镜头，落单的人先说要去哪？", "why": "边界+聚光灯承诺"},
    {"bad": "没这个选项，重选。", "good": "这个方向暂时没路，不过你注意到另外两条线索……", "why": "给替代选项"},
    {"bad": "说了不行就是不行。", "good": "KP明示一下：这条线会直接跳关，咱们先把眼前这幕走完？", "why": "L3明示但保乐趣"},
    {"bad": "你不能攻击NPC。", "good": "你可以动手，但镇民都在看着——想想后果，动手吗？", "why": "后果提示代替禁止"},
    {"bad": "模组上没写这段剧情。", "good": "有意思的想法！KP临场给你搭个台：你先过个灵感，成了就有戏。", "why": "接住玩家创造"},
    {"bad": "不可以搜这里，没东西。", "good": "你们翻了一遍，灰尘很厚——看起来很久没人动过（诚实反馈+省时间）。", "why": "诚实反馈省时间"},
    {"bad": "你不能一个人去。", "good": "单独去很危险，KP允许，但先告诉大家你的计划，镜头会切回来。", "why": "知情同意+镜头承诺"},
    {"bad": "就是不行，别问了。", "good": "KP先按不行判是为了保住今晚主线，团后咱们复盘这条支线。", "why": "解释动机+复盘承诺"},
    {"bad": "规则没写这种检定。", "good": "KP定一个：用最接近的技能，难度普通，先跑起来再说。", "why": "临场定标快判"},
    {"bad": "不能回头，剧情过了。", "good": "回去也行，但时间+1小时，追兵更近了——还回吗？", "why": "成本明示的选择"},
    {"bad": "你不能替他决定。", "good": "这个决定得他自己说——你可以在旁边劝，劝服用话术检定。", "why": "保护玩家自主+给机制"},
    {"bad": "没这个法术效果。", "good": "按字面没有，但KP允许你换个方式用：过个检定看能偏多少。", "why": "部分成功空间"},
    {"bad": "不允许跳过调查。", "good": "跳过可以，但你们会少拿两条线索，后面难度上升——确认跳？", "why": "代价透明"},
    {"bad": "模组没写结局，你赢了。", "good": "漂亮！KP按你们的行动临场收束：镇民的反应是……", "why": "临场收束不断联"},
    {"bad": "不行，你忘了你受伤了。", "good": "提醒一下：你腿上还有伤，这个动作先过体质，失败会加重——还做吗？", "why": "状态提醒+检定承接"},
]


def list_chapters() -> list[str]:
    """Frozen outline keys K1–K8 (DESIGN §2.4)."""
    return ["K1", "K2", "K3", "K4", "K5", "K6", "K7", "K8"]


def get_chapter(key: str) -> dict[str, Any]:
    if key not in CHAPTERS:
        raise KeyError(f"unknown chapter {key!r}, want one of {list_chapters()}")
    return CHAPTERS[key]


def get_cheatsheet() -> str:
    return CHAPTERS["K1"]["cheatsheet"]


def detect_veto(text: str) -> list[str]:
    """Return matched veto patterns in KP text (empty = clean)."""
    return [p for p in VETO_PATTERNS if p in (text or "")]


def suggest_rewrite(text: str) -> str:
    """Give a rewrite suggestion when veto wording is detected."""
    hits = detect_veto(text)
    if not hits:
        return "措辞干净，无需改写。"
    ex = VETO_REWRITES[hash(hits[0]) % len(VETO_REWRITES)]
    return (
        f"检测到否决式措辞{hits}。建议改写（{ex['why']}）："
        f"“{ex['good']}”（反例：{ex['bad']}）"
    )


def on_event(event: dict[str, Any] | Any) -> list[dict[str, str]]:
    """Trigger interface: event → coach reminders.

    Accepts frozen Event (pydantic) or plain dict {kind, payload}.
    Returns [{trigger: S1|S2|S3, chapter: Kx, message}].
    S2 = pace/spotlight/timeout triggers; S3 = veto/ruling triggers.
    """
    if hasattr(event, "kind") and hasattr(event, "payload"):
        kind = getattr(event.kind, "value", event.kind)
        payload: dict[str, Any] = dict(event.payload or {})
    else:
        kind = (event or {}).get("kind", "")
        payload = dict((event or {}).get("payload", {}))
    out: list[dict[str, str]] = []

    if kind == "say":
        text = str(payload.get("text", ""))
        hits = detect_veto(text)
        if hits:
            out.append({
                "trigger": "S3",
                "chapter": "K4",
                "message": f"否决式措辞{hits}，建议改写：{suggest_rewrite(text)}",
            })
    elif kind == "ruling" and payload.get("conflict"):
        out.append({
            "trigger": "S3",
            "chapter": "K7",
            "message": "规则冲突：10秒快判继续跑，记复盘项，团后对照判例库。",
        })
    elif kind == "ruling" and payload.get("needs_cheatsheet"):
        out.append({
            "trigger": "S3",
            "chapter": "K1",
            "message": f"一键速查：{get_cheatsheet()}",
        })
    elif kind == "alert":
        name = payload.get("alert", "")
        if name == "off_track":
            level = payload.get("level", "L1")
            out.append({
                "trigger": "S2",
                "chapter": "K5",
                "message": f"偏离主线（{level}）：先环境暗示→NPC拉回→KP明示，逐级升级。",
            })
        elif name == "timeout":
            out.append({
                "trigger": "S2",
                "chapter": "K6",
                "message": "超时：用快进话术推进——“你们翻了个底朝天，就在要放弃时——”。",
            })
        elif name in ("spotlight", "cold"):
            nxt = payload.get("pc", "最久没行动的PC")
            out.append({
                "trigger": "S2",
                "chapter": "K8",
                "message": f"聚光灯：点名{nxt}，给一个可行动的钩子。",
            })
    elif kind == "clue" and payload.get("at_risk"):
        out.append({
            "trigger": "S1",
            "chapter": "K2",
            "message": "漏线索风险：检查三线索保底，至少一条经NPC/环境送达。",
        })
    elif kind == "clue" and payload.get("private"):
        out.append({
            "trigger": "S1",
            "chapter": "K8",
            "message": "私聊信息：转一条桌面摘要【桌面摘要】…（细节保密）。",
        })
    elif kind == "clock":
        out.append({
            "trigger": "S2",
            "chapter": "K6",
            "message": "时钟推进：确认分幕计时与单房间调查上限。",
        })
    return out


# --- appendix: atmosphere (三感官) + NPC one-liners, 50 total ---------------

ATMOSPHERE: list[str] = [
    "视觉：煤油灯把影子拉得很长，墙上霉斑像一张脸。",
    "听觉：走廊尽头有水滴声，一下，一下，忽然停了。",
    "嗅觉：空气里有股旧纸和消毒水混在一起的味道。",
    "视觉：雾气贴着地面爬，路灯的光晕里全是飞虫。",
    "听觉：楼上地板吱呀一声——然后彻底安静。",
    "嗅觉：铁锈味越来越重，混着一点甜腻的腐气。",
    "视觉：镜子里你的倒影慢了半拍才跟上你。",
    "听觉：电话铃响了三声，在你伸手前自己断了。",
    "嗅觉：雨后泥土味里，夹着一丝烧纸钱的烟。",
    "视觉：所有钟都停在3:33，秒针还在抖。",
    "听觉：收音机沙沙响，隐约有人在念你们的名字。",
    "嗅觉：地下室飘上来霉味和机油味，还有别的。",
    "视觉：窗玻璃上有一枚从内侧按出的手印。",
    "听觉：隔壁房间传来椅子拖动声，可那间房没人住。",
    "嗅觉：花香浓得发腻，盖不住下面的土腥气。",
    "视觉：烛火无风自动，往门口的方向偏。",
    "听觉：楼梯上传来脚步声，数到第七级就没了。",
    "嗅觉：海风里有股鱼市收摊后的腥甜。",
    "视觉：照片里多了一个人，站在你们中间笑着。",
    "听觉：整点报时慢了十三秒，像有人掐着它。",
    "嗅觉：旧书页的霉味里混着新鲜血的气息。",
    "视觉：天花板的水渍正在扩大，形状像只手。",
    "听觉：风穿过门缝，听起来像有人在叹气。",
    "嗅觉：消毒水味盖不住的，是铁锈和汗的味道。",
    "视觉：路灯一盏接一盏灭过来，停在你们头顶这盏。",
]

NPC_PERSONAS: list[str] = [
    "旅店老板：口头禅“住店先押证啊”；动作：永远在擦同一个杯子。",
    "巡警老陈：口头禅“这事归我们管，也归你们倒霉”；动作：转笔。",
    "神秘线人：口头禅“你就当没见过我”；动作：说话只用左半边嘴。",
    "医生：口头禅“从医学角度说，你已经死了”；动作：推眼镜。",
    "小孩：口头禅“我妈妈说不能跟你们说话”；动作：边说边后退。",
    "酒保：口头禅“这杯算我请的，故事算你的”；动作：抛硬币决定听不听。",
    "教授：口头禅“有意思，非常有意思”；动作：掏出小本就记。",
    "司机：口头禅“这路我闭眼都能开”；动作：拍方向盘。",
    "房东太太：口头禅“电费很贵的！”；动作：随手关灯。",
    "记者：口头禅“能录音吗？就一句”；动作：笔帽按得咔哒响。",
    "渔夫：口头禅“海里的事，别问”；动作：补网的手不停。",
    "护士：口头禅“家属在外面等”；动作：看表，一分钟三次。",
    "古董商：口头禅“开过光的，真的”；动作：哈气擦货。",
    "学生：口头禅“我查过论文的”；动作：扶根本不存在的眼镜。",
    "保安：口头禅“登记一下，姓名电话”；动作：对讲机音量开最大。",
    "厨子：口头禅“趁热吃，凉了就不是这个味”；动作：颠勺。",
    "律师：口头禅“这句话我记下了”；动作：录音笔永远亮着红灯。",
    "流浪汉：口头禅“昨天我还看见他活着”；动作：数瓶盖。",
    "花店主：口头禅“花是有ینent的——是有脾气的”；动作：剪枯叶。",
    "维修工：口头禅“这楼，邪性”；动作：敲管子听声。",
    "前台：口头禅“请问有预约吗”；动作：微笑，眼睛不动。",
    "老船长：口头禅“风变了”；动作：摸胡子看天。",
    "图书管理员：口头禅“嘘——”；动作：食指永远备着。",
    "算命先生：口头禅“你印堂这团黑气啊”；动作：摸铜钱。",
    "快递员：口头禅“签收一下，代收也行”；动作：单子拍得啪啪响。",
]


def appendix_count() -> int:
    return len(ATMOSPHERE) + len(NPC_PERSONAS)


def ask_coassistant(snapshot: dict[str, Any] | None = None) -> list[str]:
    """一键AI副KP：只读快照→给三条行动建议（不断联）。"""
    snap = snapshot or {}
    scene = snap.get("scene", "当前场景")
    idle_pc = snap.get("idle_pc", "最久没行动的PC")
    risk = snap.get("risk", "主线")
    return [
        f"1）聚光灯：点名{idle_pc}，在{scene}给他一个可行动的钩子（检定/对话二选一）。",
        f"2）保底：检查{risk}的三线索路径，至少一条经NPC或环境自动送达。",
        f"3）节奏：{scene}若超20分钟无进展，用快进话术收束并推进时钟。",
    ]


# --- cases loader ------------------------------------------------------------

CASE_REQUIRED_KEYS: tuple[str, ...] = ("id", "clause", "question", "ruling", "source")


def load_cases(cases_dir: str | Path | None = None) -> list[dict[str, Any]]:
    d = Path(cases_dir) if cases_dir else CASES_DIR
    cases: list[dict[str, Any]] = []
    for path in sorted(d.glob("*.yaml")):
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"{path.name}: case must be a mapping")
            missing = [k for k in CASE_REQUIRED_KEYS if k not in item]
            if missing:
                raise ValueError(f"{path.name}: missing keys {missing}")
            cases.append(item)
    return cases


def cases_by_clause(cases: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for c in cases:
        grouped.setdefault(str(c["clause"]), []).append(c)
    return grouped
