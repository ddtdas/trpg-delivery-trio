import type { PerfSample } from './ws';

/**
 * lib/metrics —— 延迟数据适配层（对齐 runtime-contract §3 perf 五字段）。
 *
 * - 默认 mock provider（仿真数据），供 Dashboard 先行开发。
 * - 预留 fetchMetrics(baseUrl) 接 REST `GET /api/metrics/latency?campaign=<id>&n=100`
 *   → `{mean,p95,segments:{5 段},n}`；后端就绪后集成任务只需把 provider 换成真 REST，
 *   组件层零改动（铁律：适配层与组件解耦）。
 */

export type { PerfSample };

export const SEGMENTS = [
  'vad_ms',
  'stt_ms',
  'llm_first_token_ms',
  'tts_first_packet_ms',
  'approve_wait_ms',
] as const;

export type SegmentKey = (typeof SEGMENTS)[number];

export const SEGMENT_LABELS: Record<SegmentKey, string> = {
  vad_ms: '语音检测',
  stt_ms: '语音转写',
  llm_first_token_ms: 'AI 起草',
  tts_first_packet_ms: '语音合成',
  approve_wait_ms: '审批等待',
};

export const SEGMENT_COLORS: Record<SegmentKey, string> = {
  vad_ms: 'bg-gray-300',
  stt_ms: 'bg-gray-400',
  llm_first_token_ms: 'bg-gray-500',
  tts_first_packet_ms: 'bg-gray-600',
  approve_wait_ms: 'bg-red-400',
};

/** 派生：voice_loop = vad+stt+llm_first+tts_first（目标 1.0–1.3s，硬限 1.6s） */
export function voiceLoopOf(s: PerfSample): number {
  return s.vad_ms + s.stt_ms + s.llm_first_token_ms + s.tts_first_packet_ms;
}

/** REST /metrics/latency 响应体（runtime-contract §3 查询接口） */
export interface LatencySummary {
  mean: number;
  p95: number;
  segments: PerfSample;
  n: number;
}

export interface MetricsProvider {
  readonly name: string;
  getSummary(campaign: string, n?: number): Promise<LatencySummary>;
  getRecent(campaign: string, n?: number): Promise<PerfSample[]>;
}

/** mulberry32 确定性 PRNG：mock 数据可复现 */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function jitter(rand: () => number, base: number, spread: number): number {
  return Math.max(0, Math.round(base + (rand() - 0.5) * 2 * spread));
}

/** Mock provider：仿真 voice_loop 落在 1.0–1.3s 目标带的样本流 */
export class MockMetricsProvider implements MetricsProvider {
  readonly name = 'mock';
  private seed: number;

  constructor(seed = 20260919) {
    this.seed = seed;
  }

  private gen(count: number): PerfSample[] {
    const rand = mulberry32(this.seed);
    const out: PerfSample[] = [];
    for (let i = 0; i < count; i += 1) {
      out.push({
        vad_ms: jitter(rand, 110, 40),
        stt_ms: jitter(rand, 280, 90),
        llm_first_token_ms: jitter(rand, 560, 180),
        tts_first_packet_ms: jitter(rand, 210, 70),
        approve_wait_ms: jitter(rand, 140, 100),
      });
    }
    return out;
  }

  async getRecent(_campaign: string, n = 100): Promise<PerfSample[]> {
    return this.gen(Math.max(0, Math.min(n, 100)));
  }

  async getSummary(campaign: string, n = 100): Promise<LatencySummary> {
    const samples = await this.getRecent(campaign, n);
    return summarize(samples);
  }
}

/** 真 REST provider：后端就绪后用 `setMetricsProvider(new RestMetricsProvider())` 替换 */
export class RestMetricsProvider implements MetricsProvider {
  readonly name = 'rest';
  private baseUrl: string;

  constructor(baseUrl = 'http://127.0.0.1:9210') {
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  async getSummary(campaign: string, n = 100): Promise<LatencySummary> {
    const data = await fetchMetrics(this.baseUrl, campaign, n);
    return data;
  }

  async getRecent(campaign: string, n = 100): Promise<PerfSample[]> {
    const res = await fetch(
      `${this.baseUrl}/api/metrics/samples?campaign=${encodeURIComponent(campaign)}&n=${n}`,
    );
    if (!res.ok) throw new Error(`GET /api/metrics/samples failed: ${res.status}`);
    const data = (await res.json()) as { samples?: PerfSample[] };
    return data.samples ?? [];
  }
}

/** REST 查询：GET /api/metrics/latency?campaign=<id>&n=100 */
export async function fetchMetrics(
  baseUrl: string,
  campaign: string,
  n = 100,
): Promise<LatencySummary> {
  const res = await fetch(
    `${baseUrl.replace(/\/$/, '')}/api/metrics/latency?campaign=${encodeURIComponent(
      campaign,
    )}&n=${n}`,
  );
  if (!res.ok) throw new Error(`GET /api/metrics/latency failed: ${res.status}`);
  return (await res.json()) as LatencySummary;
}

export function summarize(samples: PerfSample[]): LatencySummary {
  const n = samples.length;
  if (n === 0) {
    return {
      mean: 0,
      p95: 0,
      segments: { vad_ms: 0, stt_ms: 0, llm_first_token_ms: 0, tts_first_packet_ms: 0, approve_wait_ms: 0 },
      n: 0,
    };
  }
  const loops = samples.map(voiceLoopOf).sort((a, b) => a - b);
  const mean = loops.reduce((a, b) => a + b, 0) / n;
  const p95 = loops[Math.min(n - 1, Math.ceil(n * 0.95) - 1)];
  const avg = (k: SegmentKey): number =>
    Math.round(samples.reduce((a, s) => a + s[k], 0) / n);
  // 口径（t46 收敛）：mean/p95 与分段条同源——mean=各样本四段和的均值，
  // 分段=各段跨样本均值；四段和≈mean（±舍入 2ms），审批等待另计不入单轮耗时。
  return {
    mean: Math.round(mean),
    p95: Math.round(p95),
    segments: {
      vad_ms: avg('vad_ms'),
      stt_ms: avg('stt_ms'),
      llm_first_token_ms: avg('llm_first_token_ms'),
      tts_first_packet_ms: avg('tts_first_packet_ms'),
      approve_wait_ms: avg('approve_wait_ms'),
    },
    n,
  };
}

// ---- 当前 provider（默认 mock；集成任务换真 REST 只改这里） ----
let current: MetricsProvider = new MockMetricsProvider();

export function getMetricsProvider(): MetricsProvider {
  return current;
}

export function setMetricsProvider(p: MetricsProvider): void {
  current = p;
}
