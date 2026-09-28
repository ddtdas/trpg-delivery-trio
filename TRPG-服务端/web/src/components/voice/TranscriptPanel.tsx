import React from 'react';
import { useVoiceStore } from '../../store/voice';
import { EmptyState, ErrorBanner, LoadingRow } from '../ui';
// UI-R2: 灰白黑令牌适配（仅视觉）

/** TranscriptPanel —— 转写段实时展示（TRANSCRIPT_APPENDED/READY/ERROR）。 */
export function TranscriptPanel(): React.ReactElement {
  const txPhase = useVoiceStore((s) => s.txPhase);
  const segments = useVoiceStore((s) => s.segments);
  const transcriptRef = useVoiceStore((s) => s.transcriptRef);
  const txError = useVoiceStore((s) => s.txError);
  const clearTxError = React.useCallback(() => {
    useVoiceStore.getState().set({ txError: '', txPhase: segments.length ? 'ready' : 'idle' });
  }, [segments.length]);

  return (
    <section className="panel" aria-label="实时转写" aria-live="polite">
      <h2 className="panel-title">
        实时转写 · {txPhase === 'ready' ? '完成' : txPhase === 'error' ? '转写失败' : txPhase === 'transcribing' ? '转写中…' : '等待录音'}
        {transcriptRef ? <span className="ml-2 font-mono text-xs text-gray-500">{transcriptRef}</span> : null}
      </h2>
      {txPhase === 'error' ? <ErrorBanner message={txError || '转写失败：无法识别语音。请重试录音。'} onClose={clearTxError} /> : null}
      {txPhase === 'transcribing' && segments.length === 0 ? <LoadingRow text="转写进行中…（约 1s 到达）" /> : null}
      {segments.length === 0 ? <EmptyState text="暂无转写段 —— 开始录音或点击「模拟上行」后，转写段会实时出现在这里。" /> : (
        <ul className="space-y-2">
          {segments.map((g, i) => (
            <li key={i} className="rounded-md bg-gray-100 p-3">
              <div className="flex items-center gap-2 text-xs">
                <span className="chip border-gray-400 text-gray-600">讲话人 {g.speaker}</span>
                <span className={`chip ${g.status === 'ready' ? 'border-gray-400 text-gray-800' : 'border-gray-300 text-gray-800'}`}>
                  {g.status === 'ready' ? '已对齐' : '转写中'}
                </span>
              </div>
              <p className="mt-1 text-sm leading-6">{g.text}</p>
            </li>
          ))}
        </ul>
      )}
      {txPhase === 'transcribing' && segments.length > 0 ? <div className="mt-2"><LoadingRow text="对齐中…（合并同一讲话人的相邻段）" /></div> : null}
      {txPhase === 'idle' && segments.length === 0 ? <p className="mt-2 text-xs text-gray-600" role="status">排队说明：上行分片 → 转写 → 对齐，单机演示在本地完成。</p> : null}
    </section>
  );
}
