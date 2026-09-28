import React from 'react';
import { useVoiceStore } from '../../store/voice';
import { EmptyState, ErrorBanner } from '../ui';
// UI-R2: 灰白黑令牌适配（仅视觉）

/** TtsBar —— TTS 播报条（播放/抑制联动/去重/文本兜底/错误提示）。 */
export function TtsBar(): React.ReactElement {
  const ttsPhase = useVoiceStore((s) => s.ttsPhase);
  const ttsText = useVoiceStore((s) => s.ttsText);
  const ttsDeduped = useVoiceStore((s) => s.ttsDeduped);
  const ttsError = useVoiceStore((s) => s.ttsError);
  const recPhase = useVoiceStore((s) => s.recPhase);
  const set = useVoiceStore((s) => s.set);

  const speaking = ttsPhase === 'speaking';

  const replay = React.useCallback(() => {
    const st = useVoiceStore.getState();
    if (!st.ttsText) { st.set({ ttsError: '暂无可播报文本：先完成一次转写，TTS 文本会自动到达。' }); return; }
    if (st.ttsPhase === 'speaking') { st.set({ ttsDeduped: true }); return; } // 去重：播报中重复点击记一次
    st.set({ ttsPhase: 'speaking', ttsError: '' });
    window.setTimeout(() => {
      const cur = useVoiceStore.getState();
      if (cur.ttsPhase === 'speaking') cur.set({ ttsPhase: 'done' });
    }, 2500);
  }, []);

  // mock 播报自动结束（与播报期抑制联动演示）。
  React.useEffect(() => {
    if (!speaking) return;
    const t = window.setTimeout(() => {
      const cur = useVoiceStore.getState();
      if (cur.ttsPhase === 'speaking') cur.set({ ttsPhase: 'done' });
    }, 6000);
    return () => window.clearTimeout(t);
  }, [speaking]);

  return (
    <section className="panel" aria-label="TTS 播报">
      <h2 className="panel-title">TTS 播报{ speaking ? ' · 播报中（麦克风已抑制）' : ''}</h2>
      {ttsError ? <ErrorBanner message={ttsError} onClose={() => set({ ttsError: '' })} /> : null}
      {!ttsText ? <EmptyState text="暂无播报文本 —— 转写完成后语音播报会自动生成。" /> : (
        <div className="rounded-md bg-gray-100 p-3" role="status" aria-live="polite">
          <p className="text-sm leading-6 text-gray-900">{ttsText}</p>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-gray-500">
            <span className="chip">文本兜底展示（无音频时照常可读）</span>
            {ttsDeduped ? <span className="chip border-gray-400 text-gray-600">去重：重复播报已抑制</span> : null}
            {speaking ? <span className="chip border-red-400 text-red-700">抑制联动：录音按钮已禁用</span> : null}
          </div>
        </div>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <button className="btn btn-primary" onClick={replay} disabled={!ttsText || speaking} aria-label="播放 TTS 播报">
          {speaking ? '播报中…' : '播放播报'}
        </button>
        <span className="self-center text-xs text-gray-500" aria-hidden="true">
          {recPhase === 'recording' && speaking ? '双工冲突已拦截' : '播报期录音自动抑制（aec_guard 语义）'}
        </span>
      </div>
    </section>
  );
}
