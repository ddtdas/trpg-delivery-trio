import React from 'react';
import { TRANSPORT_MODE, transport, type SendableClientFrame } from '../lib/transport';
import { EmptyState, ErrorBanner } from './ui';
import { VoiceDock } from './voice/VoiceDock';
// UI-R2: 灰白黑令牌适配（仅视觉）

const TRANSPORT_MODE_LABEL = TRANSPORT_MODE === 'real' ? '提交后主持人可见（已同步）' : '提交后记录在本页演示（单机演示数据）';

const ACTOR = { id: 'pl-linmo', token: 'mock-pl-token' } as const;
function send(frame: SendableClientFrame): void {
  transport.send(frame);
}

export function PlayerPanel(): React.ReactElement {
  const [action, setAction] = React.useState('我检查书桌上的信件，看看有没有暗格。');
  const [intent, setIntent] = React.useState('搜证：书桌');
  const [target, setTarget] = React.useState('侦查');
  const [rolls, setRolls] = React.useState<string[]>([]);
  const [turnState, setTurnState] = React.useState('IDLE');
  const [narr, setNarr] = React.useState<string[]>([]);
  const [whisperTo, setWhisperTo] = React.useState('kp');
  const [whisperBody, setWhisperBody] = React.useState('');
  const [whispers, setWhispers] = React.useState<string[]>([]);
  const [error, setError] = React.useState('');
  const [sending, setSending] = React.useState(false);
  const [sentOk, setSentOk] = React.useState('');

  React.useEffect(() => {
    transport.connect();
    const off = transport.subscribe((frame) => {
      if (frame.kind === 'TURN_UPDATED') setTurnState(frame.turn.state);
      else if (frame.kind === 'NARRATION_APPROVED') setNarr((prev) => [...prev, frame.narration.text].slice(-5));
      else if (frame.kind === 'STATE_DELTA' && frame.delta.field === 'last_roll') {
        const v = frame.delta.value as { target: string; roll: number; seed: number; result: string };
        setRolls((prev) => [`${v.target} → ${v.roll}（${v.result}）`, ...prev].slice(0, 5));
      }
    });
    return () => { off(); transport.close(); };
  }, []);

  const onSubmit = (): void => {
    if (!action.trim()) { setError('行动描述不能为空，请先填写你要做什么。'); return; }
    setError(''); setSentOk(''); setSending(true);
    send({ kind: 'SUBMIT_ACTION', action: action.trim(), intent: intent.trim() || undefined });
    window.setTimeout(() => {
      setSending(false);
      setSentOk('已提交：主持人会在回合面板看到你的行动。');
    }, 400);
  };
  const onRoll = (): void => {
    setError('');
    send({ kind: 'COMMAND', cmd: { type: 'roll_check', payload: { target, seed: 7 + rolls.length } } });
  };
  const onWhisper = (): void => {
    if (!whisperBody.trim()) { setError('私语内容不能为空。'); return; }
    setError('');
    setWhispers((prev) => [`→ ${whisperTo}：${whisperBody.trim()}（仅对方可见）`, ...prev].slice(0, 5));
    setWhisperBody('');
  };

  return (
    <div className="space-y-4 pb-[env(safe-area-inset-bottom)]">
      {error ? <ErrorBanner message={error} onClose={() => setError('')} /> : null}
      <section className="panel" aria-label="本人角色卡">
        <h2 className="panel-title">本人角色卡 · 林墨（侦探）</h2>
        <div className="flex flex-wrap gap-2 text-xs">
          {['侦查 45', '聆听 40', '闪避 35', 'HP 11/12', 'SAN 62'].map((s) => (<span key={s} className="chip">{s}</span>))}
        </div>
        <p className="mt-2 text-xs text-gray-600">回合状态：{turnState} · {TRANSPORT_MODE_LABEL}</p>
      </section>

      <section className="panel" aria-label="行动提交">
        <h2 className="panel-title">对话 / 行动输入</h2>
        <label className="mb-1 block text-xs text-gray-600" htmlFor="pl-action">行动描述（必填，说清楚你要做什么） <span className="text-gray-500">· 草稿可改，提交后以 KP 结算为准</span></label>
        <textarea id="pl-action" className="input min-h-[84px]" value={action} onChange={(e) => setAction(e.target.value)} placeholder="描述你要做什么…（必填）" aria-describedby="pl-action-help" autoFocus />
        <p id="pl-action-help" className="mt-1 text-xs text-gray-600">写给主持人看的行动 declaration，越具体结算越顺。</p>
        <label className="mb-1 mt-2 block text-xs text-gray-600" htmlFor="pl-intent">意图摘要（选填，主持人一眼看懂）</label>
        <input id="pl-intent" className="input" value={intent} onChange={(e) => setIntent(e.target.value)} placeholder="如：搜证 / 交涉 / 战斗" />
        <div className="mt-3 min-h-[44px]">
          <button className="btn btn-primary w-full sm:w-auto" onClick={onSubmit} disabled={sending} aria-busy={sending} title={sending ? '提交中：请稍候，结果会显示在下方状态行' : '提交行动给 KP 结算'}>{sending ? '提交中…' : '提交行动'}</button>
          <div className="min-h-[20px]" aria-live="polite" aria-atomic="true">
          {sentOk ? <p className="mt-2 text-xs text-gray-800" role="status">{sentOk}</p> : null}
          </div>
        </div>
      </section>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <section className="panel min-w-0" aria-label="骰点托盘">
          <h2 className="panel-title">骰点托盘</h2>
          <div className="flex flex-wrap gap-2">
            <select className="input" value={target} onChange={(e) => setTarget(e.target.value)} aria-label="检定目标">
              {['侦查', '聆听', '闪避', '图书馆'].map((t) => (<option key={t}>{t}</option>))}
            </select>
            <button className="btn btn-secondary shrink-0" onClick={onRoll}>掷骰</button>
          </div>
          {rolls.length === 0 ? <div className="mt-2"><EmptyState text="尚未掷骰 —— 选目标后点击「掷骰」。" /></div> : (
            <div>
            <ul className="mt-2 space-y-1 text-sm">{rolls.map((r, i) => (<li key={i} className="rounded bg-gray-100 px-2 py-1">{r}</li>))}</ul>
            <p className="mt-1 text-xs text-gray-500">结果不满意可换目标再掷一次（每次种子递增，结果独立）。</p>
            </div>
          )}
        </section>
        <section className="panel min-w-0" aria-label="私语">
          <h2 className="panel-title">私语（仅对方可见）</h2>
          <div className="flex flex-wrap gap-2">
            <select className="input" value={whisperTo} onChange={(e) => setWhisperTo(e.target.value)} aria-label="私语目标">
              <option value="kp">主持人</option>
              <option value="pl-surui">苏芮</option>
            </select>
            <input className="input" value={whisperBody} onChange={(e) => setWhisperBody(e.target.value)} placeholder="悄悄话内容…" aria-label="私语内容" />
            <button className="btn btn-secondary shrink-0" onClick={onWhisper}>发送</button>
          </div>
          {whispers.length === 0 ? <div className="mt-2"><EmptyState text="暂无私语 —— 选好收件人、写一句话，点发送即可（只有对方能看到）。" /></div> : (
            <ul className="mt-2 space-y-1 text-sm text-gray-800">{whispers.map((w, i) => (<li key={i} className="rounded bg-gray-100 px-2 py-1">{w}</li>))}</ul>
          )}
        </section>
      </div>

      <section className="panel" aria-label="最新旁白">
        <h2 className="panel-title">最新旁白（公开）</h2>
        {narr.length === 0 ? <EmptyState text="等待主持人批准旁白…" /> : (
          <ul className="space-y-2">{narr.map((t, i) => (<li key={i} className="rounded bg-gray-100 p-3 text-sm leading-6">{t}</li>))}</ul>
        )}
      </section>

      <VoiceDock />
    </div>
  );
}