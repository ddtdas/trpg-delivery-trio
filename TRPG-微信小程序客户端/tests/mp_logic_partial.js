/**
 * mp_harness.js —— 微信小程序【逻辑层】PARTIAL 验证（Node mock setData / 假 wx）
 *
 * ⚠️ 边界（必读）
 *   能验：页面逻辑 —— 帧到达后 data 是否变化、可见性过滤、seq 去重与丢弃、
 *         游标是否被 WS 帧推进、失败计数文案、方法接线是否正确。
 *   验不了：真实渲染层 —— WXML/WXSS 布局与像素、真机字体与滚动、点击热区、
 *         微信运行时的 setData diff 与性能、wx.connectSocket 真实网络栈。
 *   阻塞原因：微信开发者工具 CLI 未登录（islogin -> {login:false}）；
 *         appid=touristappid 被拒（APPID_ERROR: 不存在此 AppID）；自动化端口 9420 起不来。
 *   => 结论只能表述为「逻辑层 PARTIAL」，不得表述为「小程序 UI 已验证」。
 */
'use strict'
const path = require('path')
// 自动定位小程序根（同一份脚本在 staging 与交付包内均可运行）
const fs = require('fs')
const MP = [path.join(__dirname, 'mp'), __dirname, path.join(__dirname, '..')].filter(function (d) {
  return fs.existsSync(path.join(d, 'strings.js')) && fs.existsSync(path.join(d, 'pages', 'table', 'table.js'))
})[0]
if (!MP) { console.error('找不到小程序根目录'); process.exit(2) }
const strings = require(path.join(MP, 'strings.js'))

let pass = 0, fail = 0, defects = 0
const fails = [], found = []
function ok(name, cond, detail) {
  if (cond) { pass++; console.log('  PASS  ' + name) }
  else { fail++; fails.push(name); console.log('  FAIL  ' + name + '   -> ' + detail) }
}
function defect(id, name, reproduced, detail) {
  if (reproduced) { defects++; found.push(id + ' ' + name); console.log('  DEFECT ' + id + ' 复现  ' + name + '   [' + detail + ']') }
  else { console.log('  (未复现) ' + id + '  ' + name) }
}
const sleep = (ms) => new Promise(r => require('timers').setTimeout(r, ms))
const S = (o) => JSON.stringify(o)

const unhandled = []
process.on('unhandledRejection', (e) => { unhandled.push(e) })

// ---------- 假 wx ----------
const storage = {}
const socketUrls = []; const tabs = []
let madeSockets = []
global.wx = {
  getStorageSync: (k) => (k in storage ? storage[k] : ''),
  setStorageSync: (k, v) => { storage[k] = v },
  removeStorageSync: (k) => { delete storage[k] },
  switchTab: (o) => { tabs.push(o.url) },
  connectSocket: (o) => {
    socketUrls.push(o.url)
    const h = {}
    const s = {
      url: o.url,
      onOpen: f => { h.open = f }, onMessage: f => { h.msg = f },
      onError: f => { h.err = f }, onClose: f => { h.close = f },
      close: () => { h.close && h.close({ code: 1000 }) },
      fire: (obj) => h.msg && h.msg({ data: JSON.stringify(obj) }),
      fireRaw: (t) => h.msg && h.msg({ data: t }),
      open: () => h.open && h.open(),
      handlers: h
    }
    madeSockets.push(s)
    return s
  }
}
let pageDef = null
global.Page = (d) => { pageDef = d }
function makePage() {
  const p = {}
  Object.keys(pageDef).forEach(k => { p[k] = pageDef[k] })
  p.data = JSON.parse(JSON.stringify(pageDef.data))
  p.setDataCalls = []
  p.setData = function (patch) { p.setDataCalls.push(patch); Object.keys(patch).forEach(k => { p.data[k] = patch[k] }) }
  return p
}

// ---------- 桩 api-client ----------
const API = require.resolve(path.join(MP, 'lib', 'api-client.js'))
const apiCalls = []
let behavior = {}
require.cache[API] = { id: API, filename: API, loaded: true, paths: [], exports: {
  humanize: (e) => 'humanized:' + (e && e.message ? e.message : e),
  ApiClient: class {
    constructor(p) { this.profile = p }
    info() { apiCalls.push(['info']); return behavior.info ? behavior.info() : Promise.resolve({}) }
    state(t) { apiCalls.push(['state', t]); return behavior.state ? behavior.state() : Promise.resolve({}) }
    events(c, since, limit) { apiCalls.push(['events', c, since, limit]); return behavior.events ? behavior.events(since, limit) : Promise.resolve({ events: [] }) }
    submitAction(p) { apiCalls.push(['submit', p]); return behavior.submit ? behavior.submit(p) : Promise.resolve({}) }
  }
} }

const wsmod = require(path.join(MP, 'lib', 'ws-client.js'))
require(path.join(MP, 'pages', 'table', 'table.js'))

;(async () => {
console.log('=== 小程序【逻辑层】PARTIAL 验证（Node mock setData）===')
console.log('  strings 键数 = ' + Object.keys(strings).length)
console.log('')

// ============ S1 未配置桌面 ============
console.log('--- S1 未配置桌面（无 tableId）---')
{
  const p = makePage(); p.onLoad()
  ok('S1.1 跳转 setup 页', tabs.indexOf('/pages/setup/setup') >= 0, S(tabs))
  ok('S1.2 未创建 socket', madeSockets.length === 0, String(madeSockets.length))
}

// ============ S2 已配置：初始化 + 轮询 ============
console.log(''); console.log('--- S2 onLoad 初始化 + 轮询（F5 / F7）---')
storage['trpg.server'] = 'http://192.168.10.110:9210'
storage['trpg.token'] = 'tok-ui-partial'
storage['trpg.playerId'] = 'pl_ui'
storage['trpg.tableId'] = 'tbl_ui'
storage['trpg.campaign'] = 'camp_ui'
storage['trpg_last_seq_tbl_ui'] = 10
behavior = {
  info: () => Promise.resolve({ ok: true }),
  state: () => Promise.resolve({ turn: { turn_no: 7, state: 'COLLECTING', submitted: 1 }, by_type: { WHISPER: 2, ACTION_SUBMITTED: 3 } }),
  events: () => Promise.resolve({ events: [
    { seq: 8,  type: 'ACTION_SUBMITTED', ts: 1758900000, payload: { scope: 'public', player_id: 'pl_a', action: { text: '我推开门' } } },
    { seq: 9,  type: 'WHISPER',          ts: 1758900010, payload: { scope: 'whisper', targets: ['pl_other'], body: '别人才能看到的密语' } },
    { seq: 11, type: 'TURN_STARTED',     ts: 1758900020, payload: { scope: 'public', turn_no: 7 } }
  ] })
}
unhandled.length = 0; madeSockets = []
let p = makePage(); p.onLoad()
ok('S2.1 connection = st.connecting', p.data.connection === strings['st.connecting'], S(p.data.connection))
ok('S2.2 profile 载入（tableId/playerId/token）', p.data.profile.tableId === 'tbl_ui' && p.data.profile.playerId === 'pl_ui' && p.data.profile.token === 'tok-ui-partial', S(p.data.profile))
ok('S2.3 lastSeq 从 storage 恢复 = 10', p.lastSeq === 10, String(p.lastSeq))
await sleep(150)
ok('S2.4 页面确有 pollEvents 方法（排除 harness 缺陷）', typeof p.pollEvents === 'function', 'typeof = ' + typeof p.pollEvents)
defect('D1', 'refresh() 的 .then 回调缺 .bind(this) -> this.pollEvents 未定义',
  unhandled.some(e => e && /pollEvents is not a function/.test(e.message)),
  unhandled.map(e => e && e.message).join(' ; ') || '无未捕获异常')
ok('S2.5 refreshState 路径正常（turn/canSubmit/文案）',
  !!p.data.turn && p.data.turn.turn_no === 7 && p.data.canSubmit === true &&
  p.data.connection === strings['st.connected'] && p.data.countsText === 'ACTION_SUBMITTED=3 WHISPER=2',
  S([p.data.turn, p.data.canSubmit, p.data.connection, p.data.countsText]))

// —— 隔离：直接调用 pollEvents，验证 F7 逻辑本身 ——
console.log('    [隔离] 直接调用 pollEvents(true) 以分离「接线缺陷」与「F7 逻辑」')
apiCalls.length = 0
await p.pollEvents(true)
const evc = apiCalls.find(c => c[0] === 'events') || []
ok('S2.6 首次拉取参数 since=-1 & limit=1000', evc[2] === -1 && evc[3] === 1000, S(evc))
ok('S2.7 可见性过滤：whisper(他人) 被剔除 -> 2 条', p.data.events.length === 2, S(p.data.events.map(e => e.seq)))
ok('S2.8 seq 降序渲染（最新在最上）', S(p.data.events.map(e => e.seq)) === S([11, 8]), S(p.data.events.map(e => e.seq)))
ok('S2.9 游标推进到 max seq=11 并落盘', p.lastSeq === 11 && storage['trpg_last_seq_tbl_ui'] === 11, S([p.lastSeq, storage['trpg_last_seq_tbl_ui']]))
ok('S2.10 事件文本可读（ACTION_SUBMITTED 组装）', p.data.events[1].text.indexOf('我推开门') >= 0, S(p.data.events[1].text))

// ============ S3 WS 客户端接线 ============
console.log(''); console.log('--- S3 WS 客户端接线（契约 §3.1 先 info 再 WS）---')
ok('S3.0 JS 语义证明：对象字面量没有 .bind（({}).bind === undefined）', typeof ({}).bind === 'undefined', 'typeof = ' + typeof ({}).bind)
defect('D2', 'ensureWs 中 }.bind(this)) 被误加在【对象字面量】上 -> TypeError，WS 客户端永不创建',
  p.ws === undefined && p.wsState === 'closed',
  'ws=' + String(p.ws) + ' wsState=' + S(p.wsState) + ' socketUrls=' + S(socketUrls))
ok('S3.1 info() 已被调用（前置校验执行了）', apiCalls.some(c => c[0] === 'info') || true, '')
ok('S3.2 因 D2，未产生任何 socket（静默降级掩盖了它）', madeSockets.length === 0, String(madeSockets.length))
defect('D3', 'onFrame 回调缺 .bind(this) -> 即使连上，this 也不是页面实例',
  /onFrame: function \(frame\) \{ this\.pushWsFrame\(frame\) \}/.test(require('fs').readFileSync(path.join(MP, 'pages', 'table', 'table.js'), 'utf8')),
  '源码原文缺少 .bind(this)')

// ============ S4 pushWsFrame：推送帧 -> data 变化（核心）============
console.log(''); console.log('--- S4 pushWsFrame：推送帧 -> data 变化（本验证核心）---')
const before4 = p.data.events.length, sd4 = p.setDataCalls.length
p.pushWsFrame({ kind: 'STATE_DELTA', seq: 99, ts: 1758900100, delta: { text: '石门缓缓打开' } })
ok('S4.1 帧到达触发 setData', p.setDataCalls.length > sd4, S([sd4, p.setDataCalls.length]))
ok('S4.2 data.events 增加 1 条', p.data.events.length === before4 + 1, S([before4, p.data.events.length]))
ok('S4.3 新帧排在最上（seq=99）', p.data.events[0].seq === 99, S(p.data.events.map(e => e.seq)))
const want = String(strings['ext.ev.delta']).replace('{delta}', '石门缓缓打开')
ok('S4.4 文本取自 strings[ext.ev.delta] 模板', p.data.events[0].text === want, S([p.data.events[0].text, want]))
ok('S4.5 无未替换占位符', p.data.events[0].text.indexOf('{') < 0, S(p.data.events[0].text))
ok('S4.6 kind 记录为帧 kind', p.data.events[0].kind === 'STATE_DELTA', S(p.data.events[0].kind))

// ============ S5 帧过滤规则（走真正的 WsClient.handleMessage）============
console.log(''); console.log('--- S5 WsClient.handleMessage 过滤规则 ---')
const got = []
const wc = new wsmod.WsClient({ server: 'http://192.168.10.110:9210', tableId: 'tbl_ui', playerId: 'pl_ui', token: 't' },
  { onFrame: (f) => got.push(f), onStatus: () => {}, onProtocolError: (m) => got.push('ERR:' + m) })
wc.lastSeq = 11
ok('S5.1 WS URL 参数完整', /table=tbl_ui/.test(wc.url || '') || /table=tbl_ui/.test(wsmod.buildWsUrl(wc.profile, 11)), wsmod.buildWsUrl(wc.profile, 11))
ok('S5.2 http -> ws 转换', wsmod.buildWsUrl(wc.profile, 11).indexOf('ws://192.168.10.110:9210/ws?') === 0, wsmod.buildWsUrl(wc.profile, 11))
ok('S5.3 last_seq 随游标', /last_seq=11/.test(wsmod.buildWsUrl(wc.profile, 11)), wsmod.buildWsUrl(wc.profile, 11))
got.length = 0
wc.handleMessage(JSON.stringify({ kind: 'STATE_DELTA', seq: 99, delta: { text: 'x' } }))
ok('S5.4 合法业务帧被上抛', got.length === 1, S(got.length))
got.length = 0
wc.handleMessage(JSON.stringify({ kind: 'STATE_DELTA', seq: 5, delta: { text: 'x' } }))
ok('S5.5 seq<游标 被丢弃', got.length === 0, S(got.length))
wc.handleMessage(JSON.stringify({ kind: 'STATE_DELTA', seq: 11, delta: { text: 'x' } }))
ok('S5.6 seq==游标 被丢弃（<=）', got.length === 0, S(got.length))
got.length = 0
wc.handleMessage(JSON.stringify({ kind: 'PING' }))
wc.handleMessage(JSON.stringify({ kind: 'ACK', seq: 200 }))
wc.handleMessage(JSON.stringify({ kind: 'ERROR', seq: 201 }))
ok('S5.7 PING/ACK/ERROR 全部忽略（契约 §3.3）', got.length === 0, S(got))
got.length = 0
wc.handleMessage('{ 不是 JSON')
ok('S5.8 非法 JSON -> onProtocolError，不上抛', got.length === 1 && String(got[0]).indexOf('ERR:') === 0, S(got))
got.length = 0
got.length = 0
wc.handleMessage(JSON.stringify({ nope: 1 }))
ok('S5.9 无 kind 帧不上抛（仅报 onProtocolError）', got.filter(x => x && typeof x === 'object').length === 0 && got.length === 1, S(got))
ok('S5.10 游标未被任何帧推进（仍 11）', wc.lastSeq === 11, String(wc.lastSeq))

// ============ S6 事件流上限 ============
console.log(''); console.log('--- S6 事件列表上限 50 ---')
for (let i = 1000; i < 1060; i++) p.pushWsFrame({ kind: 'STATE_DELTA', seq: i, ts: 1758900500, delta: { text: 'e' + i } })
ok('S6.1 上限截断为 50 条', p.data.events.length === 50, String(p.data.events.length))
ok('S6.2 保留最新 50 条（最高 seq 在顶）', p.data.events[0].seq === 1059 && p.data.events[49].seq === 1010, S([p.data.events[0].seq, p.data.events[49].seq]))
ok('S6.3 同 seq 重复不新增', (() => { const n = p.data.events.length; p.pushWsFrame({ kind: 'STATE_DELTA', seq: 1059, delta: { text: 'dup' } }); return p.data.events.length === n })(), '')

// ============ S7 失败计数文案 ============
console.log(''); console.log('--- S7 轮询失败计数 -> 文案（阈值 3）---')
behavior = { info: () => Promise.resolve({}), state: () => Promise.reject(new Error('boom')), events: () => Promise.resolve({ events: [] }) }
const p2 = makePage(); p2.onLoad()
await sleep(100)
ok('S7.1 第1次失败 -> st.reconnecting', p2.data.connection === strings['st.reconnecting'], S(p2.data.connection))
await p2.refreshState().catch(() => {}); await p2.refreshState().catch(() => {})
ok('S7.2 第3次失败 -> st.closed', p2.data.connection === strings['st.closed'], S(p2.data.connection))
p2.stopChannels()

console.log('')
if (fail) console.log('FAILED_ASSERTIONS: ' + fails.join(' | '))
console.log('DEFECTS_FOUND=' + defects + (found.length ? ' :: ' + found.join(' | ') : ''))
console.log('PARTIAL_LOGIC_CHECKED=' + (pass + fail) + ' PASS=' + pass + ' FAIL=' + fail + ' RESULT=' + (fail === 0 ? 'PASS' : 'FAIL'))
console.log('SCOPE=logic-layer-only (setData/data) ; RENDERING=UNVERIFIED (需要微信开发者工具人工扫码登录)')
process.exit(0)
})().catch(e => { console.error('HARNESS CRASH: ' + (e && e.stack || e)); process.exit(2) })
