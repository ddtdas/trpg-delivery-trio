const store = require('../../lib/config-store')
const { map } = require('../../lib/strings-map')
const { ApiClient, humanize } = require('../../lib/api-client')

Page({
  data: {
    T: map(),
    profile: {},
    testing: false,
    resolving: false,
    joining: false,
    error: '',
    result: '',
    info: null,
    resolved: null
  },

  onShow() {
    this.setData({ profile: store.load(), error: '', result: '' })
  },

  onField(e) {
    const key = e.currentTarget.dataset.key
    const patch = {}
    patch['profile.' + key] = e.detail.value
    patch.error = ''
    patch.result = ''
    this.setData(patch)
  },

  persist() {
    const saved = store.save(this.data.profile)
    this.setData({ profile: saved })
    return saved
  },

  /** F1 服务器连接：GET /access/info → 显示版本 + 三端启用状态。 */
  onTest() {
    const profile = this.persist()
    const invalid = store.validate(profile)
    if (invalid) return this.setData({ error: invalid, result: '' })
    this.setData({ testing: true, error: '', result: '', info: null })
    new ApiClient(profile).info().then(function (data) {
      const ends = data.ends || {}
      const endsText = Object.keys(ends).map(function (name) {
        return name + '=' + (ends[name] ? '启用' : '停用')
      }).join(' ')
      this.setData({
        result: this.data.T.st_connected,
        info: { service: data.service || '', version: data.version || '', endsText: endsText }
      })
    }.bind(this)).catch(function (err) {
      this.setData({ error: humanize(err), result: '' })
    }.bind(this)).then(function () {
      this.setData({ testing: false })
    }.bind(this))
  },

  /** F2 连接码：GET /access/table/resolve?code= → 桌名/战役；不存在显示 连接码不存在。 */
  onResolve() {
    const profile = this.persist()
    const invalid = store.validate(profile)
    if (invalid) return this.setData({ error: invalid, result: '' })
    if (!String(profile.code || '').trim()) return this.setData({ error: this.data.T.ext_st_needCode, result: '' })
    this.setData({ resolving: true, error: '', result: '', resolved: null })
    new ApiClient(profile).resolveCode(profile.code).then(function (data) {
      if (!data || data.exists === false) {
        this.setData({ error: this.data.T.err_notFound, resolved: null })
        return
      }
      const saved = store.save(Object.assign({}, this.data.profile, { tableId: data.table_id || '', campaign: data.campaign || '' }))
      this.setData({
        profile: saved,
        resolved: data,
        result: (data.name || data.table_id || '') + ' · ' + (data.campaign || '')
      })
      if (this.pendingJoin) {
        this.pendingJoin = false
        wx.switchTab({ url: '/pages/table/table' })
      }
    }.bind(this)).catch(function (err) {
      this.setData({ error: humanize(err), resolved: null })
    }.bind(this)).then(function () {
      this.setData({ resolving: false })
    }.bind(this))
  },

  /** F4 加入跑团：校验 → 存本地 → 进入桌面页。 */
  onJoin() {
    const profile = this.persist()
    const invalid = store.validateJoin(profile)
    if (invalid) return this.setData({ error: invalid, result: '' })
    if (!profile.tableId) {
      this.pendingJoin = true
      return this.onResolve()
    }
    this.setData({ joining: true, error: '' })
    store.save(profile)
    this.setData({ joining: false })
    wx.switchTab({ url: '/pages/table/table' })
  }
})
