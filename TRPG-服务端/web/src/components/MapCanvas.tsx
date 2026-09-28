import React from 'react';
import { Circle, Group, Layer, Rect, Stage, Text } from 'react-konva';
import type { KonvaEventObject } from 'konva/lib/Node';
import { restConnParams, transport } from '../lib/transport';
import { ensureMapSubscription, ensureSceneNames, demoPending, mapSend, useMapStore, type MapOpKind, type MapToken, type TokenStatus } from '../store/map';
import { ErrorBanner, LoadingRow } from './ui';
// UI-R2: 灰白黑令牌适配（仅视觉）

const GRID = 20;
const W = 600;
const H = 380;

const ROOMS = [
  { id: 'r_lobby', name: '前厅/前台', x: 20, y: 20, w: 200, h: 140 },
  { id: 'r_reading', name: '阅览区', x: 240, y: 20, w: 320, h: 140 },
  { id: 'r_rare', name: '古籍室', x: 240, y: 180, w: 200, h: 160 },
  { id: 'r_secret', name: '密室（暗门后）', x: 460, y: 180, w: 100, h: 160 },
  { id: 'r_corridor', name: '走廊', x: 20, y: 180, w: 200, h: 160 },
];
const DOORS = [
  { id: 'd1', x: 230, y: 90 }, { id: 'd2', x: 340, y: 170 },
  { id: 'd3', x: 230, y: 260 }, { id: 'd_secret', x: 450, y: 260 },
];

/** token 全名（单字 label 之外的完整身份，用于画布标签与选中详情面板）。 */
const FULL_NAMES: Record<string, string> = { linmo: '林墨', surui: '苏芮', npc_clerk: 'NPC·图书管理员' };
function tokenDisplayName(t: Pick<MapToken, 'id' | 'label'>): string { return FULL_NAMES[t.id] ?? t.label; }

/** 锁房原因（玩家侧 why-locked + 下一步；R2/D4）。 */
const LOCK_REASONS: Record<string, string> = {
  r_secret: '暗门剧情未触发：密室在暗门开启前保持遮蔽',
  r_rare: '古籍室馆藏未开放：需主持人批准后揭示',
  r_lobby: '主持人设定遮蔽（暂未开放）',
  r_reading: '主持人设定遮蔽（暂未开放）',
  r_corridor: '主持人设定遮蔽（暂未开放）',
};
const LOCK_SHORT: Record<string, string> = { r_secret: '暗门未开', r_rare: '馆藏未开放' };
function roomName(id: string): string { return ROOMS.find((r) => r.id === id)?.name ?? id; }
function statusLabel(s: TokenStatus): string {
  return s === 'pending' ? '等待裁决' : s === 'rejected' ? '被拒绝回滚' : '已落位';
}

function snap(v: number): number { return Math.round(v / GRID) * GRID; }
function roomAt(x: number, y: number): string {
  const r = ROOMS.find((r_) => x >= r_.x && x <= r_.x + r_.w && y >= r_.y && y <= r_.y + r_.h);
  return r ? r.id : 'unknown';
}

/** 键盘/触屏替代操作：选 token + 数字坐标 → 同一路 move 命令（网格对齐复用）。 */
function MoveByCoord(): React.ReactElement {
  const tokens = useMapStore((s) => s.tokens);
  const set = useMapStore((s) => s.set);
  const [id, setId] = React.useState('linmo');
  const [x, setX] = React.useState('300');
  const [y, setY] = React.useState('80');
  const go = (): void => {
    const nx = snap(Math.max(0, Math.min(W, Number(x) || 0)));
    const ny = snap(Math.max(0, Math.min(H, Number(y) || 0)));
    set({
      tokens: tokens.map((t) => (t.id === id ? { ...t, status: 'pending' as const } : t)),
      pendingOp: { op: 'move', target: id, note: `键盘落位 (${nx}, ${ny}) · 等待裁决` },
      error: '',
    });
    void mapSend('move', id, { x: nx, y: ny, room: roomAt(nx, ny) });
  };
  return (
    <div className="flex flex-wrap items-center gap-2">
      <select className="input max-w-[140px]" value={id} onChange={(e) => setId(e.target.value)} aria-label="选择 token">
        {tokens.map((t) => (<option key={t.id} value={t.id}>{t.label}·{t.id}</option>))}
      </select>
      <label className="text-gray-700">X<input className="input ml-1 w-20" inputMode="numeric" value={x} onChange={(e) => setX(e.target.value)} aria-label="目标 X 坐标" /></label>
      <label className="text-gray-700">Y<input className="input ml-1 w-20" inputMode="numeric" value={y} onChange={(e) => setY(e.target.value)} aria-label="目标 Y 坐标" /></label>
      <button className="btn btn-secondary px-3 py-1 text-xs" onClick={go}>回车落位</button>
    </div>
  );
}

/** MapCanvas：Konva 地图交互（拖拽→move 命令→审批→落位/回滚；迷雾；缩放平移）。 */
export function MapCanvas(): React.ReactElement {
  const tokens = useMapStore((s) => s.tokens);
  const fog = useMapStore((s) => s.fog);
  const pendingOp = useMapStore((s) => s.pendingOp);
  const error = useMapStore((s) => s.error);
  const log = useMapStore((s) => s.log);
  const set = useMapStore((s) => s.set);
  const selectedId = useMapStore((s) => s.selectedId);
  // T16.3: 场景名统一取 store（scenes API / event_graph 单一事实源）。
  const sceneTitleText = useMapStore((s) => s.sceneTitle);
  const [scale, setScale] = React.useState(1);
  const [pos, setPos] = React.useState({ x: 0, y: 0 });
  const [newName, setNewName] = React.useState('阿强');
  const [approved, setApproved] = React.useState(true);
  const [asPlayer, setAsPlayer] = React.useState(false);
  const [mapLoading, setMapLoading] = React.useState(true);

  // 同格簇（R1）：玩家视角下只对可见 token 计簇；28px 内同 room 视为堆叠。
  const visibleTokens = React.useMemo(
    () => tokens.filter((t) => !(asPlayer && fog[t.room])),
    [tokens, asPlayer, fog],
  );
  const clusterOf = React.useMemo(() => {
    const m = new Map<string, MapToken[]>();
    for (const t of visibleTokens) {
      m.set(t.id, visibleTokens.filter((o) => o.room === t.room && Math.hypot(o.x - t.x, o.y - t.y) < 28));
    }
    return m;
  }, [visibleTokens]);
  const lockedRooms = ROOMS.filter((r) => fog[r.id]);

  // 首屏重排：初始缩放适配视口（容器 <560px 时 0.85，否则 1）。
  React.useEffect(() => {
    ensureMapSubscription();
    transport.connect();
    // T16.3: 拉取场景名（scenes API → event_graph 标题），替换原硬编码地图标题。
    void ensureSceneNames(restConnParams().campaign);
    const fit = (): void => {
      const w = typeof window !== 'undefined' ? window.innerWidth : 1280;
      setScale(w < 560 ? 0.85 : 1);
    };
    fit();
    window.addEventListener('resize', fit);
    const t = window.setTimeout(() => setMapLoading(false), 600);
    return () => { window.removeEventListener('resize', fit); window.clearTimeout(t); };
  }, []);

  /** 纯键盘移动选中棋子（方向键步进一格，Enter 落位，Delete 回起点）。 */
  const moveSelected = React.useCallback((dx: number, dy: number, commit: boolean): void => {
    const st = useMapStore.getState();
    const t = st.tokens.find((k) => k.id === st.selectedId) ?? st.tokens[0];
    if (!t) return;
    const nx = snap(Math.max(0, Math.min(W, t.x + dx)));
    const ny = snap(Math.max(0, Math.min(H, t.y + dy)));
    if (commit) {
      st.set({
        tokens: st.tokens.map((k) => (k.id === t.id ? { ...k, status: 'pending' as const } : k)),
        pendingOp: { op: 'move', target: t.id, note: `键盘落位 (${nx}, ${ny}) · 等待裁决` },
        error: '',
      });
      void mapSend('move', t.id, { x: nx, y: ny, room: roomAt(nx, ny) });
    } else {
      st.set({
        tokens: st.tokens.map((k) => (k.id === t.id ? { ...k, x: nx, y: ny, room: roomAt(nx, ny) } : k)),
      });
    }
  }, []);

  const onDragEnd = (id: string) => (e: KonvaEventObject<DragEvent>) => {
    const nx = snap(e.target.x() + 14);
    const ny = snap(e.target.y() + 14);
    // 乐观 pending 态：等下行裁决再落位/回滚。
    set({
      tokens: useMapStore.getState().tokens.map((t) => (t.id === id ? { ...t, status: 'pending' as const } : t)),
      pendingOp: { op: 'move', target: id, note: `移动到 (${nx}, ${ny}) · 等待裁决` },
      error: '',
    });
    void mapSend('move', id, { x: nx, y: ny, room: roomAt(nx, ny) });
  };

  // ★ 修复 2（放置死键）：real 模式 mapSend 走 POST /api/campaigns/{c}/map 真实落
  // MAP_UPDATED，成功后本地结算（新棋子立即上画布 + 命令日志）。mock 走命令链不变。
  const onAdd = (): void => {
    const name = newName.trim();
    if (!name) { set({ error: '新增 token 需要填写名字。' }); return; }
    const id = `t_${Date.now().toString(36)}`;
    set({ pendingOp: { op: 'add_token', target: id, note: `新增 ${name} · 写入中` }, error: '' });
    void mapSend('add_token', id, { label: name.slice(0, 1), x: 60, y: 200, room: 'r_corridor' });
    setNewName('');
  };

  // ★ 修复 3（迷雾死键）：approved 必须放**命令顶层**（后端 MapCommand.approved 只认顶层，
  // 塞在 delta 里后端读不到 -> 403/永不生效）。real 模式 REST 落 MAP_UPDATED 并本地结算。
  const onFog = (room: string): void => {
    const next = !(fog[room] ?? false);
    set({
      pendingOp: { op: 'set_fog', target: room, note: `${room} → ${next ? '遮蔽' : '揭示'} · ${approved ? '主持人批准（直接生效）' : '未附批准（演示拒绝）'}` },
      error: '',
    });
    void mapSend('set_fog', room, { fog: next }, { approved });
  };

  const opLabel: Record<MapOpKind, string> = { move: '移动', add_token: '新增', set_fog: '迷雾', set_status: '状态', set_light: '光照' };

  return (
    <div className="space-y-4">
      {error ? <ErrorBanner message={error} onClose={() => set({ error: '' })} /> : null}
      <section className="panel max-w-full overflow-hidden" aria-label="地图画布">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <h2 className="panel-title mb-0">地图 · {sceneTitleText || '当前场景'}</h2>
          <span className="chip text-gray-600">网格 {GRID}px 对齐 · 拖拽棋子或用键盘方向键移动，回车落位</span>
        </div>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <button className="chip border-gray-400 text-gray-600" onClick={() => demoPending('linmo')} aria-label="演示移动审批流程">演示：移动林墨（审批中→落位）</button>
          <details className="mt-1 text-xs text-gray-600">
            <summary className="cursor-pointer">图例：蓝色=已落位棋子 · 黄色=选中/等待裁决 · 红色=被拒绝回滚 · 紫方块=门 · 灰色罩=迷雾 · 圆点右上角 +N=同格堆叠棋子数</summary>
            <p className="mt-1">点棋子选中 → 方向键步进 → 回车发出移动命令；迷雾中的棋子玩家视角不可见。</p>
          </details>
        </div>
        <div className="mb-2 min-h-[28px]" aria-live="polite">
          {pendingOp ? <span className="chip border-gray-300 text-gray-800">审批中：{opLabel[pendingOp.op]} {pendingOp.target}</span> : <span className="text-xs text-gray-600">空闲：无在途命令</span>}
        </div>
        {mapLoading ? (
          <div className="mb-2"><LoadingRow text="地图加载中…（读取房间与棋子）" /></div>
        ) : null}
        <div className="max-w-full overflow-auto rounded-md border border-gray-300 bg-gray-100">
        <Stage
          width={W} height={H} scaleX={scale} scaleY={scale} x={pos.x} y={pos.y}
          draggable
          onDragEnd={(e: KonvaEventObject<DragEvent>) => { if (e.target === e.target.getStage()) { setPos({ x: e.target.x(), y: e.target.y() }); } }}
          className="rounded-md border border-gray-300 bg-gray-100"
          tabIndex={0}
          aria-label="地图画布：方向键移动选中棋子，回车落位，Delete 回起点"
          onKeyDown={(e: React.KeyboardEvent) => {
            if (e.key === 'ArrowUp') { e.preventDefault(); moveSelected(0, -GRID, false); }
            else if (e.key === 'ArrowDown') { e.preventDefault(); moveSelected(0, GRID, false); }
            else if (e.key === 'ArrowLeft') { e.preventDefault(); moveSelected(-GRID, 0, false); }
            else if (e.key === 'ArrowRight') { e.preventDefault(); moveSelected(GRID, 0, false); }
            else if (e.key === 'Enter') { e.preventDefault(); moveSelected(0, 0, true); }
          }}
        >
          <Layer>
            {ROOMS.map((r) => (
              <Group key={r.id}>
                <Rect x={r.x} y={r.y} width={r.w} height={r.h} fill="#1e293b" stroke="#475569" strokeWidth={1.5} cornerRadius={4} />
                <Text x={r.x + 8} y={r.y + 6} text={r.name} fontSize={13} fill="#cbd5e1" />
                {fog[r.id] ? <Rect x={r.x} y={r.y} width={r.w} height={r.h} fill="#020617" opacity={asPlayer ? 0.92 : 0.55} cornerRadius={4} /> : null}
                {fog[r.id] ? <Text x={r.x + 8} y={r.y + r.h - 22} text={asPlayer ? `🔒 已锁定：${LOCK_SHORT[r.id] ?? '主持人遮蔽'}（可向主持人请求揭示）` : '迷雾（主持人可见）'} fontSize={11} fill="#f59e0b" /> : null}
              </Group>
            ))}
            {DOORS.map((d) => (
              <Group key={d.id}>
                <Rect x={d.x - 6} y={d.y - 6} width={12} height={12} fill="#a78bfa" cornerRadius={2} />
              </Group>
            ))}
            {[...visibleTokens]
              .sort((a, b) => (a.id === selectedId ? 1 : 0) - (b.id === selectedId ? 1 : 0))
              .map((t) => {
                const selected = t.id === selectedId;
                const grp = clusterOf.get(t.id) ?? [t];
                const stackIdx = grp.findIndex((o) => o.id === t.id);
                const clusterSize = grp.length;
                // 同格堆叠：显示层向右下方错开，命中目标分离（坐标语义不变，拖拽按真实坐标网格对齐）。
                const fan = stackIdx * 14;
                const name = tokenDisplayName(t);
                const tagW = name.length * 10 + 8;
                return (
                  <Group key={t.id} x={t.x - 14} y={t.y - 14} draggable
                    onDragEnd={onDragEnd(t.id)}
                    onClick={() => set({ selectedId: t.id })}
                    onTap={() => set({ selectedId: t.id })}
                    opacity={t.status === 'pending' ? 0.6 : 1}
                  >
                    <Group x={fan} y={fan}>
                      <Circle width={28} height={28} fill={t.status === 'rejected' ? '#ef4444' : t.status === 'pending' ? '#f59e0b' : selected ? '#f59e0b' : '#0ea5e9'} stroke={selected ? '#fcd34d' : '#e2e8f0'} strokeWidth={selected ? 3 : 1.5} />
                      <Text text={t.label} fontSize={14} fill="#fff" width={28} height={28} align="center" verticalAlign="middle" />
                      {clusterSize > 1 && stackIdx === 0 ? (
                        <Group x={16} y={-11}>
                          <Rect width={20} height={14} fill="#0f172a" stroke="#fcd34d" strokeWidth={1} cornerRadius={7} />
                          <Text text={`+${clusterSize - 1}`} fontSize={9} fill="#fcd34d" width={20} height={14} align="center" verticalAlign="middle" />
                        </Group>
                      ) : null}
                      <Group y={30 + stackIdx * 13}>
                        <Rect x={-tagW / 2} width={tagW} height={13} fill="#0f172a" opacity={0.92} stroke={selected ? '#fcd34d' : '#64748b'} strokeWidth={1} cornerRadius={3} />
                        <Text text={name} fontSize={9} fill={selected ? '#fcd34d' : '#e2e8f0'} width={tagW} height={13} align="center" verticalAlign="middle" />
                      </Group>
                    </Group>
                  </Group>
                );
              })}
          </Layer>
        </Stage>
        </div>
        {(() => {
          const sel = tokens.find((t) => t.id === selectedId);
          if (!sel) {
            return <p className="mt-1 text-xs text-gray-500" role="status">未选中棋子 —— 点击地图上的棋子查看详情与操作。</p>;
          }
          const hidden = asPlayer && fog[sel.room];
          const grp = clusterOf.get(sel.id) ?? [sel];
          const gi = grp.findIndex((g) => g.id === sel.id);
          return (
            <div className="mt-2 rounded-md border border-gray-200 bg-white px-3 py-2 text-xs text-gray-700" role="status" aria-label="选中棋子详情">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                <span>棋子：<b className="text-gray-800">{tokenDisplayName(sel)}</b>（{sel.id}）</span>
                <span>房间：{roomName(sel.room)}</span>
                <span>坐标：（{sel.x}, {sel.y}）</span>
                {hidden ? (
                  <span className="text-gray-500">当前位于迷雾区域（玩家视角不可见）</span>
                ) : (
                  <span className={sel.status === 'rejected' ? 'text-red-700' : sel.status === 'pending' ? 'text-gray-800' : 'text-gray-800'}>{statusLabel(sel.status)}</span>
                )}
                {!hidden && grp.length > 1 ? (
                  <button
                    className="btn btn-secondary px-2 py-0.5 text-[11px]"
                    onClick={() => { const next = grp[(gi + 1) % grp.length]; set({ selectedId: next.id }); }}
                    aria-label="切换同格棋子"
                  >同格共 {grp.length} 个 · 切换下一个</button>
                ) : null}
              </div>
              <p className="mt-1 text-gray-500">方向键步进、回车落位、Delete 回起点；拖拽棋子发起移动命令（主持人批准后落位）。</p>
            </div>
          );
        })()}
        <p className="mt-1 flex items-center gap-2 text-xs text-gray-700">缩放
          <button className="btn btn-secondary min-h-[36px] px-2 py-0.5" onClick={() => setScale((s) => Math.max(0.5, +(s - 0.1).toFixed(2)))} aria-label="缩小地图">−</button>
          <input type="range" min={50} max={150} value={Math.round(scale * 100)} onChange={(e) => setScale(Number(e.target.value) / 100)} className="accent-gray-900" aria-label="地图缩放" />
          <button className="btn btn-secondary min-h-[36px] px-2 py-0.5" onClick={() => setScale((s) => Math.min(1.5, +(s + 0.1).toFixed(2)))} aria-label="放大地图">＋</button>
          <button className="btn btn-secondary min-h-[36px] px-2 py-0.5" onClick={() => { setScale(1); setPos({ x: 0, y: 0 }); }} aria-label="重置视图">重置</button>
          <span aria-live="polite">{Math.round(scale * 100)}%</span> · 拖背景平移 · 落位坐标自动网格对齐</p>
      </section>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <section className="panel min-w-0" aria-label="新增 token">
          <h2 className="panel-title">新增棋子</h2>
          <div className="flex flex-wrap gap-2">
            <input className="input" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="名字，如：阿强" aria-label="新 token 名字" />
            <button className="btn btn-secondary shrink-0" onClick={onAdd}>放置</button>
          </div>
          <details className="mt-2 rounded bg-gray-100 p-2 text-xs text-gray-500">
            <summary className="cursor-pointer text-gray-600">键盘/触屏替代：输入坐标落位（无需拖拽）</summary>
            <MoveByCoord />
          </details>
        </section>
        <section className="panel min-w-0" aria-label="迷雾控制">
          <h2 className="panel-title">迷雾（需主持人批准）</h2>
          <label className="mb-2 flex items-center gap-2 text-xs text-gray-500">
            <input type="checkbox" checked={approved} onChange={(e) => setApproved(e.target.checked)} className="accent-gray-900" /> 附带主持人批准（关掉可演示“拒绝回滚”）
          </label>
          <div className="flex flex-wrap gap-2">
            {ROOMS.map((r) => (
              <button key={r.id} className="btn btn-secondary px-2 py-1 text-xs" onClick={() => onFog(r.id)} aria-label={`切换${r.name}迷雾`} title={r.id === 'r_secret' ? '密室默认遮蔽：暗门剧情未触发前保持遮蔽，主持人可手动揭示' : `${r.name}：点击切换遮蔽/揭示，主持人批准后生效`}>
                {r.name}：{fog[r.id] ? '遮蔽' : '揭示'}
              </button>
            ))}
          </div>
          <p className="mt-1 text-xs text-gray-600">迷雾说明：密室默认遮蔽（暗门未开）；切换后走主持人批准链，拒绝会自动回滚。</p>
          <div className="mt-2 space-y-1 text-[11px] leading-4 text-gray-500" aria-live="polite">
            {lockedRooms.length > 0 ? lockedRooms.map((r) => (
              <p key={r.id}>🔒 <b className="text-gray-700">{r.name}</b> 已锁定：{LOCK_REASONS[r.id] ?? '主持人设定遮蔽'} —— 下一步：点上方「{r.name}」按钮请求揭示（走主持人批准链，未批准自动回滚）。</p>
            )) : <p>全部房间当前可见（无锁定）。</p>}
          </div>
          <label className="mt-2 flex items-center gap-2 text-xs text-gray-500">
            <input type="checkbox" checked={asPlayer} onChange={(e) => setAsPlayer(e.target.checked)} className="accent-gray-900" /> 以玩家视角预览（雾中 token 不可见；锁定房显示原因与请求路径）
          </label>
        </section>
        <section className="panel min-w-0" aria-label="命令日志">
          <h2 className="panel-title">命令链日志</h2>
          {log.length === 0 ? <p className="text-sm text-gray-600">暂无命令 —— 拖个棋子或放个新棋子，这里会记录每一步。</p> : (
            <ul className="space-y-1 text-sm text-gray-700">{log.map((l, i) => (
              <li key={i}>· {l.text} <span className="text-xs text-gray-600">（{l.actor} · {new Date(l.ts).toLocaleTimeString('zh-CN', { hour12: false })}）</span></li>
            ))}</ul>
          )}
        </section>
      </div>
    </div>
  );
}