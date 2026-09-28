// realTransport.testable —— 纯逻辑导出（无 DOM/WebSocket 依赖，供 node 单测 bundle）。
// 重连退避与状态演示均在此，realTransport.ts 的类方法复用同一常量。
export const SERVER_KINDS = [
  'STATE_DELTA',
  'TURN_UPDATED',
  'NARRATION_PENDING',
  'NARRATION_APPROVED',
  'WHISPER',
  'INFO_REVEALED',
  'BRANCH_TAKEN',
  'JOB_STATUS',
] as const;

export const CLIENT_KINDS = [
  'SUBMIT_ACTION',
  'START_TURN',
  'CLOSE_WINDOW',
  'APPROVE_NARRATION',
  'COMMAND',
  'AUDIO_CHUNK',
] as const;

const BACKOFF = [1000, 2000, 4000, 8000];
const MAX_DELAY = 30_000;

export function backoffBaseForTest(attempt: number): number {
  return Math.min(BACKOFF[Math.min(attempt, BACKOFF.length - 1)], MAX_DELAY);
}

/** 调度级延迟（含抖动后上限 30s，与 RealTransport.scheduleReconnect 同式）。 */
export function scheduledDelayForTest(attempt: number, jitterMs: number): number {
  return Math.min(backoffBaseForTest(attempt) + jitterMs, MAX_DELAY);
}

/** 状态机演示序列（单测断言用）：连接→打开→断线重连→恢复。 */
export function demoReconnectSequence(): string[] {
  return ['connecting', 'open', 'reconnecting', 'open'];
}

const REQUIRED_SCOPE: Record<string, string> = {
  NARRATION_PENDING: 'kp',
  NARRATION_APPROVED: 'public',
  WHISPER: 'whisper',
  INFO_REVEALED: 'condition',
  BRANCH_TAKEN: 'public',
  JOB_STATUS: 'actor',
};

const SERVER_NEEDS: Record<string, string[]> = {
  STATE_DELTA: ['delta'],
  TURN_UPDATED: ['turn'],
  NARRATION_PENDING: ['proposal'],
  NARRATION_APPROVED: ['narration'],
  WHISPER: ['targets', 'packet'],
  INFO_REVEALED: ['packet'],
  BRANCH_TAKEN: ['branch'],
  JOB_STATUS: ['actor_id', 'job'],
};

const CLIENT_NEEDS: Record<string, string[]> = {
  SUBMIT_ACTION: ['action'],
  START_TURN: ['window_sec'],
  CLOSE_WINDOW: [],
  APPROVE_NARRATION: ['proposal_id', 'decision'],
  COMMAND: ['cmd'],
  AUDIO_CHUNK: ['player_id', 'mime', 'chunk_base64', 'seq'],
};

export function decodeServerFrame(raw: unknown): Record<string, unknown> {
  if (typeof raw !== 'object' || raw === null) throw new Error('server frame must be object');
  const r = raw as Record<string, unknown>;
  if (r.kind === 'PING') {
    if (typeof r.ts !== 'number') throw new Error('PING requires ts');
    return r;
  }
  if (typeof r.kind !== 'string' || !(SERVER_KINDS as readonly string[]).includes(r.kind)) {
    throw new Error(`unknown server kind: ${String(r.kind)}`);
  }
  for (const f of ['seq', 'campaign_id', 'scope', 'ts']) {
    if (r[f] === undefined) throw new Error(`${String(r.kind)} requires ${f}`);
  }
  const need = REQUIRED_SCOPE[r.kind as string];
  if (need !== undefined && r.scope !== need) throw new Error(`${String(r.kind)} scope must be ${need}`);
  for (const f of SERVER_NEEDS[r.kind as string] ?? []) {
    if (r[f] === undefined || r[f] === null) throw new Error(`${String(r.kind)} requires ${f}`);
  }
  return r;
}

export function encodeClientFrame(
  body: Record<string, unknown>,
  envelope: { campaign: string; actor: { id: string; token?: string }; req_id: string },
): string {
  const kind = body.kind;
  if (typeof kind !== 'string' || !(CLIENT_KINDS as readonly string[]).includes(kind)) {
    throw new Error(`unknown client kind: ${String(kind)}`);
  }
  const merged: Record<string, unknown> = { ...body, ...(envelope as unknown as Record<string, unknown>) };
  for (const f of ['campaign', 'actor', 'req_id']) {
    if (merged[f] === undefined) throw new Error(`${kind} requires ${f}`);
  }
  for (const f of CLIENT_NEEDS[kind] ?? []) {
    if (merged[f] === undefined || merged[f] === null) throw new Error(`${kind} requires ${f}`);
  }
  if (kind === 'APPROVE_NARRATION' && merged.decision === 'edit' && !merged.edited_text) {
    throw new Error('APPROVE_NARRATION decision=edit requires edited_text');
  }
  return JSON.stringify(merged);
}
