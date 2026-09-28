import React from 'react';
import { ErrorBanner } from './ui';
// T16.1: CharWizard 全重写 —— 接真实 wizard_api（start/fill/back/finalize），不再纯本地演示。
//
// 契约（实测 2026-09-28，app/web/wizard_api.py）：
//   POST /api/wizard/start {campaign_id, player_id} -> 201 {ok, session:{card_id, step, ...}}
//   POST /api/wizard/{card_id}/fill {campaign_id, step, data} -> 200 {ok, session}
//   GET  /api/wizard/{card_id}?campaign= -> 200 {ok, session}
//   POST /api/wizard/{card_id}/back {campaign_id, to_step} -> 200 {ok, session}
//   POST /api/wizard/{card_id}/finalize {campaign_id} -> 201 {ok, card_id, card}
// 鉴权（access.py 实测）：start/fill/back = mobile 端 token（webapp 会 403 mobile_only）；
//   finalize = webapp（KP 端）token。因此本组件提供「玩家 token（mobile）」与「主持人 token（webapp）」
//   两个输入框，默认分别读 localStorage trpg_mobile_token / trpg_token，均可页面内设置并持久化。
// 技能单一事实源（T16 实测补充）：
//   1) 运行时 fetch GET /api/rules/rulesets/coc7（webapp token）取 rulepack.skills（42 项，
//      value=基础值 int）+ rulepack.skill_meta（attr/category）——后端权威。
//   2) 与内嵌 skills_7e.yaml（schema coc.skills_7e.v1，72 项，{base,attr,category}）合并去重，
//      归一别名（rulepack 的 firearms_rifle == 7e 的 firearms_rifle_shotgun）→ 完整清单。
//   合并口径：rulepack.skills 优先（后端权威 base/attr/category），7e 增量补齐缺失 id。
//   职业点数/兴趣点仅展示提示，最终以 finalize 硬校验为准。

const STEPS = ['概念', '属性', '技能', '背景', '确认'] as const;

/** skills_7e.yaml（官方 7e 技能清单, schema coc.skills_7e.v1）内嵌常量 —— 72 项。 */
const SKILLS_7E: Array<{ id: string; zh: string; base: number; attr: string; cat: string }> = [
  { id: 'accounting', zh: '会计', base: 5, attr: 'EDU', cat: 'knowledge' },
  { id: 'anthropology', zh: '人类学', base: 1, attr: 'EDU', cat: 'knowledge' },
  { id: 'appraise', zh: '估价', base: 5, attr: 'EDU', cat: 'knowledge' },
  { id: 'archaeology', zh: '考古学', base: 1, attr: 'EDU', cat: 'knowledge' },
  { id: 'art_craft', zh: '艺术/手艺', base: 5, attr: 'DEX', cat: 'technical' },
  { id: 'charm', zh: '魅惑', base: 15, attr: 'APP', cat: 'social' },
  { id: 'climb', zh: '攀爬', base: 20, attr: 'STR', cat: 'physical' },
  { id: 'credit_rating', zh: '信用评级', base: 0, attr: 'APP', cat: 'social' },
  { id: 'cthulhu_mythos', zh: '克苏鲁神话', base: 0, attr: '-', cat: 'mythos' },
  { id: 'disguise', zh: '乔装', base: 5, attr: 'APP', cat: 'social' },
  { id: 'dodge', zh: '闪避', base: 0, attr: 'DEX', cat: 'combat' },
  { id: 'drive_auto', zh: '汽车驾驶', base: 20, attr: 'DEX', cat: 'technical' },
  { id: 'electrical_repair', zh: '电器维修', base: 10, attr: 'DEX', cat: 'technical' },
  { id: 'fast_talk', zh: '话术', base: 5, attr: 'APP', cat: 'social' },
  { id: 'fighting_brawl', zh: '格斗', base: 25, attr: 'STR', cat: 'combat' },
  { id: 'firearms_handgun', zh: '手枪', base: 20, attr: 'DEX', cat: 'combat' },
  { id: 'firearms_rifle_shotgun', zh: '步枪/霰弹枪', base: 25, attr: 'DEX', cat: 'combat' },
  { id: 'first_aid', zh: '急救', base: 30, attr: 'EDU', cat: 'knowledge' },
  { id: 'history', zh: '历史', base: 5, attr: 'EDU', cat: 'knowledge' },
  { id: 'intimidate', zh: '恐吓', base: 15, attr: 'STR', cat: 'social' },
  { id: 'jump', zh: '跳跃', base: 20, attr: 'STR', cat: 'physical' },
  { id: 'language_own', zh: '母语', base: 0, attr: 'EDU', cat: 'knowledge' },
  { id: 'law', zh: '法律', base: 5, attr: 'EDU', cat: 'knowledge' },
  { id: 'library_use', zh: '图书馆使用', base: 20, attr: 'EDU', cat: 'knowledge' },
  { id: 'listen', zh: '聆听', base: 20, attr: '-', cat: 'perception' },
  { id: 'locksmith', zh: '锁匠', base: 1, attr: 'DEX', cat: 'technical' },
  { id: 'mechanical_repair', zh: '机械维修', base: 10, attr: 'DEX', cat: 'technical' },
  { id: 'medicine', zh: '医学', base: 1, attr: 'EDU', cat: 'knowledge' },
  { id: 'natural_world', zh: '博物学', base: 10, attr: 'EDU', cat: 'knowledge' },
  { id: 'navigate', zh: '导航', base: 10, attr: 'EDU', cat: 'technical' },
  { id: 'occult', zh: '神秘学', base: 5, attr: 'EDU', cat: 'knowledge' },
  { id: 'persuade', zh: '说服', base: 10, attr: 'APP', cat: 'social' },
  { id: 'pilot', zh: '飞行', base: 1, attr: 'DEX', cat: 'technical' },
  { id: 'psychology', zh: '心理学', base: 10, attr: 'EDU', cat: 'knowledge' },
  { id: 'ride', zh: '骑术', base: 5, attr: 'DEX', cat: 'technical' },
  { id: 'science', zh: '科学', base: 1, attr: 'EDU', cat: 'knowledge' },
  { id: 'sleight_of_hand', zh: '妙手', base: 10, attr: 'DEX', cat: 'technical' },
  { id: 'spot_hidden', zh: '侦查', base: 25, attr: '-', cat: 'perception' },
  { id: 'stealth', zh: '潜行', base: 20, attr: 'DEX', cat: 'physical' },
  { id: 'swim', zh: '游泳', base: 20, attr: 'STR', cat: 'physical' },
  { id: 'throw', zh: '投掷', base: 20, attr: 'DEX', cat: 'physical' },
  { id: 'track', zh: '追踪', base: 10, attr: '-', cat: 'perception' },
  { id: 'art_craft_acting', zh: '表演', base: 5, attr: 'APP', cat: 'technical' },
  { id: 'art_craft_painting', zh: '绘画', base: 5, attr: 'DEX', cat: 'technical' },
  { id: 'art_craft_photography', zh: '摄影', base: 5, attr: 'DEX', cat: 'technical' },
  { id: 'art_craft_writing', zh: '写作', base: 5, attr: 'DEX', cat: 'technical' },
  { id: 'firearms_smg', zh: '冲锋枪', base: 15, attr: 'DEX', cat: 'combat' },
  { id: 'firearms_heavy', zh: '重型枪械', base: 10, attr: 'DEX', cat: 'combat' },
  { id: 'fighting_sword', zh: '剑术', base: 20, attr: 'DEX', cat: 'combat' },
  { id: 'fighting_axe', zh: '斧术', base: 15, attr: 'STR', cat: 'combat' },
  { id: 'fighting_knife', zh: '刀术', base: 25, attr: 'DEX', cat: 'combat' },
  { id: 'fighting_chain', zh: '链击', base: 10, attr: 'DEX', cat: 'combat' },
  { id: 'fighting_garrote', zh: '绞索', base: 15, attr: 'DEX', cat: 'combat' },
  { id: 'fighting_flail', zh: '连枷', base: 10, attr: 'DEX', cat: 'combat' },
  { id: 'fighting_spear', zh: '矛术', base: 20, attr: 'STR', cat: 'combat' },
  { id: 'fighting_whip', zh: '鞭术', base: 5, attr: 'DEX', cat: 'combat' },
  { id: 'language_other', zh: '其他语言', base: 0, attr: 'EDU', cat: 'knowledge' },
  { id: 'language_other2', zh: '其他语言 II', base: 0, attr: 'EDU', cat: 'knowledge' },
  { id: 'demolitions', zh: '爆破', base: 1, attr: 'INT', cat: 'technical' },
  { id: 'survival', zh: '生存', base: 10, attr: 'INT', cat: 'knowledge' },
  { id: 'hypnosis', zh: '催眠', base: 1, attr: 'INT', cat: 'social' },
  { id: 'astronomy', zh: '天文学', base: 1, attr: 'EDU', cat: 'knowledge' },
  { id: 'biology', zh: '生物学', base: 1, attr: 'EDU', cat: 'knowledge' },
  { id: 'chemistry', zh: '化学', base: 1, attr: 'EDU', cat: 'knowledge' },
  { id: 'geology', zh: '地质学', base: 1, attr: 'EDU', cat: 'knowledge' },
  { id: 'mathematics', zh: '数学', base: 1, attr: 'EDU', cat: 'knowledge' },
  { id: 'physics', zh: '物理学', base: 1, attr: 'EDU', cat: 'knowledge' },
  { id: 'pharmacy', zh: '药学', base: 1, attr: 'EDU', cat: 'knowledge' },
  { id: 'cryptography', zh: '密码学', base: 1, attr: 'EDU', cat: 'knowledge' },
  { id: 'forensic_medicine', zh: '法医学', base: 1, attr: 'EDU', cat: 'knowledge' },
  { id: 'read_lips', zh: '读唇', base: 1, attr: 'INT', cat: 'perception' },
  { id: 'psychoanalysis', zh: '精神分析', base: 1, attr: 'EDU', cat: 'knowledge' },
];

/** occupations.yaml（rulepacks/coc7/occupations.yaml）内嵌职业清单 —— 仅展示参考。 */
const OCCUPATIONS: Array<{ id: string; zh: string }> = [
  { id: 'archaeologist', zh: '考古学家' },
  { id: 'author', zh: '作家' },
  { id: 'criminal', zh: '罪犯' },
  { id: 'doctor', zh: '医生' },
  { id: 'private_investigator', zh: '私家侦探' },
  { id: 'journalist', zh: '记者' },
  { id: 'professor', zh: '教授' },
  { id: 'engineer', zh: '工程师' },
  { id: 'artist', zh: '艺术家' },
  { id: 'businessperson', zh: '商人' },
  { id: 'military', zh: '军人' },
  { id: 'scientist', zh: '科学家' },
  { id: 'psychiatrist', zh: '心理医生' },
  { id: 'drifter', zh: '流浪汉' },
  { id: 'police_detective', zh: '警探' },
  { id: 'bartender', zh: '酒吧招待' },
  { id: 'librarian', zh: '图书管理员' },
  { id: 'undertaker', zh: '殡葬师' },
  { id: 'clergyman', zh: '神职人员' },
];

const ATTRS = ['STR', 'CON', 'SIZ', 'DEX', 'APP', 'INT', 'POW', 'EDU'] as const;
type AttrName = (typeof ATTRS)[number];

const BG_FIELDS: Array<{ key: string; zh: string }> = [
  { key: 'personal_desc', zh: '个人描述' },
  { key: 'beliefs', zh: '思想与信念' },
  { key: 'significant_people', zh: '重要之人' },
  { key: 'meaningful_locations', zh: '重要之地' },
  { key: 'treasured_possessions', zh: '珍贵之物' },
  { key: 'traits', zh: '特质' },
  { key: 'wounds_scars', zh: '伤痕与疤痕' },
  { key: 'phobias_manias', zh: '恐惧与狂躁' },
];

interface WizardSession {
  card_id: string;
  player_id: string;
  ruleset: string;
  step: string;
  name: string;
  age: number | null;
  attrs: Record<string, number>;
  derived: Record<string, number>;
  occupation: string;
  occupation_points: number | null;
  interest_points: number | null;
  skills: Record<string, number>;
  skill_points: { occupation?: Record<string, number>; interest?: Record<string, number> };
  background: string;
  background_details: Record<string, string>;
}

function env(): Record<string, string | undefined> {
  return (import.meta as unknown as { env?: Record<string, string | undefined> }).env ?? {};
}

/** URL 查询串参数（主持端带参加载 ?campaign=...&token=...）。 */
function urlParam(key: string): string {
  try {
    return new URLSearchParams(window.location.search).get(key) ?? '';
  } catch {
    return '';
  }
}

/** 持久化读取：localStorage 优先，回退 URL token / 构建期 env。 */
function readToken(key: string, envKey: string, urlKey: string): string {
  try {
    const ls = localStorage.getItem(key);
    if (ls && ls.trim()) return ls.trim();
  } catch { /* ignore */ }
  return urlParam(urlKey) || env()[envKey] || '';
}

/** 前端按 7e 规则计算派生值（后端 derived 已有则用后端的）。 */
function computeDerived(attrs: Record<string, number>): Record<string, number> {
  const con = attrs.CON ?? 0, siz = attrs.SIZ ?? 0, pow = attrs.POW ?? 0, dex = attrs.DEX ?? 0;
  const int = attrs.INT ?? 0, edu = attrs.EDU ?? 0;
  return {
    hp_max: Math.floor((siz + con) / 10),
    mp_max: Math.floor(pow / 10),
    san_start: Math.max(0, Math.min(99, pow)),
    luck: (attrs.LUCK ?? pow) * 5,
    dodge: Math.floor(dex / 2),
    idea: int * 5,
    knowledge: edu * 5,
  };
}

export function CharWizard(): React.ReactElement {
  const campaign = urlParam('campaign') || 'c_t9tl';
  // 两个 token：mobile=玩家端（start/fill/back），webapp=主持人端（finalize）
  const [mobileToken, setMobileToken] = React.useState(() => readToken('trpg_mobile_token', 'VITE_TRPG_MOBILE_TOKEN', 'mtoken'));
  const [kpToken, setKpToken] = React.useState(() => readToken('trpg_token', 'VITE_TRPG_TOKEN', 'token'));

  const [step, setStep] = React.useState(0);
  const [cardId, setCardId] = React.useState('');
  // card_id 同步 ref：start 异步返回后立即供 fill 使用（避免 setState 闭包过期）。
  const cardIdRef = React.useRef('');
  const [playerId, setPlayerId] = React.useState('kp1');
  const [name, setName] = React.useState('');
  const [occupation, setOccupation] = React.useState('private_investigator');
  const [creditRating, setCreditRating] = React.useState(30);
  const [attrs, setAttrs] = React.useState<Record<AttrName, number>>({ STR: 45, CON: 50, SIZ: 50, DEX: 60, APP: 45, INT: 75, POW: 70, EDU: 65 });
  const [occPool, setOccPool] = React.useState<Record<string, number>>({});
  const [intPool, setIntPool] = React.useState<Record<string, number>>({});
  const [background, setBackground] = React.useState('');
  const [bgDetails, setBgDetails] = React.useState<Record<string, string>>({});
  const [derived, setDerived] = React.useState<Record<string, number>>({});
  const [occPoints, setOccPoints] = React.useState<number | null>(null);
  const [intPoints, setIntPoints] = React.useState<number | null>(null);
  const [error, setError] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [done, setDone] = React.useState(false);
  const [finalized, setFinalized] = React.useState(false);
  // T16 实测补充：完整技能清单（rulepack 42 + 7e 增量合并去重）。默认 = 内嵌 72 项，
  // 启动时 fetch /api/rules/rulesets/coc7 用后端 base/attr/cat 覆盖（单一事实源）。
  const [skillCatalog, setSkillCatalog] = React.useState<Array<{ id: string; zh: string; base: number; attr: string; cat: string }>>(SKILLS_7E);
  const [skillSource, setSkillSource] = React.useState<'7e-inline' | 'rulepack'>('7e-inline');

  // 启动拉取 rulepack 技能（webapp token，只读）→ 合并去重为真实完整清单。
  React.useEffect(() => {
    let alive = true;
    const t = kpToken || urlParam('token');
    if (!t) return undefined;
    fetch('/api/rules/rulesets/coc7', { headers: { Authorization: 'Bearer ' + t } })
      .then((resp) => (resp.ok ? resp.json() : null))
      .then((raw) => {
        if (!alive) return;
        const rp = raw && typeof raw === 'object' ? (raw as Record<string, unknown>).rulepack as Record<string, unknown> | undefined : undefined;
        const skills = rp && typeof rp.skills === 'object' && rp.skills ? rp.skills as Record<string, number> : undefined;
        const meta = rp && typeof rp.skill_meta === 'object' && rp.skill_meta ? rp.skill_meta as Record<string, { attr?: string; category?: string }> : undefined;
        if (!skills) return;
        // 合并：rulepack base/attr/cat 覆盖 7e；firearms_rifle → 7e 的 firearms_rifle_shotgun 别名归一
        const zhById = new Map(SKILLS_7E.map((s) => [s.id, s.zh]));
        const merged = new Map<string, { id: string; zh: string; base: number; attr: string; cat: string }>();
        for (const s of SKILLS_7E) merged.set(s.id, { ...s });
        for (const [rid, baseVal] of Object.entries(skills)) {
          const cid = rid === 'firearms_rifle' ? 'firearms_rifle_shotgun' : rid;
          const prev = merged.get(cid);
          if (prev) {
            prev.base = Number(baseVal) || prev.base;
            if (meta && meta[rid]) {
              if (meta[rid].attr) prev.attr = meta[rid].attr;
              if (meta[rid].category) prev.cat = meta[rid].category;
            }
          } else {
            const m = meta ? meta[rid] : undefined;
            merged.set(cid, { id: cid, zh: zhById.get(cid) ?? rid, base: Number(baseVal) || 0, attr: m?.attr ?? '-', cat: m?.category ?? '' });
          }
        }
        setSkillCatalog([...merged.values()]);
        setSkillSource('rulepack');
      })
      .catch(() => { /* 拉取失败保持内嵌 7e 清单 */ });
    return () => { alive = false; };
  }, [kpToken]);

  const authHeaders = (t: string): Record<string, string> => ({ 'Content-Type': 'application/json', ...(t ? { Authorization: 'Bearer ' + t } : {}) });

  const api = React.useCallback(async (method: string, path: string, t: string, body?: Record<string, unknown>) => {
    const resp = await fetch(path, { method, headers: authHeaders(t), body: body ? JSON.stringify(body) : undefined });
    const raw = (await resp.json().catch(() => null)) as Record<string, unknown> | null;
    return { ok: resp.ok, status: resp.status, raw };
  }, []);

  const setStepFromBackend = (s: string): void => {
    const idx: Record<string, number> = { basics: 0, attrs: 1, derived: 1, skills: 2, background: 3, review: 4, done: 4 };
    const v = idx[s];
    if (typeof v === 'number') setStep(Math.min(4, v));
  };

  const applySession = (sess: WizardSession): void => {
    if (sess.card_id) { setCardId(sess.card_id); cardIdRef.current = sess.card_id; }
    if (sess.step) setStepFromBackend(sess.step);
    if (sess.name) setName(sess.name);
    if (sess.attrs && Object.keys(sess.attrs).length) setAttrs((prev) => {
      const next = { ...prev };
      for (const k of ATTRS) if (typeof sess.attrs[k] === 'number') next[k] = sess.attrs[k];
      return next;
    });
    if (sess.derived && Object.keys(sess.derived).length) setDerived(sess.derived);
    if (sess.occupation) setOccupation(sess.occupation);
    if (typeof sess.occupation_points === 'number') setOccPoints(sess.occupation_points);
    if (typeof sess.interest_points === 'number') setIntPoints(sess.interest_points);
    if (sess.background) setBackground(sess.background);
    if (sess.background_details && Object.keys(sess.background_details).length) setBgDetails(sess.background_details);
  };

  const fill = React.useCallback(async (stepName: string, data: Record<string, unknown>): Promise<boolean> => {
    if (!mobileToken) { setError('请先填写玩家 token（mobile 端），start/fill 需要它。'); return false; }
    setBusy(true); setError('');
    try {
      const cid = cardIdRef.current;
      if (!cid) { setError('尚未建卡（无 card_id）。'); return false; }
      const res = await api('POST', '/api/wizard/' + cid + '/fill', mobileToken, { campaign_id: campaign, step: stepName, data });
      if (!res.ok) {
        const rawMap = res.raw ?? {};
        const detail = String(rawMap.detail ?? rawMap.error ?? ('HTTP ' + res.status));
        setError('保存失败（' + stepName + '）：' + detail);
        return false;
      }
      const sess = ((res.raw as Record<string, unknown>).session ?? {}) as WizardSession;
      applySession(sess);
      return true;
    } catch (e) {
      setError('保存失败（' + stepName + '）：' + (e instanceof Error ? e.message : String(e)));
      return false;
    } finally { setBusy(false); }
  }, [api, cardId, campaign, mobileToken]);
  const start = async (): Promise<void> => {
    if (!mobileToken) { setError('请先填写玩家 token（mobile 端），start 需要它。'); return; }
    setBusy(true); setError(''); setDone(false); setFinalized(false);
    try {
      const res = await api('POST', '/api/wizard/start', mobileToken, { campaign_id: campaign, player_id: playerId });
      if (!res.ok) {
        const rawMap = res.raw ?? {};
        const detail = String(rawMap.detail ?? rawMap.error ?? ('HTTP ' + res.status));
        setError('建卡失败：' + detail);
        return;
      }
      const sess = ((res.raw as Record<string, unknown>).session ?? {}) as WizardSession;
      setCardId(sess.card_id);
      applySession(sess);
      setStep(0);
    } catch (e) {
      setError('建卡失败：' + (e instanceof Error ? e.message : String(e)));
    } finally { setBusy(false); }
  };

  const next = async (): Promise<void> => {
    setError('');
    let okSave = false;
    if (step === 0) {
      if (!name.trim()) { setError('请填写调查员姓名。'); return; }
      if (!cardId) {
        // 首次：start 建卡（生成 card_id）
        if (!mobileToken) { setError('请先填写玩家 token（mobile 端）。'); return; }
        setBusy(true);
        try {
          const res = await api('POST', '/api/wizard/start', mobileToken, { campaign_id: campaign, player_id: playerId });
          if (!res.ok) {
            const rawMap = res.raw ?? {};
            setError('建卡失败：' + String(rawMap.detail ?? rawMap.error ?? ('HTTP ' + res.status)));
            return;
          }
          const sess = ((res.raw as Record<string, unknown>).session ?? {}) as WizardSession;
          setCardId(sess.card_id);
          applySession(sess);
        } catch (e) {
          setError('建卡失败：' + (e instanceof Error ? e.message : String(e)));
          return;
        } finally { setBusy(false); }
      }
      okSave = await fill('basics', { name: name.trim() });
    } else if (step === 1) {
      okSave = await fill('attrs', { method: 'point_buy', allocation: { ...attrs }, luck_enabled: false });
    } else if (step === 2) {
      okSave = await fill('derived', { age: null });
      if (okSave) okSave = await fill('occupation', { occupation, credit_rating: creditRating });
      if (okSave) okSave = await fill('skills', { occupation: occPool, interest: intPool });
    } else if (step === 3) {
      okSave = await fill('background', { background, background_details: bgDetails });
    } else if (step === 4) {
      okSave = true; // finalize 单独处理
    }
    if (!okSave) return;
    if (step === 4) {
      if (occUsed === 0) { setError('请先在第 3 步给职业技能投入至少 1 项点数（finalize 要求 occupation skills）。'); return; }
      void doFinalize();
      return;
    }
    setStep((v) => Math.min(4, v + 1));
  };

  const back = async (): Promise<void> => {
    setError(''); setDone(false); setFinalized(false);
    if (step === 0) return;
    const toSteps = ['basics', 'attrs', 'skills', 'background', 'review'];
    const toStep = toSteps[Math.max(0, step - 1)] ?? 'basics';
    const cid = cardIdRef.current;
    if (mobileToken && cid) {
      setBusy(true);
      try {
        const res = await api('POST', '/api/wizard/' + cid + '/back', mobileToken, { campaign_id: campaign, to_step: toStep });
        if (res.ok) setStep((v) => Math.max(0, v - 1));
        else {
          const rawMap = res.raw ?? {};
          setError('回退失败：' + String(rawMap.detail ?? rawMap.error ?? ('HTTP ' + res.status)));
        }
      } catch (e) {
        setError('回退失败：' + (e instanceof Error ? e.message : String(e)));
      } finally { setBusy(false); }
    } else {
      setStep((v) => Math.max(0, v - 1));
    }
  };

  const doFinalize = async (): Promise<void> => {
    if (!kpToken) { setError('确认入桌需要主持人 token（webapp 端）。请填写后重试。'); return; }
    if (!cardId) { setError('尚未建卡（无 card_id），请从第 1 步开始。'); return; }
    setBusy(true); setError('');
    try {
      const res = await api('POST', '/api/wizard/' + cardId + '/finalize', kpToken, { campaign_id: campaign });
      if (!res.ok) {
        const rawMap = res.raw ?? {};
        setError('入桌失败：' + String(rawMap.detail ?? rawMap.error ?? ('HTTP ' + res.status)));
        return;
      }
      setDone(true); setFinalized(true);
    } catch (e) {
      setError('入桌失败：' + (e instanceof Error ? e.message : String(e)));
    } finally { setBusy(false); }
  };

  const setAttr = (a: AttrName, delta: number): void => setAttrs((prev) => ({ ...prev, [a]: Math.min(100, Math.max(1, prev[a] + delta)) }));
  const setPool = (pool: 'occ' | 'int', id: string, v: number): void => {
    const setter = pool === 'occ' ? setOccPool : setIntPool;
    setter((prev) => {
      const next = { ...prev };
      if (v <= 0) delete next[id];
      else next[id] = v;
      return next;
    });
  };
  const setBg = (key: string, v: string): void => setBgDetails((prev) => ({ ...prev, [key]: v }));

  const occUsed = Object.values(occPool).reduce((s, v) => s + v, 0);
  const intUsed = Object.values(intPool).reduce((s, v) => s + v, 0);
  const occCap = occPoints ?? (attrs.EDU > 75 ? attrs.EDU * 2 + 2 : attrs.EDU * 4);
  const intCap = intPoints ?? attrs.INT * 2;
  const der = Object.keys(derived).length ? derived : computeDerived(attrs);
  const attrSum = ATTRS.reduce((s, a) => s + attrs[a], 0);
  // T16 实测补充：完整清单（72 项全量）在职业/兴趣两栏都可投入。
  // 不再写死 42/30 切片，清单数量变化时自然跟随（rulepack 合并后仍 72）。
  const occSkills = skillCatalog;
  const interestSkills = skillCatalog;

  const skillRow = (pool: 'occ' | 'int', skill: { id: string; zh: string; base: number; attr: string; cat: string }): React.ReactElement => {
    const val = (pool === 'occ' ? occPool : intPool)[skill.id] ?? 0;
    return (
      <li key={skill.id} className="flex items-center gap-2 text-sm">
        <span className="w-32 shrink-0 truncate" title={skill.id}>{skill.zh}<span className="ml-1 text-[10px] text-gray-400">{skill.id}</span></span>
        <input type="range" min={0} max={100} value={val} onChange={(e) => setPool(pool, skill.id, Number(e.target.value))} className="flex-1 accent-gray-900" aria-label={skill.zh + (pool === 'occ' ? '职业' : '兴趣') + '点数'} />
        <span className="w-10 text-right font-mono">{val}</span>
        <span className="w-14 text-right text-[11px] text-gray-500">{skill.base + val}</span>
      </li>
    );
  };

  return (
    <div className="space-y-4">
      {/* token 设置区 */}
      <section className="panel" aria-label="接入 token">
        <h2 className="panel-title">接入 token</h2>
        <p className="mb-2 text-xs text-gray-500">start/fill/back 需玩家端（mobile）token；确认入桌需主持人端（webapp）token。填好后点「保存」，写入 localStorage 持久化。</p>
        <div className="flex flex-wrap items-end gap-2">
          <label className="min-w-[200px] flex-1 text-xs text-gray-500">
            玩家 token（mobile）
            <input className="input mt-1 font-mono" value={mobileToken} onChange={(e) => setMobileToken(e.target.value)} placeholder="mobile 端 token" aria-label="玩家 token（mobile）" />
          </label>
          <label className="min-w-[200px] flex-1 text-xs text-gray-500">
            主持人 token（webapp）
            <input className="input mt-1 font-mono" value={kpToken} onChange={(e) => setKpToken(e.target.value)} placeholder="webapp 端 token" aria-label="主持人 token（webapp）" />
          </label>
          <button className="btn btn-secondary" onClick={() => { try { localStorage.setItem('trpg_mobile_token', mobileToken.trim()); localStorage.setItem('trpg_token', kpToken.trim()); setError(''); } catch { setError('localStorage 不可用'); } }}>保存 token</button>
        </div>
        <p className="mt-1 text-[11px] text-gray-500">会话：{campaign} · 玩家：{playerId} · card_id：{cardId || '（未建卡）'} · token 仅用于请求头，不回显。</p>
      </section>

      <section className="panel" aria-label="车卡步骤">
        <p className="mb-2 text-[11px] text-gray-500">车卡步骤（共 5 步，当前步骤高亮）</p>
        <ol className="flex flex-wrap gap-2" aria-label="车卡进度">
          {STEPS.map((label, i) => (
            <li key={label} className={'chip ' + (i === step ? 'border-black bg-black text-white' : i < step ? 'border-gray-400 text-gray-800' : 'text-gray-500')} aria-current={i === step ? 'step' : undefined}>
              {i + 1}. {label}{i < step ? ' ✓' : ''}
            </li>
          ))}
        </ol>
        {error ? <div className="mt-3" role="alert" aria-live="assertive" aria-atomic="true"><ErrorBanner message={error + '（第 ' + (step + 1) + ' 步 · ' + STEPS[step] + '）'} onClose={() => setError('')} /></div> : null}
        {!cardId ? <p className="mt-2 text-xs text-gray-600" role="status">尚未建卡：填好姓名后点「下一步」自动 start 并逐步入后端保存。</p> : null}
      </section>

      {done ? (
        <section className="panel" aria-label="建卡完成">
          <h2 className="panel-title">{finalized ? '确认入桌成功 ✓' : '建卡完成（待确认入桌）'}</h2>
          <p className="text-sm">调查员 <b>{name}</b> · {occupation} · card_id <code className="rounded bg-gray-200 px-1">{cardId}</code></p>
          {finalized ? (
            <p className="mt-2 rounded-md border border-gray-300 bg-gray-50 px-3 py-2 text-sm text-gray-800" role="status">
              已触发 CHARACTER_CREATED 事件并正式落桌。玩家可在地图/总览看到新角色；主持人端复盘时间线将出现「建卡」条目。
            </p>
          ) : (
            <p className="mt-2 text-xs text-gray-600">点「确认入桌」将由主持人（webapp token）执行 finalize 硬校验并落桌。</p>
          )}
          <div className="mt-3 flex gap-2">
            <button className="btn btn-secondary" onClick={() => void back()} disabled={busy}>回退修改</button>
            {!finalized ? <button className="btn btn-primary" onClick={() => void doFinalize()} disabled={busy} aria-busy={busy}>{busy ? '入桌中…' : '确认入桌'}</button> : null}
          </div>
        </section>
      ) : null}
      {step === 0 ? (
        <section className="panel" aria-label="概念">
          <h2 className="panel-title">第 1 步 · 概念</h2>
          <label className="mb-1 block text-xs text-gray-500" htmlFor="cw-name">调查员姓名 <span className="text-gray-500">· 必填，提交即 start 建卡</span></label>
          <input id="cw-name" className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="如：林墨" autoFocus />
          <label className="mb-1 mt-2 block text-xs text-gray-500" htmlFor="cw-player">玩家标识</label>
          <input id="cw-player" className="input" value={playerId} onChange={(e) => setPlayerId(e.target.value)} placeholder="如：kp1 / pl-linmo" />
          <p className="mt-2 text-[11px] text-gray-500">点击「下一步」将调用 POST /api/wizard/start 建卡（生成 card_id），此后每步 fill 真实保存到后端。</p>
        </section>
      ) : null}

      {step === 1 ? (
        <section className="panel" aria-label="属性分配">
          <h2 className="panel-title">第 2 步 · 属性（点击 ± 微调，和 {attrSum}，point_buy 上限 460）</h2>
          <ul className="grid grid-cols-2 gap-2 md:grid-cols-4">
            {ATTRS.map((a) => (
              <li key={a} className="rounded bg-gray-100 p-2 text-center">
                <div className="text-xs text-gray-500">{a}</div>
                <div className="text-lg font-bold">{attrs[a]}</div>
                <div className="mt-1 flex justify-center gap-1">
                  <button className="btn btn-secondary px-2 py-1" onClick={() => setAttr(a, -5)} aria-label={a + ' 减 5'}>−5</button>
                  <button className="btn btn-secondary px-2 py-1" onClick={() => setAttr(a, 5)} aria-label={a + ' 加 5'}>＋5</button>
                </div>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[11px] text-gray-500">职业点数：EDU×4（EDU&gt;75 时 EDU×2+2）；兴趣点数：INT×2。下一步选职业与技能时提示剩余点数。</p>
        </section>
      ) : null}

      {step === 2 ? (
        <section className="panel" aria-label="职业与技能">
          <h2 className="panel-title">第 3 步 · 职业与技能（技能 {skillCatalog.length} 项（7e 官方清单）· 来源：{skillSource === 'rulepack' ? '后端 rulepack + 7e 增量合并' : '内嵌 7e 清单'}）</h2>
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-xs text-gray-500">
              职业
              <select className="input mt-1" value={occupation} onChange={(e) => setOccupation(e.target.value)} aria-label="职业">
                {OCCUPATIONS.map((o) => (<option key={o.id} value={o.id}>{o.zh}（{o.id}）</option>))}
              </select>
            </label>
            <label className="text-xs text-gray-500">
              信用评级
              <input className="input mt-1 w-24" type="number" min={0} max={100} value={creditRating} onChange={(e) => setCreditRating(Number(e.target.value))} aria-label="信用评级" />
            </label>
          </div>
          <div className="mt-2 rounded bg-gray-50 px-3 py-2 text-xs text-gray-600">
            {occUsed === 0 && intUsed === 0 ? <p className="mb-1 text-amber-700">提示：职业/兴趣技能至少各投入 1 项点数，否则 finalize 会被后端拦截。</p> : null}
            职业点数 <b>{occUsed}</b>/{occCap}（EDU={attrs.EDU} → {attrs.EDU > 75 ? 'EDU×2+2' : 'EDU×4'}）· 兴趣点数 <b>{intUsed}</b>/{intCap}（INT={attrs.INT} → INT×2）
          </div>
          <div className="mt-3 grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <h3 className="mb-1 text-xs font-semibold text-gray-700">职业技能投入（基础值 + 职业点数，共 {occSkills.length} 项可分配）</h3>
              <ul className="space-y-1.5">
                {occSkills.map((s) => skillRow('occ', s))}
              </ul>
            </div>
            <div>
              <h3 className="mb-1 text-xs font-semibold text-gray-700">兴趣技能投入（基础值 + 兴趣点数，共 {interestSkills.length} 项可分配）</h3>
              <ul className="space-y-1.5">
                {interestSkills.map((s) => skillRow('int', s))}
              </ul>
            </div>
          </div>
          <p className="mt-2 text-[11px] text-gray-500">技能基础值与属性/分类以 rulepack 为准（后端单一事实源）；7e 增量项在 rulepack 未覆盖时使用内嵌默认值。最终以 finalize 硬校验为准。</p>
        </section>
      ) : null}

      {step === 3 ? (
        <section className="panel" aria-label="背景">
          <h2 className="panel-title">第 4 步 · 背景（COC7 8 字段）</h2>
          <label className="mb-1 block text-xs text-gray-500" htmlFor="cw-bg">人物小传（可选，background 字段）</label>
          <textarea id="cw-bg" className="input min-h-[56px]" value={background} onChange={(e) => setBackground(e.target.value)} placeholder="一句话人物小传…" aria-label="人物背景" />
          <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
            {BG_FIELDS.map((f) => (
              <label key={f.key} className="block text-xs text-gray-500">
                {f.zh}
                <textarea className="input mt-1 min-h-[52px]" value={bgDetails[f.key] ?? ''} onChange={(e) => setBg(f.key, e.target.value)} placeholder={f.zh + '…'} aria-label={f.zh} />
              </label>
            ))}
          </div>
        </section>
      ) : null}

      {step === 4 ? (
        <section className="panel" aria-label="确认">
          <h2 className="panel-title">第 5 步 · 确认（finalize 硬校验预览）</h2>
          <ul className="space-y-1 text-sm text-gray-600">
            <li>姓名：{name || '（未填 — 提交将被拦截并提示）'}</li>
            <li>职业：{occupation} · 信用评级 {creditRating}</li>
            <li>属性：{ATTRS.map((a) => a + attrs[a]).join(' / ')}（和 {attrSum}）</li>
            <li>技能：职业 {occUsed}/{occCap} · 兴趣 {intUsed}/{intCap}</li>
          </ul>
          <div className="mt-2 rounded bg-gray-100 p-3 text-sm">
            <p className="mb-1 text-xs font-semibold text-gray-700">派生值（{Object.keys(derived).length ? '后端 derived（rulepack formulas）' : '前端 7e 兜底公式'}）</p>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-700">
              <span>HP={der.hp_max}</span><span>MP={der.mp_max}</span><span>SAN={der.san_start}</span>
              <span>幸运={der.luck}</span><span>闪避={der.dodge}</span><span>灵感={der.idea}</span><span>知识={der.knowledge}</span>
            </div>
          </div>
          <p className="mt-2 text-[11px] text-gray-500">点「确认入桌」将用主持人 token 调 POST /api/wizard/{cardId}/finalize —— 后端硬校验通过后发 CHARACTER_CREATED 事件并正式落桌。</p>
        </section>
      ) : null}

      {!done ? (
        <div className="flex gap-2">
          <button className="btn btn-secondary" onClick={() => void back()} disabled={busy || step === 0} title={step === 0 ? '已是第一步' : '回到上一步（后端回退）'}>上一步（回退）</button>
          <button className="btn btn-primary" onClick={() => void next()} disabled={busy} aria-busy={busy}>
            {busy ? '保存中…' : step === 4 ? '确认入桌' : '下一步：' + STEPS[Math.min(4, step + 1)]}
          </button>
        </div>
      ) : null}
    </div>
  );
}