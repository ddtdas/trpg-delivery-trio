// realTransport —— 真实 WS 传输层（与 MockTransport 同接口）。
//
// 协议唯一权威：docs/contracts/runtime-contract.md v1.0（冻结）。
// 字段严格按契约命名：S→C 8 类（STATE_DELTA/TURN_UPDATED/NARRATION_PENDING/
// NARRATION_APPROVED/WHISPER/INFO_REVEALED/BRANCH_TAKEN/JOB_STATUS，全带
// seq,campaign_id,scope,ts）＋心跳 PING{ts}；C→S 6 类（SUBMIT_ACTION/START_TURN/
// CLOSE_WINDOW/APPROVE_NARRATION/COMMAND/AUDIO_CHUNK，全带 campaign,actor{id,token?},req_id）。
// 铁律：不改 t19 组件与冻结契约；本文件只做传输，不碰组件接线（t22）。
import type { ClientFrame, ServerFrame, WsClientOptions, WsStatus } from './ws';

export type { WsStatus };
export type TransportListener = (frame: ServerFrame) => void;

/** 与 mockTransport.ts 同形的发送体：campaign/actor/req_id 由传输层自动补齐。 */
type DistributiveOmit<T, K extends keyof never> = T extends unknown
  ? Omit<T, K & keyof T>
  : never;
export type SendableClientFrame = DistributiveOmit<ClientFrame, 'campaign' | 'actor' | 'req_id'>;
export type EmittableServerFrame = DistributiveOmit<ServerFrame, 'seq' | 'ts' | 'campaign_id'>;

/** S→C 8 类 kind 表（PING 为心跳，8 类之外）。 */
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
export type ServerKind = (typeof SERVER_KINDS)[number];

/** C→S 6 类 kind 表。 */
export const CLIENT_KINDS = [
  'SUBMIT_ACTION',
  'START_TURN',
  'CLOSE_WINDOW',
  'APPROVE_NARRATION',
  'COMMAND',
  'AUDIO_CHUNK',
] as const;

/** scope 硬约束（契约 §1：NARRATION_PENDING=kp 等 6 类，其余按服务端下发原样透传）。 */
const REQUIRED_SCOPE: Record<string, string> = {
  NARRATION_PENDING: 'kp',
  NARRATION_APPROVED: 'public',
  WHISPER: 'whisper',
  INFO_REVEALED: 'condition',
  BRANCH_TAKEN: 'public',
  JOB_STATUS: 'actor',
};

/** S→C 各 kind 必填字段（契约 §1 全字段）。 */
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

/** C→S 各 kind 必填字段（契约 §2 全字段）。 */
const CLIENT_NEEDS: Record<string, string[]> = {
  SUBMIT_ACTION: ['action'],
  START_TURN: ['window_sec'],
  CLOSE_WINDOW: [],
  APPROVE_NARRATION: ['proposal_id', 'decision'],
  COMMAND: ['cmd'],
  AUDIO_CHUNK: ['player_id', 'mime', 'chunk_base64', 'seq'],
};

export class TransportError extends Error {}

/** S→C 解码＋严格校验（未知 kind / 缺字段 / scope 违例即抛）。 */
export function decodeServerFrame(raw: unknown): ServerFrame {
  if (typeof raw !== 'object' || raw === null) throw new TransportError('server frame must be object');
  const r = raw as Record<string, unknown>;
  if (r.kind === 'PING') {
    if (typeof r.ts !== 'number') throw new TransportError('PING requires ts');
    return r as unknown as ServerFrame;
  }
  if (typeof r.kind !== 'string' || !(SERVER_KINDS as readonly string[]).includes(r.kind)) {
    throw new TransportError(`unknown server kind: ${String(r.kind)}`);
  }
  for (const f of ['seq', 'campaign_id', 'scope', 'ts']) {
    if (r[f] === undefined) throw new TransportError(`${String(r.kind)} requires ${f}`);
  }
  const need = REQUIRED_SCOPE[r.kind as string];
  if (need !== undefined && r.scope !== need) {
    throw new TransportError(`${String(r.kind)} scope must be ${need}`);
  }
  for (const f of SERVER_NEEDS[r.kind as string] ?? []) {
    if (r[f] === undefined || r[f] === null) throw new TransportError(`${String(r.kind)} requires ${f}`);
  }
  return r as unknown as ServerFrame;
}

/** C→S 编码：补 envelope（campaign/actor/req_id）＋必填校验，返回 wire JSON。 */
export function encodeClientFrame(
  body: SendableClientFrame,
  envelope: { campaign: string; actor: { id: string; token?: string }; req_id: string },
): string {
  const kind = (body as { kind?: unknown }).kind;
  if (typeof kind !== 'string' || !(CLIENT_KINDS as readonly string[]).includes(kind)) {
    throw new TransportError(`unknown client kind: ${String(kind)}`);
  }
  const merged: Record<string, unknown> = { ...(body as Record<string, unknown>), ...(envelope as unknown as Record<string, unknown>) };
  for (const f of ['campaign', 'actor', 'req_id']) {
    if (merged[f] === undefined) throw new TransportError(`${kind} requires ${f}`);
  }
  for (const f of CLIENT_NEEDS[kind] ?? []) {
    if (merged[f] === undefined || merged[f] === null) throw new TransportError(`${kind} requires ${f}`);
  }
  if (kind === 'APPROVE_NARRATION' && merged.decision === 'edit' && !merged.edited_text) {
    throw new TransportError('APPROVE_NARRATION decision=edit requires edited_text');
  }
  return JSON.stringify(merged);
}

/** 默认 URL：VITE_TRPG_WS_URL 优先，否则**同源** ws(s)://<host>:<port>。
 *  R2/t11：原来硬编码 :9210，而服务端实际监听 9211 —— 同源部署下必然连错端口。
 *  改用 location.host（含端口）并按协议选 ws/wss，使同一份产物适配任意部署主机/端口。 */
export function defaultWsBase(): string {
  const env = (import.meta as unknown as { env?: Record<string, string | undefined> }).env ?? {};
  const fromEnv = env.VITE_TRPG_WS_URL;
  if (fromEnv && fromEnv.length > 0) return fromEnv.replace(/\/$/, '');
  if (typeof window !== 'undefined' && window.location?.host) {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${window.location.host}`;
  }
  return 'ws://127.0.0.1:9211';
}

export interface RealTransportOptions extends WsClientOptions {
  campaign?: string;
  token?: string;
  baseUrl?: string;
  /** 可注入 WebSocket 构造（单测 mock 注入；默认全局 WebSocket）。 */
  socketFactory?: (url: string) => WebSocket;
  /** 可注入时钟/随机（单测确定性退避；默认 Math.random + setTimeout）。 */
  now?: () => number;
  jitter?: () => number;
}

const BACKOFF = [1000, 2000, 4000, 8000];
const MAX_DELAY = 30_000;
const HEARTBEAT_WATCHDOG_MS = 30_000; // 30s 无帧主动重连（server 每 15s PING）

let reqCounter = 0;
export function nextReqId(): string {
  reqCounter += 1;
  return `req-${Date.now().toString(36)}-${reqCounter}`;
}

/** RealTransport —— 与 MockTransport 同接口的真实传输。 */
export class RealTransport {
  private opts: RealTransportOptions;
  private extraListeners = new Set<TransportListener>();
  private ws: WebSocket | null = null;
  private status: WsStatus = 'idle';
  private lastSeq = -1;
  private retryIdx = 0;
  private watchdog: ReturnType<typeof setTimeout> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private closedByUser = false;
  private sessionSeq = 0;
  private readonly sessionId = `sess-${Math.random().toString(36).slice(2, 8)}`;

  constructor(options: RealTransportOptions) {
    this.opts = options;
  }

  connect(): void {
    this.closedByUser = false;
    this.openSocket();
  }

  close(): void {
    this.closedByUser = true;
    this.clearTimers();
    try {
      this.ws?.close();
    } catch {
      /* ignore */
    }
    this.ws = null;
    this.setStatus('closed');
  }

  /** 发送：自动补 campaign/actor/req_id（含鉴权 token）。 */
  send(body: SendableClientFrame): void {
    const wire = encodeClientFrame(body, {
      campaign: this.opts.campaign ?? this.opts.table,
      actor: { id: this.opts.viewer, token: this.opts.token },
      req_id: nextReqId(),
    });
    if (this.ws && this.ws.readyState === 1) this.ws.send(wire);
  }

  getStatus(): WsStatus {
    return this.status;
  }

  getLastSeq(): number {
    return this.lastSeq;
  }

  /** subscribe：与 MockTransport 同形（t22 接线可互换）。 */
  subscribe(listener: TransportListener): () => void {
    this.extraListeners.add(listener);
    return () => {
      this.extraListeners.delete(listener);
    };
  }

  /** snapshot：与 MockTransport 同形（真实传输返回连接级快照）。 */
  snapshot(): { session: string; status: WsStatus; lastSeq: number } {
    return { session: this.sessionId, status: this.status, lastSeq: this.lastSeq };
  }

  /** 供单测：当前重连延迟（含抖动前基础值）。 */
  backoffBase(attempt: number): number {
    return Math.min(BACKOFF[Math.min(attempt, BACKOFF.length - 1)], MAX_DELAY);
  }

  /** 供单测：调度级延迟（含抖动后上限 30s）。 */
  scheduledDelay(attempt: number, jitterMs: number): number {
    return Math.min(this.backoffBase(attempt) + jitterMs, MAX_DELAY);
  }

  private url(): string {
    const base = (this.opts.baseUrl ?? defaultWsBase()).replace(/\/$/, '');
    const q = new URLSearchParams({
      table: this.opts.table,
      viewer: this.opts.viewer,
      role: this.opts.role,
      last_seq: String(this.lastSeq),
    });
    // EX-2 D3: /ws 握手校验 token —— 配置了 VITE_TRPG_TOKEN 时随行携带 (任一启用端)。
    if (this.opts.token) q.set('token', this.opts.token);
    return `${base}/ws?${q.toString()}`;
  }

  private factory(): (url: string) => WebSocket {
    if (this.opts.socketFactory) return this.opts.socketFactory;
    const G = globalThis as unknown as { WebSocket?: new (url: string) => WebSocket };
    if (!G.WebSocket) throw new TransportError('no WebSocket implementation');
    const Ctor = G.WebSocket;
    return (url: string) => new Ctor(url);
  }

  private openSocket(): void {
    this.setStatus(this.retryIdx === 0 ? 'connecting' : 'reconnecting');
    const ws = this.factory()(this.url());
    this.ws = ws;
    ws.onopen = () => {
      this.retryIdx = 0;
      this.setStatus('open');
      this.armWatchdog();
    };
    ws.onmessage = (ev: { data: unknown }) => {
      this.armWatchdog();
      let raw: unknown;
      try {
        raw = JSON.parse(String(ev.data));
      } catch {
        return;
      }
      if (typeof raw === 'object' && raw !== null) {
        const kind = (raw as Record<string, unknown>).kind;
        if (kind === 'PONG') return; // 心跳回包：只保活
        if (kind === 'ERROR' || kind === 'ACK') return; // 上行回执：保活，不进业务分发
      }
      let frame: ServerFrame;
      try {
        frame = decodeServerFrame(raw);
      } catch {
        return; // 坏帧丢弃（不断链）
      }
      if (frame.kind === 'PING') return; // 心跳：只保活
      if (typeof frame.seq === 'number' && frame.seq > this.lastSeq) this.lastSeq = frame.seq;
      this.sessionSeq = Math.max(this.sessionSeq, this.lastSeq);
      this.opts.onFrame?.(frame);
      this.extraListeners.forEach((l) => l(frame));
    };
    ws.onclose = () => {
      this.clearTimers();
      if (this.closedByUser) return;
      this.scheduleReconnect();
    };
    ws.onerror = () => {
      /* 出错走 onclose 重连链 */
    };
  }

  private armWatchdog(): void {
    this.clearWatchdog();
    this.watchdog = setTimeout(() => {
      try {
        this.ws?.close();
      } catch {
        /* ignore */
      }
      if (!this.closedByUser) this.scheduleReconnect();
    }, HEARTBEAT_WATCHDOG_MS);
  }

  private scheduleReconnect(): void {
    const base = this.backoffBase(this.retryIdx);
    const jitter = (this.opts.jitter ?? Math.random)() * 250;
    this.retryIdx += 1;
    this.setStatus('reconnecting');
    this.reconnectTimer = setTimeout(() => {
      if (!this.closedByUser) this.openSocket();
    }, Math.min(base + jitter, MAX_DELAY));
  }

  private clearWatchdog(): void {
    if (this.watchdog !== null) {
      clearTimeout(this.watchdog);
      this.watchdog = null;
    }
  }

  private clearTimers(): void {
    this.clearWatchdog();
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private setStatus(s: WsStatus): void {
    this.status = s;
    this.opts.onStatus?.(s);
  }
}

export function createRealTransport(options: RealTransportOptions): RealTransport {
  return new RealTransport(options);
}

/** --demo 导出点：保证 realTransport 未被 t22 接线前亦可编译验证（验收要求）。 */
export const realTransportDemo = {
  kinds: { server: [...SERVER_KINDS, 'PING'], client: [...CLIENT_KINDS] },
  urlExample: 'ws://<host>:9210/ws?table=<id>&viewer=<id>&role=kp|pl|spectator',
};
