/**
 * event-view.js —— F7 事件流视图层（契约 §4.1 F7 + §7 R1）
 *
 * 命名空间：本文件只处理**事件流 type**（命名空间 B），不处理 WS 帧 kind（命名空间 A）。
 *  - 类型标签：§5.2 ev.<type>；未知 type → ev.OTHER + 原始 type 文本
 *  - 可见性过滤（R1）：REST 事件流端点无服务端过滤，客户端必须按 payload.scope/targets
 *    自过滤：scope 缺省或 public → 可见；scope=whisper → 仅 targets 含本人；
 *    scope=condition → 仅 targets 含本人或 condition_met 为真
 *  - 文本抽取：按事件类型取可读字段，未知类型回退 JSON
 */
const strings = require('../strings')

const TEXT_PATHS = [
  ['text'], ['body'], ['body_ref'], ['label'], ['message'], ['summary'],
  ['seg', 'text'], ['action', 'text'], ['next_preview'], ['line'], ['reason'],
  ['ref'], ['clue_id'], ['transcript_ref'], ['truth_tree_ref'], ['summary_ref'],
  ['role_ref'], ['npc_id'], ['op'], ['level'], ['status_text'], ['info_id']
]

function pick(obj, pathParts) {
  let cur = obj
  for (let i = 0; i < pathParts.length; i += 1) {
    if (cur === null || cur === undefined || typeof cur !== 'object') return undefined
    cur = cur[pathParts[i]]
  }
  return cur
}

/** type → 中文标签（未知 type → 「其他事件 <原始 type>」） */
function label(type) {
  const key = 'ev.' + String(type || '')
  if (Object.prototype.hasOwnProperty.call(strings, key)) return strings[key]
  return strings['ev.OTHER'] + ' ' + String(type || '')
}

/** R1：按 payload.scope / targets / condition_met 判定该事件是否对当前玩家可见。 */
function visible(event, playerId) {
  const payload = (event && event.payload) || {}
  const scope = payload.scope
  if (scope === undefined || scope === null || scope === 'public') return true
  const targets = Array.isArray(payload.targets) ? payload.targets : []
  const mine = targets.indexOf(playerId) >= 0
  if (scope === 'whisper') return mine
  if (scope === 'condition') return mine || payload.condition_met === true
  return true
}

/** 事件文本：先按类型组装（信息量最大），再取通用文本字段，最后回退 JSON。 */
function text(event) {
  const payload = (event && event.payload) || {}
  const type = String((event && event.type) || '')
  if (type === 'ACTION_SUBMITTED') {
    const who = String(payload.player_id || (event && event.actor) || '')
    const action = payload.action && payload.action.text ? payload.action.text : JSON.stringify(payload.action || {})
    const intent = payload.intent_summary ? '（' + payload.intent_summary + '）' : ''
    return who + '：' + action + intent
  }
  if (type === 'TURN_STARTED') return '第 ' + String(payload.turn_no) + ' 回合'
  if (type === 'TURN_CLOSED') return '第 ' + String(payload.turn_no) + ' 回合结束'
  if (type === 'CHECK_RESOLVED') {
    return String(payload.card_id || '') + ' 目标 ' + String(payload.target) + ' 难度 ' + String(payload.difficulty)
      + ' 合计 ' + String(payload.total) + ' · ' + String(payload.level)
  }
  if (type === 'VOTE_CAST') return String(payload.player_id || '') + ' → ' + String(payload.target_player_id || '')
  if (type === 'ROLE_ASSIGNED') return String(payload.player_id || '') + ' · ' + String(payload.role_ref || '')
  if (type === 'EVIDENCE_DEALT') return String(payload.location || '') + ' · ' + String(payload.clue_id || '')
  for (let i = 0; i < TEXT_PATHS.length; i += 1) {
    const value = pick(payload, TEXT_PATHS[i])
    if (typeof value === 'string' && value) return value
  }
  return JSON.stringify(payload)
}

function timeText(ts) {
  if (ts === undefined || ts === null || ts === '') return ''
  let value = ts
  if (typeof value === 'number' && value < 1e12) value = value * 1000
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(ts)
  const pad = function (n) { return String(n).length < 2 ? '0' + n : String(n) }
  return pad(date.getHours()) + ':' + pad(date.getMinutes()) + ':' + pad(date.getSeconds())
}

/** 事件流条目 → 渲染项（id 用 seq，保证去重与稳定排序） */
function toItem(event, playerId) {
  return {
    id: String((event && event.seq) === undefined ? '' : event.seq),
    seq: (event && event.seq) === undefined ? -1 : event.seq,
    kind: label(event && event.type),
    text: text(event),
    time: timeText(event && event.ts)
  }
}

/**
 * 合并事件流（契约 §3.4.2 + §4.1 F7）：
 *  - 按 seq 去重（同一 seq 的轮询结果与 WS 帧只渲染一次）
 *  - **seq 降序渲染（最新在最上）**
 *  - 只保留最新 max 条（默认 50）
 *  - 渲染前按 §7 R1 做可见性过滤
 */
function mergeFeed(items, events, playerId, max) {
  const limit = max || 50
  const bySeq = {}
  ;(items || []).forEach(function (item) {
    if (item && item.seq !== undefined && item.seq !== null) bySeq[String(item.seq)] = item
  })
  ;(events || []).forEach(function (event) {
    const seq = event && event.seq
    if (seq === undefined || seq === null) return
    if (!visible(event, playerId)) return
    bySeq[String(seq)] = toItem(event, playerId)
  })
  const all = Object.keys(bySeq).map(function (key) { return bySeq[key] })
  all.sort(function (a, b) { return b.seq - a.seq })
  return all.slice(0, limit)
}

/** 合并一条 WS 增强帧（命名空间 A 的 kind）：同 seq 已存在则不再渲染（§3.4.2）。 */
function mergeFrame(items, frame, frameTextValue, frameTimeValue, max) {
  const limit = max || 50
  const list = (items || []).slice()
  const seq = frame && frame.seq
  if (seq === undefined || seq === null) return list
  const key = String(seq)
  for (let i = 0; i < list.length; i += 1) {
    if (String(list[i].seq) === key) return list
  }
  list.push({ id: key, seq: seq, kind: String(frame.kind), text: frameTextValue || '', time: frameTimeValue || '' })
  list.sort(function (a, b) { return b.seq - a.seq })
  return list.slice(0, limit)
}

module.exports = {
  label: label,
  visible: visible,
  text: text,
  timeText: timeText,
  toItem: toItem,
  mergeFeed: mergeFeed,
  mergeFrame: mergeFrame
}
