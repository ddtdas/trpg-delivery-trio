const store = require('../../lib/config-store')
const { map, format } = require('../../lib/strings-map')
const { ApiClient, humanize } = require('../../lib/api-client')

const T = map()

function seconds(ms) { return Math.max(0, Math.floor(Number(ms || 0) / 1000)) }

/** t5 fix (reviewer P2-3)：只显示 file_ref 的文件名部分，不回显服务端绝对路径（与 PC 端一致）。 */
function fileBase(p) {
  var s = String(p || '')
  var i = Math.max(s.lastIndexOf('/'), s.lastIndexOf('\\'))
  return i >= 0 ? s.slice(i + 1) : s
}

Page({
  data: {
    T: T,
    profile: {},
    recording: false,
    duration: 0,
    filePath: '',
    fileSize: 0,
    uploading: false,
    result: '',
    error: '',
    deviceId: '',
    deviceText: ''
  },

  onLoad() {
    const profile = store.load()
    this.profile = profile
    this.client = new ApiClient(profile)
    this.setData({ profile: profile })

    this.recorder = wx.getRecorderManager()
    this.recorder.onStart(function () {
      this.startedAt = Date.now()
      clearInterval(this.tick)
      this.tick = setInterval(function () {
        this.setData({ duration: seconds(Date.now() - this.startedAt) })
      }.bind(this), 1000)
    }.bind(this))
    this.recorder.onStop(function (res) {
      clearInterval(this.tick)
      this.tick = null
      const filePath = (res && res.tempFilePath) || ''
      this.setData({
        recording: false,
        filePath: filePath,
        fileSize: (res && res.fileSize) || 0,
        duration: seconds((res && res.duration) || (Date.now() - this.startedAt))
      })
      if (filePath) this.upload(filePath)
    }.bind(this))
    // 录音不可用（权限被拒 / 环境不支持）→ 明确降级提示，不静默失败
    this.recorder.onError(function (err) {
      clearInterval(this.tick)
      this.tick = null
      const detail = err && err.errMsg ? '（' + err.errMsg + '）' : ''
      this.setData({ recording: false, error: T.ext_st_recordUnsupported + detail })
    }.bind(this))
  },

  onUnload() {
    clearInterval(this.tick)
    this.tick = null
    if (this.data.recording && this.recorder) this.recorder.stop()
  },

  /** F8：开始录音 / 停止并上传（wx.getRecorderManager + wx.uploadFile → POST /access/player/audio） */
  onRecord() {
    if (!this.recorder) return
    if (this.data.recording) {
      this.recorder.stop()
      return
    }
    this.setData({ filePath: '', fileSize: 0, result: '', error: '', duration: 0 })
    this.recorder.start({
      duration: 600000,
      sampleRate: 16000,
      numberOfChannels: 1,
      encodeBitRate: 48000,
      format: 'mp3'
    })
    this.setData({ recording: true })
  },

  upload(filePath) {
    const campaign = this.profile.campaign || this.profile.tableId
    if (!campaign) {
      this.setData({ error: T.ext_st_needCode })
      return
    }
    this.setData({ uploading: true, error: '', result: '' })
    this.client.uploadAudio(filePath, {
      campaign: campaign,
      kind: 'voice',
      player_id: this.profile.playerId || ''
    }).then(function (data) {
      const stt = (data && data.stt) || {}
      this.setData({
        result: format(T.ext_st_uploadOk, { bytes: (data && data.bytes) || 0 }) + ' · '
          + format(T.ext_st_sttStatus, { status: stt.status || '' })
          + ' · file_ref: ' + fileBase(data && data.file_ref)
      })
    }.bind(this)).catch(function (err) {
      this.setData({ error: humanize(err), result: '' })
    }.bind(this)).then(function () {
      this.setData({ uploading: false })
    }.bind(this))
  },

  onDeviceId(e) { this.setData({ deviceId: e.detail.value, error: '' }) },

  /** F9：GET /access/device/status?device_id=（只读；无记录 → 404 → 无该设备记录） */
  onQuery() {
    const deviceId = String(this.data.deviceId || '').trim()
    if (!deviceId) {
      this.setData({ deviceText: '', error: T.st_noDevice })
      return
    }
    this.setData({ error: '' })
    this.client.deviceStatus(deviceId).then(function (data) {
      this.setData({
        deviceText: String(data.device_id || '') + ' · ' + String(data.status_text || '')
          + ' · battery=' + String(data.battery === null || data.battery === undefined ? '-' : data.battery)
          + ' · recording=' + String(!!data.recording) + ' · seq=' + String(data.seq)
      })
    }.bind(this)).catch(function (err) {
      if (err && err.code === 404) {
        this.setData({ deviceText: T.st_noDevice, error: '' })
        return
      }
      this.setData({ deviceText: '', error: humanize(err) })
    }.bind(this))
  }
})
