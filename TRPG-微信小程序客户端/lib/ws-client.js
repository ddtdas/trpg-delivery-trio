/**
 * ws-client.js —— 直连主持端服务器 /ws 事件流（契约 §3，只订阅不改冻结契约）
 *
 * 握手：ws(s)://<host>/ws?table=<table>&viewer=<playerId>&role=pl&last_seq=<n>&token=<mobile token>
 * 下行：8 类业务帧 + PING（15s 心跳，不进事件列表）。
 * last_seq：持久化键 trpg_last_seq_<table>（与 PC 端 key 规则相同），重连时带上以补齐。
 * 断线：指数退避 1/2/4/8s 上限 30s；30s 无帧主动重连。
 */
const store = require('./config-store')
const strings = require('../strings')
const { format } = require('./strings-map')

const DOWNSTREAM_KINDS = [
  'STATE_DELTA', 'TURN_UPDATED', 'NARRATION_PENDING', 'NARRATION_APPROVED',
  'WHISPER', 'INFO_REVEALED', 'BRANCH_TAKEN', 'JOB_STATUS'
]
const PING_KIND = 'PING'
const BACKOFF_MAX_MS = 30000
const IDLE_RECONNECT_MS = 30000

const STATUS_TEXT = {
  connecting: strings['st.connecting'],
  connected: strings['st.connected'],
  reconnecting: strings['st.reconnecting'],
  closed: strings['st.closed']
}

/** 退避序列：1s/2s/4s/8s/16s… 上限 30s。 */
function backoffMs(retry) {
  const n = Math.max(0, Number(retry) || 0)
  return Math.min(BACKOFF_MAX_MS, 1000 * Math.pow(2, n))
}

function buildWsUrl(profile, lastSeq) {
  const base = String((profile && profile.server) || '').trim().replace(/\/+$/, '').replace(/^http/i, 'ws')
  const params = [
    'table=' + encodeURIComponent((profile && profile.tableId) || ''),
    'viewer=' + encodeURIComponent((profile && profile.playerId) || ''),
    'role=pl',
    'last_seq=' + encodeURIComponent(lastSeq === undefined || lastSeq === null ? -1 : lastSeq),
    'token=' + encodeURIComponent((profile && profile.token) || '')
  ]
  return base + '/ws?' + params.join('&')
}

/** WS 帧正文：用 ext.ev.* 模板（与 PC 端逐字收敛）；REST 主通道的事件文本另见 lib/event-view.js。 */
function frameText(frame) {
  if (!frame) return ''
  const kind = frame.kind
  if (kind === 'STATE_DELTA') {
    const delta = frame.delta || {}
    return format(strings['ext.ev.delta'], { delta: delta.text || delta.message || delta.summary || JSON.stringify(delta) })
  }
  if (kind === 'TURN_UPDATED') {
    const turn = frame.turn || {}
    return format(strings['ext.ev.turn'], { turn_no: turn.turn_no === undefined ? '-' : turn.turn_no, state: turn.state || '' })
  }
  if (kind === 'NARRATION_PENDING') {
    const text = String((frame.proposal || {}).text || '')
    return format(strings['ext.ev.narrationPending']) + (text ? ' · ' + text : '')
  }
  if (kind === 'NARRATION_APPROVED') return String((frame.narration || {}).text || '')
  if (kind === 'WHISPER') {
    return format(strings['ext.ev.directed'], { body: String((frame.packet || {}).body || '') })
  }
  if (kind === 'INFO_REVEALED') {
    const packet = frame.packet || {}
    const body = String(packet.body || '')
    return format(strings['ext.ev.info'], { info_id: packet.info_id || '' }) + (body ? ' · ' + body : '')
  }
  if (kind === 'BRANCH_TAKEN') {
    const branch = frame.branch || {}
    return format(strings['ext.ev.branch'], { label: branch.label || branch.node_id || '' })
  }
  if (kind === 'JOB_STATUS') {
    const job = frame.job || {}
    return format(strings['ext.ev.job'], { job_id: job.job_id || '', status: job.status || '' })
  }
  return JSON.stringify(frame)
}

function frameTime(frame) {
  if (!frame || frame.ts === undefined || frame.ts === null) return ''
  let value = frame.ts
  if (typeof value === 'number') {
    if (value < 1e12) value = value * 1000
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(frame.ts)
  const pad = function (n) { return String(n).length < 2 ? '0' + n : String(n) }
  return pad(date.getHours()) + ':' + pad(date.getMinutes()) + ':' + pad(date.getSeconds())
}

class WsClient {
  constructor(profile, handlers) {
    this.profile = profile || {}
    this.handlers = handlers || {}
    this.tableId = String(this.profile.tableId || '')
    this.lastSeq = store.loadLastSeq(this.tableId)
    this.closedByUser = false
    this.retry = 0
    this.task = null
    this.reconnectTimer = null
    this.idleTimer = null
  }

  currentStatus() {
    return this.status || 'closed'
  }

  /** R12：由页面把「轮询推进后的权威游标」回灌给 WS 客户端，
      保证重连（buildWsUrl 带 last_seq）只补发真正缺失的帧。 */
  setLastSeq(seq) {
    const n = Number(seq)
    if (!Number.isNaN(n)) this.lastSeq = n
  }

  emitStatus(status, extra) {
    this.status = status
    if (this.handlers.onStatus) this.handlers.onStatus(status, STATUS_TEXT[status] || '', extra || {})
  }

  start() {
    if (this.closedByUser || this.task) return
    this.emitStatus('connecting')
    let task = null
    try {
      task = wx.connectSocket({ url: buildWsUrl(this.profile, this.lastSeq), timeout: 12000 })
    } catch (err) {
      // 契约 §3.4.2：连不上（含构造即抛错）→ 静默降级：不抛给调用方、不报错、不阻塞 UI、不改任何可见文案
      this.emitStatus('closed', { error: err })
      this.scheduleReconnect()
      return
    }
    this.task = task
    task.onOpen(function () {
      this.retry = 0
      this.emitStatus('connected')
      this.touchIdle()
    }.bind(this))
    task.onMessage(function (res) {
      this.touchIdle()
      this.handleMessage(res && res.data)
    }.bind(this))
    task.onError(function (err) {
      if (this.handlers.onError) this.handlers.onError(err)
    }.bind(this))
    task.onClose(function (event) {
      this.task = null
      this.clearIdle()
      this.emitStatus('closed', { event: event })
      if (!this.closedByUser) this.scheduleReconnect()
    }.bind(this))
  }

  handleMessage(raw) {
    let frame = null
    try {
      frame = typeof raw === 'string' ? JSON.parse(raw) : raw
    } catch (err) {
      if (this.handlers.onProtocolError) this.handlers.onProtocolError('收到无法解析的 WS 数据')
      return
    }
    if (!frame || typeof frame.kind !== 'string') {
      if (this.handlers.onProtocolError) this.handlers.onProtocolError('未知 WS 帧')
      return
    }
    if (frame.kind === PING_KIND) return
    // 契约 §3.3：ACK / ERROR 不属于冻结的 8 类下行帧，客户端必须忽略（不崩溃、不写事件列表）
    if (DOWNSTREAM_KINDS.indexOf(frame.kind) < 0) return
    // 契约 §3.4.2（v1.9/v1.10）：last_seq **只由轮询推进，绝不由 WS 帧推进**。
    // WS 可能只发布部分事件，用帧 seq 推进会跳过中间 seq → 轮询路径漏事件。
    // 帧 seq <= 本地游标 → 丢弃（已渲染过）；> 游标 → 交给上层渲染，但不推进游标、不落盘。
    if (typeof frame.seq === 'number' && frame.seq <= this.lastSeq) return
    if (this.handlers.onFrame) this.handlers.onFrame(frame)
  }

  scheduleReconnect() {
    if (this.closedByUser) return
    const wait = backoffMs(this.retry)
    this.retry += 1
    this.emitStatus('reconnecting', { wait: wait })
    clearTimeout(this.reconnectTimer)
    this.reconnectTimer = setTimeout(function () {
      this.reconnectTimer = null
      this.start()
    }.bind(this), wait)
  }

  touchIdle() {
    this.clearIdle()
    this.idleTimer = setTimeout(function () {
      this.idleTimer = null
      this.forceReconnect()
    }.bind(this), IDLE_RECONNECT_MS)
  }

  clearIdle() {
    if (this.idleTimer) {
      clearTimeout(this.idleTimer)
      this.idleTimer = null
    }
  }

  /** 30s 无帧：主动断开并重连（带 last_seq 补齐）。 */
  forceReconnect() {
    if (this.closedByUser) return
    const task = this.task
    this.task = null
    if (task) {
      try { task.close({ code: 1000, reason: 'idle' }) } catch (err) { /* 忽略关闭失败 */ }
    }
    this.scheduleReconnect()
  }

  stop() {
    this.closedByUser = true
    clearTimeout(this.reconnectTimer)
    this.reconnectTimer = null
    this.clearIdle()
    const task = this.task
    this.task = null
    if (task) {
      try { task.close({ code: 1000, reason: 'leave' }) } catch (err) { /* 忽略关闭失败 */ }
    }
  }
}

module.exports = {
  WsClient: WsClient,
  DOWNSTREAM_KINDS: DOWNSTREAM_KINDS,
  PING_KIND: PING_KIND,
  BACKOFF_MAX_MS: BACKOFF_MAX_MS,
  IDLE_RECONNECT_MS: IDLE_RECONNECT_MS,
  STATUS_TEXT: STATUS_TEXT,
  backoffMs: backoffMs,
  buildWsUrl: buildWsUrl,
  frameText: frameText,
  frameTime: frameTime
}
