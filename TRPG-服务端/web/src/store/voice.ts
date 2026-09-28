import { create } from 'zustand';
import type { SendableClientFrame } from '../lib/mockTransport';
import { transport } from '../lib/transport';

export type RecPhase = 'idle' | 'requesting' | 'recording' | 'paused' | 'error';
export type TxPhase = 'idle' | 'transcribing' | 'ready' | 'error';
export type TtsPhase = 'idle' | 'speaking' | 'done';

export interface TranscriptSeg {
  text: string;
  speaker: string;
  status: 'appended' | 'ready';
  chunkSeq: number;
}

interface VoiceState {
  recPhase: RecPhase;
  recSeconds: number;
  recError: string;
  chunksSent: number;
  lastSeq: number;
  txPhase: TxPhase;
  segments: TranscriptSeg[];
  transcriptRef: string;
  txError: string;
  ttsPhase: TtsPhase;
  ttsText: string;
  ttsDeduped: boolean;
  ttsError: string;
  set: (p: Partial<VoiceState>) => void;
  reset: () => void;
}

const initial: Omit<VoiceState, 'set' | 'reset'> = {
  recPhase: 'idle',
  recSeconds: 0,
  recError: '',
  chunksSent: 0,
  lastSeq: 0,
  txPhase: 'idle',
  segments: [],
  transcriptRef: '',
  txError: '',
  ttsPhase: 'idle',
  ttsText: '',
  ttsDeduped: false,
  ttsError: '',
};

/** voice slice：录音/转写/TTS 全经 transport 单一入口（铁律）。 */
export const useVoiceStore = create<VoiceState>()((set) => ({
  ...initial,
  set: (p) => set(p),
  reset: () => set({ ...initial }),
}));

let reqSeq = 5000;
function reqId(): string {
  reqSeq += 1;
  return `voice-${Date.now()}-${reqSeq}`;
}

/** 经 transport 发一帧（Sendable 体；campaign/actor/req_id 由传输层补齐）。 */
export function voiceSend(frame: SendableClientFrame, actorId = 'pl-linmo'): void {
  void actorId;
  transport.send(frame);
}

/** 订阅 transport 下行帧 → 写回 voice slice（调用一次，常驻）。 */
let subscribed = false;
export function ensureVoiceSubscription(): void {
  if (subscribed) return;
  subscribed = true;
  transport.subscribe((frame) => {
    const s = useVoiceStore.getState();
    try {
      if (frame.kind === 'STATE_DELTA' && frame.delta.field === 'transcript_seg') {
        const v = frame.delta.value as { text: string; speaker: string; status?: string; chunk_seq?: number };
        s.set({
          txPhase: 'transcribing',
          txError: '',
          segments: [...s.segments, { text: v.text, speaker: v.speaker, status: 'appended' as const, chunkSeq: v.chunk_seq ?? 0 }].slice(-8),
        });
      } else if (frame.kind === 'STATE_DELTA' && frame.delta.field === 'transcript_ready') {
        const v = frame.delta.value as { transcript_ref: string };
        s.set({
          txPhase: 'ready',
          transcriptRef: v.transcript_ref,
          segments: s.segments.map((g) => ({ ...g, status: 'ready' as const })),
          ttsPhase: 'speaking',
          ttsText: '门后的雾气缓缓退去，露出一枚带血的银钥匙。（播报中…）',
        });
      } else if (frame.kind === 'JOB_STATUS' && frame.job.job_id.startsWith('job-tts-')) {
        if (frame.job.status === 'failed') {
          // UI-2 d6 (UI1 P1 D6-3): 转写/任务失败 → 呈现 error 态（可重试）。
          s.set({ txPhase: 'error', txError: '转写任务失败：未能生成文本。请重试录音，或检查服务端转写管线。' });
          return;
        }
        const ref = String(frame.job.result_ref ?? '');
        const seen = useVoiceStore.getState().ttsText;
        s.set({
          ttsPhase: 'done',
          ttsText: ref.replace(/^tts:/, ''),
          ttsDeduped: ref === seen || useVoiceStore.getState().ttsDeduped,
        });
      }
    } catch (e) {
      // 防御：帧处理异常不崩订阅，转写态落 error（可重试）。
      s.set({ txPhase: 'error', txError: `转写处理异常：${e instanceof Error ? e.message : String(e)}` });
    }
  });
}
