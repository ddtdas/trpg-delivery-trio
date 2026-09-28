import React from 'react';
import { Link, Route, Routes, useLocation } from 'react-router-dom';
import { CharWizard } from './components/CharWizard';
import { DshPanel } from './components/DshPanel';
import { KpBoard } from './components/KpBoard';
import { LatencyDashboard } from './components/Dashboard/LatencyDashboard';
import { MapCanvas } from './components/MapCanvas';
import Overview from './components/Overview';
import { PlayerPanel } from './components/PlayerPanel';
import { ReviewView } from './components/ReviewView';
import { SharedScreen } from './components/SharedScreen';
import { TRANSPORT_MODE, getTransportStatus, resolveTransportParams, subscribeStatus, transportStatusLabel, type WsStatus } from './lib/transport';
import { ToastZone } from './components/ui';

const LINKS = [
  { to: '/overview', label: '主持人总览' },
  { to: '/kp', label: '主持人看板' },
  { to: '/player', label: '玩家面板' },
  { to: '/shared', label: '共享屏' },
  { to: '/wizard', label: '车卡向导' },
  { to: '/review', label: '复盘视图' },
  { to: '/dashboard', label: '仪表盘' },
  { to: '/map', label: '地图' },
  { to: '/dsh', label: 'DSH 助手' },
];

/** UI-R1: 左侧边栏导航 —— 宽屏固定 208px；窄屏由外层抽屉承载（同一组件）。 */
function SidebarNav({ onNavigate }: { onNavigate?: () => void }): React.ReactElement {
  const { pathname } = useLocation();
  return (
    <nav className="flex flex-col gap-1" aria-label="主导航">
      {LINKS.map((l) => {
        const active = pathname === l.to || (l.to === '/kp' && pathname === '/');
        return (
          <Link
            key={l.to}
            to={l.to}
            onClick={onNavigate}
            aria-current={active ? 'page' : undefined}
            className={`sidebar-link ${active ? 'sidebar-link-active' : ''}`}
          >
            {l.label}
          </Link>
        );
      })}
    </nav>
  );
}

/** App：灰白黑路由壳 —— 左侧边栏（宽屏固定 / 窄屏抽屉）+ 主区；skip-link 与 #main 保留（UI-2 d7）。 */
export function App(): React.ReactElement {
  const [toasts, setToasts] = React.useState<Array<{ id: string; text: string }>>([]);
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const closeDrawer = React.useCallback(() => setDrawerOpen(false), []);
  // 路由切换时关闭抽屉（窄屏）
  const { pathname } = useLocation();
  React.useEffect(() => { setDrawerOpen(false); }, [pathname]);

  // R2/t11：横幅与提示跟随**真实连接状态**（而非仅构建期模式）。
  // 断连/重连时给出降级提示，避免"看着像已同步、其实没连上"。
  const [connStatus, setConnStatus] = React.useState<WsStatus>(() => getTransportStatus());
  const connParams = React.useMemo(() => resolveTransportParams(), []);
  React.useEffect(() => subscribeStatus(setConnStatus), []);
  const connText = TRANSPORT_MODE === 'real'
    ? transportStatusLabel(connStatus)
    : '单机演示数据：改动只保存在本页（演示用，无同步）';
  const connTone = TRANSPORT_MODE !== 'real'
    ? 'chip-warn'
    : connStatus === 'open'
      ? 'chip-ok'
      : 'chip-warn';

  React.useEffect(() => {
    if (TRANSPORT_MODE !== 'real' || connStatus !== 'open') return;
    const id = `conn-${Date.now()}`;
    setToasts([{ id, text: '已连接服务器，改动会实时同步。' }]);
    const t = window.setTimeout(() => setToasts((prev) => prev.filter((x) => x.id !== id)), 8000);
    return () => window.clearTimeout(t);
  }, [connStatus]);

  return (
    <div className="min-h-screen overflow-x-clip bg-[var(--bg)]">
      <a href="#main" className="skip-link">跳到主内容</a>

      {/* 宽屏固定侧边栏（≥768px 显示） */}
      <aside className="sidebar hidden md:flex" aria-label="侧边导航">
        <div className="mb-3 px-1 text-sm font-bold tracking-wide text-gray-900">TRPG 辅助系统</div>
        <SidebarNav />
      </aside>

      {/* 窄屏抽屉（<768px）：汉堡按钮 + overlay */}
      <button
        className="btn btn-secondary fixed left-3 top-3 z-50 min-h-[40px] px-3 md:hidden"
        onClick={() => setDrawerOpen((v) => !v)}
        aria-label={drawerOpen ? '关闭导航菜单' : '打开导航菜单'}
        aria-expanded={drawerOpen}
      >
        ☰
      </button>
      {drawerOpen ? (
        <>
          <div className="drawer-overlay" onClick={closeDrawer} aria-hidden="true" />
          <aside className="sidebar md:hidden" aria-label="侧边导航（抽屉）">
            <div className="mb-3 flex items-center justify-between px-1">
              <span className="text-sm font-bold tracking-wide text-gray-900">TRPG 辅助系统</span>
              <button className="rounded px-2 py-1 text-gray-600 hover:bg-gray-100" onClick={closeDrawer} aria-label="关闭导航菜单">
                ✕
              </button>
            </div>
            <SidebarNav onNavigate={closeDrawer} />
          </aside>
        </>
      ) : null}

      {/* 主区：宽屏让出侧栏宽度 */}
      <div className="md:pl-52">
        <div className="mx-auto max-w-6xl space-y-4 p-4 pb-[env(safe-area-inset-bottom)] pt-16 md:pt-4">
          <header className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h1 className="text-xl font-bold tracking-wide text-gray-900">TRPG 辅助系统 · 雾港来信</h1>
              {/* R2/t11：原来硬编码 camp-mist-port —— 即使已接真服务端，页头仍显示 mock 战役名，
                  会被误判为"仍在 mock 模式"。改为显示**实际解析出的**战役/牌桌。 */}
              <span
                className="chip"
                data-campaign={TRANSPORT_MODE === 'real' ? connParams.campaign : 'camp-mist-port'}
                data-table={TRANSPORT_MODE === 'real' ? connParams.table : ''}
                data-conn-source={TRANSPORT_MODE === 'real' ? 'server' : 'mock'}
              >
                CoC7 · {TRANSPORT_MODE === 'real' ? connParams.campaign : 'camp-mist-port'}
                {TRANSPORT_MODE === 'real' && connParams.table ? ` · ${connParams.table}` : ''}
              </span>
            </div>
            <p
              className="rounded-md border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-600"
              role="status"
              data-conn-mode={TRANSPORT_MODE}
              data-conn-status={TRANSPORT_MODE === 'real' ? connStatus : 'mock'}
              data-conn-label={connTone}
            >
              {connText}
            </p>
            <div className="min-h-[8px]" aria-live="polite">
            {toasts.length > 0 ? (
              <ToastZone items={toasts} onClose={(id) => setToasts((prev) => prev.filter((x) => x.id !== id))} />
            ) : null}
            </div>
          </header>
          <main id="main" className="min-w-0">
            <Routes>
              <Route path="/" element={<KpBoard />} />
              <Route path="/kp" element={<KpBoard />} />
          <Route path="/overview" element={<Overview />} />
              <Route path="/player" element={<PlayerPanel />} />
              <Route path="/shared" element={<SharedScreen />} />
              <Route path="/wizard" element={<CharWizard />} />
              <Route path="/review" element={<ReviewView />} />
              <Route path="/map" element={<MapCanvas />} />
              <Route path="/dashboard" element={<LatencyDashboard />} />
              <Route path="/dsh" element={<DshPanel />} />
            </Routes>
          </main>
        </div>
      </div>
    </div>
  );
}