const store = require('../../lib/config-store')
const { map, format } = require('../../lib/strings-map')
const { ApiClient, humanize } = require('../../lib/api-client')
const reqId = require('../../lib/req-id')
const wsmod = require('../../lib/ws-client')
const eventView = require('../../lib/event-view')

const T = map()
const MAX_EVENTS = 50      // 契约 §4 F7：展示最新 50 条
const FETCH_LIMIT = 1000   // 契约 §4.1 F7 取数规则 (a)：首次 since=-1&limit=1000，客户端取最新 50
const POLL_LIMIT = 50      // 契约 §3.4.1：轮询 since=<last_seq>&limit=50
const CATCHUP_ROUNDS = 3   // 一次拉满 ⇒ 立即续拉，保证不滞后（§4.1 F7(a) 的意图：不丢事件）
const POLL_MS = 15000      // R12：轮询降级为兜底（15s 心跳）；实时性由 WS 推送驱动
const PUSH_DEBOUNCE_MS = 60 // R12：WS 帧到达 -> 立即拉权威数据（去抖合并同批帧）

Page({
  data: {
    T: T,
    profile: {},
    turn: null,
    turnLine: '',
    countsText: '',
    events: [],
    connection: '',
    error: '',
    actionText: '',
    intent: '',
    submitting: false,
    canSubmit: false,
    lastSubmit: '',
    // M3 (T6): 私聊/公共频道
    chatBadge: '',
    chatMode: 'chat_enabled',
    chatPlayers: [],
    chatTargetIndex: -1,
    chatTargetName: '',
    chatText: '',
    chatSending: false,
    chatInputDisabled: false,
    chatInputPlaceholder: '',
    chatErr: '',
    chatOk: '',
    chatLog: [],
    chatLastLoad: 0
  },

  onLoad() {
    const profile = store.load()
    if (!profile.tableId) {
      wx.switchTab({ url: '/pages/setup/setup' })
      return
    }
    this.profile = profile
    this.campaign = profile.campaign || profile.tableId
    this.client = new ApiClient(profile)
    // last_seq 键规则与 PC 端相同：trpg_last_seq_<table>
    this.lastSeq = store.loadLastSeq(profile.tableId)
    // F10 状态行：四态**只由轮询驱动**（契约 §3.4.2：WS 连不上/403/被拒/断开 → 静默降级，
    // 不得报错、不得阻塞 UI、**不得改变任何文案**）；WS 状态只记在内存，不写任何可见文案。
    this.pollFails = 0
    this.setData({ profile: profile, connection: T.st_connecting })
    this.loaded = true
    this.startChannels()
  },

  /** tab 重新可见：恢复轮询与订阅 */
  onShow() {
    if (this.loaded) this.startChannels()
  },

  /** tab 隐藏：暂停轮询与订阅，避免后台常驻 */
  onHide() {
    this.stopChannels()
  },

  onUnload() {
    this.loaded = false
    this.stopChannels()
  },

  startChannels() {
    if (this.poller || !this.loaded) return
    // F5 + F7 主通道（契约 §3.4.1：无论 WS 是否可用都必须实现）
    this.chatRefresh(true)
    this.refresh(true)
    this.poller = setInterval(function () { this.refresh(false) }.bind(this), POLL_MS)
    this.ensureWs()
  },

  stopChannels() {
    if (this.poller) clearInterval(this.poller)
    this.poller = null
    if (this.ws) {
      this.ws.stop()
      this.ws = null
    }
  },

  /**
   * 契约 §3.1：**先**用 GET /access/info 校验 token 与可达性，**再**尝试 WS。
   * 契约 §3.4.2：连不上/握手 403/被拒/断开 → 静默降级（只走轮询，不报错、不改文案、不阻塞 UI）。
   * 不得依赖 WS 关闭码或握手状态码做错误分类（4400 永不到达，403 不可细分）。
   */
  ensureWs() {
    if (this.ws) {
      this.ws.start()
      return
    }
    this.client.info().then(function () {
      if (!this.loaded || this.ws) return
      this.ws = new wsmod.WsClient(this.profile, {
        // 契约 §3.4.2：WS 状态只记在内存（this.wsState），**不写任何可见文案**；失败静默降级
        onStatus: function (status) { this.wsState = status }.bind(this),
        onFrame: function (frame) { this.pushWsFrame(frame) }
      }.bind(this))
      this.ws.start()
    }.bind(this)).catch(function () {
      // 静默降级：WS 不可用不改变任何可见文案（F10 状态行只由轮询驱动）
      this.wsState = 'closed'
    }.bind(this))
  },

  refresh(initial) {
    return this.refreshState().then(function () {
      this.chatRefresh(false)
      return this.pollEvents(initial)
    }.bind(this))
  },

  /** F5：GET /access/mobile/state?table_id= */
  refreshState() {
    return this.client.state(this.profile.tableId).then(function (state) {
      const turn = state.turn || null
      const byType = state.by_type || {}
      this.setData({
        turn: turn,
        turnLine: turn ? format(T.ext_turn_line, { turn_no: turn.turn_no, state: turn.state, submitted: turn.submitted }) : '',
        countsText: Object.keys(byType).sort().map(function (key) { return key + '=' + byType[key] }).join(' '),
        // 契约 §7 R2：只把 COLLECTING 当作可提交，其余状态原样显示字符串
        canSubmit: !!turn && turn.state === 'COLLECTING',
        connection: T.st_connected
      })
      this.pollFails = 0
    }.bind(this)).catch(function (err) {
      // 与 PC app.js:352-353 同语义：连续失败 <3 次显示 重连中…，≥3 次显示 已断开
      this.pollFails += 1
      this.setData({ connection: this.pollFails >= 3 ? T.st_closed : T.st_reconnecting, error: humanize(err) })
    }.bind(this))
  },

  /**
   * F7 主通道（契约 §4.1 F7 取数规则 (a)）：
   *   首次：since=-1&limit=1000 → 客户端按 seq 取**最新 50 条** → 降序渲染
   *   之后：since=<本地 last_seq>&limit=50 → 新事件插入顶部（降序）；满 50 则续拉，最多 3 轮（§3.4.1）
   * ⚠ 陷阱：since=-1&limit=50 返回的是**最旧**的 50 条，不得直接当「最新 50 条」渲染。
   */
  pollEvents(initial, round) {
    const attempt = round || 0
    const since = initial ? -1 : this.lastSeq
    const limit = initial ? FETCH_LIMIT : POLL_LIMIT
    return this.client.events(this.campaign, since, limit).then(function (res) {
      const list = res.events || []
      let maxSeq = this.lastSeq
      list.forEach(function (event) {
        if (typeof event.seq === 'number' && event.seq > maxSeq) maxSeq = event.seq
      })
      this.lastSeq = maxSeq
      store.saveLastSeq(this.profile.tableId, this.lastSeq)
      if (this.ws) this.ws.setLastSeq(this.lastSeq)   // R12：回灌游标，重连精确追平
      // 合并 + 去重 + 降序 + 取最新 50（可见性过滤在 mergeFeed 内做，§7 R1）
      this.setData({ events: eventView.mergeFeed(this.data.events, list, this.profile.playerId, MAX_EVENTS) })
      // 一次拉满 ⇒ 后面可能还有（服务端是「取前 limit 条」），立即续拉，避免滞后
      if (list.length >= limit && attempt < CATCHUP_ROUNDS) return this.pollEvents(false, attempt + 1)
      return null
    }.bind(this)).catch(function (err) {
      // 与 PC app.js:552-556 对齐：事件流失败只显示错误条，**不改状态行**
      // （状态行四态只由 refreshState 的轮询失败计数驱动）
      this.setData({ error: humanize(err) })
    }.bind(this))
  },

  /**
   * WS 增强帧（可选）：按 seq 去重后并入事件流，最新在最上（契约 §3.4.2）。
   * - seq <= 本地 last_seq ⇒ 已被轮询覆盖/已显示过，直接丢弃（恢复后不得重复渲染）
   * - **不**用 WS 帧推进 last_seq：游标权威恒为轮询（避免 WS 只发布部分事件时漏掉中间 seq）
   */
  pushWsFrame(frame) {
    const seq = frame && frame.seq
    if (typeof seq === 'number' && seq <= this.lastSeq) return
    this.setData({
      events: eventView.mergeFrame(this.data.events, frame, wsmod.frameText(frame), wsmod.frameTime(frame), MAX_EVENTS)
    })
    // R12：推送驱动 —— 帧到达即拉权威数据（去抖），不再等兜底轮询
    this.pushRefresh()
    if (frame.kind === 'WHISPER') this.chatOnWhisper(frame)
    if (frame.kind === 'STATE_DELTA' && (frame.delta || {}).field === 'chat_mode') this.chatOnStateDelta(frame)
  },

  /** R12：WS 帧触发的权威数据刷新（去抖 PUSH_DEBOUNCE_MS，合并同批帧）。 */
  pushRefresh() {
    if (this.pushTimer || !this.loaded) return
    this.pushTimer = setTimeout(function () {
      this.pushTimer = null
      if (!this.loaded) return
      this.refresh(false)
    }.bind(this), PUSH_DEBOUNCE_MS)
  },

  onAction(e) { this.setData({ actionText: e.detail.value, error: '' }) },

  onIntent(e) { this.setData({ intent: e.detail.value }) },

  /** F6：行动提交（COLLECTING 门控 + req_id 幂等 + 重复提示；空文本不发请求） */
  onSubmit() {
    if (!this.data.canSubmit) {
      this.setData({ error: T.st_notCollecting, lastSubmit: '' })
      return
    }
    const text = String(this.data.actionText || '').trim()
    if (!text) {
      this.setData({ error: T.st_emptyAction })
      return
    }
    const turn = this.data.turn || {}
    const payload = {
      campaign: this.campaign,
      turn_no: turn.turn_no,
      player_id: this.profile.playerId,
      action: text,
      intent_summary: String(this.data.intent || '').trim(),
      req_id: reqId.create('player')
    }
    this.setData({ submitting: true, error: '' })
    this.client.submitAction(payload).then(function (data) {
      const duplicated = !!data && data.status === 'duplicate'
      this.setData({
        lastSubmit: duplicated ? T.st_duplicate : T.st_submitted,
        actionText: duplicated ? this.data.actionText : '',
        intent: duplicated ? this.data.intent : ''
      })
      // 契约 §3.4.1：提交后立即拉取一次
      return this.refresh(false)
    }.bind(this)).catch(function (err) {
      this.setData({ error: humanize(err), lastSubmit: '' })
    }.bind(this)).then(function () {
      this.setData({ submitting: false })
    }.bind(this))
  },

  /** 离开桌面：停止订阅并清理桌面上下文 */
  onLeave() {
    if (this.ws) this.ws.stop()
    const profile = store.load()
    store.save(Object.assign({}, profile, { tableId: '', campaign: '' }))
    wx.switchTab({ url: '/pages/setup/setup' })
  },

  onNavVoice() { wx.switchTab({ url: '/pages/voice/voice' }) },

  /* ======================= M3 (T6): 私聊/公共频道 ======================= */

  /** 四态 + 玩家列表（服务端权威；5s 节流）。 */
  chatRefresh(force) {
    if (!this.loaded) return
    const now = Date.now()
    if (!force && now - this.chatLastLoad < 5000) return
    this.chatLastLoad = now
    return this.client.chatStatus(this.campaign).then(function (d) {
      const mode = String((d && d.mode) || 'chat_enabled')
      const players = (d && d.players) || []
      const privOk = mode === 'chat_enabled'
      const pubOk = mode !== 'all_disabled'
      const modeText = T['chat.st.' + mode] || mode
      const badge = format(T.chat_status, { state: modeText }) +
        ' · ' + (privOk ? T.chat_privateAllowed : T.chat_privateBlocked) +
        ' · ' + (pubOk ? T.chat_publicAllowed : T.chat_publicBlocked)
      const names = players.map(function (p) { return String(p.id || '') }).filter(function (id) { return id && id !== this.profile.playerId }.bind(this))
      this.setData({
        chatMode: mode,
        chatPlayers: players,
        chatBadge: badge,
        chatPlayerNames: names,
        chatInputDisabled: !privOk && !pubOk,
        chatInputPlaceholder: pubOk ? T.chat_inputPub : T.chat_inputPriv
      })
    }.bind(this)).catch(function (err) {
      // 静默：聊天状态拉取失败不阻塞（轮询主通道不受影响）
    })
  },

  onChatInput(e) { this.setData({ chatText: e.detail.value, chatErr: '', chatOk: '' }) },

  onChatTargetChange(e) {
    const idx = Number(e.detail.value)
    const names = this.data.chatPlayerNames || []
    this.setData({
      chatTargetIndex: idx,
      chatTargetName: (idx >= 0 && idx < names.length) ? names[idx] : '',
      chatErr: '', chatOk: ''
    })
  },

  onChatSend() {
    if (!this.loaded || this.data.chatSending) return
    const text = String(this.data.chatText || '').trim()
    if (!text) return
    const target = String(this.data.chatTargetName || '').trim()
    const isPriv = !!target
    const mode = this.data.chatMode
    if (isPriv && mode !== 'chat_enabled') {
      this.setData({ chatErr: format(T.chat_privDisabled, { state: T['chat.st.' + mode] || mode }) })
      return
    }
    if (!isPriv && mode === 'all_disabled') {
      this.setData({ chatErr: format(T.chat_pubDisabled, { state: T['chat.st.' + mode] || mode }) })
      return
    }
    const payload = {
      player_id: this.profile.playerId,
      to_players: isPriv ? [target] : ['_public_'],
      text: text
    }
    this.setData({ chatSending: true, chatErr: '', chatOk: '' })
    this.client.chatSend(this.campaign, payload).then(function (data) {
      const out = isPriv ? T.chat_sent : T.chat_pubSent
      this.setData({
        chatSending: false, chatOk: out, chatText: '',
        chatLog: (this.data.chatLog || []).concat([{
          seq: 'chat-' + Date.now(),
          kind: isPriv ? '私聊' : '公共',
          who: this.profile.playerId + (isPriv ? '→' + target : ''),
          text: text
        }]).slice(-100)
      })
      return this.refresh(false)
    }.bind(this)).catch(function (err) {
      this.setData({ chatSending: false, chatErr: format(T.chat_reqFailed, { err: humanize(err) }) })
    }.bind(this))
  },

  /** WS WHISPER 帧 -> 私聊气泡（仅目标收到；服务端已定向）。 */
  chatOnWhisper(frame) {
    const body = String((frame && frame.packet && frame.packet.body) || '')
    const from = String((frame && frame.packet && frame.packet.info_id) || '')
    if (!body) return
    this.setData({
      chatLog: (this.data.chatLog || []).concat([{
        seq: 'ws-' + (frame.seq || Date.now()),
        kind: '私聊', who: from, text: body
      }]).slice(-100)
    })
  },

  /** STATE_DELTA(chat_mode) -> 四态徽标实时更新。 */
  chatOnStateDelta(frame) {
    const d = (frame && frame.delta) || {}
    if (d.field !== 'chat_mode') return
    const mode = String((d.value || {}).mode || this.data.chatMode)
    const privOk = mode === 'chat_enabled'
    const pubOk = mode !== 'all_disabled'
    const modeText = T['chat.st.' + mode] || mode
    const badge = format(T.chat_status, { state: modeText }) +
      ' · ' + (privOk ? T.chat_privateAllowed : T.chat_privateBlocked) +
      ' · ' + (pubOk ? T.chat_publicAllowed : T.chat_publicBlocked)
    this.setData({
      chatMode: mode, chatBadge: badge,
      chatInputDisabled: !privOk && !pubOk,
      chatInputPlaceholder: pubOk ? T.chat_inputPub : T.chat_inputPriv
    })
  }
})