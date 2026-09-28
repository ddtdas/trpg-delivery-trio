// transport —— 传输层单一入口（铁律：组件只经此处收发）。
//
// 运行模式由 VITE_TRPG_TRANSPORT 决定：
//   - 'mock'（默认）：mockTransport（demo 演示，无后端可跑）
//   - 'real'：RealTransport（真实 WS）
// 组件与 slice 只认本文件的 { connect, close, send, subscribe } 形状，
// 切换模式零改动组件。当前模式经 TRANSPORT_MODE 暴露，UI 打徽标。
//
// R2/t11（P0 修复）：
//   1) 连接参数支持**运行时**从 URL 查询串覆盖，构建期 env 仅作默认值 ——
//      同一份产物可在任意主机/端口/牌桌使用，无需重新构建：
//        /app/?table=t_xxx&viewer=kp1&role=kp&campaign=c_xxx&token=<token>#/kp
//      （查询串写在 hash 路由之前或之内均可）
//   2) 暴露连接状态订阅（subscribeStatus / getTransportStatus），供 UI 显示
//      真实连接态与**断连降级**提示。
//   3) 暴露 transportSnapshot()：统一 mock/real 两种实现的初始事件快照形状，
//      组件不再直接依赖 mockTransport。
import { createRealTransport, type TransportListener } from './realTransport';
import { mockTransport, type SendableClientFrame } from './mockTransport';
import type { WsStatus } from './ws';

export type MockListener = TransportListener;
export type { SendableClientFrame };
export type { WsStatus };

interface Transport {
  connect(): void;
  close(): void;
  send(frame: SendableClientFrame): void;
  subscribe(listener: MockListener): () => void;
  getStatus?(): string;
  /** 两种实现的快照形状**本就不同**：mock 返回 {state,submitted,events,proposals}，
   *  real 返回 {session,status,lastSeq}。此处放宽为 unknown，统一形状交给 transportSnapshot()。 */
  snapshot?(): unknown;
}

function env(): Record<string, string | undefined> {
  return (import.meta as unknown as { env?: Record<string, string | undefined> }).env ?? {};
}

/** 运行时覆盖：?key=value（同时支持 hash 路由内的查询串）。 */
function runtimeParam(key: string): string | undefined {
  if (typeof window === 'undefined' || !window.location) return undefined;
  try {
    const fromSearch = new URLSearchParams(window.location.search).get(key);
    if (fromSearch) return fromSearch;
    const hash = window.location.hash;
    const qi = hash.indexOf('?');
    if (qi >= 0) {
      const fromHash = new URLSearchParams(hash.slice(qi + 1)).get(key);
      if (fromHash) return fromHash;
    }
  } catch {
    /* ignore malformed query */
  }
  return undefined;
}

/** 运行时 URL 参数优先，localStorage 兜底，构建期 env 兜底。 */
function pick(paramKey: string, envKey: string): string | undefined {
  return runtimeParam(paramKey) ?? env()[envKey];
}

/** token 单一来源（T16.2）：URL ?token= > localStorage('trpg_token') > VITE_TRPG_TOKEN。
 *  页面内 DshPanel 的 token 编辑器写 localStorage，本函数与 lib/nlClient.ts:nlToken()
 *  同源（两者都读 trpg_token），避免 WS/REST 与 /access/nl 各用各的 token。 */
function pickToken(): string | undefined {
  const fromUrl = runtimeParam('token');
  if (fromUrl) return fromUrl;
  try {
    const ls = typeof localStorage !== 'undefined' ? localStorage.getItem('trpg_token') : null;
    if (ls && ls.trim()) return ls.trim();
  } catch {
    // localStorage 不可用（隐私模式等）——回退 env
  }
  return env().VITE_TRPG_TOKEN;
}

export type TransportRole = 'kp' | 'pl' | 'spectator';

export interface ResolvedTransportParams {
  table: string;
  viewer: string;
  role: TransportRole;
  campaign: string;
  token?: string;
  baseUrl?: string;
}

/** 解析当前连接参数（供 UI/证据展示，避免"连到哪张桌"不可见）。 */
export function resolveTransportParams(): ResolvedTransportParams {
  return {
    table: pick('table', 'VITE_TRPG_TABLE') ?? 'tbl_demo',
    viewer: pick('viewer', 'VITE_TRPG_VIEWER') ?? 'kp',
    role: (pick('role', 'VITE_TRPG_ROLE') as TransportRole | undefined) ?? 'kp',
    campaign: pick('campaign', 'VITE_TRPG_CAMPAIGN') ?? 'camp-mist-port',
    token: pickToken(),
    baseUrl: pick('ws', 'VITE_TRPG_WS_URL'),
  };
}

export function resolveMode(): 'mock' | 'real' {
  return pick('transport', 'VITE_TRPG_TRANSPORT') === 'real' ? 'real' : 'mock';
}

/* ---------------- 连接状态（R2/t11：断连降级提示的数据源） ---------------- */

const statusListeners = new Set<(s: WsStatus) => void>();
let lastStatus: WsStatus = 'idle';

function emitStatus(s: WsStatus): void {
  lastStatus = s;
  for (const fn of Array.from(statusListeners)) {
    try {
      fn(s);
    } catch {
      /* 单个订阅者异常不影响传输层 */
    }
  }
}

export function getTransportStatus(): WsStatus {
  return lastStatus;
}

/** 订阅连接状态；订阅时立即以当前状态回调一次。返回退订函数。 */
export function subscribeStatus(cb: (s: WsStatus) => void): () => void {
  statusListeners.add(cb);
  cb(lastStatus);
  return () => {
    statusListeners.delete(cb);
  };
}

/** 人类可读的连接状态文案（UI 横幅 + 降级提示共用，避免各处口径不一）。 */
export function transportStatusLabel(s: WsStatus): string {
  switch (s) {
    case 'open':
      return '已连接服务器（实时同步）';
    case 'connecting':
      return '正在连接服务器…';
    case 'reconnecting':
      return '连接中断，正在重连…（本地改动暂存，恢复后同步）';
    case 'closed':
      return '连接已关闭：改动不会同步到服务器（降级为单机演示）';
    default:
      return '尚未连接服务器';
  }
}

function buildTransport(): Transport {
  if (resolveMode() === 'real') {
    const p = resolveTransportParams();
    return createRealTransport({
      table: p.table,
      viewer: p.viewer,
      role: p.role,
      campaign: p.campaign,
      token: p.token,
      baseUrl: p.baseUrl,
      onStatus: emitStatus,
    });
  }
  return mockTransport;
}

/** 当前传输实现（构建时确定；组件层只用此单例）。 */
export const transport: Transport = buildTransport();

/** 显式标记当前走的是哪条链路（UI 横幅/证据用）。 */
export const TRANSPORT_MODE: 'mock' | 'real' = resolveMode();

/**
 * 初始事件快照 —— 统一 mock/real 形状。
 * mock 有内置剧本事件；real 无本地事件（初始为空，靠服务端帧填充）。
 */
export function transportSnapshot(): { events: string[] } {
  const snap = typeof transport.snapshot === 'function' ? transport.snapshot() : undefined;
  const events =
    snap && typeof snap === 'object' && Array.isArray((snap as { events?: unknown }).events)
      ? ((snap as { events: string[] }).events)
      : [];
  return { events };
}

/* ============================================================================
 * 写路径（REST）—— real 模式的**真实写入**通道。
 *
 * 根因（本文件修复记录）：
 *   服务端 /ws 上行 (app/web/ws.py::Hub.handle_up) 对 START_TURN / CLOSE_WINDOW /
 *   COMMAND(map) **只做协议校验并回 ACK，从不落 command bus / 事件流**；
 *   且 realTransport.send() 在 socket 未 OPEN 时**静默丢弃**。
 *   ⇒ 单靠 WS 帧驱动，主持端「开始回合 / 放置棋子 / 迷雾切换」点击后
 *     服务端零写入、前端零反馈（死键）。
 *
 * 方案（不触碰后端、不新增端点，复用服务端**既有**写路径）：
 *   - 开回合   -> POST /access/host/turn                    (app/web/access.py:1537，webapp/KP 端)
 *                 内部走 command_bus start_turn -> 落 TURN_STARTED -> ws_bridge 广播 TURN_UPDATED
 *   - 关窗口   -> POST /api/campaigns/{c}/pipeline/resolve  (app/web/pipeline_api.py:369)
 *                 body.close_window=true -> 落 TURN_CLOSED -> 产出待审候选提案
 *   - 地图 op  -> POST /api/campaigns/{c}/map                (app/web/rest.py:527)
 *                 落 MAP_UPDATED；set_fog/set_light 需顶层 approved=true 才放行
 *   - 战斗掷骰 -> POST /api/campaigns/{c}/combat/round       (app/web/combat_api.py:173)
 *                 落 COMBAT_ROUND_PROPOSED（pending_approval，即「待批提案」）
 *
 * mock 演示模式**不**走本通道：继续用 transport.send() 走 mock 会话（demo 不回归）。
 * ========================================================================== */

export interface RestWriteResult {
  ok: boolean;
  status: number;
  data: Record<string, unknown> | null;
  error: string;
}

/** 当前页的连接参数（campaign/token）；缺 token 时写路径不可用。 */
export function restConnParams(): { campaign: string; token: string } {
  const p = resolveTransportParams();
  return { campaign: p.campaign, token: p.token ?? '' };
}

/** POST JSON（Bearer 鉴权）；**任何** HTTP 失败都转成结构化结果，绝不抛。 */
export async function postJson(
  path: string,
  body: Record<string, unknown>,
  token: string,
): Promise<RestWriteResult> {
  try {
    const resp = await fetch(path, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    });
    const raw = (await resp.json().catch(() => null)) as Record<string, unknown> | null;
    if (!resp.ok) {
      const detail = raw && typeof raw === 'object'
        ? String(raw.detail ?? raw.error ?? '')
        : '';
      return {
        ok: false,
        status: resp.status,
        data: raw,
        error: detail || `HTTP ${resp.status}`,
      };
    }
    // /access/* 统一包裹 {ok,data|error,code}；/api/* 裸 JSON。
    if (raw && raw.ok === true) {
      return {
        ok: true,
        status: resp.status,
        data: (raw.data as Record<string, unknown>) ?? {},
        error: '',
      };
    }
    if (raw && raw.ok === false) {
      return {
        ok: false,
        status: resp.status,
        data: raw,
        error: String(raw.error ?? `HTTP ${resp.status}`),
      };
    }
    return { ok: true, status: resp.status, data: raw ?? {}, error: '' };
  } catch (e) {
    return {
      ok: false,
      status: 0,
      data: null,
      error: e instanceof Error ? e.message : String(e),
    };
  }
}

/** 缺连接参数时的统一错误文案（各组件共用，避免各处口径不一）。 */
export const REST_NEED_PARAMS = '缺少连接参数：请用 ?campaign=<战役>&token=<webapp token> 打开本页';

/** 开回合（真实写入 TURN_STARTED）。 */
export async function restStartTurn(
  campaign: string,
  token: string,
  windowSec: number,
  reqId: string,
): Promise<RestWriteResult> {
  return postJson('/access/host/turn', { campaign, window_sec: windowSec, req_id: reqId }, token);
}

/** 结束响应窗口（真实写入 TURN_CLOSED；服务端同时算候选进待批队列）。 */
export async function restCloseWindow(
  campaign: string,
  token: string,
  turnNo: number | null,
): Promise<RestWriteResult> {
  return postJson(
    `/api/campaigns/${encodeURIComponent(campaign)}/pipeline/resolve`,
    { turn_no: turnNo, close_window: true },
    token,
  );
}

/** 地图命令（真实写入 MAP_UPDATED）。fog/light 需 approved=true。 */
export async function restMapOp(
  campaign: string,
  token: string,
  op: string,
  target: string,
  delta: Record<string, unknown>,
  approved: boolean,
): Promise<RestWriteResult> {
  return postJson(
    `/api/campaigns/${encodeURIComponent(campaign)}/map`,
    {
      map_id: 'map_library',
      op,
      target,
      delta,
      actor: 'kp',
      approved,
    },
    token,
  );
}

/**
 * 拍板待批提案（真实写入 NARRATION_APPROVED / NARRATION_EDITED / NARRATION_REJECTED）。
 * 服务端 app/web/rest.py:332 decide_approval 是既有审批总线唯一入口，WS 上行
 * APPROVE_NARRATION 同样只 ACK 不落业务，故 real 模式必须走此 REST。
 */
export async function restApprove(
  campaign: string,
  token: string,
  proposalId: string,
  decision: 'approve' | 'edit' | 'reject',
  editedText?: string,
  reason?: string,
): Promise<RestWriteResult> {
  const body: Record<string, unknown> = { proposal_id: proposalId, decision };
  if (editedText) body.edited_text = editedText;
  if (reason) body.reason = reason;
  return postJson(`/api/campaigns/${encodeURIComponent(campaign)}/approvals`, body, token);
}

/** 战斗结算掷骰（真实写入 COMBAT_ROUND_PROPOSED，即待批提案）。 */
export async function restCombatRound(
  campaign: string,
  token: string,
  combatId: string,
  actions: Array<{ actor: string; action: string }>,
): Promise<RestWriteResult> {
  return postJson(
    `/api/campaigns/${encodeURIComponent(campaign)}/combat/round`,
    { combat_id: combatId, actions },
    token,
  );
}
