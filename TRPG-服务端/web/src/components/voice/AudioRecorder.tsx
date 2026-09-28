import React from 'react';
import { transport } from '../../lib/transport';
import { ensureVoiceSubscription, useVoiceStore, voiceSend } from '../../store/voice';
import { ErrorBanner } from '../ui';
// UI-R2: 灰白黑令牌适配（仅视觉）

function fmt(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function toB64(bytes: Uint8Array): string {
  let bin = '';
  for (let i = 0; i < bytes.length; i += 1) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}

/** AudioRecorder —— MediaRecorder opus 上行分片（AUDIO_CHUNK，seq/时间戳）。 */
export function AudioRecorder(): React.ReactElement {
  const recPhase = useVoiceStore((s) => s.recPhase);
  const recSeconds = useVoiceStore((s) => s.recSeconds);
  const recError = useVoiceStore((s) => s.recError);
  const chunksSent = useVoiceStore((s) => s.chunksSent);
  const set = useVoiceStore((s) => s.set);
  const recRef = React.useRef<{ stream?: MediaStream; rec?: MediaRecorder; timer?: number; seq: number } | null>(null);
  const [noMic, setNoMic] = React.useState(false);

  React.useEffect(() => {
    ensureVoiceSubscription();
    transport.connect();
    if (!('mediaDevices' in navigator) || typeof MediaRecorder === 'undefined') setNoMic(true);
  }, []);

  const pushChunk = React.useCallback((blob: Blob) => {
    void blob.arrayBuffer().then((buf) => {
      const st = useVoiceStore.getState();
      const seq = st.lastSeq + 1;
      voiceSend({ kind: 'AUDIO_CHUNK', player_id: 'pl-linmo', mime: 'audio/opus', chunk_base64: toB64(new Uint8Array(buf)), seq });
      st.set({ chunksSent: st.chunksSent + 1, lastSeq: seq });
    });
  }, []);

  const start = React.useCallback(async () => {
    const st = useVoiceStore.getState();
    if (st.recPhase === 'recording') return;
    set({ recError: '' });
    // 抑制联动：TTS 播报中禁止开麦（a11y 文案说明原因）。
    if (useVoiceStore.getState().ttsPhase === 'speaking') {
      set({ recPhase: 'error', recError: 'TTS 播报中已抑制麦克风，请等待播报结束再录音。' });
      return;
    }
    set({ recPhase: 'requesting' });
    try {
      if (!('mediaDevices' in navigator) || typeof MediaRecorder === 'undefined') {
        throw new Error('当前浏览器不支持录音（缺少 MediaRecorder）。请用桌面 Chrome/Edge，或走下方「模拟上行」演示完整循环。');
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
      const holder: { stream?: MediaStream; rec?: MediaRecorder; timer?: number; seq: number } = { stream, rec, seq: st.lastSeq };
      recRef.current = holder;
      rec.ondataavailable = (ev: BlobEvent) => { if (ev.data && ev.data.size > 0) pushChunk(ev.data); };
      rec.onerror = () => set({ recPhase: 'error', recError: '录音中断 idealized，请点击重试（已保留已发分片）。' });
      rec.start(1000); // 1s 一片 → AUDIO_CHUNK
      holder.timer = window.setInterval(() => {
        const cur = useVoiceStore.getState();
        cur.set({ recSeconds: cur.recSeconds + 1 });
      }, 1000);
      set({ recPhase: 'recording' });
    } catch (e) {
      const msg = e instanceof DOMException && e.name === 'NotAllowedError'
        ? '麦克风权限被拒绝：请在浏览器地址栏放行麦克风后重试；或用「模拟上行」继续演示。'
        : e instanceof DOMException && e.name === 'NotFoundError'
          ? '未检测到麦克风设备：请接入麦克风后重试；或用「模拟上行」继续演示。'
          : e instanceof Error ? e.message : String(e);
      set({ recPhase: 'error', recError: msg });
    }
  }, [pushChunk, set]);

  const pause = React.useCallback(() => {
    const h = recRef.current;
    if (h?.rec && useVoiceStore.getState().recPhase === 'recording') {
      h.rec.pause();
      useVoiceStore.getState().set({ recPhase: 'paused' });
    }
  }, []);

  const resume = React.useCallback(() => {
    const h = recRef.current;
    if (h?.rec && useVoiceStore.getState().recPhase === 'paused') {
      h.rec.resume();
      useVoiceStore.getState().set({ recPhase: 'recording' });
    }
  }, []);

  const stop = React.useCallback(() => {
    const h = recRef.current;
    try { h?.rec?.state !== 'inactive' && h?.rec?.stop(); } catch { /* ignore */ }
    h?.stream?.getTracks().forEach((t) => t.stop());
    if (h?.timer) window.clearInterval(h.timer);
    recRef.current = null;
    const cur = useVoiceStore.getState();
    if (cur.recPhase === 'recording' || cur.recPhase === 'paused') cur.set({ recPhase: 'idle' });
  }, []);

  React.useEffect(() => () => {
    const h = recRef.current;
    try { h?.rec?.state !== 'inactive' && h?.rec?.stop(); } catch { /* ignore */ }
    h?.stream?.getTracks().forEach((t) => t.stop());
    if (h?.timer) window.clearInterval(h.timer);
  }, []);

  /** 无麦克风/无权限环境：模拟上行，走同一 transport 入口（证据截图用）。 */
  const demoUplink = React.useCallback(() => {
    const st = useVoiceStore.getState();
    const seq = st.lastSeq + 1;
    voiceSend({ kind: 'AUDIO_CHUNK', player_id: 'pl-linmo', mime: 'audio/opus', chunk_base64: btoa('mock-opus-bytes'), seq });
    st.set({ chunksSent: st.chunksSent + 1, lastSeq: seq, recPhase: 'recording', recSeconds: st.recSeconds + 1 });
  }, []);

  const busy = recPhase === 'requesting';
  const recording = recPhase === 'recording';
  const paused = recPhase === 'paused';

  return (
    <section className="panel" aria-label="语音录音">
      <h2 className="panel-title">语音录音</h2>
      {recError ? <ErrorBanner message={recError} onClose={() => set({ recPhase: 'idle', recError: '' })} /> : null}
      <div className="flex items-center gap-3">
        <span className={`inline-block h-3 w-3 rounded-full ${recording ? 'animate-pulse bg-red-500' : 'bg-gray-400'}`} aria-hidden="true" />
        <span className="font-mono text-lg tabular-nums" aria-label="录音时长">{fmt(recSeconds)}</span>
        <span className="text-xs text-gray-500">已发分片 {chunksSent} · {recording ? '录音中…' : paused ? '已暂停' : busy ? '请求麦克风…' : '空闲'}</span>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button className="btn btn-primary" onClick={() => void start()} disabled={busy || recording} aria-label="开始录音">开始录音</button>
        {!paused
          ? <button className="btn btn-secondary" onClick={pause} disabled={!recording} aria-label="暂停录音">暂停</button>
          : <button className="btn btn-secondary" onClick={resume} aria-label="继续录音">继续</button>}
        <button className="btn btn-secondary" onClick={stop} disabled={!recording && !paused} aria-label="停止录音">停止</button>
        <button className="btn btn-secondary" onClick={demoUplink} aria-label="模拟上行一片音频">模拟上行（一片）</button>
      </div>
      {noMic ? <p className="mt-2 text-xs text-gray-800">提示：当前环境没有麦克风，真录音不可用；点「模拟上行」可走同样链路演示完整循环。</p> : null}
    </section>
  );
}
