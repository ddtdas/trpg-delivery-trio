import React from 'react';
import {
  SEGMENT_COLORS,
  SEGMENT_LABELS,
  SEGMENTS,
  voiceLoopOf,
  type PerfSample,
} from '../../lib/metrics';

const VOICE_LOOP_LIMIT_MS = 1600;

interface PerfBarProps {
  /** 单回合样本；缺省时渲染空状态 */
  sample?: PerfSample;
  compact?: boolean;
}

/** PerfBar —— 单回合延迟分解条（五段比例条＋数值，纯 CSS/Tailwind）。 */
export function PerfBar({ sample, compact }: PerfBarProps): React.ReactElement {
  if (!sample) {
    return (
      <div className="panel p-3 text-sm text-gray-700" role="status">
        暂无延迟样本 —— 完成一次回合结算后，这里会出现耗时分解条。
      </div>
    );
  }
  const loop = voiceLoopOf(sample);
  const over = loop > VOICE_LOOP_LIMIT_MS;
  const denom = Math.max(1, loop + sample.approve_wait_ms);
  return (
    <div className="panel p-3">
      <div className="flex items-baseline justify-between text-sm text-gray-800">
        <span className="font-semibold">
          单轮耗时 {loop}ms
          <span className={over ? 'ml-2 font-semibold text-red-300' : 'ml-2 font-semibold text-gray-800'}>
            {over ? '超 1.6s 硬限' : '≤1.6s 达标'}
          </span>
        </span>
        {!compact && (
          <span className="text-xs text-gray-600">审批等待 {sample.approve_wait_ms}ms（另计）</span>
        )}
      </div>
      <div
        className="mt-2 flex h-4 w-full overflow-hidden rounded"
        role="img"
        aria-label={`延迟分解：单轮耗时 ${loop}ms`}
      >
        {SEGMENTS.map((k) => {
          const v = sample[k];
          const pct = Math.max(0, (v / denom) * 100);
          return (
            <div
              key={k}
              className={`${SEGMENT_COLORS[k]} h-full`}
              style={{ width: `${pct}%` }}
              title={`${SEGMENT_LABELS[k]} ${v}ms`}
            />
          );
        })}
      </div>
      {!compact && (
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-700">
          {SEGMENTS.map((k) => (
            <span key={k}>
              <i className={`${SEGMENT_COLORS[k]} mr-1 inline-block h-2 w-2 rounded-sm`} />
              {SEGMENT_LABELS[k]} {sample[k]}ms
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
