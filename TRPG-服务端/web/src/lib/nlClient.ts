// nlClient —— /access/nl 自然语言调度客户端（DSH-3, additive; 仅 web/src）。
//
// 调用主持端服务器（9210）的 NL 端点：POST /access/nl（webapp=KP 端 token,
// Authorization: Bearer —— token 来源：localStorage('trpg_token') 优先 >
// VITE_TRPG_TOKEN（构建期），运行时可在页面控制台设置、演示无需重编；绝不回显/落日志）。
// 端点语义（DSH-2）：返回 {intent, params, suggestion?, events?, status},
// 只产出建议/提案, 从不自动执行（无 AINPC）; 不可用/异常降级为错误返回, 不抛。
export interface NlResult {
  intent: string;
  params: Record<string, unknown>;
  suggestion?: Record<string, unknown> | null;
  events?: Array<Record<string, unknown>>;
  status?: string;
}

export interface NlResponse {
  ok: boolean;
  data: NlResult | null;
  code?: number;
  error?: string;
}

function env(): Record<string, string | undefined> {
  return (import.meta as unknown as { env?: Record<string, string | undefined> }).env ?? {};
}

/** webapp（主持端）token —— URL ?token= > localStorage('trpg_token') > VITE_TRPG_TOKEN
 *  （T16.2 与 transport.ts:pickToken 同源，避免 WS/REST 与 /access/nl 各用各的 token）。
 *  仅用于 Authorization 头，任何路径不回显/不落日志。 */
export function nlToken(): string {
  try {
    const fromUrl = new URLSearchParams(window.location.search).get('token');
    if (fromUrl && fromUrl.trim()) return fromUrl.trim();
  } catch { /* ignore */ }
  try {
    const ls = typeof localStorage !== 'undefined' ? localStorage.getItem('trpg_token') : null;
    if (ls && ls.trim()) return ls.trim();
  } catch {
    // localStorage 不可用（隐私模式等）——回退构建期 env
  }
  return env().VITE_TRPG_TOKEN ?? '';
}

export async function postNl(
  text: string,
  campaign: string,
  opts?: { scene?: string },
): Promise<NlResponse> {
  const token = nlToken();
  const base = (env().VITE_TRPG_BASE_URL ?? '').replace(/\/$/, '');
  const url = `${base}/access/nl`;
  const body: Record<string, unknown> = { campaign, text };
  if (opts?.scene) body.scene = opts.scene;
  try {
    const resp = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    });
    const raw = (await resp.json().catch(() => null)) as
      | { ok?: boolean; data?: NlResult | null; code?: number; error?: string }
      | null;
    if (!raw) {
      return { ok: false, data: null, code: resp.status, error: `无法解析响应（HTTP ${resp.status}）` };
    }
    return { ok: raw.ok === true, data: raw.data ?? null, code: raw.code ?? resp.status, error: raw.error };
  } catch (e) {
    // 网络/超时等 —— 降级错误返回, 不抛异常给 UI。
    return { ok: false, data: null, error: e instanceof Error ? e.message : String(e) };
  }
}