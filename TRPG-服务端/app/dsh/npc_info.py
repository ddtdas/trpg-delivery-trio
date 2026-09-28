"""T7 (additive): M1-ext background -> NPC public info (MIT).

After a card finalizes, derive "what NPCs can learn about this player"
from background_details (personal_desc / beliefs / significant_people etc).
Output lands as NPC_INFO_GENERATED and mirrors into campaign relations.
Deterministic generation (no LLM dependency); gateway upgrade stubbed.
Python 3.12 compatible.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.domain.events import make_event


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_FIELD_TEMPLATES = {
    "personal_desc": "调查员的外貌与气质",
    "beliefs": "调查员的信念与信仰",
    "significant_people": "调查员的重要之人",
    "meaningful_locations": "调查员的重要之地",
    "treasured_possessions": "调查员的珍贵之物",
    "traits": "调查员的性格",
    "wounds_scars": "调查员的旧伤",
    "phobias_manias": "调查员的恐惧",
}


def derive_public_infos(background_details):
    """Map background details to public-info lines (deterministic)."""
    details = dict(background_details or {})
    out = []
    for field, template in _FIELD_TEMPLATES.items():
        text = str(details.get(field) or "").strip()
        if not text:
            continue
        confidence = min(0.95, 0.5 + len(text) / 200.0)
        out.append({"field": field,
                    "info_text": "%s：%s" % (template, text[:120]),
                    "confidence": round(confidence, 2)})
    return out


async def generate_npc_info(campaign_id, card, npc_ids=None):
    """Derive public infos for a card and append NPC_INFO_GENERATED."""
    public_infos = derive_public_infos(card.get("background_details") or {})
    if not public_infos:
        return []
    from app.web import rest as rest_mod
    store = rest_mod._store()
    await store.init()
    player_id = str(card.get("player_id") or "")
    ev = make_event(seq=0, campaign_id=campaign_id, type="NPC_INFO_GENERATED",
                    payload={"campaign_id": campaign_id,
                             "player_id": player_id,
                             "npc_ids": list(npc_ids or []),
                             "public_infos": public_infos},
                    actor="kp", ts=_now())
    await store.append(campaign_id, [ev])
    try:
        from app.repository import campaign_folder as cf
        cf.ensure_campaign(campaign_id)
        for info in public_infos:
            cf.append_relation(campaign_id, {
                "from": player_id, "to": "npc:public", "kind": "public_info",
                "label": info.get("field"), "text": info.get("info_text"),
                "ts": _now()})
    except Exception:
        pass
    return public_infos
