import type { ClientFrame, ServerFrame, WsClientOptions, WsStatus } from './ws';

export type MockListener = (frame: ServerFrame) => void;

/** Omit 在联合类型上默认塌缩 —— 经泛型形参分配，保持各 kind 的字段类型。 */
type DistributiveOmit<T, K extends keyof never> = T extends unknown ? Omit<T, K & keyof T> : never;
export type SendableClientFrame = DistributiveOmit<ClientFrame, 'campaign' | 'actor' | 'req_id'>;
export type EmittableServerFrame = DistributiveOmit<ServerFrame, 'seq' | 'ts' | 'campaign_id'>;

class DemoSession {
  seq = 0;
  state: 'IDLE' | 'COLLECTING' | 'CLOSING' | 'RESOLVING' | 'DISTRIBUTED' = 'IDLE';
  submitted: Array<{ player_id: string; intent: string }> = [];
  listeners = new Set<MockListener>();
  proposals = [{ id: 'prop-1', text: '门后的雾气像活物般缓缓退去，露出一枚带血的银钥匙。', intention: '推进调查线', source: 'mock-kp' }];
  events = ['剧本《雾港来信》已载入', '玩家连接：林墨、苏芮', '规则包：CoC7 · 种子 20260919'];
  emit(frame: EmittableServerFrame): void {
    const full = { ...frame, seq: ++this.seq, ts: Date.now(), campaign_id: 'camp-mist-port' } as ServerFrame;
    this.events = [this.label(full), ...this.events].slice(0, 8);
    this.listeners.forEach((listener) => listener(full));
  }
  label(frame: ServerFrame): string {
    if (frame.kind === 'TURN_UPDATED') return `回合状态：${frame.turn.state}`;
    if (frame.kind === 'NARRATION_APPROVED') return '旁白已批准并广播';
    if (frame.kind === 'WHISPER') return `私语：${frame.packet.info_id}`;
    if (frame.kind === 'STATE_DELTA') return `${frame.delta.field} 已更新`;
    return frame.kind;
  }
  receive(frame: ClientFrame): void {
    if (frame.kind === 'START_TURN') {
      this.state = 'COLLECTING'; this.submitted = [];
      this.emit({ kind: 'TURN_UPDATED', scope: 'public', turn: { state: 'COLLECTING', submitted: [], total: 2, countdown_end_ts: Date.now() + frame.window_sec * 1000 } });
      this.emit({ kind: 'NARRATION_PENDING', scope: 'kp', proposal: this.proposals[0] });
    } else if (frame.kind === 'SUBMIT_ACTION') {
      this.submitted = [...this.submitted.filter((p) => p.player_id !== frame.actor.id), { player_id: frame.actor.id, intent: frame.intent ?? String(frame.action) }];
      this.emit({ kind: 'TURN_UPDATED', scope: 'public', turn: { state: this.state === 'IDLE' ? 'COLLECTING' : this.state, submitted: this.submitted, total: 2, countdown_end_ts: Date.now() + 90000 } });
    } else if (frame.kind === 'CLOSE_WINDOW') {
      this.state = 'RESOLVING'; this.emit({ kind: 'TURN_UPDATED', scope: 'public', turn: { state: 'RESOLVING', submitted: this.submitted, total: 2, countdown_end_ts: 0 } });
      this.emit({ kind: 'BRANCH_TAKEN', scope: 'public', branch: { node_id: 'library', label: '银钥匙线索', consequences: ['发现地下室入口'] } });
    } else if (frame.kind === 'APPROVE_NARRATION') {
      const proposal = this.proposals.find((p) => p.id === frame.proposal_id) ?? this.proposals[0];
      if (frame.decision === 'approve' || frame.decision === 'edit') this.emit({ kind: 'NARRATION_APPROVED', scope: 'public', narration: { id: proposal.id, text: frame.edited_text || proposal.text } });
      else this.emit({ kind: 'STATE_DELTA', scope: 'kp', delta: { field: 'proposal', value: 'rejected' } });
    } else if (frame.kind === 'COMMAND') {
      if (frame.cmd.type === 'map') {
        // t27 地图命令链 mock：move/add_token 直接批准落位；set_fog/set_light 需 approved 旗。
        const p = frame.cmd.payload as { map_id?: string; op?: string; target?: string; delta?: Record<string, number | string | boolean>; approved?: boolean };
        const op = String(p.op ?? '');
        const target = String(p.target ?? '');
        const needsApproval = op === 'set_fog' || op === 'set_light';
        if (needsApproval && p.approved !== true) {
          this.emit({ kind: 'STATE_DELTA', scope: 'public', delta: { field: 'map_op', value: { op, target, delta: p.delta ?? {}, verdict: 'rejected', note: '需 KP 批准后执行' } } });
        } else {
          this.emit({ kind: 'STATE_DELTA', scope: 'public', delta: { field: 'map_op', value: { op, target, delta: p.delta ?? {}, verdict: 'approved' } } });
        }
        return;
      }
      const seed = Number(frame.cmd.payload.seed ?? 7);
      const roll = ((seed * 37) % 100) + 1;
      this.emit({ kind: 'STATE_DELTA', scope: 'public', delta: { field: 'last_roll', value: { target: frame.cmd.payload.target ?? '侦查', roll, seed, result: roll <= 45 ? '成功' : '失败' } } });
    } else if (frame.kind === 'AUDIO_CHUNK') {
      // t25 语音循环：上行分片 → 转写段 → 转写就绪 → TTS 播报（全 mock，按 runtime 帧形状）。
      const seq = frame.seq;
      this.emit({ kind: 'STATE_DELTA', scope: 'public', delta: { field: 'transcript_seg', value: { text: '我推开图书馆的门，雾气扑面而来。', t0: 0.0, t1: 1.2, speaker: frame.player_id, chunk_seq: seq, status: 'appended' } } });
      this.emit({ kind: 'STATE_DELTA', scope: 'public', delta: { field: 'transcript_ready', value: { transcript_ref: `tr-${frame.player_id}-${seq}`, aligned: true, chunk_seq: seq, status: 'ready' } } });
      this.emit({ kind: 'JOB_STATUS', scope: 'actor', actor_id: frame.player_id, job: { job_id: `job-tts-${seq}`, status: 'done', result_ref: 'tts:门后的雾气缓缓退去（播报就绪）' } });
    }
  }
}
const session = new DemoSession();

export class MockTransport {
  private listener?: MockListener;
  private status: WsStatus = 'idle';
  constructor(private readonly options: WsClientOptions = { table: 'demo', viewer: 'kp', role: 'kp' }) {}
  connect(): void { this.status = 'open'; this.options.onStatus?.('open'); this.listener = (frame) => this.options.onFrame?.(frame); session.listeners.add(this.listener); }
  close(): void { if (this.listener) session.listeners.delete(this.listener); this.status = 'closed'; this.options.onStatus?.('closed'); }
  send(frame: SendableClientFrame): void { session.receive(frame as ClientFrame); }
  getStatus(): WsStatus { return this.status; }
  getLastSeq(): number { return session.seq; }
  snapshot() { return { state: session.state, submitted: [...session.submitted], events: [...session.events], proposals: [...session.proposals] }; }
  subscribe(listener: MockListener): () => void { session.listeners.add(listener); return () => session.listeners.delete(listener); }
}
export function createMockTransport(options?: Partial<WsClientOptions>): MockTransport { return new MockTransport({ table: 'demo', viewer: 'kp', role: 'kp', ...options }); }
export const mockTransport = new MockTransport();
