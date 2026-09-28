import React from 'react';
import {
  SEGMENT_COLORS,
  SEGMENT_LABELS,
  SEGMENTS,
  getMetricsProvider,
  voiceLoopOf,
  type LatencySummary,
  type PerfSample,
} from '../../lib/metrics';
import { PerfBar } from './PerfBar';
import { SkeletonRows } from '../ui';
// UI-R2: 灰白黑令牌适配（仅视觉）

type LoadState = 'loading' | 'ready' | 'empty' | 'error';

const VOICE_LOOP_LIMIT_MS = 1600;

/** 分段横条：五段均值分解（纯 CSS/Tailwind，不引第三方图表库） */
function SegmentBars({ segments }: { segments: PerfSample }): React.ReactElement {
  const total = Math.max(1, voiceLoopOf(segments) + segments.approve_wait_ms);
  const max = Math.max(1, ...SEGMENTS.map((k) => segments[k]));
  return (
    <div className="space-y-2">
      {SEGMENTS.map((k) => {
        const v = segments[k];
        return (
          <div key={k} className="flex items-center gap-2 text-sm">
            <span className="w-28 shrink-0 text-gray-700" title={`${SEGMENT_LABELS[k]}（${k}）`}>{SEGMENT_LABELS[k]}</span>
            <div className="h-4 flex-1 overflow-hidden rounded bg-gray-200">
              <div
                className={`${SEGMENT_COLORS[k]} h-full rounded`}
                style={{ width: `${Math.max(1, (v / max) * 100)}%` }}
              />
            </div>
            <span className="w-20 shrink-0 text-right tabular-nums text-gray-800">{v}ms</span>
            <span className="w-14 shrink-0 text-right text-xs tabular-nums text-gray-700">
              {Math.round((v / total) * 100)}%
            </span>
          </div>
        );
      })}
    </div>
  );
}

/** 最近样本 voice_loop 迷你柱状（纯 div 条） */
function RecentSpark({ samples }: { samples: PerfSample[] }): React.ReactElement {
  const show = samples.slice(-40);
  const max = Math.max(VOICE_LOOP_LIMIT_MS, ...show.map(voiceLoopOf), 1);
  return (
    <div className="flex h-16 items-end gap-[3px]" role="img" aria-label="最近样本 voice_loop 迷你柱状">
      {show.map((s, i) => {
        const v = voiceLoopOf(s);
        return (
          <div
            key={i}
            className={`w-full rounded-t ${v > VOICE_LOOP_LIMIT_MS ? 'bg-red-600' : 'bg-gray-600'}`}
            style={{ height: `${Math.max(4, (v / max) * 100)}%` }}
            title={`#${i + 1} voice_loop ${v}ms`}
          />
        );
      })}
    </div>
  );
}

/** LatencyDashboard —— 最近 100 条均值＋P95＋五段分解可视化（mock 先行）。 */
export function LatencyDashboard(): React.ReactElement {
  const [state, setState] = React.useState<LoadState>('loading');
  const [summary, setSummary] = React.useState<LatencySummary | null>(null);
  const [recent, setRecent] = React.useState<PerfSample[]>([]);
  const [error, setError] = React.useState<string>('');
  const [providerName, setProviderName] = React.useState<string>('');

  const [updatedAt, setUpdatedAt] = React.useState<number>(0);
  const [refreshTick, setRefreshTick] = React.useState(0);
  const [refreshing, setRefreshing] = React.useState(false);

  const refresh = React.useCallback(() => setRefreshTick((t) => t + 1), []);

  React.useEffect(() => {
    let alive = true;
    const provider = getMetricsProvider();
    setProviderName(provider.name);
    setState('loading');
    setRefreshing(refreshTick > 0);
    (async () => {
      try {
        const [s, r] = await Promise.all([
          provider.getSummary('demo', 100),
          provider.getRecent('demo', 100),
        ]);
        if (!alive) return;
        if (s.n === 0) {
          setState('empty');
          return;
        }
        setSummary(s);
        setRecent(r);
        setUpdatedAt(Date.now());
        setRefreshing(false);
        setState('ready');
      } catch (e) {
        if (!alive) return;
        setError(e instanceof Error ? e.message : String(e));
        setRefreshing(false);
        setState('error');
      }
    })();
    return () => {
      alive = false;
    };
  }, [refreshTick]);

  if (state === 'loading') {
    // FZ-1: 加载期骨架占位（复用 SkeletonRows，.animate-pulse），替代纯 LoadingRow。
    return (
      <div className="panel" aria-busy="true">
        <h2 className="panel-title">延迟仪表盘</h2>
        <SkeletonRows rows={4} title label="延迟样本加载中（读取最近 100 条 perf 打点）" />
      </div>
    );
  }

  if (state === 'error') {
    return (
      <div className="panel" role="alert">
        <h2 className="panel-title">延迟仪表盘</h2>
        <p className="mt-2 text-sm text-red-700">加载失败：{error} —— 请检查后端 /api/metrics/latency 是否可达。</p>
        <button
          className="btn btn-secondary mt-3"
          onClick={() => window.location.reload()}
        >
          重试加载
        </button>
      </div>
    );
  }

  if (state === 'empty' || !summary) {
    return (
      <div className="panel">
        <h2 className="panel-title">延迟仪表盘</h2>
        <p className="mt-2 text-sm text-gray-700">暂无样本 —— 完成一次「开始回合→提交→结算」后，这里会出现延迟分解。</p>
      </div>
    );
  }

  const over = summary.mean > VOICE_LOOP_LIMIT_MS;
  return (
    <div className="space-y-4">
      <div className="panel">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="panel-title mb-0">延迟仪表盘 · 单轮语音耗时</h2>
          <span className="chip border-gray-400 text-gray-600" title="当前为本地生成的演示数据，非真实采集">加载演示数据（本地生成，不替换线上数据）</span>
        </div>
        <p className="mt-1 text-xs text-gray-700">
          口径：平均耗时=各样本四段（语音检测+转写+AI 起草+语音合成）和的均值；下表分段为各段均值，四段和≈平均（±舍入 2ms）；审批等待另计。最近 {summary.n} 条
          {updatedAt ? ` · 更新于 ${new Date(updatedAt).toLocaleTimeString('zh-CN', { hour12: false })}` : ''}
        </p>
        <div className="mt-2 min-h-[28px]">
          <button className="btn btn-secondary px-3 py-1 text-xs" onClick={refresh} disabled={refreshing} aria-busy={refreshing} aria-label="重新读取最近 100 条延迟样本" title={updatedAt ? `上次更新 ${new Date(updatedAt).toLocaleTimeString('zh-CN', { hour12: false })}；点击重新读取` : '点击重新读取最近 100 条延迟样本'}>{refreshing ? '刷新中…' : '刷新延迟样本'}</button>
        </div>
        <div className="mt-2 flex flex-wrap gap-6 text-sm text-gray-800">
          <span>
            平均耗时 <b className="tabular-nums">{summary.mean}ms</b>
          </span>
          <span>
            95% 分位 <b className="tabular-nums">{summary.p95}ms</b>
          </span>
          <span className={over ? 'font-semibold text-red-700' : 'font-semibold text-gray-800'}>
            1.6s 硬限：{over ? '超限' : '达标'}
          </span>
        </div>
        <div className="mt-3">
          <SegmentBars segments={summary.segments} />
          <table className="sr-only" aria-label="延迟五段数值表明细">
            <caption>五段均值与占比（毫秒）</caption>
            <tbody>
              {SEGMENTS.map((k) => (
                <tr key={k}><th scope="row">{SEGMENT_LABELS[k]}</th><td>{summary.segments[k]}ms</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="panel">
        <h3 className="panel-title">最近样本耗时（右为最新，单位毫秒）</h3>
        <div className="mt-2">
          <RecentSpark samples={recent} />
          <table className="sr-only" aria-label="最近样本 voice_loop 数值表">
            <caption>最近样本 voice_loop（毫秒，右为最新）</caption>
            <tbody>
              {recent.slice(-10).map((s, i) => (
                <tr key={i}><th scope="row">样本 {recent.length - Math.min(10, recent.length) + i + 1}</th><td>{voiceLoopOf(s)}ms</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <PerfBar sample={recent[recent.length - 1]} />
    </div>
  );
}
