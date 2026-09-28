import React from 'react';
import { restConnParams, transport, transportSnapshot } from '../lib/transport';
import { ensureSceneNames, mapSceneTitle } from '../store/map';
import { EmptyState, SkeletonBlock } from './ui';
import { useMapStore } from '../store/map';
// UI-R2: 灰白黑令牌适配（仅视觉）

export function SharedScreen(): React.ReactElement {
  const [narr, setNarr] = React.useState<string[]>(['雨落在加油站的雨棚上，泵灯在夜色里发着惨白的光。']);
  const [events, setEvents] = React.useState<string[]>([]);
  // T16.3: 场景名统一取 store（scenes API / event_graph 单一事实源）。
  const sceneTitleText = useMapStore((s) => s.sceneTitle);
  const [imgRetry, setImgRetry] = React.useState(0);
  // UI-2 d9/d6: 场景图重试的加载反馈（按钮禁用 + LoadingRow），800ms 后复位；
  // 重试一轮仍未生成 → 进入"已失败"态（区分 准备中/已失败，UI1 P1 D6-2）。
  const [imgLoading, setImgLoading] = React.useState(false);
  const [imgFailed, setImgFailed] = React.useState(false);
  const onRetryImg = (): void => {
    if (imgLoading) return;
    setImgFailed(false);
    setImgLoading(true);
    window.setTimeout(() => {
      setImgLoading(false);
      setImgRetry((n) => n + 1);
      setImgFailed(true); // 本轮未生成 → 占位回退（与超时回退语义一致）
    }, 800);
  };

  React.useEffect(() => {
    setEvents(transportSnapshot().events);
    transport.connect();
    // T16.3: 拉取场景名（scenes API → event_graph 标题）。
    void ensureSceneNames(restConnParams().campaign);
    const off = transport.subscribe((frame) => {
      if (frame.kind === 'NARRATION_APPROVED') setNarr((prev) => [...prev, frame.narration.text].slice(-5));
      else if (frame.kind === 'BRANCH_TAKEN') setEvents((prev) => [`分支：${frame.branch.label}`, ...prev].slice(0, 6));
    });
    return () => { off(); transport.close(); };
  }, []);

  return (
    <div className="space-y-4">
      <section className="panel" aria-label="当前场景">
        <h2 className="panel-title">共享屏 · 当前场景：{sceneTitleText || '未同步'}</h2>
        <div className="flex min-h-[120px] max-h-44 flex-col items-center justify-center gap-2 overflow-hidden rounded-md border border-dashed border-gray-300 bg-gray-100 p-4 text-center" role="img" aria-label="场景图未就绪">
          <p className="text-sm text-gray-700">场景图还在准备中</p>
          <p className="text-xs text-gray-600">图片生成后会自动显示在这里；可先看下方叙事正文继续游玩</p>
          <p className="text-xs text-gray-500">占位属主：主持人（场景图由主持端触发生成，玩家只读）· 引擎 engine=placeholder · 占位编号 placeholder_ref=scene-pending</p>
          <p className="text-xs text-gray-500">超时说明：生成超过 15s 未返回时自动回退到占位图，不阻塞叙事；可点下方「重试加载场景图」（已重试次数可见）。</p>
          {imgFailed ? (
            <p className="w-full rounded-md border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-800" role="alert">
              场景图生成未完成（已回退占位图）—— 可再点一次重试，或先看下方叙事正文继续游玩。
            </p>
          ) : null}
          <div className="min-h-[20px] w-full" aria-live="polite" aria-atomic="true">
          {imgLoading ? <SkeletonBlock className="h-16 w-full" /> : null}
          </div>
          <button className="btn btn-secondary px-3 py-1 text-xs" onClick={onRetryImg} disabled={imgLoading} aria-busy={imgLoading} title="重新请求场景图（占位重试，不影响叙事）">{imgLoading ? '重试中…' : '重试加载场景图'}{imgRetry > 0 ? `（已试 ${imgRetry} 次）` : ''}</button>
        </div>
      </section>
      <section className="panel" aria-label="查看说明">
        <h2 className="panel-title">查看说明</h2>
        <p className="text-xs text-gray-600">共享屏为只读旁观视图：无操作按钮是设计如此，无需行动；玩家请回玩家面板提交，主持人请回主持人看板推进。</p>
      </section>
      <section className="panel" aria-label="叙事正文">
        <h2 className="panel-title">叙事正文（公开）</h2>
        <div className="space-y-2">
          {narr.map((t, i) => (<p key={i} className={`rounded-md p-3 text-sm leading-7 ${i === narr.length - 1 ? 'bg-gray-100 text-gray-900' : 'bg-gray-100 text-gray-600'}`}>{t}</p>))}
        </div>
      </section>
      <section className="panel" aria-label="最近事件">
        <h2 className="panel-title">最近事件</h2>
        {events.length === 0 ? <EmptyState text="暂无事件。" /> : (
          <ul className="space-y-1 text-sm text-gray-600">{events.map((e, i) => (<li key={i}>· {e}</li>))}</ul>
        )}
      </section>
    </div>
  );
}