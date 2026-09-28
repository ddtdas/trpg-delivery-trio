import React from 'react';
import { AudioRecorder } from './AudioRecorder';
import { TranscriptPanel } from './TranscriptPanel';
import { TtsBar } from './TtsBar';
// UI-R2: 灰白黑令牌适配（仅视觉）

/** VoiceDock —— 语音三件套组合（录音 → 转写 → 播报），供 PlayerPanel 嵌入。 */
export function VoiceDock(): React.ReactElement {
  return (
    <div className="space-y-4" aria-label="语音交互">
      <AudioRecorder />
      <TranscriptPanel />
      <TtsBar />
    </div>
  );
}
