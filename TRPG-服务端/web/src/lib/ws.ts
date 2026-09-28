// WS 帧约定（预留类型定义，对齐 docs/contracts/runtime-contract.md v1.0 冻结件）。
// 传输：ws://127.0.0.1:9210/ws?table=<id>&viewer=<id>&role=kp|pl|spectator

/** S→C 8 类：全带 seq, campaign_id, scope, ts */
export type ServerScope = 'viewer' | 'kp' | 'public' | 'whisper' | 'condition' | 'actor';

export type TurnState =
  | 'COLLECTING'
  | 'CLOSING'
  | 'RESOLVING'
  | 'DISTRIBUTED'
  | 'ADVANCED';

export interface ServerFrameBase {
  kind:
    | 'STATE_DELTA'
    | 'TURN_UPDATED'
    | 'NARRATION_PENDING'
    | 'NARRATION_APPROVED'
    | 'WHISPER'
    | 'INFO_REVEALED'
    | 'BRANCH_TAKEN'
    | 'JOB_STATUS'
    | 'PING';
  seq: number;
  campaign_id: string;
  scope: ServerScope;
  ts: number;
}

export interface StateDeltaFrame extends ServerFrameBase {
  kind: 'STATE_DELTA';
  delta: { field: string; value: unknown };
}

export interface TurnUpdatedFrame extends ServerFrameBase {
  kind: 'TURN_UPDATED';
  turn: {
    state: TurnState;
    submitted: Array<{ player_id: string; intent?: string }>;
    total: number;
    countdown_end_ts: number;
  };
}

export interface NarrationPendingFrame extends ServerFrameBase {
  kind: 'NARRATION_PENDING';
  scope: 'kp';
  proposal: { id: string; text: string; intention?: string; source?: string };
}

export interface NarrationApprovedFrame extends ServerFrameBase {
  kind: 'NARRATION_APPROVED';
  narration: { id: string; text: string };
}

export interface WhisperFrame extends ServerFrameBase {
  kind: 'WHISPER';
  scope: 'whisper';
  targets: string[];
  packet: { info_id: string; body: string };
}

export interface InfoRevealedFrame extends ServerFrameBase {
  kind: 'INFO_REVEALED';
  packet: { info_id: string; body: string };
}

export interface BranchTakenFrame extends ServerFrameBase {
  kind: 'BRANCH_TAKEN';
  branch: { node_id: string; label: string; consequences: unknown[] };
}

export interface JobStatusFrame extends ServerFrameBase {
  kind: 'JOB_STATUS';
  actor_id: string;
  job: {
    job_id: string;
    status: 'queued' | 'running' | 'done' | 'failed';
    result_ref?: string;
  };
}

export interface PingFrame extends ServerFrameBase {
  kind: 'PING';
}

export type ServerFrame =
  | StateDeltaFrame
  | TurnUpdatedFrame
  | NarrationPendingFrame
  | NarrationApprovedFrame
  | WhisperFrame
  | InfoRevealedFrame
  | BranchTakenFrame
  | JobStatusFrame
  | PingFrame;

/** C→S 6 类：全带 campaign, actor{id,token?}, req_id */
export interface ClientActor {
  id: string;
  token?: string;
}

export type ClientFrame =
  | {
      kind: 'SUBMIT_ACTION';
      campaign: string;
      actor: ClientActor;
      req_id: string;
      action: unknown;
      intent?: string;
    }
  | {
      kind: 'START_TURN';
      campaign: string;
      actor: ClientActor;
      req_id: string;
      window_sec: number;
    }
  | {
      kind: 'CLOSE_WINDOW';
      campaign: string;
      actor: ClientActor;
      req_id: string;
    }
  | {
      kind: 'APPROVE_NARRATION';
      campaign: string;
      actor: ClientActor;
      req_id: string;
      proposal_id: string;
      decision: 'approve' | 'edit' | 'reject';
      edited_text?: string;
    }
  | {
      kind: 'COMMAND';
      campaign: string;
      actor: ClientActor;
      req_id: string;
      cmd: { type: 'roll_check' | 'map' | 'quick'; payload: Record<string, unknown> };
    }
  | {
      kind: 'AUDIO_CHUNK';
      campaign: string;
      actor: ClientActor;
      req_id: string;
      player_id: string;
      mime: 'audio/opus';
      chunk_base64: string;
      seq: number;
    };

/** perf 五字段（随事件附加，落 perf_metrics 独表） */
export interface PerfSample {
  vad_ms: number;
  stt_ms: number;
  llm_first_token_ms: number;
  tts_first_packet_ms: number;
  approve_wait_ms: number;
}

export type WsStatus = 'idle' | 'connecting' | 'open' | 'closed' | 'reconnecting';

export interface WsClientOptions {
  table: string;
  viewer: string;
  role: 'kp' | 'pl' | 'spectator';
  baseUrl?: string; // 默认 ws://127.0.0.1:9210
  onFrame?: (frame: ServerFrame) => void;
  onStatus?: (status: WsStatus) => void;
  onPerf?: (perf: PerfSample) => void;
}

const BACKOFF_STEPS = [1000, 2000, 4000, 8000]; // 指数退避 1/2/4/8s，上限 30s
const HEARTBEAT_TIMEOUT_MS = 30_000; // 30s 无帧主动重连（server 每 15s PING）

/**
 * WebSocket 客户端封装：连接 / 重连（指数退避＋last_seq 重放）/ 心跳 / 消息类型分发。
 * 联调在后续 WS 任务；本骨架只保证类型完备、可实例化、可关闭。
 */
export class WsClient {
  private opts: WsClientOptions;
  private ws: WebSocket | null = null;
  private status: WsStatus = 'idle';
  private lastSeq = -1;
  private retryIdx = 0;
  private heartbeatTimer: number | null = null;
  private reconnectTimer: number | null = null;
  private closedByUser = false;

  constructor(opts: WsClientOptions) {
    this.opts = opts;
  }

  connect(): void {
    this.closedByUser = false;
    this.openSocket();
  }

  close(): void {
    this.closedByUser = true;
    this.clearTimers();
    this.ws?.close();
    this.ws = null;
    this.setStatus('closed');
  }

  getStatus(): WsStatus {
    return this.status;
  }

  getLastSeq(): number {
    return this.lastSeq;
  }

  send(frame: ClientFrame): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(frame));
    }
  }

  private url(): string {
    const base = this.opts.baseUrl ?? 'ws://127.0.0.1:9210';
    const q = new URLSearchParams({
      table: this.opts.table,
      viewer: this.opts.viewer,
      role: this.opts.role,
      last_seq: String(this.lastSeq),
    });
    return `${base}/ws?${q.toString()}`;
  }

  private openSocket(): void {
    this.setStatus(this.retryIdx === 0 ? 'connecting' : 'reconnecting');
    const ws = new WebSocket(this.url());
    this.ws = ws;

    ws.onopen = () => {
      this.retryIdx = 0;
      this.setStatus('open');
      this.armHeartbeat();
    };

    ws.onmessage = (ev: MessageEvent) => {
      this.armHeartbeat();
      let raw: unknown;
      try {
        raw = JSON.parse(String(ev.data));
      } catch {
        return;
      }
      this.dispatch(raw);
    };

    ws.onclose = () => {
      this.clearTimers();
      if (this.closedByUser) return;
      this.scheduleReconnect();
    };

    ws.onerror = () => {
      // 出错走 onclose 的重连链；此处不单独处理。
    };
  }

  private dispatch(raw: unknown): void {
    if (typeof raw !== 'object' || raw === null) return;
    const frame = raw as ServerFrame & { perf?: PerfSample };
    if (typeof frame.seq === 'number' && frame.seq > this.lastSeq) {
      this.lastSeq = frame.seq;
    }
    if (frame.perf) this.opts.onPerf?.(frame.perf);
    if (frame.kind === 'PING') return; // 心跳帧：只用于保活计时，不分发业务
    this.opts.onFrame?.(frame);
  }

  private armHeartbeat(): void {
    this.clearHeartbeat();
    this.heartbeatTimer = window.setTimeout(() => {
      // 30s 无帧 → 主动重连
      try {
        this.ws?.close();
      } catch {
        /* ignore */
      }
      if (!this.closedByUser) this.scheduleReconnect();
    }, HEARTBEAT_TIMEOUT_MS);
  }

  private scheduleReconnect(): void {
    const step = BACKOFF_STEPS[Math.min(this.retryIdx, BACKOFF_STEPS.length - 1)];
    const delay = Math.min(step, 30_000);
    this.retryIdx += 1;
    this.setStatus('reconnecting');
    this.reconnectTimer = window.setTimeout(() => {
      if (!this.closedByUser) this.openSocket();
    }, delay);
  }

  private clearHeartbeat(): void {
    if (this.heartbeatTimer !== null) {
      window.clearTimeout(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private clearTimers(): void {
    this.clearHeartbeat();
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private setStatus(s: WsStatus): void {
    this.status = s;
    this.opts.onStatus?.(s);
  }
}

/** REST 降级轮询：WS 不可用时 GET /api/state?since=<seq>（2s 一次）——后续任务实现，此处预留签名。 */
export async function fetchStateSince(
  campaign: string,
  since: number,
  baseUrl = 'http://127.0.0.1:9210',
): Promise<ServerFrame[]> {
  const res = await fetch(
    `${baseUrl}/api/state?campaign=${encodeURIComponent(campaign)}&since=${since}`,
  );
  if (!res.ok) throw new Error(`GET /api/state failed: ${res.status}`);
  const data = (await res.json()) as { frames?: ServerFrame[] };
  return data.frames ?? [];
}
