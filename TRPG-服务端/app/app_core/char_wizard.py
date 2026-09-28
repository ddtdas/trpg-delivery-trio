"""TRPG character-creation wizard state machine (MIT).

Multi-step fill, backward moves (CARD_REVERTED), validation via the shared
hard gate, and CARD_FINALIZED/CARD_REVERTED/CHARACTER_CREATED events into
the store. Python 3.12 compatible.

T1 (additive): the wizard now walks the full CoC7 creation flow --
    basics -> attrs -> derived -> occupation -> skills -> background
    -> review -> done
while remaining backward compatible with the legacy 6-step flow: the old
"attrs" payload shape ({STR:.., CON:.., ...}) still works, "skills" accepts
both the legacy flat dict and the new occupation/interest pools, and
"background" accepts both the legacy string and background_details.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.app_core.coc7_rules import (
    interest_points,
    load_background_tables,
    load_occupations,
    load_skill_base,
    load_wizard_config,
    occupation_points,
    recompute_derived,
    roll_attrs,
    roll_background,
    san_current_for,
)
from app.domain.character import REQUIRED_ATTRS, CharacterCard, validate_card
from app.domain.events import make_event
from app.store.event_store import EventStore

STEPS: tuple[str, ...] = ("basics", "attrs", "derived", "occupation", "skills",
                          "background", "review", "done")

STEP_INDEX: dict[str, int] = {name: i for i, name in enumerate(STEPS)}

# Legacy 6-step flow (pre-T1): attrs/skills/background with old payload shapes.
LEGACY_STEPS = ("basics", "attrs", "skills", "background", "review", "done")


class WizardError(ValueError):
    """Raised on illegal wizard transitions or bad step data."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class WizardSession:
    card_id: str
    player_id: str
    ruleset: str = "coc7"
    step: str = "basics"
    name: str = ""
    age: int | None = None
    age_mod_applied: bool = False
    attrs: dict[str, int] = field(default_factory=dict)
    attrs_method: str = "dice"
    luck_enabled: bool = False
    luck: int | None = None
    roll_seed: int | None = None
    derived: dict[str, int] = field(default_factory=dict)
    occupation: str = ""
    occupation_credit: str = ""
    occupation_points: int | None = None
    interest_points: int | None = None
    skills: dict[str, int] = field(default_factory=dict)
    skill_points: dict[str, dict[str, int]] = field(default_factory=dict)
    background: str = ""
    background_details: dict[str, str] = field(default_factory=dict)
    idea: int | None = None
    knowledge: int | None = None
    san_current: int | None = None
    random_background_ref: str | None = None
    secret_ref: str | None = None
    history: list[str] = field(default_factory=list)

    def to_card(self) -> CharacterCard:
        return CharacterCard(
            card_id=self.card_id,
            player_id=self.player_id,
            ruleset=self.ruleset,
            name=self.name,
            attrs=dict(self.attrs),
            skills=dict(self.skills),
            background=self.background,
            secret_ref=self.secret_ref,
            age=self.age,
            age_mod_applied=self.age_mod_applied,
            luck=self.luck,
            derived=dict(self.derived),
            occupation=self.occupation,
            occupation_credit=self.occupation_credit,
            occupation_points=self.occupation_points,
            interest_points=self.interest_points,
            skill_points={k: dict(v) for k, v in self.skill_points.items()},
            background_details=dict(self.background_details),
            idea=self.idea,
            san_current=self.san_current,
            random_background_ref=self.random_background_ref,
            attrs_method=self.attrs_method,
        )


class CharWizard:
    """In-memory sessions; every mutation emits store events for audit."""

    def __init__(self, store: EventStore, campaign_id: str, actor: str = "kp") -> None:
        self.store = store
        self.campaign_id = campaign_id
        self.actor = actor
        self.sessions: dict[str, WizardSession] = {}
        self.wizard_cfg = load_wizard_config()

    def start(self, player_id: str, ruleset: str = "coc7",
              card_id: str | None = None) -> WizardSession:
        cid = card_id or ("card_" + uuid.uuid4().hex[:8])
        if cid in self.sessions:
            raise WizardError("card already in progress: %s" % cid)
        sess = WizardSession(card_id=cid, player_id=player_id, ruleset=ruleset)
        sess.history.append("basics")
        self.sessions[cid] = sess
        return sess

    def get(self, card_id: str) -> WizardSession:
        try:
            return self.sessions[card_id]
        except KeyError:
            raise WizardError("unknown card: %s" % card_id) from None

    # ---- step validation helpers ----

    def _validate_attrs(self, sess: WizardSession, data: dict) -> None:
        """attrs: dice (rolls) or point_buy (allocation), optional LUCK."""
        # Legacy shape: {STR:.., CON:.., ...} == dice rolls without method.
        method = str(data.get("method", "dice"))
        if method not in ("dice", "point_buy"):
            raise WizardError("attrs.method must be dice|point_buy")
        luck_enabled = bool(data.get("luck_enabled", False))
        luck = data.get("luck")
        if luck_enabled and luck is None:
            raise WizardError("attrs.luck: required when luck_enabled")
        if luck_enabled:
            try:
                luck_v = int(luck)
            except (TypeError, ValueError):
                raise WizardError("attrs.luck: not an int") from None
            if not 1 <= luck_v <= 100:
                raise WizardError("attrs.luck: out of range 1..100")
        # LUCK lives in the separate luck field when dice; only point_buy
        # may carry LUCK inside allocation (per wizard_config.exclude it is
        # normally excluded from the point pool).
        keys = list(REQUIRED_ATTRS)
        src = data.get("rolls" if method == "dice" else "allocation", data)
        if not isinstance(src, dict):
            raise WizardError("attrs: must be an object")
        for attr in keys:
            if attr not in src:
                raise WizardError("attrs.%s: missing" % attr)
            try:
                v = int(src[attr])
            except (TypeError, ValueError):
                raise WizardError("attrs.%s: not an int" % attr) from None
            if not 1 <= v <= 100:
                raise WizardError("attrs.%s: out of range 1..100" % attr)
        if method == "point_buy":
            cfg = self.wizard_cfg.get("point_buy") or {}
            total = int(cfg.get("total", 460))
            low = int(cfg.get("min", 15))
            high = int(cfg.get("max", 90))
            alloc = {k: int(v) for k, v in src.items()}
            for k, v in alloc.items():
                if v < low or v > high:
                    raise WizardError("attrs.%s: point_buy out of range %d..%d"
                                      % (k, low, high))
            if sum(alloc.values()) > total:
                raise WizardError("attrs: point_buy total exceeds %d" % total)
        sess.attrs = {k: int(src[k]) for k in keys}
        if luck_enabled:
            sess.attrs["LUCK"] = int(luck)
        sess.attrs_method = method
        sess.luck_enabled = luck_enabled
        sess.luck = int(luck) if luck_enabled else None
        sess.roll_seed = data.get("seed")

    def _validate_derived(self, sess: WizardSession, data: dict) -> None:
        """derived: apply age modifier once, then recompute derived sheet."""
        age = data.get("age")
        if age is not None:
            try:
                age = int(age)
            except (TypeError, ValueError):
                raise WizardError("derived.age: not an int") from None
        cfg = self.wizard_cfg.get("age_rule") or {}
        if age is not None and age < int(cfg.get("min_investigator_age", 15)):
            raise WizardError("derived.age: below min investigator age")
        sess.age = age
        if age is not None and not sess.age_mod_applied and cfg.get("apply", True):
            mods = cfg.get("age_mods") or []
            band = None
            for m in mods:
                if int(m.get("min", 0)) <= age <= int(m.get("max", 999)):
                    band = m
                    break
            if band is not None:
                # 【队长裁决 2026-09-28】7e 官方表只修 INT 与 EDU，不修 SIZ；修正后上限 99。
                cap = int(cfg.get("cap", 99) or 99)
                for attr, key in (("EDU", "edu"), ("INT", "int")):
                    mod = int(band.get(key, 0) or 0)
                    if mod and attr in sess.attrs:
                        sess.attrs[attr] = max(1, min(cap, sess.attrs[attr] + mod))
                sess.age_mod_applied = True
        # Recompute derived sheet (idempotent). 【队长裁决 2026-09-28】MP=POW/10 默认 7e。
        rv = str((self.wizard_cfg.get("ruleset_version") or {}).get("version", "7e")
                 if isinstance(self.wizard_cfg.get("ruleset_version"), dict)
                 else self.wizard_cfg.get("ruleset_version", "7e") or "7e")
        sess.derived = recompute_derived(
            sess.attrs, luck_enabled=sess.luck_enabled, luck=sess.luck,
            ruleset_version=rv)
        sess.idea = sess.attrs.get("INT", 0) * 5
        sess.knowledge = sess.attrs.get("EDU", 0) * 5
        sess.san_current = san_current_for(sess.attrs)

    def _validate_occupation(self, sess: WizardSession, data: dict) -> None:
        """occupation: known id, credit within range, points computed."""
        occ_id = str(data.get("occupation", "")).strip()
        occs = load_occupations(sess.ruleset)
        occ = occs.get(occ_id)
        if not occ:
            raise WizardError("occupation: unknown id %r" % occ_id)
        credit = data.get("credit_rating")
        if credit is None:
            raise WizardError("occupation.credit_rating: required")
        try:
            credit = int(credit)
        except (TypeError, ValueError):
            raise WizardError("occupation.credit_rating: not an int") from None
        cr = occ.get("credit") or {}
        if credit < int(cr.get("min", 0)) or credit > int(cr.get("max", 100)):
            raise WizardError("occupation.credit_rating: out of range %d..%d"
                              % (int(cr.get("min", 0)), int(cr.get("max", 100))))
        sess.occupation = occ_id
        sess.occupation_credit = str(credit)
        sess.occupation_points = occupation_points(occ, sess.attrs.get("EDU", 0))
        sess.interest_points = interest_points(sess.attrs.get("INT", 0))

    def _validate_skills(self, sess: WizardSession, data: dict) -> None:
        """skills: occupation pool + interest pool (or legacy flat dict)."""
        base = load_skill_base(sess.ruleset)
        cfg = self.wizard_cfg
        cap75 = bool(cfg.get("skill_creation_cap75", True))
        max_total = int(cfg.get("max_skill_total", 4000))
        # Legacy: flat {skill: final_value} == points applied on top of base.
        if "occupation" not in data and "interest" not in data:
            flat = data.get("skills", data)
            if not isinstance(flat, dict):
                raise WizardError("skills: must be an object")
            final: dict[str, int] = {}
            for k, v in flat.items():
                try:
                    iv = int(v)
                except (TypeError, ValueError):
                    raise WizardError("skills.%s: not an int" % k) from None
                if not 0 <= iv <= 100:
                    raise WizardError("skills.%s: out of range 0..100" % k)
                final[k] = iv
            sess.skills = final
            sess.skill_points = {}
            return
        occ_pool = data.get("occupation") or {}
        int_pool = data.get("interest") or {}
        if not isinstance(occ_pool, dict) or not isinstance(int_pool, dict):
            raise WizardError("skills pools must be objects")
        final = dict(base)
        for pool in ("occupation", "interest"):
            pool_data = occ_pool if pool == "occupation" else int_pool
            for k, v in pool_data.items():
                if k not in base:
                    raise WizardError("skills.%s: unknown skill" % k)
                try:
                    pts = int(v)
                except (TypeError, ValueError):
                    raise WizardError("skills.%s.%s: not an int" % (pool, k)) from None
                if pts < 0:
                    raise WizardError("skills.%s.%s: negative points" % (pool, k))
                total = int(base.get(k, 0)) + pts
                if not 0 <= total <= 100:
                    raise WizardError("skills.%s: total out of range 0..100" % k)
                if total > 75 and cap75 and k not in ("credit_rating", "cthulhu_mythos"):
                    raise WizardError("skills.%s: exceeds 75 creation cap" % k)
                final[k] = total
        if sum(int(v) for v in occ_pool.values()) > (sess.occupation_points or 0):
            raise WizardError("skills: occupation points exceeded")
        if sum(int(v) for v in int_pool.values()) > (sess.interest_points or 0):
            raise WizardError("skills: interest points exceeded")
        if sum(final.values()) > max_total:
            raise WizardError("skills: total exceeds %d" % max_total)
        sess.skills = final
        sess.skill_points = {"occupation": {k: int(v) for k, v in occ_pool.items()},
                             "interest": {k: int(v) for k, v in int_pool.items()}}

    def _validate_background(self, sess: WizardSession, data: dict) -> None:
        """background: legacy string + optional details; all optional."""
        ALLOWED = {"personal_desc", "traits", "beliefs", "significant_people",
                   "meaningful_locations", "treasured_possessions",
                   "wounds_scars", "phobias_manias"}
        details = data.get("background_details")
        if details is not None and not isinstance(details, dict):
            raise WizardError("background_details: must be an object")
        if isinstance(details, dict):
            for k in details:
                if k not in ALLOWED:
                    raise WizardError("background_details.%s: unknown key" % k)
            sess.background_details = {k: str(v) for k, v in details.items()}
        if data.get("background") is not None:
            sess.background = str(data["background"])
        if data.get("secret_ref") is not None:
            sess.secret_ref = str(data["secret_ref"])
        # Optional random background (default off).
        if bool(self.wizard_cfg.get("random_background_enabled", False)) \
                and not sess.random_background_ref \
                and not sess.background_details:
            tables = load_background_tables(sess.ruleset)
            if tables:
                details, ref = roll_background(sess.ruleset, seed=sess.roll_seed,
                                               tables=tables)
                sess.background_details = details
                sess.random_background_ref = ref or None

    def fill(self, card_id: str, step: str, data: dict) -> WizardSession:
        sess = self.get(card_id)
        if step not in STEP_INDEX:
            raise WizardError("unknown step: %r" % step)
        if step == "done":
            raise WizardError("use finalize() to reach done")
        if not isinstance(data, dict):
            raise WizardError("step data must be an object")
        if step == "basics":
            name = str(data.get("name", ""))
            if not name.strip():
                raise WizardError("basics.name: required")
            sess.name = name.strip()
            if data.get("age") is not None:
                try:
                    sess.age = int(data["age"])
                except (TypeError, ValueError):
                    raise WizardError("basics.age: not an int") from None
        elif step == "attrs":
            self._validate_attrs(sess, data)
        elif step == "derived":
            self._validate_derived(sess, data)
        elif step == "occupation":
            self._validate_occupation(sess, data)
        elif step == "skills":
            self._validate_skills(sess, data)
        elif step == "background":
            self._validate_background(sess, data)
        elif step == "review":
            pass  # review carries no new data; gate lives in finalize()
        # Forward-only step pointer, but any earlier step may be re-filled.
        if STEP_INDEX[step] > STEP_INDEX[sess.step]:
            sess.step = step
        if step not in sess.history:
            sess.history.append(step)
        return sess

    def back(self, card_id: str, to_step: str) -> WizardSession:
        """Move the pointer back; the move itself is audited on finalize path."""
        sess = self.get(card_id)
        if to_step not in STEP_INDEX:
            raise WizardError("unknown step: %r" % to_step)
        if STEP_INDEX[to_step] >= STEP_INDEX[sess.step]:
            raise WizardError("back() must move to an earlier step")
        sess.step = to_step
        sess.history.append("back:%s" % to_step)
        return sess

    async def revert(self, card_id: str, to_step: str, reason: str) -> WizardSession:
        sess = self.back(card_id, to_step)
        from_step = sess.history[-2] if len(sess.history) >= 2 else sess.step
        ev = make_event(
            seq=0, campaign_id=self.campaign_id, type="CARD_REVERTED",
            payload={"card_id": card_id, "from_step": from_step,
                     "to_step": to_step, "reason": reason},
            actor=self.actor, ts=_now())
        await self.store.append(self.campaign_id, [ev])
        return sess

    async def finalize(self, card_id: str) -> CharacterCard:
        sess = self.get(card_id)
        card = sess.to_card()
        report = validate_card(card)
        if not report.ok:
            raise WizardError("card invalid: %s" % "; ".join(report.errors))
        # Soft->hard gate for full COC7 flow: once the card has walked the
        # derived/occupation steps (i.e. the new 8-step path, not legacy),
        # occupation + skill legality is enforced. Legacy 6-step cards that
        # never entered derived/occupation skip this gate entirely.
        if "derived" in sess.history or "occupation" in sess.history:
            if not sess.occupation:
                raise WizardError("card invalid: occupation required (full flow)")
            if not sess.skill_points.get("occupation"):
                raise WizardError("card invalid: occupation skills required (full flow)")
        created = make_event(
            seq=0, campaign_id=self.campaign_id, type="CHARACTER_CREATED",
            payload={"card_id": card.card_id, "player_id": card.player_id,
                     "ruleset": card.ruleset,
                     "card": card.model_dump(mode="json")},
            actor=self.actor, ts=_now())
        finalized = make_event(
            seq=0, campaign_id=self.campaign_id, type="CARD_FINALIZED",
            payload={"card_id": card.card_id, "validation_report_ref": "vr:%s" % card.card_id},
            actor=self.actor, ts=_now(), approved_by=self.actor)
        await self.store.append(self.campaign_id, [created, finalized])
        sess.step = "done"
        sess.history.append("done")
        return card
