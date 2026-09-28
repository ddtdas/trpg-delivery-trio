import { create } from 'zustand';
import { transport } from '../lib/transport';

export interface ReviewEvent {
  seq: number;
  kind: string;
  actor: string;
  summary: string;
  detail: string;
  ts: number;
}

interface ReviewState {
  events: ReviewEvent[];
  set: (p: Partial<ReviewState>) => void;
  reset: () => void;
}

const seed: ReviewEvent[] = [
  { seq: 0, kind: 'CAMPAIGN_STARTED', actor: 'kp', summary: '开团《雾港来信》', detail: 'CoC7 · 种子 20260919', ts: Date.now() - 3600_000 },
  { seq: 1, kind: 'CHARACTER_CREATED', actor: 'pl-linmo', summary: '林墨建卡', detail: '侦探 · 侦查 45', ts: Date.now() - 3500_000 },
  { seq: 2, kind: 'TURN_STARTED', actor: 'kp', summary: '第 1 回合开窗', detail: 'window 120s', ts: Date.now() - 3400_000 },
  { seq: 3, kind: 'ACTION_SUBMITTED', actor: 'pl-linmo', summary: '搜证：书桌', detail: '我检查书桌上的信件，看看有没有暗格。', ts: Date.now() - 3300_000 },
  { seq: 4, kind: 'CHECK_RESOLVED', actor: 'system', summary: '侦查 60（失败）', detail: 'target 侦查 · roll 60 · seed 7 · level fail', ts: Date.now() - 3200_000 },
  { seq: 5, kind: 'NARRATION_PROPOSED', actor: 'agent', summary: '旁白提案 prop-1', detail: '门后的雾气像活物般缓缓退去……', ts: Date.now() - 3100_000 },
  { seq: 6, kind: 'NARRATION_APPROVED', actor: 'kp', summary: '批准 prop-1', detail: 'approved_by kp', ts: Date.now() - 3000_000 },
  { seq: 7, kind: 'BRANCH_TAKEN', actor: 'system', summary: '银钥匙线索', detail: 'node library → 发现地下室入口', ts: Date.now() - 2900_000 },
  { seq: 8, kind: 'NARRATION_REJECTED', actor: 'kp', summary: '否决 prop-2', detail: 'reason：节奏太快，打回重写', ts: Date.now() - 2800_000 },
];

export const useReviewStore = create<ReviewState>()((set) => ({
  events: seed,
  set: (p) => set(p),
  reset: () => set({ events: seed }),
}));

/** transport 下行 → 复盘流追加（调用一次，常驻；mock 演示可看到新事件进来）。 */
let subscribed = false;
export function ensureReviewSubscription(): void {
  if (subscribed) return;
  subscribed = true;
  transport.subscribe((frame) => {
    const s = useReviewStore.getState();
    const push = (kind: string, actor: string, summary: string, detail: string): void => {
      const seq = s.events.length ? s.events[s.events.length - 1].seq + 1 : 0;
      s.set({ events: [...s.events, { seq, kind, actor, summary, detail, ts: Date.now() }].slice(-60) });
    };
    if (frame.kind === 'NARRATION_APPROVED') push('NARRATION_APPROVED', 'kp', `批准 ${frame.narration.id}`, frame.narration.text);
    else if (frame.kind === 'BRANCH_TAKEN') push('BRANCH_TAKEN', 'system', frame.branch.label, `node ${frame.branch.node_id}`);
    else if (frame.kind === 'TURN_UPDATED') push('TURN_UPDATED', 'system', `回合 ${frame.turn.state}`, `已提交 ${frame.turn.submitted.length}/${frame.turn.total}`);
    else if (frame.kind === 'STATE_DELTA' && frame.delta.field === 'map_op') {
      const v = frame.delta.value as { op: string; target: string; verdict: string };
      push('MAP_UPDATED', 'kp', `${v.op} ${v.target}`, `verdict ${v.verdict}`);
    }
  });
}
