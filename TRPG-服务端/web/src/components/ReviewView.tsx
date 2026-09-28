import React from 'react';
import { restConnParams, transport } from '../lib/transport';
import { ensureReviewSubscription, useReviewStore } from '../store/review';
import { EmptyState, ErrorBanner, SkeletonRows } from './ui';
// UI-R2: 灰白黑令牌适配（仅视觉）

const KIND_FILTERS = ['全部', '检定', '叙事', '行动', '地图', '分支'] as const;
const KIND_ZH: Record<string, string> = {
  CAMPAIGN_STARTED: '开团', CHARACTER_CREATED: '建卡', TURN_STARTED: '回合开始',
  ACTION_SUBMITTED: '行动提交', CHECK_RESOLVED: '检定结算', NARRATION_PROPOSED: '旁白提案',
  NARRATION_APPROVED: '旁白已批准', NARRATION_EDITED: '旁白已编辑', NARRATION_REJECTED: '旁白已否决',
  BRANCH_TAKEN: '剧情分支', MAP_UPDATED: '地图更新', TURN_UPDATED: '回合更新',
};
/** T16.4: 事件 payload 转可读文本（详情按钮内容）。 */
function formatPayload(payload: unknown, kind: string): string {
  if (payload === null || payload === undefined) return '';
  if (typeof payload === 'string') return payload;
  if (typeof payload !== 'object') return String(payload);
  const o = payload as Record<string, unknown>;
  const parts: string[] = [];
  const push = (label: string, v: unknown): void => {
    if (v === undefined || v === null || v === '') return;
    if (typeof v === 'object') {
      parts.push(label + '：' + JSON.stringify(v, null, 0).slice(0, 400));
    } else {
      parts.push(label + '：' + String(v));
    }
  };
  // 常见事件 payload 的友好字段（其余按原始 JSON 兜底）
  if (kind === 'CHARACTER_CREATED') {
    const card = o.card as Record<string, unknown> | undefined;
    push('调查员', card && (card.name ?? o.player_id));
    push('职业', card && card.occupation);
    push('card_id', o.card_id);
    if (card && typeof card.attrs === 'object') parts.push('属性：' + JSON.stringify(card.attrs));
    if (card && typeof card.skills === 'object' && Object.keys(card.skills as object).length) parts.push('技能：' + JSON.stringify(card.skills));
  } else if (kind === 'SCENE_UPDATED') {
    push('场景', o.scene_id);
    push('地图', o.map_id);
    push('原因', o.reason);
  } else if (kind === 'MAP_UPDATED') {
    push('地图', o.map_id);
    push('操作', o.op);
    push('目标', o.target);
    push('变更', o.delta);
  } else if (kind === 'NARRATION_PROPOSED' || kind === 'NARRATION_APPROVED' || kind === 'NARRATION_EDITED') {
    push('文本', o.text ?? o.narration_text);
  } else if (kind === 'CHECK_RESOLVED') {
    push('目标', o.target);
    push('掷骰', o.roll);
    push('结果', o.result ?? o.level);
  } else if (kind === 'CHECKPOINT_TAKEN') {
    push('存档点', o.checkpoint_id);
    push('标签', o.label);
    push('seq', o.seq);
  }
  const rest = Object.entries(o).filter(([k]) => !['card', 'campaign_id'].includes(k) && (kind === 'CHARACTER_CREATED' ? !['name', 'occupation', 'attrs', 'skills', 'player_id'].includes(k) : true));
  for (const [k, v] of rest) {
    if (v === undefined || v === null || v === '') continue;
    if (typeof v === 'object') parts.push(k + '：' + JSON.stringify(v).slice(0, 400));
    else parts.push(k + '：' + String(v));
  }
  const text = parts.join('；');
  return text || '（无更多字段）';
}

interface ApiEvent {
  seq: number;
  type: string;
  actor: string;
  ts: string;
  payload?: unknown;
}

/** 事件摘要（API 事件没有现成 summary，取 payload 的关键字段做一行摘要）。 */
function summarize(e: ApiEvent): string {
  const p = (e.payload ?? {}) as Record<string, unknown>;
  const card = p.card as Record<string, unknown> | undefined;
  if (e.type === 'CHARACTER_CREATED') return '建卡：' + String((card && card.name) || p.player_id || p.card_id || '');
  if (e.type === 'CARD_FINALIZED') return '卡定稿：' + String(p.card_id || '');
  if (e.type === 'SCENE_UPDATED') return '场景推进 → ' + String(p.scene_id || '');
  if (e.type === 'MAP_UPDATED') return '地图更新：' + String(p.op || '') + ' ' + String(p.target || '');
  if (e.type === 'TURN_STARTED') return '回合开始';
  if (e.type === 'TURN_CLOSED') return '回合关闭';
  if (e.type === 'ACTION_SUBMITTED') return '行动提交：' + String(p.intent || p.player_id || '');
  if (e.type === 'CHECK_RESOLVED') return '检定结算：' + String(p.target || '');
  if (e.type === 'CHECKPOINT_TAKEN') return '存档点：' + String(p.label || p.checkpoint_id || '');
  if (e.type === 'TIMELINE_ROLLBACK') return '回退到 seq ' + String(p.target_seq ?? '');
  if (e.type === 'NPC_TENDENCY_UPDATED') return 'NPC 倾向更新';
  return e.type;
}

function kindGroup(kind: string): string {
  if (kind.includes('CHECK')) return '检定';
  if (kind.includes('NARRATION')) return '叙事';
  if (kind.includes('ACTION') || kind.includes('TURN')) return '行动';
  if (kind.includes('MAP')) return '地图';
  if (kind.includes('BRANCH')) return '分支';
  return '其他';
}

/** ReviewView：复盘时间线（seq 序、筛选、详情、骰点/叙事对照、主持人标记）。 */
export function ReviewView(): React.ReactElement {
  const storeEvents = useReviewStore((s) => s.events);
  const [kindFilter, setKindFilter] = React.useState<(typeof KIND_FILTERS)[number]>('全部');
  const [actorFilter, setActorFilter] = React.useState('');
  const [openSeq, setOpenSeq] = React.useState<number | null>(null);

  const [reviewLoading, setReviewLoading] = React.useState(true);
  const [loadErr, setLoadErr] = React.useState(false);
  // T16.4: 真实事件流（GET /api/campaigns/{c}/events）—— 详情按钮的内容与时间线均以其为准。
  const [apiEvents, setApiEvents] = React.useState<ApiEvent[] | null>(null);
  const [payloadBySeq, setPayloadBySeq] = React.useState<Record<number, string>>({});

  React.useEffect(() => {
    ensureReviewSubscription();
    transport.connect();
    const { campaign, token } = restConnParams();
    let alive = true;
    if (campaign) {
      const pull = (): void => {
        fetch('/api/campaigns/' + encodeURIComponent(campaign) + '/events?limit=500' + (token ? ('&token=' + encodeURIComponent(token)) : ''), {
          headers: token ? { Authorization: 'Bearer ' + token } : {},
        })
          .then((r) => (r.ok ? r.json() : null))
          .then((raw) => {
            if (!alive) return;
            const evs = raw && Array.isArray(raw.events) ? (raw.events as ApiEvent[]) : null;
            if (evs && evs.length) {
              const m: Record<number, string> = {};
              for (const e of evs) m[e.seq] = formatPayload(e.payload, e.type);
              setApiEvents(evs.slice().sort((a, b) => b.seq - a.seq));
              setPayloadBySeq(m);
              setLoadErr(false);
            }
          })
          .catch(() => { /* 保留 store 现有 detail */ });
      };
      pull();
      const tPoll = window.setInterval(pull, 6000);
      const t = window.setTimeout(() => setReviewLoading(false), 500);
      const tErr = window.setTimeout(() => {
        if (useReviewStore.getState().events.length === 0 && !apiEvents) setLoadErr(true);
      }, 8000);
      return () => { alive = false; window.clearTimeout(t); window.clearTimeout(tErr); window.clearInterval(tPoll); };
    }
    const t = window.setTimeout(() => setReviewLoading(false), 500);
    return () => { window.clearTimeout(t); };
  }, []);

  /** 真实事件优先；无 campaign 参数时回落到 store（mock 演示）事件。 */
  const rows = React.useMemo(() => {
    if (apiEvents && apiEvents.length) {
      return apiEvents.map((e) => ({
        seq: e.seq,
        kind: e.type,
        actor: e.actor || '-',
        summary: summarize(e),
        detail: payloadBySeq[e.seq] || '',
        ts: e.ts,
      }));
    }
    return storeEvents;
  }, [apiEvents, storeEvents, payloadBySeq]);

  const events = rows;
  const actors = React.useMemo(() => [...new Set(rows.map((e) => e.actor))], [rows]);
  const shown = rows.filter((e) => (kindFilter === '全部' || kindGroup(e.kind) === kindFilter) && (!actorFilter || e.actor === actorFilter));

  const badge = (kind: string): string => {
    if (kind === 'NARRATION_REJECTED') return 'border-red-500 bg-red-50 text-red-700';
    if (kind === 'NARRATION_EDITED' || kind === 'NARRATION_APPROVED') return 'border-gray-400 text-gray-800';
    if (kind.includes('CHECK')) return 'border-gray-400 text-gray-600';
    return 'border-gray-400 text-gray-600';
  };

  return (
    <div className="space-y-4">
      {loadErr ? (
        <ErrorBanner message="复盘加载超时：8 秒内未收到事件流。请检查与主持端服务器的连接后重试。" onClose={() => window.location.reload()} />
      ) : null}
      <section className="panel" aria-label="复盘筛选">
        <h2 className="panel-title">复盘 · 事件时间线（{shown.length}/{events.length}）</h2>
        <p className="mb-2 text-xs text-gray-500">时间线只读：复盘数据来自事件流快照（保存 / 同步状态见后端事件审计）。</p>
        <div className="flex flex-wrap gap-2">
          {KIND_FILTERS.map((k) => (
            <button key={k} className={`chip ${kindFilter === k ? 'border-gray-400 bg-gray-100 text-gray-800' : 'text-gray-500'}`} onClick={() => setKindFilter(k)} aria-pressed={kindFilter === k}>{k}</button>
          ))}
          <select className="input max-w-[180px]" value={actorFilter} onChange={(e) => setActorFilter(e.target.value)} aria-label="按角色筛选">
            <option value="">全部角色</option>
            {actors.map((a) => (<option key={a} value={a}>{a}</option>))}
          </select>
          {(kindFilter !== '全部' || actorFilter) ? (
            <button className="chip border-gray-400 text-gray-700" onClick={() => { setKindFilter('全部'); setActorFilter(''); }} aria-label="清除筛选">清除筛选 ✕</button>
          ) : null}
        </div>
      </section>
      <ol className="space-y-2" aria-live="polite" aria-atomic="true">
        {reviewLoading ? <SkeletonRows rows={4} label="复盘时间线加载中" /> : null}
        <div className="min-h-[8px]" aria-live="polite" aria-atomic="true" />
        {!reviewLoading && shown.length === 0 ? <EmptyState text="没有命中筛选的事件 —— 点「清除筛选」回到全部，或等主持人推进回合产生新事件。" /> : null}
        {!reviewLoading ? shown.map((e) => (
          <li key={e.seq} className="rounded-lg border border-gray-200 bg-white p-3">
            <button className="flex w-full items-center gap-2 text-left" onClick={() => setOpenSeq((v) => (v === e.seq ? null : e.seq))} aria-expanded={openSeq === e.seq} aria-label={`事件 ${e.seq} 详情`}>
              <span className="font-mono text-xs text-gray-600">#{e.seq}</span>
              <span className={`chip ${badge(e.kind)}`} title={e.kind}>{KIND_ZH[e.kind] ?? e.kind}</span>
              <span className="text-sm text-gray-800">{e.summary}</span>
              <span className="ml-auto text-xs text-gray-700">{e.actor}</span>
            </button>
            {openSeq === e.seq ? (
              <div className="mt-2 rounded bg-gray-100 p-2 text-sm leading-6 text-gray-700">
                <p>{payloadBySeq[e.seq] || e.detail || '（该事件无 payload 详情）'}</p>
                {e.kind === 'CHECK_RESOLVED' ? <p className="mt-1 text-xs text-gray-600">对照：骰点结果 ↔ 叙事影响（主持人定夺后写入旁白）</p> : null}
                {e.kind === 'NARRATION_REJECTED' ? <p className="mt-1 text-xs text-red-700">主持人标记：已否决（打回重写，不入正史）</p> : null}
                {e.kind === 'NARRATION_APPROVED' ? <p className="mt-1 text-xs text-gray-800">主持人标记：已批准（入正史，可引用）</p> : null}
                {e.kind !== 'NARRATION_REJECTED' && e.kind !== 'NARRATION_APPROVED' && e.kind !== 'CHECK_RESOLVED' ? (
                  <p className="mt-1 text-[11px] text-gray-500">原始事件类型：{e.kind}</p>
                ) : null}
              </div>
            ) : null}
          </li>
        )) : null}
      </ol>
    </div>
  );
}