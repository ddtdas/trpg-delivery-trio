import * as React from 'react';
import { loadSceneInfo, sceneTitle } from '../lib/sceneNames';

/**
 * R5 —— 主持人单窗口总览（六类信息块）。
 *
 * 判据（R5 原文）：① 地图总览 ② 玩家位置/状态 ③ 当前回合与已提交行动
 *                  ④ 待审队列 ⑤ 事件/线索 ⑥ NPC 状态
 *                  **1920×1080 与 1366×768 首屏无滚动、无重叠**。
 *
 * 数据源：服务端装配的权威总览 `GET /api/campaigns/{c}/overview`（与 R4 同一套 grounding）。
 * 连接参数（campaign / token）**直接取自本页 URL**（主持端本来就是带参加载的），
 * 因此本组件**不依赖 transport 内部实现**，也就不必改动 t11 的传输层核心文件。
 *
 * 布局要点（"无滚动/无重叠"由布局保证，而非靠内容少）：
 *   * 外层高度钉死视口，六块用 CSS Grid 固定 3×2；
 *   * 每块内部各自 `overflow:auto` ⇒ **页面本身不产生纵向滚动**，内容溢出被约束在块内；
 *   * 子项 `min-h-0` —— grid/flex 子项默认 `min-height:auto` 会撑破容器，**这正是"重叠"的常见成因**；
 *   * 每块带 `data-r5-block`，断连带 `data-r5-degraded` ⇒ **tester 可用 DOM 断言六块齐全**，不必依赖截图。
 */

type OverviewPayload = {
  campaign_id: string;
  blocks: {
    map: { map_id: string; rooms: string[]; tokens: Record<string, string>; fog: string[]; maps_count: number };
    players: Array<{ player_id: string; name: string; occupation?: string; status: string; room_id: string; source?: string }>;
    turn: null | { turn_no: number; state: string; submitted_count: number; submitted: Array<{ player_id: string; intent: string }>; order: string[] };
    approvals: { pending_count: number; pending: Array<{ proposal_id: string; text: string; source: string }> };
    events: { recent: Array<{ seq: number; type: string }>; clues: unknown[]; infos: unknown[]; tip: number };
    npcs: { count: number; npcs: Array<{ npc_id: string; line: string }> };
  };
  counts: { players: number; pending: number; clues: number; npcs: number; events: number };
};

/** 从本页 URL 取连接参数（主持端带参加载：?campaign=...&token=...&role=kp）。 */
function connParams(): { campaign: string; token: string } {
  const q = new URLSearchParams(window.location.search);
  return { campaign: q.get('campaign') || '', token: q.get('token') || '' };
}

function Block({ title, badge, children }: { title: string; badge?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="flex min-h-0 flex-col rounded border border-gray-200 bg-white" data-r5-block={title}>
      <header className="flex shrink-0 items-center justify-between border-b border-gray-200 px-3 py-1.5">
        <h2 className="text-sm font-semibold text-gray-800">{title}</h2>
        {badge}
      </header>
      <div className="min-h-0 flex-1 overflow-auto px-3 py-2 text-xs text-gray-700">{children}</div>
    </section>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="text-gray-400">{text}</p>;
}

export default function Overview() {
  const [data, setData] = React.useState<OverviewPayload | null>(null);
  const [err, setErr] = React.useState<string>('');
  const [ts, setTs] = React.useState<string>('');
  // T16.3: 当前场景名（单一事实源：scenes API / event_graph）。
  const [scene, setScene] = React.useState<{ currentId: string; currentTitle: string; byId: Record<string, string> }>({ currentId: '', currentTitle: '', byId: {} });

  const load = React.useCallback(async () => {
    const { campaign, token } = connParams();
    if (!campaign || !token) {
      setErr('缺少连接参数（URL 需带 campaign 与 token）');
      return;
    }
    try {
      const res = await fetch(`/api/campaigns/${encodeURIComponent(campaign)}/overview`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData((await res.json()) as OverviewPayload);
      setErr('');
      setTs(new Date().toLocaleTimeString());
    } catch (e: any) {
      setErr(String(e?.message || e));
    }
  }, []);

  React.useEffect(() => {
    void load();
    const t = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(t);
  }, [load]);

  // T16.3: 场景名与轮询同源（scenes API），供页头「当前场景」显示。
  const { campaign } = connParams();
  React.useEffect(() => {
    if (!campaign) return undefined;
    let alive = true;
    const pull = (): void => {
      void loadSceneInfo(campaign).then((info) => {
        if (!alive) return;
        setScene({ currentId: info.currentId, currentTitle: info.currentTitle || sceneTitle(info.byId, info.currentId), byId: info.byId });
      });
    };
    pull();
    const t = window.setInterval(pull, 8000);
    return () => { alive = false; window.clearInterval(t); };
  }, [campaign]);

  const b = data?.blocks;

  return (
    <div className="flex h-[calc(100vh-9rem)] min-h-0 flex-col gap-2" data-r5-overview="1">
      <div className="flex shrink-0 items-center justify-between">
        <h1 className="text-lg font-bold text-gray-900">主持人总览</h1>
        <span className="chip border-gray-300 text-gray-700" data-r5-scene={scene.currentId} title="场景名单一事实源：GET /api/campaigns/{c}/scenes">当前场景：{scene.currentTitle || '未同步'}</span>
        <span className="text-xs text-gray-500">
          {err
            ? <span className="text-red-600" data-r5-degraded="1">总览不可用：{err}</span>
            : `更新于 ${ts}`}
        </span>
      </div>

      {!data && !err ? <p className="text-sm text-gray-500">加载中…</p> : null}

      {data && b ? (
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-2 md:grid-cols-3 md:grid-rows-2">
          <Block title="① 地图总览" badge={<span className="text-xs text-gray-500">{b.map.maps_count} 张</span>}>
            {b.map.map_id ? (
              <ul className="space-y-1">
                <li>地图：<b>{sceneTitle(scene.byId, b.map.map_id) || b.map.map_id}</b>{sceneTitle(scene.byId, b.map.map_id) ? '' : '（' + b.map.map_id + '）'}</li>
                <li>房间（{b.map.rooms.length}）：{(b.map.rooms.map((r) => sceneTitle(scene.byId, r) || r).join('、')) || '—'}</li>
                <li>棋子（{Object.keys(b.map.tokens).length}）：{Object.entries(b.map.tokens).map(([k, v]) => `${k}→${v}`).join('，') || '—'}</li>
                <li>迷雾格：{b.map.fog.length}</li>
              </ul>
            ) : <Empty text="本战役尚未载入地图" />}
          </Block>

          <Block title="② 玩家位置/状态" badge={<span className="text-xs text-gray-500">{b.players.length} 人</span>}>
            {b.players.length ? (
              <table className="w-full">
                <tbody>
                  {b.players.map((p) => (
                    <tr key={p.player_id} className="border-b border-gray-100 last:border-0">
                      <td className="py-0.5 pr-2 font-medium">{p.name}</td>
                      <td className="py-0.5 pr-2 text-gray-500">{p.room_id || '未落位'}</td>
                      <td className="py-0.5 text-right text-gray-500">{p.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <Empty text="本战役暂无玩家" />}
          </Block>

          <Block title="③ 回合与已提交行动" badge={b.turn ? <span className="text-xs text-gray-500">{b.turn.state}</span> : undefined}>
            {b.turn ? (
              <div className="space-y-1">
                <div>第 <b>{b.turn.turn_no}</b> 回合 · 已提交 <b>{b.turn.submitted_count}</b>/{b.turn.order.length || '?'}</div>
                {b.turn.submitted.length
                  ? <ul className="space-y-0.5">{b.turn.submitted.map((s) => (
                      <li key={s.player_id}><span className="font-medium">{s.player_id}</span>：{s.intent || '（未填意图）'}</li>
                    ))}</ul>
                  : <Empty text="尚无玩家提交行动" />}
              </div>
            ) : <Empty text="当前无进行中的回合窗口" />}
          </Block>

          <Block title="④ 待审队列" badge={<span className="text-xs text-gray-500">{b.approvals.pending_count} 条</span>}>
            {b.approvals.pending.length ? (
              <ul className="space-y-1">
                {b.approvals.pending.map((a) => (
                  <li key={a.proposal_id} className="rounded bg-amber-50 px-1.5 py-0.5">{a.text}</li>
                ))}
              </ul>
            ) : <Empty text="无待审项" />}
          </Block>

          <Block title="⑤ 事件与线索" badge={<span className="text-xs text-gray-500">游标 {b.events.tip}</span>}>
            <div className="space-y-1">
              <div>线索 {b.events.clues.length} · 情报 {b.events.infos.length}</div>
              {b.events.recent.length
                ? <ul className="space-y-0.5">{b.events.recent.slice(-8).reverse().map((e) => (
                    <li key={e.seq} className="text-gray-600">#{e.seq} {e.type}</li>
                  ))}</ul>
                : <Empty text="暂无事件" />}
            </div>
          </Block>

          <Block title="⑥ NPC 状态" badge={<span className="text-xs text-gray-500">{b.npcs.count} 个</span>}>
            {b.npcs.npcs.length ? (
              <ul className="space-y-1">
                {b.npcs.npcs.map((n) => (
                  <li key={n.npc_id}><span className="font-medium">{n.npc_id}</span>：{n.line || '（无台词）'}</li>
                ))}
              </ul>
            ) : <Empty text="本战役暂无 NPC 台词" />}
          </Block>
        </div>
      ) : null}
    </div>
  );
}