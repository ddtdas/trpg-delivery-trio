import React from 'react';
import {
  TRANSPORT_MODE,
  REST_NEED_PARAMS,
  restApprove,
  restCloseWindow,
  restCombatRound,
  restStartTurn,
  transport,
  transportSnapshot,
  type SendableClientFrame,
} from '../lib/transport';
import type { ClientFrame } from '../lib/ws';
import { EmptyState, ErrorBanner, LoadingRow, SkeletonRows } from './ui';
// UI-R2: 灰白黑令牌适配（仅视觉）

const ACTOR = { id: 'kp', token: 'mock-kp-token' } as const;

interface Proposal { id: string; text: string; intention: string; source: string }
interface NarrMsg { id: string; text: string }

function useNow(intervalMs = 1000): number {
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(timer);
  }, [intervalMs]);
  return now;
}

let reqSeq = 0;
function reqId(): string { reqSeq += 1; return `kp-${Date.now()}-${reqSeq}`; }
function send(frame: SendableClientFrame): void {
  transport.send(frame);
}

/* M3 (T6): 主持人四态调控 —— REST 直连（webapp token 来自 URL；与 Overview 同构）。 */
function connParams(): { campaign: string; token: string } {
  const q = new URLSearchParams(window.location.search);
  const hash = window.location.hash;
  const qi = hash.indexOf('?');
  if (qi >= 0) {
    const hq = new URLSearchParams(hash.slice(qi + 1));
    return { campaign: hq.get('campaign') || q.get('campaign') || '', token: hq.get('token') || q.get('token') || '' };
  }
  return { campaign: q.get('campaign') || '', token: q.get('token') || '' };
}

const CHAT_MODES: Array<{ value: string; label: string; hint: string }> = [
  { value: 'chat_enabled', label: '能私聊 + 公共', hint: '私聊与公共频道全开（默认）' },
  { value: 'chat_disabled', label: '不能私聊', hint: '私聊关闭，公共频道开放' },
  { value: 'public_only', label: '仅公共', hint: '能交流（公共频道），不能私聊' },
  { value: 'all_disabled', label: '不能交流', hint: '私聊与公共频道全关' },
];

export function KpBoard(): React.ReactElement {
  const [turnState, setTurnState] = React.useState<string>('IDLE');
  const [submitted, setSubmitted] = React.useState<Array<{ player_id: string; intent: string }>>([]);
  const [countdown, setCountdown] = React.useState(0);
  const [proposals, setProposals] = React.useState<Proposal[]>([]);
  const [narr, setNarr] = React.useState<NarrMsg[]>([]);
  const [events, setEvents] = React.useState<string[]>([]);
  const [lastRoll, setLastRoll] = React.useState<string>('尚未掷骰');
  const [editText, setEditText] = React.useState<Record<string, string>>({});
  const [error, setError] = React.useState('');
  const [acting, setActing] = React.useState<Record<string, boolean>>({});
  // UI-2 d9: 回合控制指令发送中的忙碌态（按钮禁用 + LoadingRow 反馈）。
  const [turnBusy, setTurnBusy] = React.useState(false);
  // UI-P2 d9: 最近事件流加载期骨架占位（短模拟 400ms 后出内容）。
  const [eventsLoading, setEventsLoading] = React.useState(true);
  // M3 (T6): 私聊四态调控（主持人）—— GET chat/status + POST chat/mode。
  const [chatMode, setChatMode] = React.useState<string>('');
  const [chatPlayers, setChatPlayers] = React.useState<Array<{ id: string; chat_state: string }>>([]);
  const [chatBusy, setChatBusy] = React.useState(false);
  const now = useNow();

  React.useEffect(() => {
    setEvents(transportSnapshot().events);
    window.setTimeout(() => setEventsLoading(false), 400);
    transport.connect();
    loadChatStatus();
    loadProposals();
    const off = transport.subscribe((frame) => {
      if (frame.kind === 'TURN_UPDATED') {
        setTurnState(frame.turn.state);
        setSubmitted(frame.turn.submitted.map((s) => ({ player_id: s.player_id, intent: s.intent ?? '' })));
        // 单位归一：服务端 ws_bridge._epoch 出的是**秒**，本组件的 useNow 是毫秒。
        // 混用会让 remain 恒为 0（秒被当毫秒）或恒等于一个巨大的负数被夹到 0。
        const ts = Number(frame.turn.countdown_end_ts) || 0;
        setCountdown(ts > 0 && ts < 1e11 ? ts * 1000 : ts);
      } else if (frame.kind === 'NARRATION_PENDING') {
        setProposals((prev) => (prev.some((p) => p.id === frame.proposal.id) ? prev : [...prev, { ...frame.proposal, intention: frame.proposal.intention ?? '', source: frame.proposal.source ?? 'agent' }]));
      } else if (frame.kind === 'NARRATION_APPROVED') {
        setNarr((prev) => [...prev, { id: frame.narration.id, text: frame.narration.text }]);
        setProposals((prev) => prev.filter((p) => p.id !== frame.narration.id));
      } else if (frame.kind === 'STATE_DELTA' && frame.delta.field === 'last_roll') {
        const v = frame.delta.value as { target: string; roll: number; seed: number; result: string };
        setLastRoll(`${v.target}：${v.roll}（${v.result}，种子 ${v.seed}）`);
      } else if (frame.kind === 'BRANCH_TAKEN') {
        setEvents((prev) => [`分支推进：${frame.branch.label}`, ...prev].slice(0, 8));
      }
    });
    return () => { off(); transport.close(); };
  }, []);

  const remain = Math.max(0, Math.ceil((countdown - now) / 1000));

  // 回合控制命令统一走忙碌态（d9）：发送瞬间禁用按钮并给 LoadingRow，600ms 后复位。
  // fakeFlushError: 忙碌态是本地临时标志（600ms 自动复位）；REST 失败时把真实错误交给 setKpError。
  const runTurnCmd = (fn: (flushErr: (msg: string) => void) => void): void => {
    setError(''); setConfirm(null); setTurnBusy(true);
    fn((msg: string) => setError(msg));
    window.setTimeout(() => setTurnBusy(false), 600);
  };
  // ★ 修复 1（开始回合死键）：real 模式真实写入 POST /access/host/turn —— 服务端落
  // TURN_STARTED -> ws_bridge 广播 TURN_UPDATED（本组件订阅后自动刷新相位）。
  // mock 模式沿用命令链（demo 不回归）。此前直接 transport.send(START_TURN) 在
  // real 下服务端只 ACK 不落业务 + socket 未 OPEN 时被静默丢弃 -> 恒 IDLE。
  const onStart = (): void => runTurnCmd((flushErr) => {
    const { campaign, token } = connParams();
    if (TRANSPORT_MODE === 'real') {
      if (!campaign || !token) { flushErr(REST_NEED_PARAMS); return; }
      void restStartTurn(campaign, token, 120, reqId()).then((res) => {
        if (!res.ok && res.status !== 200) {
          flushErr(`开始回合失败：${res.error}`);
          return;
        }
        // 乐观更新：REST 已 200（TURN_STARTED 落库）。即便 WS 广播因房间映射
        // 暂时未达，相位也应立即进 COLLECTING；广播到达后会用服务端权威值覆盖。
        const epoch = Number(res.data?.countdown_end_ts_epoch ?? res.data?.countdown_end_ts ?? 0);
        const endTs = epoch > 0 && epoch < 1e11 ? epoch * 1000 : epoch;
        setTurnState('COLLECTING');
        setSubmitted([]);
        if (endTs > 0) setCountdown(endTs);
        setEvents((prev) => [`回合状态：COLLECTING（第 ${String(res.data?.turn_no ?? 1)} 回合）`, ...prev].slice(0, 8));
        loadProposals();
      });
      return;
    }
    send({ kind: 'START_TURN', window_sec: 120 });
  });
  const onSettle = (): void => runTurnCmd((flushErr) => {
    const { campaign, token } = connParams();
    if (TRANSPORT_MODE === 'real') {
      if (!campaign || !token) { flushErr(REST_NEED_PARAMS); return; }
      // 结算掷骰 -> COMBAT_ROUND_PROPOSED（落库 => 进入「待批提案」，服务端同一条审批总线）。
      // 无 active combat 时后端 422 -> 文案直读；成功则组件在 STATE_DELTA/轮询下可见提案区。
      void restCombatRound(campaign, token, '', [{ actor: 'kp', action: '侦查' }]).then((res) => {
        if (!res.ok) {
          flushErr(`结算掷骰失败：${res.error}`);
          return;
        }
        const roundNo = Number(res.data?.round ?? 0);
        setEvents((prev) => [`结算掷骰：第 ${roundNo} 回合候选已进待批队列（${res.data?.status ?? 'pending_approval'}）`, ...prev].slice(0, 8));
        loadProposals();
      });
      return;
    }
    send({ kind: 'COMMAND', cmd: { type: 'roll_check', payload: { target: '侦查', seed: 7 } } });
  });
  // 破坏类二次确认：结束响应窗口会关闭提交（未提交行动的玩家需补交），先确认。
  const [confirm, setConfirm] = React.useState<null | { action: 'close' }>(null);
  const confirmYesRef = React.useRef<HTMLButtonElement | null>(null);
  const closeAskRef = React.useRef<HTMLButtonElement | null>(null);
  const confirmWasOpenRef = React.useRef(false);
  const dialogRef = React.useRef<HTMLDivElement | null>(null);
  // UI-2 d7 (UI1 P2 D7-3): 对话框焦点管理 —— 打开即聚焦「确认结束」，关闭恢复给触发按钮（仅曾打开后），Esc 关闭。
  React.useEffect(() => {
    if (confirm) {
      confirmWasOpenRef.current = true;
      confirmYesRef.current?.focus();
    } else if (confirmWasOpenRef.current) {
      confirmWasOpenRef.current = false;
      closeAskRef.current?.focus();
    }
  }, [confirm]);
  const onCloseAsk = (): void => { setError(''); setConfirm({ action: 'close' }); };
  const onCloseYes = (): void => runTurnCmd((flushErr) => {
    const { campaign, token } = connParams();
    if (TRANSPORT_MODE === 'real') {
      if (!campaign || !token) { flushErr(REST_NEED_PARAMS); return; }
      // 结束响应窗口 -> pipeline/resolve(close_window=true) 落 TURN_CLOSED + 产出待审候选。
      void restCloseWindow(campaign, token, null).then((res) => {
        if (!res.ok) {
          flushErr(`结束响应窗口失败：${res.error}`);
          return;
        }
        // 乐观更新：TURN_CLOSED 已落库 -> 相位进 CLOSING（服务端映射），
        // 待批提案区随后由 GET /approvals（或广播）填充。
        setTurnState('CLOSING');
        setEvents((prev) => [`回合状态：CLOSING（响应窗口已关闭）`, ...prev].slice(0, 8));
        loadProposals();
      });
      return;
    }
    send({ kind: 'CLOSE_WINDOW' });
  });
  // ★ 提案拍板（real）：走既有审批总线 POST /api/campaigns/{c}/approvals（真写
  // NARRATION_APPROVED/EDITED/REJECTED）；确定后 ws_bridge 广播 NARRATION_APPROVED
  // 帧 -> 本组件订阅自动从待批区移除并落入叙事流。mock 沿用命令链。
  const decide = (id: string, decision: 'approve' | 'edit' | 'reject', text?: string): void => {
    setActing((p) => ({ ...p, [id]: true }));
    const { campaign, token } = connParams();
    if (TRANSPORT_MODE === 'real') {
      if (!campaign || !token) { setError(REST_NEED_PARAMS); return; }
      void restApprove(campaign, token, id, decision, decision === 'edit' ? text : undefined, decision === 'reject' ? '主持人否决' : undefined)
        .then((res) => { if (!res.ok) setError(`提案处理失败：${res.error}`); else loadProposals(); })
        .finally(() => setActing((p) => ({ ...p, [id]: false })));
      return;
    }
    send({ kind: 'APPROVE_NARRATION', proposal_id: id, decision, edited_text: decision === 'edit' ? text : undefined });
    window.setTimeout(() => setActing((p) => ({ ...p, [id]: false })), 600);
  };
  const onApprove = (id: string): void => decide(id, 'approve');
  const onReject = (id: string): void => decide(id, 'reject');
  const onEdit = (id: string): void => {
    const text = (editText[id] ?? '').trim();
    if (!text) { setError('编辑内容不能为空，请先填写修改后的旁白。'); return; }
    setError('');
    decide(id, 'edit', text);
  };

  // M3 (T6): 拉取四态 + 玩家状态
  const loadChatStatus = (): void => {
    const { campaign, token } = connParams();
    if (!campaign || !token) return;
    fetch(`/api/campaigns/${encodeURIComponent(campaign)}/chat/status`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status))))
      .then((d) => {
        setChatMode(String(d.mode || 'chat_enabled'));
        setChatPlayers(Array.isArray(d.players) ? d.players : []);
        setError('');
      })
      .catch((e: unknown) => setError('拉取聊天状态失败：' + String((e as Error)?.message || e)));
  };

  // real 模式待批提案：GET /api/campaigns/{c}/approvals（app/web/pipeline_api.py:290，
  // 仅 webapp/KP token 可读）。这是「待批提案恒 0」的第二个根因：原实现只等 WS
  // NARRATION_PENDING 帧，而广播里的 proposal 是**脱敏标签**且不保证到达；这里以
  // 服务端待审队列为权威源，把可拍板的提案（含真实正文）填进提案区。
  const loadProposals = (): void => {
    const { campaign, token } = connParams();
    if (TRANSPORT_MODE !== 'real' || !campaign || !token) return;
    fetch(`/api/campaigns/${encodeURIComponent(campaign)}/approvals`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status))))
      .then((d: { pending?: Array<{ proposal_id: string; text?: string; label?: string; kind?: string; source?: string }> }) => {
        const pending = Array.isArray(d.pending) ? d.pending : [];
        setProposals(pending.map((it) => ({
          id: it.proposal_id,
          text: it.text || it.label || it.proposal_id,
          intention: it.kind || '',
          source: it.source || 'agent',
        })));
      })
      .catch(() => { /* 待批区拉取失败不阻塞回合控制（不弹错） */ });
  };

  // M3 (T6): 主持人切换四态
  const onSetChatMode = (mode: string): void => {
    const { campaign, token } = connParams();
    if (!campaign || !token) { setError('缺少连接参数（URL 需带 campaign 与 token）'); return; }
    setChatBusy(true);
    fetch(`/api/campaigns/${encodeURIComponent(campaign)}/chat/mode`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ mode, scope: 'campaign' }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status))))
      .then((d) => { setChatMode(String(d.mode || mode)); loadChatStatus(); setError(''); })
      .catch((e: unknown) => setError('切换聊天模式失败：' + String((e as Error)?.message || e)))
      .finally(() => setChatBusy(false));
  };

  return (
    <div className="space-y-4 pb-[env(safe-area-inset-bottom)]">
      {error ? <ErrorBanner message={error} onClose={() => setError('')} /> : null}
      <section className="panel" aria-label="回合控制">
        <h2 className="panel-title">回合控制 · {turnState}{turnState === 'COLLECTING' && countdown > 0 ? ` · 剩余 ${remain}s` : ''}</h2>
        <div className="flex flex-wrap gap-2">
          <button className="btn btn-primary w-full sm:w-auto" onClick={onStart} disabled={turnBusy || turnState === 'COLLECTING'} aria-busy={turnBusy} title={turnState === 'COLLECTING' ? '回合进行中：先结束响应窗口再开新回合' : '开始新回合：打开行动提交窗口'} aria-disabled={turnBusy || turnState === 'COLLECTING'}>{turnBusy ? '发送中…' : '开始回合'}</button>
          <button ref={closeAskRef} className="btn btn-secondary" onClick={onCloseAsk} disabled={turnBusy || turnState !== 'COLLECTING'} title={turnState !== 'COLLECTING' ? '当前无进行中回合：先点「开始回合」' : '关闭提交窗口后进入结算，未提交的玩家需补交'} aria-disabled={turnBusy || turnState !== 'COLLECTING'}>{turnBusy ? '发送中…' : '结束响应窗口'}</button>
          <button className="btn btn-secondary" onClick={onSettle} disabled={turnBusy || turnState !== 'RESOLVING'} title={turnState === 'RESOLVING' ? '结算掷骰：投一次侦查检定并结算本回合结果' : turnState === 'COLLECTING' ? '收集中：先「结束响应窗口」进入结算阶段，才能结算掷骰' : '待机中：先「开始回合」并「结束响应窗口」进入结算，才能掷骰'} aria-disabled={turnBusy || turnState !== 'RESOLVING'}>{turnBusy ? '发送中…' : '结算掷骰'}</button>
        </div>
        {turnState === 'COLLECTING' ? (
          <p className="mt-1 text-xs text-gray-500">收集中：可「结束响应窗口」进入结算；「开始回合」已禁用。</p>
        ) : (
          <p className="mt-1 text-xs text-gray-500">{turnState === 'RESOLVING' ? '结算中：响应窗口已关闭，可「结算掷骰」结算本回合；之后可开始新回合。' : '待机中：仅「开始回合」可用；「结束响应窗口」「结算掷骰」需进入对应阶段才会开放。'}</p>
        )}
        <div className="mt-2 min-h-[20px]" aria-live="polite" aria-atomic="true">
        {turnBusy ? <LoadingRow text="指令已发送：等待服务端确认…" /> : null}
        {confirm ? (
          <div ref={dialogRef} className="mt-2 rounded-md border border-gray-300 bg-gray-100 p-3 text-sm" role="alertdialog" aria-modal="true" aria-label="确认结束响应窗口" onKeyDown={(e) => {
            if (e.key === 'Escape') { setConfirm(null); return; }
            if (e.key !== 'Tab') return;
            // FZ-1: focus-trap —— Tab/Shift+Tab 循环约束在对话框内（确认结束/取消），
            // 焦点不在对话框内时 Tab 先拉回第一个可聚焦元素（无新依赖，useEffect 内联 keydown）。
            const el = dialogRef.current;
            if (!el) return;
            const focusables = Array.from(el.querySelectorAll<HTMLElement>(
              'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'));
            if (focusables.length === 0) return;
            const first = focusables[0];
            const last = focusables[focusables.length - 1];
            if (!el.contains(document.activeElement)) {
              e.preventDefault();
              first.focus();
              return;
            }
            if (e.shiftKey && document.activeElement === first) {
              e.preventDefault();
              last.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
              e.preventDefault();
              first.focus();
            }
          }}>
            <p>确定结束响应窗口？未提交行动的玩家将进入补交流程（LATE），可在下一窗口补交。</p>
            <div className="mt-2 flex gap-2">
              <button ref={confirmYesRef} className="btn btn-danger" onClick={onCloseYes} aria-label="确认结束">确认结束</button>
              <button className="btn btn-secondary" onClick={() => setConfirm(null)} aria-label="取消">取消</button>
            </div>
          </div>
        ) : null}
        <p className="mt-2 text-xs text-gray-600">已提交 {submitted.length}/2 · 数据经传输层单一入口收发</p>
        </div>
      </section>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <section className="panel min-w-0 md:col-span-2" aria-label="叙事流">
          <h2 className="panel-title">叙事流</h2>
          {narr.length === 0 ? <EmptyState text="暂无已批准旁白 —— 批准一条提案后会显示在这里（当前等待主持人开始回合）。" /> : (
            <ul className="space-y-2">
              {narr.map((n) => (<li key={n.id} className="rounded-md bg-gray-100 p-3 text-sm leading-6">{n.text}</li>))}
            </ul>
          )}
        </section>
        <section className="panel min-w-0" aria-label="角色表">
          <h2 className="panel-title">角色表侧栏</h2>
          <ul className="space-y-2 text-sm text-gray-800">
            <li className="rounded bg-gray-100 p-2">林墨 · 侦探 · HP 11/12 <span className="chip ml-1 border-gray-400 text-gray-800">已提交</span></li>
            <li className="rounded bg-gray-100 p-2">苏芮 · 记者 · HP 9/10 <span className="chip ml-1 border-gray-300 text-gray-700">待提交</span></li>
          </ul>
          <div className="mt-3 rounded bg-gray-100 p-2 text-xs text-gray-600">延迟条：单轮语音耗时约 1.2s / 目标 ≤1.6s（演示数据）</div>
        </section>
      </div>

      <section className="panel" aria-label="待批提案">
        <h2 className="panel-title">待批提案（{proposals.length} 条待处理）</h2>
        {proposals.length === 0 ? <EmptyState text="暂无待批提案（等待主持人开始回合推送）。" /> : (
          <ul className="space-y-3">
            {proposals.map((p) => (
              <li key={p.id} className="rounded-md border border-gray-300 bg-gray-100 p-3">
                <p className="text-sm leading-6">{p.text}</p>
                <p className="mt-1 text-xs text-gray-600">意图：{p.intention} · 来源：{p.source === 'agent' ? 'AI 起草' : p.source}</p>
                <input className="input mt-2" placeholder="编辑后的旁白（可选，用于批准并编辑）" value={editText[p.id] ?? ''} onChange={(e) => setEditText((prev) => ({ ...prev, [p.id]: e.target.value }))} aria-label={`编辑提案 ${p.id}`} />
                <div className="mt-2 flex flex-wrap gap-2">
                  <button className="btn btn-primary" onClick={() => onApprove(p.id)} disabled={!!acting[p.id]} aria-busy={!!acting[p.id]}>{acting[p.id] ? '处理中…' : '批准'}</button>
                  <button className="btn btn-secondary" onClick={() => onEdit(p.id)} disabled={!!acting[p.id]}>批准并采用编辑</button>
                  <button className="btn btn-danger" onClick={() => onReject(p.id)} disabled={!!acting[p.id]}>{acting[p.id] ? '处理中…' : '否决'}</button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <section className="panel min-w-0" aria-label="最近事件">
          <h2 className="panel-title">最近事件</h2>
          {eventsLoading ? <SkeletonRows rows={3} label="最近事件加载中" /> : events.length === 0 ? <EmptyState text="暂无事件 —— 开局（开始回合/分支推进）后事件流会显示在这里。" /> : (
          <ul className="space-y-1 text-sm text-gray-600" aria-live="polite" aria-atomic="true">{events.map((e, i) => (<li key={i}>· {e}</li>))}</ul>
          )}
        </section>
        <section className="panel min-w-0" aria-label="最近掷骰">
          <h2 className="panel-title">最近掷骰</h2>
          <p className="text-sm">{lastRoll}</p>
        </section>
      </div>

      <section className="panel" aria-label="私聊调控">
        <h2 className="panel-title">私聊调控（主持人） · 当前：{(CHAT_MODES.find((m) => m.value === chatMode)?.label) ?? (chatMode || '未知')}</h2>
        <p className="mt-1 text-xs text-gray-600">四态为服务端权威门控：私聊/公共频道按此放行。切换后玩家端徽标与输入框实时更新。</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {CHAT_MODES.map((m) => (
            <button
              key={m.value}
              className={'btn ' + (m.value === chatMode ? 'btn-primary' : 'btn-secondary')}
              onClick={() => onSetChatMode(m.value)}
              disabled={chatBusy}
              aria-busy={chatBusy}
              title={m.hint}
            >
              {m.label}
            </button>
          ))}
        </div>
        <p className="mt-2 text-xs text-gray-500">
          {chatPlayers.length
            ? '玩家：' + chatPlayers.map((p) => p.id + '（' + p.chat_state + '）').join('、')
            : '（暂无已建卡/已落位玩家）'}
        </p>
      </section>
    </div>
  );
}