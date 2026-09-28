/**
 * api-client.js —— 直连主持端服务器 9210 的 /access 契约（无中转层）
 *
 * 鉴权：Authorization: Bearer <mobile token>（契约 §1）。
 * 统一响应包裹：成功 {ok:true,data,code:0}；失败 {ok:false,error,code:<http>}。
 * 端点（契约 §1）：GET /access/info、GET /access/table/resolve、
 * GET /access/mobile/state、POST /access/mobile/action、
 * POST /access/player/audio、GET /access/device/status。
 */
const strings = require('../strings')

class ApiError extends Error {
  constructor(message, code, status) {
    super(message)
    this.name = 'ApiError'
    // code=0 表示本地网络失败（非 HTTP 错误码），不能回退成 500
    const resolved = code === undefined || code === null || code === '' ? status : code
    this.code = Number(resolved || 0)
    this.status = Number(status || 0)
  }
}

function unwrap(status, body) {
  if (body && body.ok === true) return body.data
  if (body && body.ok === false) {
    throw new ApiError(body.error || strings['err.server'], body.code, status)
  }
  throw new ApiError(strings['err.server'], status || 500, status)
}

/** 统一文案映射（契约 §5 err.*）：401 身份验证失败 / 404 连接码不存在 / 5xx 服务端异常 / 网络失败。 */
function humanize(err) {
  if (!err) return strings['err.server']
  if (err.name === 'ApiError') {
    if (err.code === 401) return strings['err.auth']
    if (err.code === 404) return strings['err.notFound']
    if (err.code >= 500) return strings['err.server']
    return err.message || strings['err.server']
  }
  return strings['err.net']
}

function queryString(query) {
  if (!query) return ''
  const parts = []
  Object.keys(query).forEach(function (key) {
    const value = query[key]
    if (value === undefined || value === null || value === '') return
    parts.push(encodeURIComponent(key) + '=' + encodeURIComponent(value))
  })
  return parts.length ? '?' + parts.join('&') : ''
}

class ApiClient {
  constructor(profile) {
    this.profile = profile || {}
  }

  base() {
    return String(this.profile.server || '').trim().replace(/\/+$/, '')
  }

  url(path, query) {
    return this.base() + path + queryString(query)
  }

  headers() {
    return {
      'content-type': 'application/json',
      Authorization: 'Bearer ' + String(this.profile.token || '')
    }
  }

  request(method, path, options) {
    const opts = options || {}
    return new Promise(function (resolve, reject) {
      wx.request({
        url: this.url(path, opts.query),
        method: method,
        data: opts.data,
        header: this.headers(),
        timeout: 15000,
        success: function (res) {
          try {
            resolve(unwrap(res.statusCode, res.data))
          } catch (err) {
            reject(err)
          }
        },
        fail: function () {
          reject(new ApiError(strings['err.net'], 0, 0))
        }
      })
    }.bind(this))
  }

  /** F1：服务信息 + 三端启用状态（任意启用端 token）。 */
  info() {
    return this.request('GET', '/access/info')
  }

  /** F2：连接码 → {code,table_id,campaign,name,exists}（任意启用端 token）。 */
  resolveCode(code) {
    return this.request('GET', '/access/table/resolve', { query: { code: code } })
  }

  /** F5：会话状态（mobile 端 token）。 */
  state(tableId) {
    return this.request('GET', '/access/mobile/state', { query: { table_id: tableId } })
  }

  /** F6：行动提交（mobile 端 token，req_id 幂等）。 */
  submitAction(payload) {
    return this.request('POST', '/access/mobile/action', { data: payload })
  }

  /** F9：录音设备状态只读（任意启用端 token；无记录 → 404）。 */
  deviceStatus(deviceId) {
    return this.request('GET', '/access/device/status', { query: { device_id: deviceId } })
  }

  /**
   * F7 主通道：GET /api/campaigns/{campaign}/events?since=&limit=
   * 注意（契约 §1.3）：/api/* 层**不使用** {ok,data} 包裹 —— 成功直接返回 {events,tip}，
   * 失败返回 {detail:"…"} + 4xx/422，故此处单独解析。
   */
  events(campaign, since, limit) {
    // R9（additive）：改走 mobile 端事件流 —— 服务端按 viewer 权威裁剪后才下发
    // （只给可见 DTO，不再下发全量后靠客户端过滤）。响应是统一包裹 {ok,data}。
    const path = '/access/mobile/events'
    const query = {
      table_id: String(this.profile.tableId || campaign || ''),
      viewer: String(this.profile.playerId || ''),
      since: since === undefined || since === null ? -1 : since,
      limit: limit || 50
    }
    return new Promise(function (resolve, reject) {
      wx.request({
        url: this.url(path, query),
        method: 'GET',
        header: this.headers(),
        timeout: 15000,
        success: function (res) {
          let data = null
          try {
            data = unwrap(res.statusCode, res.data)
          } catch (err) {
            reject(err)
            return
          }
          resolve({ events: (data && data.events) || [], tip: data && data.tip })
        },
        fail: function () {
          reject(new ApiError(strings['err.net'], 0, 0))
        }
      })
    }.bind(this))
  }

  /** M3 (T6): 四态 + 玩家状态（mobile/webapp token）。 */
  chatStatus(campaign) {
    return this.request('GET', '/api/campaigns/' + encodeURIComponent(campaign) + '/chat/status')
  },

  /** M3 (T6): 发送私聊 / 公共消息（mobile token；_public_ = 公共频道）。 */
  chatSend(campaign, payload) {
    return this.request('POST', '/api/campaigns/' + encodeURIComponent(campaign) + '/chat/private', { data: payload })
  },

  /**
   * F8：玩家录音上传（mobile 端 token，multipart: file/campaign/kind/player_id）。
   * ⚠ 只带 Authorization：**不得**带 content-type —— multipart 的 Content-Type（含 boundary）
   * 必须由 wx.uploadFile 自行设置，显式给 application/json 会导致服务端解析不到 file 字段（实测 400）。
   */
  uploadAudio(filePath, formData) {
    return new Promise(function (resolve, reject) {
      wx.uploadFile({
        url: this.url('/access/player/audio'),
        filePath: filePath,
        name: 'file',
        header: { Authorization: 'Bearer ' + String(this.profile.token || '') },
        formData: formData || {},
        timeout: 60000,
        success: function (res) {
          let body = null
          try {
            body = JSON.parse(res.data)
          } catch (err) {
            reject(new ApiError(strings['err.server'], res.statusCode, res.statusCode))
            return
          }
          try {
            resolve(unwrap(res.statusCode, body))
          } catch (err) {
            reject(err)
          }
        },
        fail: function () {
          reject(new ApiError(strings['err.net'], 0, 0))
        }
      })
    }.bind(this))
  }
}

module.exports = { ApiClient: ApiClient, ApiError: ApiError, unwrap: unwrap, humanize: humanize, queryString: queryString }