// realTransport 单测（node 直跑，无前端测试框架依赖）。
// 运行：npx esbuild scripts/check_realTransport.ts --bundle --platform=node --format=cjs --outfile=/tmp/check_rt.cjs && node /tmp/check_rt.cjs
// 覆盖：编解码往返、心跳 PING/PONG、重连退避序列、mock WebSocket 注入的状态机。
import {
  CLIENT_KINDS,
  SERVER_KINDS,
  backoffBaseForTest,
  decodeServerFrame,
  encodeClientFrame,
  demoReconnectSequence,
  scheduledDelayForTest,
} from '../src/lib/realTransport.testable';

let failures = 0;
function check(name: string, cond: boolean, detail = ''): void {
  if (cond) console.log(`ok - ${name}`);
  else {
    failures += 1;
    console.log(`FAIL - ${name} ${detail}`);
  }
}

// 1. S→C 8 类往返
const sCases: Array<Record<string, unknown>> = [
  { kind: 'STATE_DELTA', seq: 1, campaign_id: 'c', scope: 'viewer', ts: 1, delta: { field: 'f', value: 1 } },
  { kind: 'TURN_UPDATED', seq: 2, campaign_id: 'c', scope: 'public', ts: 1, turn: { state: 'COLLECTING', submitted: [], total: 2, countdown_end_ts: 0 } },
  { kind: 'NARRATION_PENDING', seq: 3, campaign_id: 'c', scope: 'kp', ts: 1, proposal: { id: 'p', text: 't' } },
  { kind: 'NARRATION_APPROVED', seq: 4, campaign_id: 'c', scope: 'public', ts: 1, narration: { id: 'p', text: 't' } },
  { kind: 'WHISPER', seq: 5, campaign_id: 'c', scope: 'whisper', ts: 1, targets: ['pl1'], packet: { info_id: 'i', body: 's' } },
  { kind: 'INFO_REVEALED', seq: 6, campaign_id: 'c', scope: 'condition', ts: 1, packet: { info_id: 'i', body: 'b' } },
  { kind: 'BRANCH_TAKEN', seq: 7, campaign_id: 'c', scope: 'public', ts: 1, branch: { node_id: 'n', label: 'l', consequences: [] } },
  { kind: 'JOB_STATUS', seq: 8, campaign_id: 'c', scope: 'actor', ts: 1, actor_id: 'pl1', job: { job_id: 'j', status: 'done' } },
];
check('server kinds = 8', SERVER_KINDS.length === 8, JSON.stringify(SERVER_KINDS));
for (const c of sCases) {
  const d = decodeServerFrame(c);
  check(`decode ${String(c.kind)}`, d.kind === c.kind);
}
// 坏帧拒绝
for (const bad of [
  { kind: 'NOPE', seq: 0, campaign_id: 'c', scope: 'public', ts: 1 },
  { kind: 'WHISPER', seq: 0, campaign_id: 'c', scope: 'public', ts: 1, targets: [], packet: { info_id: 'i', body: 'b' } },
  { kind: 'TURN_UPDATED', seq: 0, campaign_id: 'c', scope: 'public', ts: 1 },
]) {
  let threw = false;
  try {
    decodeServerFrame(bad);
  } catch {
    threw = true;
  }
  check(`reject ${String((bad as { kind: unknown }).kind)}`, threw);
}
// 心跳
check('PING passthrough', decodeServerFrame({ kind: 'PING', ts: 9 }).kind === 'PING');

// 2. C→S 6 类编码
check('client kinds = 6', CLIENT_KINDS.length === 6, JSON.stringify(CLIENT_KINDS));
const env = { campaign: 'c', actor: { id: 'kp' }, req_id: 'r1' };
const wire = encodeClientFrame({ kind: 'START_TURN', window_sec: 60 } as never, env);
const parsed = JSON.parse(wire) as Record<string, unknown>;
check('encode START_TURN envelope', parsed.campaign === 'c' && parsed.req_id === 'r1' && (parsed.actor as { id: string }).id === 'kp');
let editThrew = false;
try {
  encodeClientFrame({ kind: 'APPROVE_NARRATION', proposal_id: 'p', decision: 'edit' } as never, env);
} catch {
  editThrew = true;
}
check('encode edit requires edited_text', editThrew);

// 3. 重连退避 1/2/4/8s 上限 30s
check('backoff 1/2/4/8', JSON.stringify([0, 1, 2, 3].map(backoffBaseForTest)) === JSON.stringify([1000, 2000, 4000, 8000]));
check('backoff repeats last step', backoffBaseForTest(99) === 8000);
check('scheduled delay caps 30s', scheduledDelayForTest(3, 50000) === 30000 && scheduledDelayForTest(0, 100) === 1100);
check('reconnect seq demo', demoReconnectSequence().join(',') === 'connecting,open,reconnecting,open');

// 4. mock WebSocket 注入状态机（打开→收帧→PING 保活→关闭重连）
import { RealTransport } from '../src/lib/realTransport';

type Handler = (ev?: unknown) => void;
class FakeSocket {
  onopen: Handler = () => undefined;
  onmessage: Handler = () => undefined;
  onclose: Handler = () => undefined;
  onerror: Handler = () => undefined;
  readyState = 1;
  sent: string[] = [];
  closed = false;
  constructor(public url: string) {
    FakeSocket.instances.push(this);
  }
  send(s: string): void {
    this.sent.push(s);
  }
  close(): void {
    this.closed = true;
  }
  static instances: FakeSocket[] = [];
}

const seen: string[] = [];
const frames: string[] = [];
const t = new RealTransport({
  table: 't1',
  viewer: 'kp',
  role: 'kp',
  campaign: 'c1',
  socketFactory: (url: string) => new FakeSocket(url) as unknown as WebSocket,
  jitter: () => 0,
  onStatus: (s) => seen.push(s),
  onFrame: (f) => frames.push(f.kind),
});
t.connect();
const sock = FakeSocket.instances[0];
check('url has table/viewer/role/last_seq', sock.url.includes('table=t1') && sock.url.includes('viewer=kp') && sock.url.includes('last_seq=-1'));
sock.onopen();
check('open status', seen.includes('open'));
sock.onmessage({ data: JSON.stringify({ kind: 'PING', ts: 1 }) });
check('PING not dispatched', frames.length === 0);
sock.onmessage({
  data: JSON.stringify({ kind: 'TURN_UPDATED', seq: 0, campaign_id: 'c1', scope: 'public', ts: 1, turn: { state: 'COLLECTING', submitted: [], total: 1, countdown_end_ts: 0 } }),
});
check('TURN_UPDATED dispatched + lastSeq', frames.includes('TURN_UPDATED') && t.getLastSeq() === 0);
t.send({ kind: 'CLOSE_WINDOW' } as never);
const sentParsed = JSON.parse(sock.sent[0]) as Record<string, unknown>;
check('send fills envelope', sentParsed.campaign === 'c1' && (sentParsed.actor as { id: string }).id === 'kp' && typeof sentParsed.req_id === 'string');
sock.onclose();
check('close schedules reconnect', seen.includes('reconnecting'));
t.close();

if (failures > 0) {
  console.log(`${failures} FAILURES`);
  process.exit(1);
}
console.log('ALL TRANSPORT CHECKS PASSED');
