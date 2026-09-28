// T16.3: 场景名单一事实源 —— 优先读后端 GET /api/campaigns/{c}/scenes（事件图 event_graph 派生），
// 不可用时回退到静态场景名表（来源：modpacks/…/event_graph.yaml / scenes API 实测值）。
//
// 背景：修复前「雾港图书馆 / 密斯卡托尼克大学图书馆 / 雨夜抵达加油站」三处硬编码不一致。
// 这里统一为 campaign 场景 id → 名称映射：同一 URL（campaign）下所有组件读同一份标题。

export interface SceneInfo {
  byId: Record<string, string>;
  currentId: string;
  currentTitle: string;
}

/** 静态回退表 —— 来源：event_graph.yaml（dead_light 模组，scenes API 实测 2026-09-28）。 */
const FALLBACK_SCENES: Record<string, string> = {
  n_arrival: '雨夜抵达加油站',
  n_forecourt: '前场勘察',
  n_shop_search: '便利店搜证',
  n_store_find: '后仓发现',
  n_office_ledger: '办公室账簿',
  n_washroom_clue: '洗手间镜面',
  n_roadblock: '公路封锁',
  n_lobby: '旅店门厅',
  n_dining_meet: '餐厅会面',
  n_kitchen_noise: '厨房异响',
  n_guest_room: '客房搜查',
  n_cellar_deadlight: '地窖死光',
  n_confrontation: '对峙',
  n_ending: '终局',
  library: '雾港图书馆',
};

function urlParam(key: string): string {
  try {
    return new URLSearchParams(window.location.search).get(key) ?? '';
  } catch {
    return '';
  }
}

function readToken(): string {
  try {
    const ls = localStorage.getItem('trpg_token');
    if (ls && ls.trim()) return ls.trim();
  } catch { /* ignore */ }
  return urlParam('token') || '';
}

let cache: { key: string; info: SceneInfo } | null = null;

/** 拉取场景表（带缓存）：成功 -> 事件图标题；失败 -> 静态回退表。 */
export async function loadSceneInfo(campaign: string): Promise<SceneInfo> {
  const key = campaign || 'default';
  if (cache && cache.key === key) return cache.info;
  let info: SceneInfo = {
    byId: { ...FALLBACK_SCENES },
    currentId: '',
    currentTitle: '',
  };
  const token = readToken();
  try {
    const resp = await fetch('/api/campaigns/' + encodeURIComponent(key) + '/scenes' + (token ? ('?token=' + encodeURIComponent(token)) : ''), {
      headers: token ? { Authorization: 'Bearer ' + token } : {},
    });
    if (resp.ok) {
      const raw = (await resp.json()) as { scenes?: Array<{ scene_id: string; title: string }>; current_scene?: string };
      const byId: Record<string, string> = { ...FALLBACK_SCENES };
      for (const s of raw.scenes ?? []) {
        if (s.scene_id) byId[s.scene_id] = s.title || s.scene_id;
      }
      const currentId = raw.current_scene ?? '';
      info = { byId, currentId, currentTitle: currentId ? (byId[currentId] || currentId) : '' };
    }
  } catch { /* 网络失败 —— 保持静态回退 */ }
  cache = { key, info };
  return info;
}

/** 场景 id -> 标题（回退自己）。 */
export function sceneTitle(byId: Record<string, string>, id: string): string {
  return (id && byId[id]) || id || '';
}
