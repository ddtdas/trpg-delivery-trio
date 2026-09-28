import React from 'react';
import { nlToken, postNl, type NlResult } from '../lib/nlClient';
import { EmptyState, ErrorBanner, LoadingRow } from './ui';
// UI-R2: 灰白黑令牌适配（仅视觉）

/** 快捷意图 chips —— 点击即发送对应自然语言指令（建议/推进/裁决/记录/摘要）。 */
const QUICK_INTENTS = [
  { label: '建议', text: '建议皮克曼教授对玩家的提问给出反应（三选一）' },
  { label: '推进', text: '推进到教堂，描述下一步场景' },
  { label: '裁决', text: '裁决：这轮侦查检定是否算成功' },
  { label: '记录', text: '记录：玩家刚才说他们在检查书桌，记一笔' },
  { label: '摘要', text: '摘要：总结当前局势和待办线索' },
];

const INTENT_ZH: Record<string, string> = {
  advice: '建议', advance: '推进', record: '记录', summary: '摘要',
};

interface HistoryItem {
  id: string;
  text: string;
  ts: number;
  intent?: string;
  status?: string;
  suggestion?: Record<string, unknown> | null;
  events?: Array<Record<string, unknown>>;
  error?: string;
}

function SuggestionBlock({ item }: { item: HistoryItem }): React.ReactElement | null {
  const sug = item.suggestion;
  if (!sug) return null;
  const options = Array.isArray(sug.options) ? (sug.options as unknown[]) : [];
  const rationale = typeof sug.rationale === 'string' ? sug.rationale : '';
  return (
    <div className="mt-2 rounded-md bg-gray-100 p-2">
      {options.length > 0 ? (
        <ul className="space-y-1 text-sm text-gray-900">
          {options.map((o, i) => (
            <li key={i}>· {String(o)}</li>
          ))}
        </ul>
      ) : null}
      {rationale ? <p className="mt-1 text-xs text-gray-600">理由：{rationale}</p> : null}
      {(item.events ?? []).length > 0 ? (
        <p className="mt-1 text-xs text-gray-600">
          提案（待主持人确认）：{(item.events ?? []).map((e) => String((e as Record<string, unknown>).kind ?? e)).join('、')}
        </p>
      ) : null}
    </div>
  );
}

function KeeperFrame({ token }: { token: string }): React.ReactElement {
  const env = (import.meta as unknown as { env?: Record<string, string | undefined> }).env ?? {};
  // TD-2: 同源托管 —— /app/keeper-ui/index.html 经 FastAPI /app 挂载（web/dist/keeper-ui 构建产物）；
  // 显式指向 index.html（尾斜杠目录路径会落到主应用 index 回退）。VITE_KEEPER_UI_URL 可覆盖。
  const src = env.VITE_KEEPER_UI_URL ?? '/app/keeper-ui/index.html';
  const [sent, setSent] = React.useState(false);
  return (
    <section className="panel" aria-label="keeper-ui 嵌入面板">
      <h2 className="panel-title">keeper-ui（DSH Web GUI，iframe 同源嵌入）</h2>
      <p className="mb-2 text-xs text-gray-500">
        TD-2 同源一体化托管：无独立进程/端口；iframe 隔离 + postMessage 注入 webapp token（token 不回显、不落 URL）。
      </p>
      <iframe
        title="主持人 DSH 面板"
        src={src}
        sandbox="allow-scripts allow-same-origin allow-forms"
        className="h-[60vh] w-full rounded-lg border border-gray-300 bg-white"
        onLoad={(e) => {
          // 握手：向 iframe 投递 webapp token（仅当配置了 VITE_TRPG_TOKEN）。
          if (!token || sent) return;
          const win = (e.target as HTMLIFrameElement).contentWindow;
          win?.postMessage({ type: 'trpg:token', token }, '*');
          setSent(true);
        }}
      />
      <p className="mt-1 text-xs text-gray-500">默认 src=/app/keeper-ui/index.html（同源）；VITE_KEEPER_UI_URL 可覆盖。</p>
    </section>
  );
}

/** DshPanel —— 主持端自然语言助手（DSH-3）：NL → /access/nl → 建议/提案回显。 */
export function DshPanel(): React.ReactElement {
  const [input, setInput] = React.useState('');
  const [campaign, setCampaign] = React.useState('camp-mist-port');
  const [sending, setSending] = React.useState(false);
  const [error, setError] = React.useState('');
  const [history, setHistory] = React.useState<HistoryItem[]>([]);
  // TD-2: keeper-ui 同源托管（web/dist/keeper-ui）——iframe 默认开启。
  const [showFrame, setShowFrame] = React.useState(true);
  const token = nlToken();
  const reqSeq = React.useRef(0);
  // T16.2: 页面内 token 编辑器 —— 默认读 localStorage 同源（nlClient.nlToken）；
  // 保存写回 localStorage trpg_token；清除则移除（回到构建期 env 兜底）。
  const [tokenDraft, setTokenDraft] = React.useState(token);
  const [tokenSaved, setTokenSaved] = React.useState(false);
  const saveToken = (): void => {
    const v = tokenDraft.trim();
    try {
      if (v) localStorage.setItem('trpg_token', v);
      else localStorage.removeItem('trpg_token');
      setTokenSaved(true);
      window.setTimeout(() => setTokenSaved(false), 1500);
    } catch {
      setError('localStorage 不可用，token 未持久化。');
    }
  };
  const clearToken = (): void => {
    try {
      localStorage.removeItem('trpg_token');
      setTokenDraft('');
      setTokenSaved(false);
    } catch {
      setError('localStorage 不可用。');
    }
  };

  const send = React.useCallback(async (text: string): Promise<void> => {
    const t = text.trim();
    if (!t) { setError('自然语言指令不能为空。'); return; }
    setError('');
    setSending(true);
    const id = `nl-${Date.now()}-${(reqSeq.current += 1)}`;
    const item: HistoryItem = { id, text: t, ts: Date.now() };
    setHistory((prev) => [item, ...prev].slice(0, 30));
    const resp = await postNl(t, campaign);
    setSending(false);
    setHistory((prev) => prev.map((h) => {
      if (h.id !== id) return h;
      if (resp.ok && resp.data) {
        return {
          ...h, intent: resp.data.intent, status: resp.data.status,
          suggestion: resp.data.suggestion ?? null,
          events: resp.data.events ?? [],
        };
      }
      return { ...h, error: resp.error ?? `请求失败（code ${resp.code ?? '?'}）` };
    }));
    if (!resp.ok) {
      setError(`NL 请求失败：${resp.error ?? resp.code ?? '未知错误'}`);
    }
  }, [campaign]);

  const onQuick = (text: string): void => { setInput(text); void send(text); };

  const intentZh = (intent?: string): string => (intent ? INTENT_ZH[intent] ?? intent : '');

  return (
    <div className="space-y-4">
      <section className="panel" aria-label="自然语言助手">
        <h2 className="panel-title">DSH 助手 · 主持端自然语言面板</h2>
        <p className="mb-2 text-xs text-gray-500">
          指令经 POST /access/nl（webapp=主持端 token，Bearer 传递，token 不回显）→ 建议/提案回显；
          仅产出建议与待主持人确认的提案，绝不自动执行（无 AINPC）。
        </p>
        {/* T16.2: 页面内 token 设置（不再要求用户开控制台）。默认读 localStorage trpg_token
            （nlClient.nlToken 同源），保存后写回 localStorage，WS/REST 立即带上。 */}
        <div className="mb-2 rounded-md border border-gray-300 bg-gray-50 px-3 py-2" role="group" aria-label="接入 token 设置">
          <label className="mb-1 block text-xs font-semibold text-gray-700" htmlFor="dsh-token">
            接入 token（webapp / 主持端）
            <span className="ml-2 font-normal text-gray-500">
              {token ? '已配置（' + token.slice(0, 6) + '…，不回显全文）' : '未配置 —— NL 与 keeper-ui 均会 401/403'}
            </span>
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <input
              id="dsh-token"
              className="input min-w-[240px] flex-1 font-mono"
              type="password"
              value={tokenDraft}
              onChange={(e) => setTokenDraft(e.target.value)}
              placeholder="粘贴 webapp token（configs/access_config.yaml ends.webapp.token）"
              autoComplete="off"
            />
            <button className="btn btn-secondary" onClick={saveToken} disabled={tokenSaved} aria-label="保存 token 到 localStorage">
              {tokenSaved ? '已保存 ✓' : '保存 token'}
            </button>
            <button className="btn btn-secondary" onClick={clearToken} disabled={!token} aria-label="清除已保存的 token">清除</button>
          </div>
          <p className="mt-1 text-[11px] text-gray-500">
            token 保存在浏览器 localStorage 的 <code className="rounded bg-gray-200 px-1">trpg_token</code>，
            供 <code className="rounded bg-gray-200 px-1">nlClient.nlToken()</code>（/access/nl）与 keeper-ui iframe 握手共用；仅作 Authorization 头，不落 URL、不写日志。
          </p>
          <p className="mt-1 text-[11px] text-gray-500">
            提示：若页面上方 iFrame 面板报 <code className="rounded bg-gray-200 px-1">/app/keeper-ui/api/remote.mux 403</code>，
            这是 9211 对 <code className="rounded bg-gray-200 px-1">/app/</code> 静态托管路径下 WebSocket 反代的白名单问题（服务端侧，本次不改后端）；
            页面内保存 token 可让同源 /access/* 与 REST 走通，DSH 面板的 NL 建议链可用。
          </p>
        </div>
        {error ? <ErrorBanner message={error} onClose={() => setError('')} /> : null}
        <label className="mb-1 block text-xs text-gray-500" htmlFor="dsh-nl">
          自然语言指令 <span className="text-gray-500">· 如「建议皮克曼教授的反应」「推进到教堂」</span>
        </label>
        <textarea
          id="dsh-nl"
          className="input min-h-[72px]"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="自然语言指令：如「建议皮克曼教授的反应」「推进到教堂」"
        />
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 text-xs text-gray-500">
            会话
            <input className="input w-44" value={campaign} onChange={(e) => setCampaign(e.target.value)} aria-label="会话 id" />
          </label>
          <button
            className="btn btn-primary w-full sm:w-auto"
            onClick={() => void send(input)}
            disabled={sending}
            aria-busy={sending}
            title={sending ? '发送中：等待主持端服务器解析并返回建议…' : '发送自然语言指令给主持端服务器'}
          >
            {sending ? '发送中…' : '发送'}
          </button>
        </div>
        <div className="mt-3 flex flex-wrap gap-2" aria-label="快捷意图">
          {QUICK_INTENTS.map((q) => (
            <button key={q.label} className="chip border-gray-300 text-gray-900 hover:bg-gray-100" onClick={() => onQuick(q.text)} disabled={sending} aria-label={`快捷意图：${q.label}`}>
              {q.label}
            </button>
          ))}
        </div>
        <div className="mt-3 min-h-[20px]" aria-live="polite">
          {sending ? <LoadingRow text="NL 解析中…（intent → 建议/提案）" /> : null}
        </div>
      </section>

      <section className="panel" aria-label="历史对话">
        <div className="flex items-center justify-between gap-2">
          <h2 className="panel-title mb-0">历史对话（{history.length} 条，本地 state）</h2>
          <label className="flex items-center gap-2 text-xs text-gray-500">
            <input type="checkbox" checked={showFrame} onChange={(e) => setShowFrame(e.target.checked)} className="accent-gray-900" aria-label="嵌入 keeper-ui 开关" />
            嵌入 keeper-ui（iframe，默认开启）
          </label>
        </div>
        {history.length === 0 ? (
          <div className="mt-2"><EmptyState text="暂无对话 —— 输入自然语言指令或点上方快捷意图。" /></div>
        ) : (
          <ul className="mt-2 space-y-3">
            {history.map((h) => (
              <li key={h.id} className="rounded-lg border border-gray-200 bg-white p-3">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="text-gray-700">{h.text}</span>
                  <span className="ml-auto text-gray-500">{new Date(h.ts).toLocaleTimeString('zh-CN', { hour12: false })}</span>
                </div>
                {h.error ? (
                  <p className="mt-1 text-xs text-red-700" role="alert">失败：{h.error}</p>
                ) : (
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-gray-600">
                    {h.intent ? <span className="chip border-gray-300 text-gray-900">意图：{intentZh(h.intent)}</span> : null}
                    {h.status ? <span className="chip border-gray-400 text-gray-600">状态：{h.status}</span> : null}
                    {h.suggestion ? <SuggestionBlock item={h} /> : null}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {showFrame ? <KeeperFrame token={token} /> : null}
    </div>
  );
}