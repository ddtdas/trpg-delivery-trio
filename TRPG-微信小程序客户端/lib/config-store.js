/**
 * config-store.js —— 玩家端本地配置（微信小程序 storage）
 *
 * 存储键与 PC 端（localStorage）同名同义：trpg.server / trpg.code /
 * trpg.playerId / trpg.playerName / trpg.token，另有 trpg.tableId / trpg.campaign。
 * mobile token 只存本机 storage：不硬编码、不写日志、不随事件上报。
 */
const strings = require('../strings')

const KEYS = {
  server: 'trpg.server',
  code: 'trpg.code',
  playerId: 'trpg.playerId',
  playerName: 'trpg.playerName',
  token: 'trpg.token',
  tableId: 'trpg.tableId',
  campaign: 'trpg.campaign'
}

// 默认服务器地址：**留空**（不绑定任何内网 IP / 域名，交付给他人时不携带本环境信息）。
// 由用户在「连接设置」页填写主持端地址（占位符文案见契约 §5 ph.server，仅作示例提示，不是预填值）。
const DEFAULT_SERVER = ''

function getRaw(key) {
  const value = wx.getStorageSync(key)
  return value === '' || value === null || value === undefined ? '' : value
}

function normalizeServer(value) {
  return String(value || '').trim().replace(/\/+$/, '')
}

function load() {
  return {
    server: getRaw(KEYS.server) || DEFAULT_SERVER,
    code: String(getRaw(KEYS.code) || ''),
    playerId: String(getRaw(KEYS.playerId) || ''),
    playerName: String(getRaw(KEYS.playerName) || ''),
    token: String(getRaw(KEYS.token) || ''),
    tableId: String(getRaw(KEYS.tableId) || ''),
    campaign: String(getRaw(KEYS.campaign) || '')
  }
}

function save(profile) {
  const next = Object.assign(load(), profile || {})
  next.server = normalizeServer(next.server)
  next.code = String(next.code || '').trim()
  next.playerId = String(next.playerId || '').trim()
  next.playerName = String(next.playerName || '').trim()
  next.token = String(next.token || '').trim()
  wx.setStorageSync(KEYS.server, next.server)
  wx.setStorageSync(KEYS.code, next.code)
  wx.setStorageSync(KEYS.playerId, next.playerId)
  wx.setStorageSync(KEYS.playerName, next.playerName)
  wx.setStorageSync(KEYS.token, next.token)
  wx.setStorageSync(KEYS.tableId, String(next.tableId || ''))
  wx.setStorageSync(KEYS.campaign, String(next.campaign || ''))
  return next
}

function clear() {
  Object.keys(KEYS).forEach(function (name) { wx.removeStorageSync(KEYS[name]) })
}

/** last_seq 存储键规则（契约 §3，与 PC 端 key 规则相同）：trpg_last_seq_<table> */
function lastSeqKey(tableId) {
  return 'trpg_last_seq_' + String(tableId || '')
}

function loadLastSeq(tableId) {
  const raw = wx.getStorageSync(lastSeqKey(tableId))
  if (raw === '' || raw === null || raw === undefined) return -1
  const value = Number(raw)
  return Number.isFinite(value) ? value : -1
}

function saveLastSeq(tableId, seq) {
  wx.setStorageSync(lastSeqKey(tableId), Number(seq))
}

function clearLastSeq(tableId) {
  wx.removeStorageSync(lastSeqKey(tableId))
}

/** F1/F2 校验：服务器地址 + mobile token。返回 '' 表示通过，否则返回文案。 */
function validate(profile) {
  if (!normalizeServer(profile && profile.server)) return strings['ext.st.needServer']
  if (!/^https?:\/\//i.test(normalizeServer(profile.server))) return strings['ext.st.needServer']
  if (!String((profile && profile.token) || '').trim()) return strings['ext.st.needToken']
  return ''
}

/** F3/F4 校验：服务器 + token + 玩家 ID + 连接码。 */
function validateJoin(profile) {
  const base = validate(profile)
  if (base) return base
  if (!String((profile && profile.playerId) || '').trim()) return strings['ext.st.needPlayerId']
  if (!String((profile && profile.code) || '').trim()) return strings['ext.st.needCode']
  return ''
}

module.exports = {
  KEYS: KEYS,
  DEFAULT_SERVER: DEFAULT_SERVER,
  normalizeServer: normalizeServer,
  load: load,
  save: save,
  clear: clear,
  validate: validate,
  validateJoin: validateJoin,
  lastSeqKey: lastSeqKey,
  loadLastSeq: loadLastSeq,
  saveLastSeq: saveLastSeq,
  clearLastSeq: clearLastSeq
}
