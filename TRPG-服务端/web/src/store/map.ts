import { create } from 'zustand';
import type { SendableClientFrame } from '../lib/mockTransport';
import { TRANSPORT_MODE, restConnParams, restMapOp, transport } from '../lib/transport';
import { loadSceneInfo, sceneTitle } from '../lib/sceneNames';

export type MapOpKind = 'move' | 'add_token' | 'set_fog' | 'set_status' | 'set_light';
export type TokenStatus = 'settled' | 'pending' | 'rejected';

export interface MapToken {
  id: string;
  label: string;
  x: number;
  y: number;
  room: string;
  visible: boolean;
  status: TokenStatus;
}

interface MapState {
  tokens: MapToken[];
  fog: Record<string, boolean>;
  pendingOp: { op: MapOpKind; target: string; note: string } | null;
  error: string;
  log: Array<{ text: string; ts: number; actor: string }>;
  selectedId: string | null;
  /** T16.3: 场景名（单一事实源：scenes API / event_graph 静态回退表）。 */
  sceneTitle: string;
  sceneById: Record<string, string>;
  set: (p: Partial<MapState>) => void;
  reset: () => void;
}

const initialTokens: MapToken[] = [
  { id: 'linmo', label: '林', x: 60, y: 60, room: 'r_lobby', visible: true, status: 'settled' },
  { id: 'surui', label: '苏', x: 120, y: 100, room: 'r_lobby', visible: true, status: 'settled' },
  { id: 'npc_clerk', label: '员', x: 300, y: 60, room: 'r_reading', visible: true, status: 'settled' },
];

const initial: Omit<MapState, 'set' | 'reset'> = {
  tokens: initialTokens,
  fog: { r_secret: true },
  pendingOp: null,
  error: '',
  // T16.3: 原硬编码「密斯卡托尼克大学图书馆（一层）」与 SharedScreen/Overview 不一致 ——
  // 改为加载后由 scenes API（event_graph 单一事实源）或静态回退表填充。
  log: [{ text: '地图已载入，正在同步场景…', ts: Date.now(), actor: 'system' }],
  selectedId: 'linmo',
  sceneTitle: '',
  sceneById: {},
};

export const useMapStore = create<MapState>()((set) => ({
  ...initial,
  set: (p) => set(p),
  reset: () => set({ ...initial, tokens: initialTokens.map((t) => ({ ...t })) }),
}));

/** T16.3: 加载场景表写入 store（MapCanvas 挂载时调用一次，常驻缓存）。
 *  数据源 = GET /api/campaigns/{c}/scenes（event_graph 派生，服务端权威）；失败回退静态表。 */
export async function ensureSceneNames(campaign: string): Promise<void> {
  try {
    const info = await loadSceneInfo(campaign);
    const title = info.currentTitle || sceneTitle(info.byId, info.currentId) || '当前场景';
    const cur = useMapStore.getState();
    cur.set({
      sceneById: info.byId,
      sceneTitle: title,
      log: [{ text: '地图已载入：' + title, ts: Date.now(), actor: 'system' }, ...cur.log].slice(0, 8),
    });
  } catch {
    /* 加载失败保持初始值 */
  }
}

/** 场景 id -> 标题（store 内查询）。 */
export function mapSceneTitle(id: string): string {
  const byId = useMapStore.getState().sceneById;
  return (id && byId[id]) || id || '';
}

let reqSeq = 7000;
function reqId(): string {
  reqSeq += 1;
  return `map-${Date.now()}-${reqSeq}`;
}

/** 本地结算：REST 写入成功后立即把结果应用到画布并写日志。
 *
 *  为什么需要「本地结算」：服务端对 MAP_UPDATED 的 WS 广播走 ws_bridge 的**回退帧**
 *  STATE_DELTA{field:"event",value:{type,redacted:true}}（app/web/ws_bridge.py:239），
 *  **不带 map_id/op/target/delta**。因此前端既收不到 map_op 明细，也无法从下行判
 *  断这次操作成没成功 —— 只能以 REST 响应（201 + seq）为准，在本地落位/写日志。
 *  mock 模式仍走下行 map_op 帧（保持演示链路与逐帧日志不变）。
 */
function applyLocal(op: MapOpKind, target: string, delta: Record<string, unknown>): void {
  const s = useMapStore.getState();
  const d = delta as Record<string, string | number | boolean>;
  if (op === 'move') {
    s.set({
      tokens: s.tokens.map((t) => (t.id === target
        ? { ...t, x: Number(d.x ?? t.x), y: Number(d.y ?? t.y), room: String(d.room ?? t.room), status: 'settled' as const }
        : t)),
      pendingOp: null,
      log: [{ text: `落位：${target} → (${d.x}, ${d.y})`, ts: Date.now(), actor: 'kp' }, ...s.log].slice(0, 8),
    });
  } else if (op === 'add_token') {
    if (s.tokens.some((t) => t.id === target)) return; // 幂等：重复落地不重复加
    s.set({
      tokens: [...s.tokens, {
        id: target, label: String(d.label ?? '新'), x: Number(d.x ?? 60),
        y: Number(d.y ?? 60), room: String(d.room ?? 'r_lobby'),
        visible: true, status: 'settled',
      }],
      pendingOp: null,
      selectedId: target,
      log: [{ text: `新增棋子：${String(d.label ?? '')}（${target}）已落位`, ts: Date.now(), actor: 'kp' }, ...s.log].slice(0, 8),
    });
  } else if (op === 'set_fog' || op === 'set_light') {
    if (op === 'set_fog') {
      s.set({
        fog: { ...s.fog, [target]: Boolean(d.fog) },
        pendingOp: null,
        log: [{ text: `迷雾：${target} → ${d.fog ? '遮蔽' : '揭示'}`, ts: Date.now(), actor: 'kp' }, ...s.log].slice(0, 8),
      });
    } else {
      s.set({ pendingOp: null, log: [{ text: `光照：${target}`, ts: Date.now(), actor: 'kp' }, ...s.log].slice(0, 8) });
    }
  } else {
    s.set({ pendingOp: null });
  }
}

/** 写入失败：清 pending 并给出可读错误（不静默）。 */
function applyFailure(op: MapOpKind, target: string, msg: string): void {
  const s = useMapStore.getState();
  s.set({
    pendingOp: null,
    tokens: op === 'add_token'
      ? s.tokens
      : s.tokens.map((t) => (t.id === target ? { ...t, status: 'rejected' as const } : t)),
    error: `地图命令失败（${op} ${target}）：${msg}`,
    log: [{ text: `命令失败：${op} ${target} · ${msg}`, ts: Date.now(), actor: 'system' }, ...s.log].slice(0, 8),
  });
}

/**
 * 地图命令写路径。
 *
 * real 模式：POST /api/campaigns/{c}/map（app/web/rest.py:527）—— 落 MAP_UPDATED，
 *   fog/light 需**顶层** approved=true（后端 537 行读 body.approved，不看 delta）。
 *   201 -> 本地结算；4xx/网络错 -> 本地失败态。
 * mock 模式：COMMAND map 帧走 mock 会话（演示链路不变；裁决仍由下行 map_op 帧驱动）。
 *
 * 返回 Promise：调用方可 await 以便串联（调用方不 await 也不阻塞 UI）。
 */
export function mapSend(
  op: MapOpKind,
  target: string,
  delta: Record<string, unknown>,
  opts?: { approved?: boolean },
): Promise<void> {
  // approved 必须放在**命令顶层**（mock 读 payload.approved / 后端读 MapCommand.approved），
  // 塞在 delta 里两边都读不到 —— 这正是原「迷雾切换」死键的第二个根因。
  const approved = opts?.approved ?? Boolean((delta as { approved?: boolean }).approved ?? true);
  if (TRANSPORT_MODE !== 'real') {
    transport.send({
      kind: 'COMMAND',
      cmd: { type: 'map', payload: { map_id: 'map_library', op, target, delta, approved } },
    } as SendableClientFrame);
    void reqId;
    return Promise.resolve();
  }
  const { campaign, token } = restConnParams();
  if (!campaign) {
    applyFailure(op, target, '缺少连接参数（URL 需带 campaign）');
    return Promise.resolve();
  }
  return restMapOp(campaign, token, op, target, delta, approved).then((res) => {
    if (res.ok) {
      applyLocal(op, target, delta);
      useMapStore.getState().set({ error: '' });
    } else {
      applyFailure(op, target, res.error);
    }
  });
}

/** 演示钩子（验收截图用）：强制进入 pending 态，不发命令。 */
export function demoPending(target = 'linmo'): void {
  const s = useMapStore.getState();
  s.set({
    tokens: s.tokens.map((t) => (t.id === target ? { ...t, status: 'pending' as const } : t)),
    pendingOp: { op: 'move', target, note: '演示：拖拽已发起 · 等待裁决（mock 0.6s 后落位）' },
  });
  window.setTimeout(() => {
    const cur = useMapStore.getState();
    cur.set({
      tokens: cur.tokens.map((t) => (t.id === target
        ? { ...t, x: 300, y: 80, room: 'r_reading', status: 'settled' as const }
        : t)),
      pendingOp: null,
      log: [{ text: `落位：${target} → (300, 80)`, ts: Date.now(), actor: 'kp' }, ...cur.log].slice(0, 8),
    });
  }, 600);
}

/** 订阅 transport 下行 → 落位/拒绝回滚（调用一次，常驻）。 */
let subscribed = false;
export function ensureMapSubscription(): void {
  if (subscribed) return;
  subscribed = true;
  transport.subscribe((frame) => {
    const s = useMapStore.getState();
    if (frame.kind === 'STATE_DELTA' && frame.delta.field === 'map_op') {
      const v = frame.delta.value as { op: MapOpKind; target: string; delta: Record<string, number | string | boolean>; verdict: 'approved' | 'rejected'; note?: string };
      if (v.verdict === 'approved') {
        if (v.op === 'move') {
          s.set({
            tokens: s.tokens.map((t) => (t.id === v.target
              ? { ...t, x: Number(v.delta.x ?? t.x), y: Number(v.delta.y ?? t.y), room: String(v.delta.room ?? t.room), status: 'settled' as const }
              : t)),
            pendingOp: null,
            log: [{ text: `落位：${v.target} → (${v.delta.x}, ${v.delta.y})`, ts: Date.now(), actor: 'kp' }, ...s.log].slice(0, 8),
          });
        } else if (v.op === 'add_token') {
          s.set({
            tokens: [...s.tokens, {
              id: String(v.target), label: String(v.delta.label ?? '新'), x: Number(v.delta.x ?? 60),
              y: Number(v.delta.y ?? 60), room: String(v.delta.room ?? 'r_lobby'),
              visible: true, status: 'settled',
            }],
            pendingOp: null,
            selectedId: String(v.target),
            log: [{ text: `新增棋子：${v.target}`, ts: Date.now(), actor: 'kp' }, ...s.log].slice(0, 8),
          });
        } else if (v.op === 'set_fog') {
          s.set({
            fog: { ...s.fog, [String(v.target)]: Boolean(v.delta.fog) },
            pendingOp: null,
            log: [{ text: `迷雾：${v.target} → ${v.delta.fog ? '遮蔽' : '揭示'}`, ts: Date.now(), actor: 'kp' }, ...s.log].slice(0, 8),
          });
        }
      } else {
        // 审批拒绝 → 回滚到 settled（token 位置不动，仅清 pending 态）。
        s.set({
          tokens: s.tokens.map((t) => (t.id === v.target ? { ...t, status: 'rejected' as const } : t)),
          pendingOp: null,
          error: `审批拒绝：${v.target} 的 ${v.op} 未执行（${v.note ?? '主持人否决'}），位置已回滚。`,
          log: [{ text: `拒绝回滚：${v.target}`, ts: Date.now(), actor: 'system' }, ...s.log].slice(0, 8),
        });
        window.setTimeout(() => {
          const cur = useMapStore.getState();
          cur.set({ tokens: cur.tokens.map((t) => (t.id === v.target ? { ...t, status: 'settled' as const } : t)) });
        }, 2500);
      }
    }
  });
}