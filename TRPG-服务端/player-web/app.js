/* TRPG 跑团玩家端（PC / 移动浏览器版）—— 零构建、零依赖、无 CDN。
   实现依据: docs/CROSS-END-CONTRACT.md v1.1
     §1 端点与统一包裹 / §2 设计令牌 / §3 WS（可选增强通道）/ §4 F1-F10 / §5 固定文案 / §7 约束与风险
   与小程序端功能集合、文案、设计令牌完全一致。 */
(function () {
  'use strict';

  /* 构建标记（便于验收确认加载的是哪一版）：契约 v1.1 实现 */
  window.__TRPG_PLAYER_BUILD = 'web-player/v1.1.0';

  /* ---------- 固定文案（与 strings.json 逐字相同；契约 §5.1 / §5.2） ---------- */
  var S = {
    'title': 'TRPG 跑团玩家端',
    'nav.setup': '连接设置',
    'nav.table': '桌面',
    'nav.voice': '语音',
    'btn.test': '测试连接',
    'btn.resolve': '解析连接码',
    'btn.join': '加入跑团',
    'btn.leave': '离开桌面',
    'btn.submit': '提交行动',
    'btn.recStart': '开始录音',
    'btn.recStop': '停止并上传',
    'btn.query': '查询',
    'ph.server': '服务器地址，如 http://192.168.10.110:9210',
    'ph.code': '连接码，如 TABLE-XXXX',
    'ph.playerId': '玩家 ID，如 pl-001',
    'ph.playerName': '昵称',
    'ph.action': '描述你要做什么…（必填）',
    'ph.intent': '意图摘要（选填）',
    'ph.deviceId': '设备 ID',
    'st.connecting': '连接中…',
    'st.connected': '已连接',
    'st.reconnecting': '重连中…',
    'st.closed': '已断开',
    'st.collecting': '行动收集中',
    'st.notCollecting': '当前不在行动收集阶段，请等待主持人开启回合',
    'st.submitted': '已提交，等待主持人结算',
    'st.duplicate': '重复提交已忽略',
    'st.emptyAction': '行动描述不能为空',
    'st.noTurn': '尚未开启回合',
    'st.noDevice': '无该设备记录',
    'err.net': '网络连接失败，请检查服务器地址与网络',
    'err.auth': '身份验证失败：token 无效或未启用该端',
    'err.notFound': '连接码不存在',
    'err.server': '服务端异常',
    'sec.role': '我的状态',
    'sec.turn': '回合',
    'sec.action': '行动',
    'sec.events': '事件流',
    'sec.voice': '语音',
    'sec.device': '录音设备',
    'ev.ACTION_SUBMITTED': '行动提交',
    'ev.TURN_STARTED': '回合开始',
    'ev.TURN_CLOSED': '回合结束',
    'ev.CHECK_RESOLVED': '检定',
    'ev.NARRATION_PROPOSED': '旁白待审',
    'ev.NARRATION_APPROVED': '旁白',
    'ev.NARRATION_EDITED': '旁白（已修订）',
    'ev.NARRATION_REJECTED': '旁白（未通过）',
    'ev.INFO_REVEALED': '公开信息',
    'ev.CLUE_GRANTED': '线索',
    'ev.BRANCH_TAKEN': '分支',
    'ev.BRANCH_OVERRIDDEN': '分支（已覆盖）',
    'ev.TRANSCRIPT_APPENDED': '语音转写',
    'ev.TRANSCRIPT_READY': '语音转写完成',
    'ev.ROLE_ASSIGNED': '角色分配',
    'ev.EVIDENCE_DEALT': '证据发放',
    'ev.VOTE_CAST': '投票',
    'ev.TRUTH_REVEALED': '真相揭示',
    'ev.MAP_UPDATED': '地图更新',
    'ev.SESSION_SUMMARIZED': '场次小结',
    'ev.OTHER': '其他事件',
    'ev.NPC_ACT_PROPOSED': 'NPC 台词待审',
    'ev.NPC_ACT_APPROVED': 'NPC 台词',
    /* 扩展文案（契约 §5 之外，两端逐字相同） */
    'ext.ph.tokenOld': '访问 token（mobile 端）',
    'ext.lbl.table': '桌面名称',
    'ext.lbl.campaign': '战役',
    'ext.lbl.version': '服务版本',
    'ext.lbl.ends': '启用端',
    'ext.st.recording': '录音中…',
    'ext.st.recordUnsupported': '当前环境不支持录音（需要 HTTPS/localhost 且设备有可用麦克风）',
    'ext.st.uploadOk': '已上传 {bytes} 字节',
    'ext.st.sttStatus': '转写状态：{status}',
    'ext.st.needServer': '请先填写服务器地址',
    'ext.st.needCode': '请先填写连接码',
    'ext.st.needPlayerId': '请先填写玩家 ID',
    'ext.st.needToken': '请先填写访问 token',
    'ext.st.deviceNone': '无该设备记录',
    'ext.turn.line': '回合 {turn_no} · {state} · 已提交 {submitted}',
    'ext.ev.turn': '回合 {turn_no} · {state}',
    'ext.ev.delta': '状态更新 {delta}',
    'ext.ev.narrationPending': '旁白待审',
    'ext.ev.info': '信息公开 {info_id}',
    'ext.ev.branch': '分支推进 {label}',
    'ext.ev.job': '任务 {job_id} · {status}',
    'ext.ev.directed': '定向消息 {body}',
    /* T15 (additive): R10/R11 地点交互面板文案（与小程序端同键同名，服务端 label 优先） */
    'ix.title': '地点交互',
    'ix.room': '当前房间：{room} · 可交互物 {n} 个',
    'ix.all': '可交互物 {n} 个（未定位到你的房间，显示全部）',
    'ix.none': '当前房间没有可交互物',
    'ix.needJoin': '加入跑团后可进行地点交互',
    'ix.report': '（需报备）',
    'ix.pending': '已上报待主持人',
    'ix.delivered': '主持人已允许',
    'ix.rejected': '主持人暂未允许',
    'ix.mine': '我的交互',
    'ix.pick': '请选择要交互的家具',
    /* T1 (additive): 场景栏目（地图卡下方，多线叙事） */
    'sc.title': '场景',
    'sc.current': '当前场景：{scene}',
    'sc.branch': '前往：{label}',
    'sc.locked': '（未解锁）',
    'sc.back': '← 上一场景',
    'sc.empty': '暂无场景（未加载模组场景图）',
    'sc.loading': '加载场景中…',
    'ev.SCENE_UPDATED': '场景更新',
    /* M3 (additive, T6): 私聊系统文案（两端逐字一致） */
    'chat.st.chat_enabled': '能私聊',
    'chat.st.chat_disabled': '不能私聊',
    'chat.st.public_only': '仅公共',
    'chat.st.all_disabled': '不能交流',
    'chat.title': '聊天',
    'chat.status': '当前状态：{state}',
    'chat.privateAllowed': '私聊开放',
    'chat.privateBlocked': '私聊已关闭',
    'chat.publicAllowed': '公共频道开放',
    'chat.publicBlocked': '公共频道关闭',
    'chat.inputPub': '公共频道发言…',
    'chat.inputPriv': '私聊 {to}：',
    'chat.send': '发送',
    'chat.targetPlaceholder': '选择私聊对象…',
    'chat.toSelf': '不能私聊自己',
    'chat.noTarget': '请选择私聊对象',
    'chat.reqFailed': '发送失败：{err}',
    'chat.sent': '已发送',
    'chat.pubSent': '已发到公共频道',
    'chat.noPlayers': '无可私聊对象（仅同场景玩家）',
    'chat.needJoin': '加入跑团后可聊天',
    'chat.pubDisabled': '公共频道已关闭（主持人设为『{state}』）',
    'chat.privDisabled': '私聊已关闭（主持人设为『{state}』）',
    'chat.sec': '聊天',
    /* R13 身份验证修复（UI 多模态实测：玩家加入后恒「已断开」+「token 无效」）：
       服务端 /access/mobile/* 走**端隔离**（configs/access_config.yaml 的 mobile.token），
       而 /access/info 与 /ws 是「任一启用端 token 放行」。故填了 webapp/recorder token 时
       /access/info 与 /ws 都通过、但 /access/mobile/state|events|action 一律 401 —— 表现为
       「已连接过又立刻断开 + 身份验证失败」。这里在加入前用 mobile 端点做端归属校验，
       失败时给出可执行的定位指引（哪个文件/哪个字段），而不是笼统的 err.auth。 */
    'ext.ph.token': '移动端访问 token（access_config.yaml → mobile.token）',
    'ext.err.wrongEnd': '身份验证失败：当前 token 不是「移动端」凭证。玩家端点 /access/mobile/* 只认 mobile.token；请把 token 输入框改成 configs/access_config.yaml 里 mobile.token 的值（websocket 与 /access/info 放行任一启用端，故此前不报错，直到这里才暴露）。',
    'ext.st.checking': '正在校验移动端凭证…',
    /* T13 (additive): 大厅/开始页/进行中三视图 + phase 门控（M5 文档化） */
    'lobby.title': '大厅',
    'lobby.codeNote': '连接码 = campaign_id，非密钥（鉴权靠端 token）',
    'lobby.tokenNote': '主持人请填 webapp token（access_config.yaml → webapp.token）；玩家只需 mobile token',
    'lobby.newName': '新团名称（可留空）',
    'lobby.create': '新建团',
    'lobby.refresh': '刷新列表',
    'lobby.list': '团列表',
    'lobby.empty': '暂无团（主持人可点击上方「新建团」）',
    'lobby.phase': '阶段：{phase}',
    'lobby.players': '玩家 {n} 人',
    'lobby.checkpoints': '存档点 {n} 个',
    'lobby.enter': '进入',
    'lobby.joinHint': '玩家加入：输入连接码（= campaign_id）',
    'lobby.joinCode': '连接码',
    'lobby.joinBtn': '加入 / 校验',
    'lobby.notFound': '未找到该连接码对应的团',
    'lobby.needServerToken': '请先填写服务器地址与访问 token',
    'lobby.created': '已创建团 {id}（{phase}）',
    'lobby.createFailed': '新建团失败：{err}',
    'lobby.needServer': '请先填写服务器地址与访问 token 后再操作大厅',
    'lobby.needJoin': '请先填写服务器地址与访问 token（大厅需要端 token 鉴权）',
    'setup.back': '← 返回大厅',
    'setup.title': '团配置：{name}',
    'setup.id': '团 ID（连接码）',
    'setup.ruleset': '规则：{ruleset}',
    'setup.module': '模组：{module}',
    'setup.phase': '阶段：{phase}',
    'setup.players': '玩家座位：{n} 人',
    'setup.scenes': '场景数：{n}',
    'setup.checkpoints': '存档点',
    'setup.noCheckpoints': '暂无存档点',
    'setup.start': '开始游戏',
    'setup.startHint': '开始后玩家端才会显示「玩家情况」',
    'setup.resume': '读档',
    'setup.save': '存档',
    'setup.saveLabel': '存档标签',
    'setup.saved': '已存档 {snapshot_id}',
    'setup.saveFailed': '存档失败：{err}',
    'setup.resumed': '已读档：{from}',
    'setup.resumeFailed': '读档失败：{err}',
    'setup.needConfig': '需先完成配置（开始游戏需要 phase=configuring，当前为 {phase}）',
    'setup.needCheckpoint': '暂无可读档的存档点',
    'gate.waiting': '等待开始',
    'gate.preparing': '准备中',
    'gate.ended': '本场已结束',
    'gate.notRunning': '游戏尚未开始：玩家情况（状态/回合/行动/事件）暂不显示，主持人点击「开始游戏」后即可进入。',
    'gate.refreshPhase': '刷新阶段',
    'gate.startFailed': '开始游戏失败：{err}',
    'gate.phaseUpdated': '阶段已更新：{phase}'
  };

  function t(key) { return S[key] || key; }
  function tpl(key, vars) {
    var out = t(key);
    for (var k in vars) {
      if (Object.prototype.hasOwnProperty.call(vars, k)) {
        out = out.split('{' + k + '}').join(String(vars[k]));
      }
    }
    return out;
  }

  /* ---------- 本地存储（F3 / 契约 §3.5） ---------- */
  var LS = {
    playerId: 'trpg.playerId',
    playerName: 'trpg.playerName',
    server: 'trpg.server',
    code: 'trpg.code',
    token: 'trpg.token'
  };
  var LAST_SEQ_PREFIX = 'trpg_last_seq_';   /* 键规则与小程序端相同 */

  function lsGet(k) {
    try { return window.localStorage.getItem(k) || ''; } catch (e) { return ''; }
  }
  function lsSet(k, v) {
    try { window.localStorage.setItem(k, v); } catch (e) { /* 隐私模式降级 */ }
  }

  /* ---------- 全局状态 ---------- */
  var state = {
    server: '', token: '', code: '', tableId: '', campaign: '', tableName: '',
    playerId: '', playerName: '', turn: null, joined: false,
    items: {}, cursor: -1, tip: -1, byType: {}, connState: 'closed', pollFails: 0, infoOk: false,
    ws: null, wsState: 'closed', backoffIdx: 0, lastFrameTs: 0, watchTimer: null,
    /* R13 断线自愈：重连定时器与握手超时定时器（各自单例，退出桌面时撤销） */
    reconnectTimer: null, handshakeTimer: null,
    pollTimer: null, pushTimer: null, mediaRecorder: null, mediaStream: null, chunks: [],
    lastSubmit: null, submitMsg: '', turnKey: '',
    /* T13 (additive): 当前团 phase（lobby/configuring/running/paused/ended），门控用 */
    phase: ''
  };

  /* T13 (additive): 大厅/开始页/进行中三视图状态 */
  var T13 = {
    campaigns: [],        /* GET /api/campaigns 结果 */
    lobby: null,          /* GET /api/campaigns/{id}/lobby 结果 */
    checkpoints: [],      /* GET /api/campaigns/{id}/checkpoints 结果 */
    setupId: '',          /* 当前开始页 campaign_id */
    gateBusy: false,
    gateTimer: null,
    gatePollMs: 15000     /* 门控兜底轮询（WS 不可用/丢帧时追平） */
  };

  var $ = function (id) { return document.getElementById(id); };

  function show(el, visible) {
    if (!el) { return; }
    if (visible) { el.classList.remove('hidden'); } else { el.classList.add('hidden'); }
  }
  function setErr(el, msg) {
    if (!el) { return; }
    if (msg) { el.textContent = msg; show(el, true); } else { el.textContent = ''; show(el, false); }
  }
  function hmsFromTs(ts) {
    var d = new Date(ts);
    if (isNaN(d.getTime())) { return String(ts || ''); }
    var p = function (n) { return (n < 10 ? '0' : '') + n; };
    return p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
  }
  function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function normalizeServer(v) {
    var s = String(v || '').trim();
    if (!s) { return ''; }
    if (!/^https?:\/\//i.test(s)) { s = 'http://' + s; }
    if (s.charAt(s.length - 1) === '/') { s = s.slice(0, -1); }
    return s;
  }
  function newReqId() {
    try {
      if (window.crypto && typeof window.crypto.randomUUID === 'function') {
        return window.crypto.randomUUID();
      }
    } catch (e) { /* fallthrough */ }
    return 'req-' + Date.now() + '-' + Math.random().toString(16).slice(2, 10);
  }

  /* ---------- 统一响应包裹与错误文案 ---------- */
  function errTextFor(status, json) {
    if (status === 0) { return t('err.net'); }
    if (status === 401 || status === 403) { return t('err.auth'); }
    if (status === 404) { return t('err.notFound'); }
    if (status >= 500) { return t('err.server'); }
    if (json && json.error) { return String(json.error); }
    if (json && json.detail) { return String(json.detail); }
    return t('err.server');
  }

  /* api(): /access/* 与 /api/* 直连；REST 带 Authorization: Bearer <mobile token> */
  function api(path, opts) {
    opts = opts || {};
    var url = normalizeServer(state.server) + path;
    var headers = {};
    if (state.token) { headers['Authorization'] = 'Bearer ' + state.token; }
    var init = { method: opts.method || 'GET', headers: headers };
    if (opts.body !== undefined) {
      if (opts.form) { init.body = opts.body; } else {
        headers['Content-Type'] = 'application/json';
        init.body = JSON.stringify(opts.body);
      }
    }
    return fetch(url, init).then(function (r) {
      return r.text().then(function (text) {
        var json = null;
        try { json = JSON.parse(text); } catch (e) { json = null; }
        return { status: r.status, json: json, text: text };
      });
    }, function () {
      return { status: 0, json: null, text: '' };
    });
  }

  /* ---------- 视图切换 ---------- */
  function showView(name) {
    show($('viewSetup'), name === 'setup');
    show($('viewTable'), name === 'table');
    show($('viewVoice'), name === 'voice');
    $('navSetup').setAttribute('aria-current', name === 'setup' ? 'true' : 'false');
    $('navTable').setAttribute('aria-current', name === 'table' ? 'true' : 'false');
    $('navVoice').setAttribute('aria-current', name === 'voice' ? 'true' : 'false');
  }

  /* ---------- F1 服务器连接 ---------- */
  function testConnection() {
    state.server = normalizeServer($('server').value);
    state.token = String($('token').value || '').trim();
    lsSet(LS.server, state.server);
    lsSet(LS.token, state.token);
    if (!state.server) { setErr($('setupErr'), t('ext.st.needServer')); return Promise.resolve(false); }
    if (!state.token) { setErr($('setupErr'), t('ext.st.needToken')); return Promise.resolve(false); }
    setErr($('setupErr'), '');
    $('setupStatus').textContent = t('st.connecting');
    show($('infoBox'), false);
    return api('/access/info').then(function (res) {
      if (res.status !== 200 || !res.json || !res.json.ok) {
        $('setupStatus').textContent = t('st.closed');
        setErr($('setupErr'), errTextFor(res.status, res.json));
        return false;
      }
      var d = res.json.data || {};
      var ends = d.ends || {};
      $('setupStatus').textContent = t('st.connected');
      var html = '';
      html += '<div class="kv"><span class="k">' + t('ext.lbl.version') + '</span><span>' +
        escapeHtml(String(d.version || '')) + '</span></div>';
      html += '<div class="kv"><span class="k">' + t('ext.lbl.ends') + '</span><span>' +
        escapeHtml(['mobile', 'webapp', 'recorder'].map(function (k) {
          return k + '=' + (ends[k] ? 'on' : 'off');
        }).join(' ')) + '</span></div>';
      $('infoBox').innerHTML = html;
      show($('infoBox'), true);
      state.infoOk = true;
      return true;
    });
  }

  /* ---------- F2 连接码解析 ---------- */
  function resolveCode() {
    state.server = normalizeServer($('server').value);
    state.token = String($('token').value || '').trim();
    state.code = String($('code').value || '').trim();
    lsSet(LS.server, state.server); lsSet(LS.token, state.token); lsSet(LS.code, state.code);
    if (!state.server) { setErr($('setupErr'), t('ext.st.needServer')); return Promise.resolve(false); }
    if (!state.code) { setErr($('setupErr'), t('ext.st.needCode')); return Promise.resolve(false); }
    setErr($('setupErr'), '');
    $('setupStatus').textContent = t('st.connecting');
    return api('/access/table/resolve?code=' + encodeURIComponent(state.code)).then(function (res) {
      if (res.status === 404) {
        $('setupStatus').textContent = t('st.closed');
        setErr($('setupErr'), t('err.notFound'));
        return false;
      }
      if (res.status !== 200 || !res.json || !res.json.ok) {
        $('setupStatus').textContent = t('st.closed');
        setErr($('setupErr'), errTextFor(res.status, res.json));
        return false;
      }
      var d = res.json.data || {};
      if (d.exists === false) {
        $('setupStatus').textContent = t('st.closed');
        setErr($('setupErr'), t('err.notFound'));
        return false;
      }
      state.tableId = String(d.table_id || '');
      state.campaign = String(d.campaign || d.table_id || '');
      state.tableName = String(d.name || d.table_id || '');
      $('setupStatus').textContent = t('st.connected');
      var html = '';
      html += '<div class="kv"><span class="k">' + t('ext.lbl.table') + '</span><span>' +
        escapeHtml(state.tableName) + '</span></div>';
      html += '<div class="kv"><span class="k">' + t('ext.lbl.campaign') + '</span><span>' +
        escapeHtml(state.campaign) + '</span></div>';
      $('infoBox').innerHTML = html;
      show($('infoBox'), true);
      return true;
    });
  }

  /* R13（identity）：校验当前 token 是否为「移动端」凭证。
     判据：GET /access/mobile/state?table_id=... —— 该端点由服务端 _require_end("mobile")
     强端隔离（未启用该端 / token 不匹配 -> 401）。返回 true 表示 token 属于 mobile 端，
     玩家端全部 /access/mobile/* 与 /ws 均可通行。
     注意：只读探测，不改任何可见文案以外的契约文案；失败文案是新增的 ext.err.wrongEnd。 */
  function verifyMobileEnd() {
    var tid = state.tableId || state.code;
    if (!tid) { return Promise.resolve(true); }
    return api('/access/mobile/state?table_id=' + encodeURIComponent(tid)).then(function (res) {
      if (res.status === 200 && res.json && res.json.ok) { return true; }
      if (res.status === 401 || res.status === 403) {
        state.infoOk = false;    /* 该 token 对移动端点无效 -> 后续 join 会重新走完整校验 */
        setErr($('setupErr'), t('ext.err.wrongEnd'));
        $('setupStatus').textContent = t('st.closed');
        return false;
      }
      /* 网络层错误（0）/其它非鉴权错误：不阻断加入，沿用原降级路径 */
      return true;
    }, function () { return true; });
  }

  /* ---------- F4 加入桌面 ---------- */
  function joinTable() {
    state.playerId = String($('pid').value || '').trim();
    state.playerName = String($('pname').value || '').trim();
    lsSet(LS.playerId, state.playerId);
    lsSet(LS.playerName, state.playerName);
    if (!state.server) { setErr($('setupErr'), t('ext.st.needServer')); return Promise.resolve(); }
    if (!state.code) { setErr($('setupErr'), t('ext.st.needCode')); return Promise.resolve(); }
    if (!state.playerId) { setErr($('setupErr'), t('ext.st.needPlayerId')); return Promise.resolve(); }
    /* 契约 §3.1：连接 WS 之前必须先用 GET /access/info 校验 token 与可达性
       （失败一律不区分 token 错/参数错/路径错，故先用 info 判定） */
    setConnStatus('connecting');
    var p = state.infoOk ? Promise.resolve(true) : testConnection();
    return p.then(function (okInfo) {
      if (!okInfo) { setConnStatus('closed'); return false; }
      return state.tableId ? true : resolveCode();
    }).then(function (okResolve) {
      if (!okResolve) { setConnStatus('closed'); return; }
      /* R13：进入桌面前校验「玩家端点端归属」——
         /access/info 与 /ws 是任一启用端 token 放行（故填错端也能过），但玩家真正依赖的
         /access/mobile/state|events|action 是 mobile 端专属。这里先探一次：401/403 说明
         token 不是 mobile 端凭证，给出可执行指引并中止，避免进入桌面后恒「已断开」。 */
      return verifyMobileEnd();
    }).then(function (okMobile) {
      if (!okMobile) { setConnStatus('closed'); return; }
      state.joined = true;
      state.items = {};
      state.cursor = parseInt(lsGet(LAST_SEQ_PREFIX + state.tableId) || '-1', 10);
      if (isNaN(state.cursor)) { state.cursor = -1; }
      render();
      $('rolePid').textContent = state.playerId;
      $('roleName').textContent = state.playerName || state.playerId;
      $('roleCode').textContent = state.code;
      $('roleTable').textContent = state.tableName || state.tableId;
      $('roleCampaign').textContent = state.campaign;
      showView('table');
      refreshState();
      loadEvents(true);
      startPolling();
      connectWs();
      ixStart();   /* T15 (additive): 进入桌面后加载地点交互面板 */
      chatStart();  /* M3 (additive, T6): 进入桌面后加载聊天面板 */
      /* T13 (additive): 加入后同步 phase 并应用门控（未 running 不渲染玩家情况） */
      syncPhaseForTable().then(applyPhaseGate);
      startGatePolling();
      /* 开始页也跟随当前团（若有 hash 指向 #/setup/:id） */
      if (state.campaign && T13.setupId !== state.campaign) {
        T13.setupId = state.campaign;
        if (document.getElementById('setupView') && !document.getElementById('setupView').classList.contains('hidden')) {
          setupView(state.campaign);
        }
      }
      /* 玩家在 #/play/:id 未加入时先落到 setup —— 加入成功后跳回进行中 */
      if (T13.pendingPlay && (T13.pendingPlay === state.campaign || T13.pendingPlay === state.tableId)) {
        var target = T13.pendingPlay;
        T13.pendingPlay = '';
        window.location.hash = '#/play/' + encodeURIComponent(target);
      }
    });
  }

  function leaveTable() {
    state.joined = false;
    stopPolling();
    closeWs();
    ixStop();   /* T15 (additive): 清空地点交互面板 */
    ixSceneStop();   /* T1 (additive): 清空场景栏目 */
    T7 = { board: null, combat: null, timeline: [], dash: null, mounted: false, last: 0 };
    chatStop();  /* M3 (additive, T6): 清空聊天面板 */
    /* T13 (additive): 停止门控兜底轮询；离开桌面时若停留在开始页，刷新该团 phase 门控 */
    stopGatePolling();
    var sv = document.getElementById('setupView');
    if (T13.setupId && sv && !sv.classList.contains('hidden')) {
      setupView(T13.setupId);
    }
    showView('setup');
  }

  /* ---------- F5 回合状态（2s 轮询兜底） ---------- */
  function refreshState() {
    if (!state.joined || !state.tableId) { return Promise.resolve(); }
    return api('/access/mobile/state?table_id=' + encodeURIComponent(state.tableId))
      .then(function (res) {
        if (res.status === 200 && res.json && res.json.ok) {
          var d = res.json.data || {};
          if (d.campaign) { state.campaign = String(d.campaign); }
          state.turn = d.turn || null;
          state.tip = (typeof d.tip === 'number') ? d.tip : -1;
          state.byType = d.by_type || {};
          state.pollFails = 0;
          setConnStatus('connected');
          renderTurn();
        } else {
          state.pollFails = (state.pollFails || 0) + 1;
          setConnStatus(state.pollFails >= 3 ? 'closed' : 'reconnecting');
          if (res.status === 401 || res.status === 403) { setErr($('submitErr'), t('err.auth')); }
        }
      });
  }
  /* R12：轮询**降级为兜底**（15s 心跳，仅用于 WS 不可用/丢帧时追平）；
     实时性由 WS 推送驱动（onmessage -> pushRefresh -> 立即拉权威数据）。 */
  var POLL_FALLBACK_MS = 15000;
  var PUSH_DEBOUNCE_MS = 60;
  function startPolling() {
    stopPolling();
    state.pollTimer = window.setInterval(function () {
      refreshState();
      loadEvents(false);
    }, POLL_FALLBACK_MS);
  }
  /* WS 帧到达 -> 立即拉一次权威数据（去抖合并同批帧，不等待兜底轮询）。 */
  function pushRefresh() {
    if (state.pushTimer) { return; }
    state.pushTimer = window.setTimeout(function () {
      state.pushTimer = null;
      if (!state.joined) { return; }
      refreshState();
      loadEvents(false);
      ixRefresh();   /* T15 (additive): R10/R11 面板随 WS 帧追平（内部 2.5s/5s 节流） */
      chatRefresh();  /* M3 (additive, T6): 聊天面板随 WS 帧追平（5s 节流） */
    }, PUSH_DEBOUNCE_MS);
  }
  function stopPolling() {
    if (state.pollTimer) { window.clearInterval(state.pollTimer); state.pollTimer = null; }
  }

  function renderTurn() {
    var turn = state.turn;
    if (!turn) {
      $('turnLine').textContent = t('st.noTurn');
      show($('turnChip'), false);
      renderCounts();
      setSubmitEnabled(false);
      return;
    }
    $('turnLine').textContent = tpl('ext.turn.line', {
      turn_no: turn.turn_no, state: turn.state, submitted: turn.submitted
    });
    /* R2: 只把 COLLECTING 当可提交，其余状态原样显示字符串 */
    var collecting = String(turn.state) === 'COLLECTING';
    $('turnChip').textContent = t('st.collecting');
    show($('turnChip'), collecting);
    renderCounts();
    var key = String(turn.turn_no) + '|' + String(turn.state);
    if (key !== state.turnKey) { state.turnKey = key; state.submitMsg = ''; }
    setSubmitEnabled(collecting);
  }

  /* by_type 计数行（与小程序端 table.js::countsText 一致） */
  function renderCounts() {
    if (!$('turnCounts')) { return; }
    var keys = Object.keys(state.byType || {}).sort();
    var parts = [];
    for (var i = 0; i < keys.length; i++) { parts.push(keys[i] + '=' + state.byType[keys[i]]); }
    $('turnCounts').textContent = parts.join(' ');
  }
  function setSubmitEnabled(on) {
    $('btnSubmit').disabled = !on;
    /* 非 COLLECTING 一律显示 st.notCollecting；可提交时显示 st.collecting。
       提交结果（st.submitted / st.duplicate）走 .ok-line，避免被 2s 轮询覆盖。 */
    $('submitStatus').textContent = on ? t('st.collecting') : t('st.notCollecting');
  }

  /* ---------- F6 行动提交 ---------- */
  function submitAction() {
    var text = String($('action').value || '').trim();
    var intent = String($('intent').value || '').trim();
    setErr($('submitErr'), '');
    if (!text) { setErr($('submitErr'), t('st.emptyAction')); return Promise.resolve(); }
    var turn = state.turn;
    if (!turn || String(turn.state) !== 'COLLECTING') {
      setErr($('submitErr'), t('st.notCollecting'));
      return Promise.resolve();
    }
    /* req_id 幂等：同回合同内容 3s 内重复点击视为同一次逻辑提交（防双击），
       复用 req_id -> 服务端只落 1 条事件并返回 duplicate -> 显示 st.duplicate */
    var dedupeKey = turn.turn_no + '|' + text + '|' + intent;
    var reqId;
    if (state.lastSubmit && state.lastSubmit.key === dedupeKey &&
        (Date.now() - state.lastSubmit.ts) < 3000) {
      reqId = state.lastSubmit.reqId;
    } else {
      reqId = newReqId();
    }
    state.lastSubmit = { key: dedupeKey, reqId: reqId, ts: Date.now() };
    var body = {
      campaign: state.campaign,
      turn_no: turn.turn_no,
      player_id: state.playerId,
      action: text,
      intent_summary: intent,
      req_id: reqId
    };
    $('btnSubmit').disabled = true;
    var send = function (attempt) {
      return api('/access/mobile/action', { method: 'POST', body: body }).then(function (res) {
        if (res.status === 0 && attempt === 0) {
          $('submitStatus').textContent = t('st.reconnecting');
          return new Promise(function (resolve) {
            window.setTimeout(function () { resolve(send(1)); }, 800);
          });
        }
        return res;
      });
    };
    return send(0).then(function (res) {
      if (res.status === 200 && res.json && res.json.ok) {
        var d = res.json.data || {};
        state.submitMsg = (d.status === 'duplicate') ? t('st.duplicate') : t('st.submitted');
        if ($('submitOk')) { $('submitOk').textContent = state.submitMsg; }
        refreshState();
        loadEvents(false);
      } else {
        state.submitMsg = '';
        if ($('submitOk')) { $('submitOk').textContent = ''; }
        setErr($('submitErr'), errTextFor(res.status, res.json));
      }
      $('btnSubmit').disabled = !(state.turn && String(state.turn.state) === 'COLLECTING');
    });
  }

  /* ---------- F7 事件流（主通道 REST；契约 §3.4 / §4 F7 / §7 R1） ----------
     渲染规则与小程序端 clients/miniprogram/lib/event-view.js 逐条对齐（标签/正文/时间/可见性）。 */
  var TAIL = 50;

  function evLabel(type) {
    var key = 'ev.' + type;
    return (key in S) ? S[key] : t('ev.OTHER') + ' ' + String(type || '');
  }

  function pickPath(obj, pathParts) {
    var cur = obj;
    for (var i = 0; i < pathParts.length; i++) {
      if (cur === null || cur === undefined || typeof cur !== 'object') { return undefined; }
      cur = cur[pathParts[i]];
    }
    return cur;
  }

  /* 可见性过滤（R1：REST 事件流无服务端过滤，客户端必须自行过滤） */
  function isVisible(ev) {
    var p = (ev && ev.payload) || {};
    var scope = p.scope;
    if (scope === undefined || scope === null || scope === 'public') { return true; }
    var targets = Array.isArray(p.targets) ? p.targets : [];
    var mine = targets.indexOf(state.playerId) >= 0;
    if (scope === 'whisper') { return mine; }
    if (scope === 'condition') { return mine || p.condition_met === true; }
    return true;
  }

  var TEXT_PATHS = [
    ['text'], ['body'], ['body_ref'], ['label'], ['message'], ['summary'],
    ['seg', 'text'], ['action', 'text'], ['next_preview'], ['line'], ['reason'],
    ['ref'], ['clue_id'], ['transcript_ref'], ['truth_tree_ref'], ['summary_ref'],
    ['role_ref'], ['npc_id'], ['op'], ['level'], ['status_text'], ['info_id']
  ];

  /* 事件正文（与小程序端 event-view.js::text 逐条一致） */
  function evText(ev) {
    var p = (ev && ev.payload) || {};
    var type = String((ev && ev.type) || '');
    if (type === 'ACTION_SUBMITTED') {
      var who = String(p.player_id || (ev && ev.actor) || '');
      var action = (p.action && p.action.text) ? p.action.text : JSON.stringify(p.action || {});
      var intent = p.intent_summary ? '（' + p.intent_summary + '）' : '';
      return who + '：' + action + intent;
    }
    if (type === 'TURN_STARTED') { return '第 ' + String(p.turn_no) + ' 回合'; }
    if (type === 'TURN_CLOSED') { return '第 ' + String(p.turn_no) + ' 回合结束'; }
    if (type === 'CHECK_RESOLVED') {
      return String(p.card_id || '') + ' 目标 ' + String(p.target) + ' 难度 ' + String(p.difficulty) +
        ' 合计 ' + String(p.total) + ' · ' + String(p.level);
    }
    if (type === 'VOTE_CAST') { return String(p.player_id || '') + ' → ' + String(p.target_player_id || ''); }
    if (type === 'ROLE_ASSIGNED') { return String(p.player_id || '') + ' · ' + String(p.role_ref || ''); }
    if (type === 'EVIDENCE_DEALT') { return String(p.location || '') + ' · ' + String(p.clue_id || ''); }
    for (var i = 0; i < TEXT_PATHS.length; i++) {
      var value = pickPath(p, TEXT_PATHS[i]);
      if (typeof value === 'string' && value) { return value; }
    }
    return JSON.stringify(p);
  }

  function ingestEvents(list) {
    if (!Array.isArray(list)) { return; }
    for (var i = 0; i < list.length; i++) {
      var ev = list[i];
      if (!ev || typeof ev.seq !== 'number') { continue; }
      /* 游标只由轮询推进（§3.4.2）：不可见事件也推进游标，保证不重复拉取 */
      if (ev.seq > state.cursor) { state.cursor = ev.seq; }
      if (!isVisible(ev)) { continue; }        /* R1：不可见事件不入列表 */
      var key = String(ev.seq);
      /* 去重键 = seq（与 WS 帧共用同一键空间）。契约 §3.4.2 竞态规则（队长裁决）：
         **轮询结果覆盖同 seq 的 WS 帧条目** —— REST 是主通道与权威表示（标签按 §5.2 ev.* 映射），
         且覆盖规则与网络时序无关（确定性），故此处不跳过、直接重写该键。 */
      state.items[key] = {
        id: key, order: ev.seq, seq: ev.seq,
        kind: evLabel(ev.type), text: evText(ev), time: hmsFromTs(ev.ts)
      };
    }
    if (state.tableId) { lsSet(LAST_SEQ_PREFIX + state.tableId, String(state.cursor)); }
    render();
  }

  /* F7 主通道：GET /api/campaigns/{campaign}/events（契约 §3.4.1 / §4.1 F7）
     取数做法 (a)：首次 since=-1&limit=1000 → 客户端取最新 50 条；
     增量 since=<游标>&limit=50；任一请求拉满（条数 == limit）则用推进后的游标续拉，最多 3 轮。
     请求一律带 ?token=<mobile token>（前向兼容，服务端当前忽略）。 */
  var FIRST_LIMIT = 1000;
  function loadEvents(initial, round) {
    if (!state.joined || !state.campaign) { return Promise.resolve(); }
    var attempt = round || 0;
    var limit = initial ? FIRST_LIMIT : TAIL;
    var since = initial ? -1 : state.cursor;
    /* R9：改走 mobile 端事件流 —— 服务端按 viewer 权威裁剪后才下发，
       客户端只拿可见 DTO（不再下发全量后靠前端隐藏）。 */
    var path = '/access/mobile/events?table_id=' + encodeURIComponent(state.tableId) +
      '&viewer=' + encodeURIComponent(state.playerId) +
      '&since=' + since + '&limit=' + limit +
      '&token=' + encodeURIComponent(state.token);
    return api(path).then(function (res) {
      if (res.status !== 200 || !res.json) {
        if (res.status === 0) { setErr($('eventsErr'), t('err.net')); }
        return;
      }
      setErr($('eventsErr'), '');
      /* /access/* 是统一包裹 {ok,data}；/api/* 是裸对象 —— 两者都兼容 */
      var body = (res.json && res.json.ok === true && res.json.data) ? res.json.data : res.json;
      var list = (body && body.events) || [];
      ingestEvents(list);
      if (list.length >= limit && attempt < 2) { return loadEvents(false, attempt + 1); }
    });
  }

  /* 按 seq 降序渲染（最新在最上），展示最新 TAIL 条（契约 §4 F7 / §4.1） */
  function render() {
    var all = [];
    for (var k in state.items) {
      if (Object.prototype.hasOwnProperty.call(state.items, k)) { all.push(state.items[k]); }
    }
    all.sort(function (a, b) { return b.order - a.order; });
    var newest = all.slice(0, TAIL);
    if (all.length > 200) {
      var keep = {};
      for (var j = 0; j < 200; j++) { keep[all[j].id] = all[j]; }
      state.items = keep;
    }
    var box = $('events');
    var html = '';
    for (var i = 0; i < newest.length; i++) {
      var e = newest[i];
      html += '<div class="item ev-item"><span class="ev-kind">' + escapeHtml(e.kind) + '</span>' +
        '<span class="ev-ts">#' + escapeHtml(String(e.seq)) + ' ' + escapeHtml(e.time) + '</span>' +
        '<div class="ev-text">' + escapeHtml(e.text) + '</div></div>';
    }
    box.innerHTML = html;
    box.scrollTop = 0;
  }

  /* ---------- F10 连接状态 + WS（可选增强通道；契约 §3） ---------- */
  /* 心跳语义（契约 §3.2/§3.5）：以「收到服务端 PING」为准 —— 服务端每 15s 下发 PING；
     客户端**不上行 PING**（服务端忽略上行 PING、无 PONG），只把任何收到的帧（含 PING）
     计入 lastFrameTs；连续 30s 无任何帧才主动重连（带 last_seq）。 */
  var BACKOFF = [1, 2, 4, 8, 30];
  var IDLE_LIMIT_MS = 30000;
  var KNOWN_KINDS = {
    STATE_DELTA: 1, TURN_UPDATED: 1, NARRATION_PENDING: 1, NARRATION_APPROVED: 1,
    WHISPER: 1, INFO_REVEALED: 1, BRANCH_TAKEN: 1, JOB_STATUS: 1,
    NPC_ACT_PROPOSED: 1, NPC_ACT_APPROVED: 1, SCENE_UPDATED: 1,
    PHASE_UPDATED: 1
  };

  /* WS 帧正文（与小程序端 lib/ws-client.js::frameText 逐条一致；契约 §3.4 可选增强通道） */
  function frameText(f) {
    if (!f) { return ''; }
    var kind = f.kind;
    if (kind === 'STATE_DELTA') {
      var delta = f.delta || {};
      return tpl('ext.ev.delta', { delta: delta.text || delta.message || delta.summary || JSON.stringify(delta) });
    }
    if (kind === 'TURN_UPDATED') {
      var turn = f.turn || {};
      return tpl('ext.ev.turn', { turn_no: (turn.turn_no === undefined ? '-' : turn.turn_no), state: turn.state || '' });
    }
    if (kind === 'NARRATION_PENDING') {
      var ptext = String((f.proposal || {}).text || '');
      return t('ext.ev.narrationPending') + (ptext ? ' · ' + ptext : '');
    }
    if (kind === 'NARRATION_APPROVED') { return String((f.narration || {}).text || ''); }
    if (kind === 'WHISPER') { return tpl('ext.ev.directed', { body: String((f.packet || {}).body || '') }); }
    if (kind === 'INFO_REVEALED') {
      var packet = f.packet || {};
      var body = String(packet.body || '');
      return tpl('ext.ev.info', { info_id: packet.info_id || '' }) + (body ? ' · ' + body : '');
    }
    if (kind === 'BRANCH_TAKEN') {
      var branch = f.branch || {};
      return tpl('ext.ev.branch', { label: branch.label || branch.node_id || '' });
    }
    if (kind === 'JOB_STATUS') {
      var job = f.job || {};
      return tpl('ext.ev.job', { job_id: job.job_id || '', status: job.status || '' });
    }
    return JSON.stringify(f);
  }

  function frameTime(ts) {
    if (ts === undefined || ts === null || ts === '') { return ''; }
    var value = ts;
    if (typeof value === 'number' && value < 1e12) { value = value * 1000; }
    var d = new Date(value);
    if (isNaN(d.getTime())) { return String(ts); }
    var p = function (n) { return String(n).length < 2 ? '0' + n : String(n); };
    return p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
  }

  /* WS 增强帧处置（契约 §3.4.2，两端逐字一致）：
     - 帧 seq <= 本地 last_seq → 直接丢弃（已被轮询覆盖或已显示过）
     - 帧 seq >  last_seq → 渲染（插入顶部、保持降序），但**不推进** last_seq
     - 去重键 = seq，与轮询结果共用同一键空间 */
  function pushWsFrame(f) {
    if (typeof f.seq !== 'number') { return; }
    if (f.seq <= state.cursor) { return; }
    var key = String(f.seq);
    if (state.items[key]) { return; }
    state.items[key] = {
      id: key, order: f.seq, seq: f.seq,
      kind: String(f.kind), text: frameText(f), time: frameTime(f.ts)
    };
    render();
  }

  function wsUrl() {
    var wsBase = normalizeServer(state.server)
      .replace(/^http:/i, 'ws:').replace(/^https:/i, 'wss:');
    /* 契约 §1.4：真实 WS 路径是 /ws；禁止使用 /access/info 的 data.ws 字段 */
    return wsBase + '/ws?table=' + encodeURIComponent(state.tableId) +
      '&viewer=' + encodeURIComponent(state.playerId) +
      '&role=pl&last_seq=' + state.cursor +
      '&token=' + encodeURIComponent(state.token);
  }

  /* F10 状态行：四态**只由轮询驱动**（契约 §3.4.2：WS 连不上/403/被拒/断开 → 静默降级，
     不得报错、不得阻塞 UI、**不得改变任何文案**）。因此 WS 状态只记在内存，不写任何可见文案。 */
  function setConnStatus(s) {
    state.connState = s;
    if ($('wsStatus')) { $('wsStatus').textContent = t('st.' + s); }
  }

  /* R13 断线自愈（UI 多模态实测修复：服务端重启后 10 分钟不恢复）：
     1) 握手超时 —— new WebSocket 在服务端重启/反代不可达时可能长期停在 CONNECTING，
        既不 open 也不 close，而看门狗只在 onopen 后才挂 -> 永远不重连。
        故对 CONNECTING 阶段独立设 HANDSHAKE_TIMEOUT_MS，超时强制 close -> onclose -> scheduleReconnect。
     2) onerror 不再吞 —— 原 onerror 是空实现。握手失败(502/403)会先 error 再 close；
        这里显式兜底，保证「只 error 没 close」也进重连链。
     3) scheduleReconnect 去重 —— 原实现用裸 setTimeout 不持句柄，error+close 双触发会叠加出
        多个定时器，退避被击穿。改为单一可取消的 state.reconnectTimer。
     4) 离开桌面/主动重连时撤销未决定时器，避免僵尸重连。 */
  var HANDSHAKE_TIMEOUT_MS = 10000;

  function clearReconnectTimer() {
    if (state.reconnectTimer) { window.clearTimeout(state.reconnectTimer); state.reconnectTimer = null; }
  }
  function clearHandshakeTimer() {
    if (state.handshakeTimer) { window.clearTimeout(state.handshakeTimer); state.handshakeTimer = null; }
  }

  function connectWs() {
    clearReconnectTimer();   /* 主动重连前先撤掉未决的重连定时器，避免叠加 */
    closeWs();
    if (!state.joined) { return; }
    var ws;
    try { ws = new WebSocket(wsUrl()); } catch (e) { scheduleReconnect(); return; }
    state.ws = ws;
    state.wsState = 'connecting';
    /* 握手超时看门狗：CONNECTING 卡住 >= HANDSHAKE_TIMEOUT_MS 即强制断开重连 */
    clearHandshakeTimer();
    state.handshakeTimer = window.setTimeout(function () {
      state.handshakeTimer = null;
      if (state.ws !== ws) { return; }
      var ready = -1;
      try { ready = ws.readyState; } catch (e) { /* ignore */ }
      if (ready === 0 || ready === 2) {   /* CONNECTING / CLOSING */
        try { ws.close(); } catch (e) { /* ignore */ }
        /* 某些浏览器/代理下 close() 不派发 onclose，显式补一次重连调度（去重保证只有一个定时器） */
        if (state.ws === ws) { state.ws = null; scheduleReconnect(); }
      }
    }, HANDSHAKE_TIMEOUT_MS);
    ws.onopen = function () {
      clearHandshakeTimer();
      state.wsState = 'open';
      state.backoffIdx = 0;
      state.lastFrameTs = Date.now();
      startWatchdog();
      /* R12 断线重连自动追平：重连成功立即按本地游标拉齐（无需用户操作/刷新） */
      state.cursor = parseInt(lsGet(LAST_SEQ_PREFIX + state.tableId) || String(state.cursor), 10);
      if (isNaN(state.cursor)) { state.cursor = -1; }
      refreshState();
      loadEvents(false);
    };
    ws.onmessage = function (ev) {
      state.lastFrameTs = Date.now();
      var f = null;
      try { f = JSON.parse(ev.data); } catch (e) { return; }
      if (!f || typeof f !== 'object') { return; }
      if (f.kind === 'PING') { return; }          /* PING 只刷新心跳（上方已置 lastFrameTs），不进事件列表 */
      if (!KNOWN_KINDS[f.kind]) { return; }        /* ACK / ERROR 等未知 kind 一律忽略（契约 §3.3） */
      pushWsFrame(f);                              /* 先按帧立即渲染（最快路径） */
      if (f.kind === 'WHISPER') { chatOnWhisper(f); }
      if (f.kind === 'STATE_DELTA' && (f.delta || {}).field === 'chat_mode') { chatOnStateDelta(f); }
      if (f.kind === 'STATE_DELTA' && (f.delta || {}).field === 'phase') { onPhaseDelta(f); }
      /* R12：推送驱动 —— 帧到达即拉权威事件流。游标仍只由 REST 拉取推进
         （保证 WS 漏帧时不跳过中间 seq），但**不再等 2s/15s 轮询**。 */
      pushRefresh();
    };
    ws.onclose = function () {
      stopWatchdog();
      clearHandshakeTimer();
      if (state.ws !== ws) { return; }   /* 已被 closeWs() 主动关闭（切页/离开桌面）则不重连 */
      state.ws = null;
      state.wsState = 'closed';
      scheduleReconnect();               /* 已连接后又断开（服务端重启）-> 立即进退避重连链 */
    };
    ws.onerror = function () {
      /* R13：error 也进重连链（原为空实现被吞）。onclose 随后通常会再触发一次，
         scheduleReconnect 内部去重，不会叠加定时器。失败不阻塞 UI（§3.1）。 */
      if (state.ws === ws) { scheduleReconnect(); }
    };
  }

  function closeWs() {
    stopWatchdog();
    clearHandshakeTimer();
    clearReconnectTimer();   /* 主动关闭（离开桌面/卸载）时撤销未决重连 */
    var ws = state.ws;
    state.ws = null;
    if (ws) {
      try { ws.onclose = null; ws.onerror = null; ws.close(); } catch (e) { /* ignore */ }
    }
  }

  function scheduleReconnect() {
    if (!state.joined) { return; }
    clearReconnectTimer();   /* 同一时刻只保留一个重连定时器（error+close 双触发不叠加） */
    var idx = Math.min(state.backoffIdx, BACKOFF.length - 1);
    var delay = BACKOFF[idx];
    state.backoffIdx = state.backoffIdx + 1;
    state.reconnectTimer = window.setTimeout(function () {
      state.reconnectTimer = null;
      if (state.joined) { connectWs(); }
    }, delay * 1000);
  }

  function startWatchdog() {
    stopWatchdog();
    state.watchTimer = window.setInterval(function () {
      if (Date.now() - state.lastFrameTs > IDLE_LIMIT_MS) {
        state.lastFrameTs = Date.now();
        connectWs();     /* 30s 无任何帧：主动重连（connectWs 内部先清未决重连定时器） */
      }
    }, 5000);
  }
  function stopWatchdog() {
    if (state.watchTimer) { window.clearInterval(state.watchTimer); state.watchTimer = null; }
  }

  /* ---------- F8 语音录制与上传 ---------- */
  function recSupported() {
    var nav = window.navigator || {};
    return !!(nav.mediaDevices && nav.mediaDevices.getUserMedia && window.MediaRecorder);
  }
  function startRecording() {
    setErr($('recErr'), '');
    $('recOk').textContent = '';
    if (!recSupported()) {
      setErr($('recErr'), t('ext.st.recordUnsupported'));
      return;
    }
    if (!state.joined || !state.campaign) {
      setErr($('recErr'), t('ext.st.needCode'));
      return;
    }
    window.navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      state.mediaStream = stream;
      state.chunks = [];
      var mr = new MediaRecorder(stream);
      state.mediaRecorder = mr;
      mr.ondataavailable = function (ev) { if (ev.data && ev.data.size > 0) { state.chunks.push(ev.data); } };
      mr.onstop = function () { uploadRecording(); };
      mr.start();
      $('btnRecStart').disabled = true;
      $('btnRecStop').disabled = false;
      $('recStatus').textContent = t('ext.st.recording');
    }, function () {
      setErr($('recErr'), t('ext.st.recordUnsupported'));
    });
  }
  function stopRecording() {
    var mr = state.mediaRecorder;
    if (!mr) { return; }
    try { mr.stop(); } catch (e) { /* ignore */ }
    $('btnRecStart').disabled = false;
    $('btnRecStop').disabled = true;
    if (state.mediaStream) {
      try { state.mediaStream.getTracks().forEach(function (tr) { tr.stop(); }); } catch (e) { /* ignore */ }
      state.mediaStream = null;
    }
  }
  function uploadRecording() {
    var blob = new Blob(state.chunks, { type: 'audio/webm' });
    state.chunks = [];
    if (!blob.size) {
      setErr($('recErr'), t('err.server'));
      return;
    }
    var fd = new FormData();
    fd.append('file', blob, 'voice.webm');
    fd.append('campaign', state.campaign);
    fd.append('kind', 'voice');
    fd.append('player_id', state.playerId);
    $('recStatus').textContent = t('st.connecting');
    api('/access/player/audio', { method: 'POST', body: fd, form: true }).then(function (res) {
      $('recStatus').textContent = t('st.connected');
      if (res.status === 200 && res.json && res.json.ok) {
        var d = res.json.data || {};
        var line = tpl('ext.st.uploadOk', { bytes: (d.bytes === undefined ? blob.size : d.bytes) });
        /* file_ref 只显示文件名部分（两端一致）：不回显服务端绝对路径 */
        if (d.file_ref) {
          var parts = String(d.file_ref).split(/[\\/]/);
          line += ' · ' + parts[parts.length - 1];
        }
        if (d.stt && d.stt.status) { line += ' · ' + tpl('ext.st.sttStatus', { status: d.stt.status }); }
        $('recOk').textContent = line;
      } else {
        setErr($('recErr'), errTextFor(res.status, res.json));
      }
    });
  }

  /* ---------- F9 录音设备状态（只读） ---------- */
  function queryDevice() {
    setErr($('deviceErr'), '');
    $('deviceOut').innerHTML = '';
    var id = String($('deviceId').value || '').trim();
    if (!id) { setErr($('deviceErr'), t('ph.deviceId')); return; }
    api('/access/device/status?device_id=' + encodeURIComponent(id)).then(function (res) {
      if (res.status === 404) { setErr($('deviceErr'), t('st.noDevice')); return; }
      if (res.status !== 200 || !res.json || !res.json.ok) {
        setErr($('deviceErr'), errTextFor(res.status, res.json));
        return;
      }
      var d = res.json.data || {};
      var keys = ['device_id', 'status_text', 'recording', 'flagged', 'battery', 'note', 'ts', 'seq'];
      var html = '';
      for (var i = 0; i < keys.length; i++) {
        var k = keys[i];
        if (d[k] === undefined) { continue; }
        html += '<div class="kv"><span class="k">' + escapeHtml(k) + '</span><span>' +
          escapeHtml(String(d[k])) + '</span></div>';
      }
      $('deviceOut').innerHTML = html;
    });
  }

  /* ---------- T15 (additive): R10/R11 地点交互面板 ----------
     只新增：不改既有轮询/WS/提交链路；动作集与热区锚点全部由服务端下发
     （GET /api/campaigns/{c}/interactives -> anchor/actions；POST .../interact）。
     敏感动作走既有审批总线（服务端返回 pending_approval -> 玩家进入「已上报待主持人」）。 */
  var IX = { objects: [], rooms: [], selId: '', busy: false, mounted: false,
             lastMine: 0, lastLoad: 0, loadedCampaign: '', lastLabel: '', pendingLabel: '',
             scenes: [], currentScene: '', sceneTrace: [], scenesLoaded: false };
  var IX_LOAD_MS = 5000;
  var IX_MINE_MS = 2500;
  /* 家具种类 -> 短标签（热区按钮用；避免长名称溢出，见 R33 碰撞判据） */
  var IX_KIND = {
    cabinet: '柜子', desk: '书桌', drawer: '抽屉', door: '门', safe: '保险箱',
    shelf: '架子', locker: '柜子', chest: '箱子', box: '箱子', table: '桌子',
    bed: '床', window: '窗', painting: '画', statue: '雕像', furniture: '家具'
  };

  function ixShort(o) { return IX_KIND[o.kind] || String(o.name || o.id); }

  function ixMount() {
    if (IX.mounted || !$('viewTable')) { return; }
    var card = document.createElement('div');
    card.className = 'card';
    card.id = 'ixCard';
    card.innerHTML =
      '<h2 class="card-title">' + escapeHtml(t('ix.title')) + '</h2>' +
      '<div class="status-line" id="ixRoom"></div>' +
      '<div id="ixMap" style="position:relative;height:150px;margin:var(--space-sm) 0;' +
      'border:1px solid var(--color-border);border-radius:var(--radius-card);overflow:hidden"></div>' +
      /* T1 (additive): 场景栏目 —— 地图卡下方，多线叙事入口 */
      '<div class="scenes card-section" id="ixScenes" style="margin-top:var(--space-sm)">' +
        '<h3 class="card-subtitle">' + escapeHtml(t('sc.title')) + '</h3>' +
        '<div class="status-line" id="ixSceneTitle">' + escapeHtml(t('sc.loading')) + '</div>' +
        '<div class="scene-branches" id="ixSceneBranches"></div>' +
        '<div class="status-line scene-trace" id="ixSceneTrace"></div>' +
        '<div class="ok-line" id="ixSceneOut"></div>' +
      '</div>' +
      '<div class="actions" id="ixActions"></div>' +
      '<div class="events" id="ixList"></div>' +
      '<div class="row" style="margin-top:8px"><div class="ok-line" id="ixOut"></div></div>' +
      '<div class="status-line" id="ixMine"></div>' +
      '<div id="ixErr" class="err-bar hidden"></div>';
    $('viewTable').appendChild(card);
    IX.mounted = true;
  }

  function ixLoad() {
    if (!state.joined || !state.campaign) { return Promise.resolve(); }
    if (IX.loadedCampaign !== state.campaign) { IX.loadedCampaign = state.campaign; IX.selId = ''; }
    return api('/api/campaigns/' + encodeURIComponent(state.campaign) + '/interactives?viewer=' +
               encodeURIComponent(state.playerId || '')).then(function (res) {
      if (res.status !== 200 || !res.json) { setErr($('ixErr'), errTextFor(res.status, res.json)); return; }
      setErr($('ixErr'), '');
      IX.objects = res.json.objects || [];
      IX.rooms = res.json.rooms || [];
      var still = false;
      for (var i = 0; i < IX.objects.length; i++) { if (IX.objects[i].id === IX.selId) { still = true; } }
      if (!still) { IX.selId = ''; }
      ixRender();
    });
  }

  function ixRender() {
    if (!IX.mounted) { return; }
    var room = IX.rooms.length ? IX.rooms[0] : null;
    $('ixRoom').textContent = room
      ? tpl('ix.room', { room: room.name || room.id, n: IX.objects.length })
      : (IX.objects.length ? tpl('ix.all', { n: IX.objects.length }) : t('ix.none'));
    var map = $('ixMap');
    map.innerHTML = '';
    if (room) {
      var w = map.clientWidth || 320;
      var s = Math.min(w / Math.max(room.w || 1, 1), 150 / Math.max(room.h || 1, 1));
      for (var i = 0; i < IX.objects.length; i++) {
        if (String(IX.objects[i].room) !== String(room.id)) { continue; }   /* 只画本房间热区 */
        (function (o) {
          var b = document.createElement('button');
          b.type = 'button';
          b.className = 'btn' + (o.id === IX.selId ? ' btn-primary' : '');
          b.setAttribute('data-ix-hot', o.id);
          b.textContent = ixShort(o);
          b.style.position = 'absolute';
          b.style.left = Math.round((o.anchor.x - room.x) * s) + 'px';
          b.style.top = Math.round((o.anchor.y - room.y) * s) + 'px';
          b.style.padding = '2px 8px';
          b.style.fontSize = '12px';
          b.onclick = function () { ixSelect(o.id); };
          map.appendChild(b);
        })(IX.objects[i]);
      }
    }
    var html = '';
    for (var j = 0; j < IX.objects.length; j++) {
      var o = IX.objects[j];
      html += '<div class="item ev-item"><span class="ev-kind">' + escapeHtml(ixShort(o)) + '</span>' +
        '<span class="ev-ts">' + escapeHtml(String(o.room)) + '</span>' +
        '<div class="ev-text">' + escapeHtml(o.name) + '</div></div>';
    }
    $('ixList').innerHTML = html;
    ixRenderActions();
  }

  function ixSelected() {
    for (var i = 0; i < IX.objects.length; i++) {
      if (IX.objects[i].id === IX.selId) { return IX.objects[i]; }
    }
    return null;
  }

  function ixRenderActions() {
    var box = $('ixActions');
    if (!box) { return; }
    box.innerHTML = '';
    var obj = ixSelected();
    if (!obj) { box.textContent = t('ix.pick'); return; }
    box.textContent = '';
    var acts = obj.actions || [];
    for (var k = 0; k < acts.length; k++) {
      (function (a) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = a.sensitive ? 'btn' : 'btn-primary';
        b.setAttribute('data-ix-action', a.action);
        b.textContent = String(a.label || a.action) + (a.sensitive ? t('ix.report') : '');
        b.disabled = !!IX.busy;
        b.onclick = function () { ixAct(obj.id, a.action); };
        box.appendChild(b);
      })(acts[k]);
    }
  }

  function ixSelect(id) { IX.selId = id; ixRender(); }

  function ixAct(objectId, action) {
    if (IX.busy || !state.joined || !state.campaign) { return; }
    IX.busy = true;
    setErr($('ixErr'), '');
    $('ixOut').textContent = '';
    ixRenderActions();
    api('/api/campaigns/' + encodeURIComponent(state.campaign) + '/interact', {
      method: 'POST',
      body: { player_id: state.playerId, object_id: objectId, action: action, req_id: newReqId() }
    }).then(function (res) {
      IX.busy = false;
      var j = res.json || {};
      if (res.status === 201 && j.status === 'ok') {
        var r = j.result || {};
        $('ixOut').textContent = String(r.text || '') +
          (r.level ? '（' + String(r.level) + (typeof r.rolled === 'number' ? ' d100=' + r.rolled : '') + '）' : '');
        loadEvents(false);
      } else if (res.status === 201 && j.status === 'pending_approval') {
        IX.lastLabel = String(j.label || '');
        IX.pendingLabel = IX.lastLabel;   /* 未决定期间：WS 帧到达即强制刷新（绕过节流） */
        $('ixOut').textContent = String(j.state || t('ix.pending')) + '：' + IX.lastLabel;
        ixMine(true);
      } else {
        setErr($('ixErr'), errTextFor(res.status, res.json));
      }
      ixRenderActions();
    });
  }

  function ixMine(force) {
    if (!state.joined || !state.campaign) { return; }
    var now = Date.now();
    if (!force && now - IX.lastMine < IX_MINE_MS) { return; }
    IX.lastMine = now;
    api('/api/campaigns/' + encodeURIComponent(state.campaign) + '/pipeline/mine?player_id=' +
        encodeURIComponent(state.playerId || '')).then(function (res) {
      if (res.status !== 200 || !res.json) { return; }
      var items = res.json.items || [];
      var lines = [];
      for (var i = 0; i < items.length; i++) {
        var it = items[i];
        var st = String(it.state) === '已下发' ? t('ix.delivered')
          : (String(it.state) === '已驳回' ? t('ix.rejected') : t('ix.pending'));
        lines.push(String(it.label || '') + ' · ' + st + (it.text ? '：' + String(it.text) : ''));
        /* 主持人已决定 -> 就地刷新结果行（无需手动刷新页面） */
        if (IX.lastLabel && String(it.label) === IX.lastLabel && it.text) {
          $('ixOut').textContent = st + '：' + String(it.text);
        }
        if (IX.pendingLabel && String(it.label) === IX.pendingLabel &&
            (String(it.state) === '已下发' || String(it.state) === '已驳回')) {
          IX.pendingLabel = '';   /* 已决定：恢复节流 */
        }
      }
      $('ixMine').textContent = lines.length ? (t('ix.mine') + '：' + lines.join(' ｜ ')) : '';
    });
  }

  function ixRefresh() {
    if (!state.joined) { return; }
    ixMine(!!IX.pendingLabel);   /* 自己有未决定的报备 -> 强制刷新，避免漏掉下发 */
    ixSceneLoad();
    t7Refresh();
    var now = Date.now();
    if (now - IX.lastLoad < IX_LOAD_MS) { return; }
    IX.lastLoad = now;
    ixLoad();
  }

  function ixStart() {
    ixMount();
    IX.selId = '';
    IX.lastMine = 0;
    IX.lastLoad = Date.now();
    ixLoad();
    ixMine(true);
    ixSceneLoad();   /* T1 (additive): 进入桌面加载场景栏目 */
    t7Mount();       /* T7 (additive): M4/M5/M6/M7 主持人台 */
    t7Load(true);
  }

  function ixStop() {
    IX.objects = [];
    IX.rooms = [];
    IX.selId = '';
    if (IX.mounted) { ixRender(); }
  }

  /* ---------- T1 (additive): 场景栏目（地图卡下方，多线叙事） ---------- */
  function ixSceneLoad() {
    if (!state.joined || !state.campaign) { return Promise.resolve(); }
    if (IX.scenesLoaded) { return Promise.resolve(); }
    IX.scenesLoaded = true;
    var box = $('ixScenes');
    if (box) { $('ixSceneTitle').textContent = t('sc.loading'); }
    return api('/api/campaigns/' + encodeURIComponent(state.campaign) + '/scenes')
      .then(function (res) {
        if (res.status !== 200 || !res.json) { return; }
        var body = res.json;
        IX.scenes = (body && body.scenes) || [];
        IX.currentScene = String((body && body.current_scene) || '');
        if (IX.scenes.length) {
          if (!IX.currentScene) { IX.currentScene = IX.scenes[0].scene_id; }
          ixSceneRender();
        }
      });
  }

  function ixSceneCurrent() {
    for (var i = 0; i < IX.scenes.length; i++) {
      if (String(IX.scenes[i].scene_id) === String(IX.currentScene)) { return IX.scenes[i]; }
    }
    return null;
  }

  function ixSceneRender() {
    if (!IX.mounted) { return; }
    var cur = ixSceneCurrent();
    var titleBox = $('ixSceneTitle');
    var branchesBox = $('ixSceneBranches');
    var traceBox = $('ixSceneTrace');
    var outBox = $('ixSceneOut');
    if (!cur) {
      if (titleBox) { titleBox.textContent = t('sc.empty'); }
      if (branchesBox) { branchesBox.innerHTML = ''; }
      if (traceBox) { traceBox.innerHTML = ''; }
      if (outBox) { outBox.textContent = ''; }
      return;
    }
    if (titleBox) {
      titleBox.textContent = tpl('sc.current', { scene: cur.title || cur.scene_id }) +
        (cur.summary ? ' · ' + String(cur.summary) : '');
    }
    branchesBox.innerHTML = '';
    var branches = cur.branches || [];
    if (!branches.length) {
      branchesBox.textContent = t('sc.locked') === '（未解锁）' ? '' : '';
      branchesBox.textContent = '';
    }
    for (var i = 0; i < branches.length; i++) {
      (function (br) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'btn' + (br.locked ? '' : ' btn-primary');
        b.setAttribute('data-scene-branch', br.to_scene_id);
        b.disabled = !!br.locked;
        b.textContent = tpl('sc.branch', { label: br.label || br.to_scene_id }) +
          (br.locked ? t('sc.locked') : '') +
          (br.condition ? ' · ' + String(br.condition) : '');
        b.onclick = function () { ixSceneAdvance(br.to_scene_id, br.edge_id); };
        branchesBox.appendChild(b);
      })(branches[i]);
    }
    /* 叙事轨迹：n_arrival → n_forecourt → ... */
    if (traceBox) {
      var trace = [];
      for (var j = 0; j < IX.sceneTrace.length; j++) {
        trace.push(IX.sceneTrace[j].scene_id || IX.sceneTrace[j]);
      }
      if (IX.currentScene && trace[trace.length - 1] !== IX.currentScene) {
        trace.push(IX.currentScene);
      }
      traceBox.textContent = trace.length ? '轨迹：' + trace.join(' → ') : '';
    }
    if (outBox) { outBox.textContent = ''; }
  }

  function ixSceneAdvance(toSceneId, edgeId) {
    if (!state.joined || !state.campaign) { return; }
    var body = { to_scene_id: toSceneId, req_id: newReqId(), actor: state.playerId || 'pl' };
    if (edgeId) { body.edge_id = edgeId; }
    $('ixSceneOut').textContent = '';
    return api('/api/campaigns/' + encodeURIComponent(state.campaign) + '/scenes/advance', {
      method: 'POST',
      body: body
    }).then(function (res) {
      if (res.status === 201 && res.json && res.json.ok) {
        var j = res.json;
        IX.sceneTrace.push(IX.currentScene);
        IX.currentScene = String(j.scene_id || toSceneId);
        ixSceneRender();
        /* 场景切换 -> 地图变化：刷新交互面板的房间/热区 */
        if (j.map_id) { IX.loadedCampaign = ''; ixLoad(); }
        loadEvents(false);
        refreshState();
      } else {
        $('ixSceneOut').textContent = errTextFor(res.status, res.json);
      }
    });
  }

  function ixSceneStop() {
    IX.scenes = [];
    IX.currentScene = '';
    IX.sceneTrace = [];
    IX.scenesLoaded = false;
    if (IX.mounted) { ixSceneRender(); }
  }


  /* ---------- T7 (additive): M4 看板 / M5 战斗 / M6 轨迹 / M7 仪表盘 ---------- */
  var T7 = { board: null, combat: null, timeline: [], dash: null, mounted: false, last: 0 };
  var T7_LOAD_MS = 6000;

  function t7Mount() {
    if (T7.mounted || !$('viewTable')) { return; }
    var card = document.createElement('div');
    card.className = 'card';
    card.id = 't7Card';
    card.innerHTML =
      '<h2 class="card-title">' + escapeHtml('主持人台') + '</h2>' +
      '<div class="status-line" id="t7DashMini"></div>' +
      '<div class="events" id="t7Combat" style="max-height:120px;overflow:auto;margin-top:6px"></div>' +
      '<div class="events" id="t7Timeline" style="max-height:120px;overflow:auto;margin-top:6px"></div>' +
      '<div class="events" id="t7Board" style="max-height:140px;overflow:auto;margin-top:6px"></div>' +
      '<div class="ok-line" id="t7Out"></div>';
    $('viewTable').appendChild(card);
    T7.mounted = true;
  }

  function t7Load(force) {
    if (!state.joined || !state.campaign) { return Promise.resolve(); }
    var now = Date.now();
    if (!force && now - T7.last < T7_LOAD_MS) { return Promise.resolve(); }
    T7.last = now;
    var c = encodeURIComponent(state.campaign);
    var hdr = {};
    if (state.token) { hdr.Authorization = 'Bearer ' + state.token; }
    return Promise.all([
      api('/api/campaigns/' + c + '/dashboard'),
      api('/api/campaigns/' + c + '/combat/current'),
      api('/api/campaigns/' + c + '/timeline'),
      api('/api/campaigns/' + c + '/board')
    ]).then(function (rs) {
      var dash = rs[0] && rs[0].json || {};
      var combat = rs[1] && rs[1].json || {};
      var tl = rs[2] && rs[2].json || {};
      var board = rs[3] && rs[3].json || {};
      T7.dash = dash; T7.combat = combat; T7.timeline = (tl.timeline || []); T7.board = board;
      t7Render();
    });
  }

  function t7Render() {
    if (!T7.mounted) { return; }
    // dashboard mini
    var dm = $('t7DashMini');
    if (dm) {
      var ai = (T7.dash && T7.dash.ai) || {};
      var prog = (T7.dash && T7.dash.progress) || {};
      dm.textContent = '事件 ' + (prog.total_events || 0) + ' · 场景 ' + (prog.current_scene || '—') +
        ' · AI: ' + (ai.next_step || '（无建议）') + (ai.needs_host ? ' · 等待主持人' : '');
    }
    // combat
    var cm = $('t7Combat');
    if (cm) {
      var cbt = (T7.combat && T7.combat.combat) || null;
      if (!cbt) { cm.textContent = '（无进行中的战斗）'; }
      else {
        var pend = (cbt.pending_resolutions || []).length;
        var rnd = cbt.round || 0;
        cm.textContent = '战斗 ' + (cbt.combat_id || '') + ' · 第 ' + rnd + ' 轮 · ' +
          (pend ? '待批准 ' + pend + ' 项（未批准不写入）' : '已批准') + ' · 状态 ' + cbt.status;
      }
    }
    // timeline
    var tm = $('t7Timeline');
    if (tm) {
      var cps = (T7.timeline || []).filter(function (x) { return x.type === 'checkpoint'; });
      tm.textContent = '轨迹: ' + T7.timeline.length + ' 项 · 存档点 ' + cps.length + ' 个' +
        (cps.length ? '（最新 ' + cps[cps.length - 1].label + '）' : '');
    }
    // board
    var bd = $('t7Board');
    if (bd) {
      var npcs = (T7.board.npcs || []);
      var players = (T7.board.players || []);
      var line = '玩家 ' + players.length + ' · NPC ' + npcs.length;
      if (npcs.length) {
        var t0 = (npcs[0].behavior_tendency || {});
        line += ' · ' + npcs[0].npc_id + ' 倾向 ' + (t0.kind || '—') + ' (' + (t0.status || '—') + ')';
      }
      bd.textContent = line;
    }
  }

  function t7Refresh() { if (state.joined) { t7Load(); } }

  /* ---------- M3 (additive, T6): 私聊系统 ----------
     四态徽标 + 公共/私聊输入；服务端权威门控（前端只读展示 + 提交前本地提示）。
     REST: GET /api/campaigns/{c}/chat/status, POST /api/campaigns/{c}/chat/private。
     WS: PRIVATE_MSG -> WHISPER 帧（目标定向）；CHAT_MODE_SET -> STATE_DELTA(chat_mode)。 */
  var CHAT = {
    mode: 'chat_enabled', players: [], mounted: false, busy: false,
    lastLoad: 0, loadedCampaign: '', history: []
  };
  var CHAT_LOAD_MS = 5000;

  function chatMount() {
    if (CHAT.mounted || !$('viewTable')) { return; }
    var card = document.createElement('div');
    card.className = 'card';
    card.id = 'chatCard';
    card.innerHTML =
      '<h2 class="card-title">' + escapeHtml(t('chat.title')) + '</h2>' +
      '<div class="status-line" id="chatBadge"></div>' +
      '<div class="row" style="margin-top:8px">' +
      '  <select id="chatTarget" class="input" style="flex:1" title="' + escapeHtml(t('chat.targetPlaceholder')) + '"></select>' +
      '</div>' +
      '<div class="row" style="margin-top:8px">' +
      '  <input id="chatText" class="input" style="flex:1" maxlength="2000" placeholder="' + escapeHtml(t('chat.inputPub')) + '" />' +
      '  <button id="chatSend" class="btn btn-primary" type="button">' + escapeHtml(t('chat.send')) + '</button>' +
      '</div>' +
      '<div class="events" id="chatLog" style="max-height:180px;overflow:auto;margin-top:8px"></div>' +
      '<div class="ok-line" id="chatOut"></div>' +
      '<div id="chatErr" class="err-bar hidden"></div>';
    $('viewTable').appendChild(card);
    $('chatSend').onclick = chatSend;
    $('chatText').onkeydown = function (e) {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); chatSend(); }
    };
    CHAT.mounted = true;
  }

  function chatLoad(force) {
    if (!state.joined || !state.campaign) { return Promise.resolve(); }
    var now = Date.now();
    if (!force && now - CHAT.lastLoad < CHAT_LOAD_MS) { return Promise.resolve(); }
    CHAT.lastLoad = now;
    return api('/api/campaigns/' + encodeURIComponent(state.campaign) + '/chat/status').then(function (res) {
      if (res.status !== 200 || !res.json) { setErr($('chatErr'), errTextFor(res.status, res.json)); return; }
      setErr($('chatErr'), '');
      var d = res.json;
      CHAT.mode = d.mode || 'chat_enabled';
      CHAT.players = Array.isArray(d.players) ? d.players : [];
      CHAT.history = CHAT.history || [];
      chatRender();
    });
  }

  function chatRender() {
    if (!CHAT.mounted) { return; }
    var badge = $('chatBadge');
    if (!badge) { return; }
    var modeText = t('chat.st.' + CHAT.mode) || CHAT.mode;
    var privOk = CHAT.mode === 'chat_enabled';
    var pubOk = CHAT.mode !== 'all_disabled';
    badge.textContent = tpl('chat.status', { state: modeText }) +
      ' · ' + (privOk ? t('chat.privateAllowed') : t('chat.privateBlocked')) +
      ' · ' + (pubOk ? t('chat.publicAllowed') : t('chat.publicBlocked'));
    var sel = $('chatTarget');
    if (sel) {
      var html = '<option value="">' + escapeHtml(t('chat.targetPlaceholder')) + '</option>';
      var seen = {};
      for (var i = 0; i < CHAT.players.length; i++) {
        var pid = String(CHAT.players[i].id || '');
        if (!pid || pid === state.playerId || seen[pid]) { continue; }
        seen[pid] = 1;
        html += '<option value="' + escapeHtml(pid) + '">' + escapeHtml(pid) + '</option>';
      }
      sel.innerHTML = html;
    }
    var input = $('chatText');
    var sendBtn = $('chatSend');
    if (input) { input.disabled = !pubOk && !privOk; }
    if (sendBtn) { sendBtn.disabled = !pubOk && !privOk; }
    if (sel) { sel.disabled = !pubOk; }
    chatRenderLog();
  }

  function chatRenderLog() {
    var box = $('chatLog');
    if (!box) { return; }
    var html = '';
    for (var i = 0; i < CHAT.history.length; i++) {
      var m = CHAT.history[i];
      html += '<div class="item ev-item"><span class="ev-kind">' + escapeHtml(m.kind) + '</span>' +
        '<span class="ev-ts">' + escapeHtml(String(m.who || '')) + '</span>' +
        '<div class="ev-text">' + escapeHtml(m.text) + '</div></div>';
    }
    box.innerHTML = html;
    box.scrollTop = box.scrollHeight;
  }

  function chatSend() {
    if (!state.joined || !state.campaign) { setErr($('chatErr'), t('chat.needJoin')); return; }
    var text = String($('chatText').value || '').trim();
    if (!text) { return; }
    var target = String($('chatTarget').value || '').trim();
    var isPriv = !!target;
    if (target === state.playerId) { setErr($('chatErr'), t('chat.toSelf')); return; }
    if (isPriv && CHAT.mode !== 'chat_enabled') {
      setErr($('chatErr'), tpl('chat.privDisabled', { state: t('chat.st.' + CHAT.mode) || CHAT.mode }));
      return;
    }
    if (!isPriv && CHAT.mode === 'all_disabled') {
      setErr($('chatErr'), tpl('chat.pubDisabled', { state: t('chat.st.' + CHAT.mode) || CHAT.mode }));
      return;
    }
    if (CHAT.busy) { return; }
    CHAT.busy = true;
    setErr($('chatErr'), '');
    var body = { player_id: state.playerId, to_players: isPriv ? [target] : ['_public_'], text: text };
    api('/api/campaigns/' + encodeURIComponent(state.campaign) + '/chat/private', {
      method: 'POST', body: body
    }).then(function (res) {
      CHAT.busy = false;
      if (res.status === 201 && res.json) {
        $('chatOut').textContent = isPriv ? t('chat.sent') : t('chat.pubSent');
        CHAT.history.push({ kind: isPriv ? '私聊' : '公共', who: state.playerId + (isPriv ? '→' + target : ''), text: text });
        if (CHAT.history.length > 100) { CHAT.history = CHAT.history.slice(-100); }
        $('chatText').value = '';
        chatRenderLog();
        loadEvents(false);
      } else {
        setErr($('chatErr'), tpl('chat.reqFailed', { err: errTextFor(res.status, res.json) }));
      }
    });
  }

  function chatOnWhisper(frame) {
    var body = String((frame.packet || {}).body || '');
    var from = String((frame.packet || {}).info_id || '');
    if (!body) { return; }
    CHAT.history = CHAT.history || [];
    CHAT.history.push({ kind: '私聊', who: from, text: body });
    if (CHAT.history.length > 100) { CHAT.history = CHAT.history.slice(-100); }
    if (CHAT.mounted) { chatRenderLog(); }
  }

  function chatOnStateDelta(frame) {
    var d = frame.delta || {};
    if (d.field === 'chat_mode') {
      CHAT.mode = String((d.value || {}).mode || CHAT.mode);
      if (CHAT.mounted) { chatRender(); }
    }
  }

  function chatRefresh() {
    if (!state.joined) { return; }
    chatLoad(false);
  }

  function chatStart() {
    chatMount();
    CHAT.lastLoad = 0;
    chatLoad(true);
  }

  function chatStop() {
    CHAT.history = [];
    CHAT.players = [];
    if (CHAT.mounted) { chatRender(); }
  }

  /* ==================================================================
     T13 (additive): 大厅 / 开始页 / 进行中 三视图 + phase 门控
     最小侵入：全部为新增函数 + 新增容器，不改 showView / joinTable /
     ixMount / chatMount / t7Mount 内部逻辑。
     契约（launcher_api，实测）：
       GET  /api/campaigns                  [任意启用端] 团列表
       POST /api/campaigns                  [主持人 webapp] 新建团
       GET  /api/campaigns/{id}/lobby       [主持人] 开始页聚合
       POST /api/campaigns/{id}/start       [主持人] phase->running
       POST /api/campaigns/{id}/pause|end   [主持人]
       POST /api/campaigns/{id}/resume      [主持人] 读档
       GET  /api/campaigns/{id}/checkpoints [主持人] 存档点
       POST /api/campaigns/{id}/timeline/checkpoint [主持人] 手动存档
     hash 路由：无 hash 直连兼容（?campaign= 老书签仍走现有 viewTable 流程）。
  ================================================================== */

  /* ---- hash 路由：三视图切换（不触碰 showView 内部逻辑） ---- */
  function currentHashPath() {
    var h = String(window.location.hash || '').replace(/^#/, '');
    if (h.charAt(0) !== '/') { h = '/' + h; }
    return h;
  }

  function parseHash() {
    var h = currentHashPath();
    var m;
    if (h === '/lobby' || h === '/') { return { view: 'lobby' }; }
    m = h.match(/^\/setup\/([^/?#]+)/);
    if (m) { return { view: 'setup', id: decodeURIComponent(m[1]) }; }
    m = h.match(/^\/play\/([^/?#]+)/);
    if (m) { return { view: 'play', id: decodeURIComponent(m[1]) }; }
    return { view: null };
  }

  function routeHash() {
    var r = parseHash();
    if (!r.view) {
      /* 未知 hash / 无 hash：保留无 hash 直连兼容 —— 不劫持老书签流程 */
      return;
    }
    if (r.view === 'lobby') {
      showView('setup');
      lobbyMount();
      showLobbyCard(true);
      showSetupCard(false);
      hideGateBar();
      lobbyRefresh();
      return;
    }
    if (r.view === 'setup') {
      showView('setup');
      lobbyMount();
      showLobbyCard(false);
      showSetupCard(true);
      hideGateBar();
      T13.setupId = r.id;
      setupView(r.id);
      return;
    }
    if (r.view === 'play') {
      if (state.joined && state.campaign) {
        showLobbyCard(false);
        showSetupCard(false);
        showView('table');
        applyPhaseGate();
        syncPhaseForTable().then(applyPhaseGate);
      } else {
        showView('setup');
        lobbyMount();
        showLobbyCard(false);
        showSetupCard(false);
        T13.pendingPlay = r.id;
        setErr($('setupErr'), t('lobby.needJoin'));
      }
      return;
    }
  }


  /* ---- 大厅/开始页卡片显隐（三视图互斥呈现） ---- */
  function showLobbyCard(on) {
    var c = document.getElementById('lobbyCard');
    if (c) { show(c, on); }
  }
  function showSetupCard(on) {
    var c = document.getElementById('setupView');
    if (c) { show(c, on); }
  }
  function hideGateBar() {
    var g = document.getElementById('gateBar');
    if (g) { show(g, false); }
  }

  /* ---- 大厅只读数据源：GET /api/campaigns（任意启用端 token 可读，含玩家） ---- */
  /* 大厅按钮直接读输入框（与 testConnection/resolveCode 一致），不要求先点「测试连接」 */
  function lobbySyncCreds() {
    /* D2 (T15): 只在输入框有值时覆盖 state，避免空输入把 localStorage 持久化的
       server/token 冲掉（applyPrefs 已把持久值装入 state）。 */
    var srv = document.getElementById('server');
    var tok = document.getElementById('token');
    if (srv && String(srv.value || '').trim()) {
      state.server = normalizeServer(srv.value);
      lsSet(LS.server, state.server);
    }
    if (tok && String(tok.value || '').trim()) {
      state.token = String(tok.value || '').trim();
      lsSet(LS.token, state.token);
    }
    if (!state.server) {
      var saved = lsGet(LS.server);
      if (saved) { state.server = normalizeServer(saved); }
    }
    if (!state.token) {
      var savedTok = lsGet(LS.token);
      if (savedTok) { state.token = savedTok.trim(); }
    }
  }

  function lobbyNeedCreds() {
    lobbySyncCreds();
    var okServer = !!(state.server && state.token);
    if (!okServer) {
      if (document.getElementById('lobbyErr')) { setErr($('lobbyErr'), t('lobby.needServerToken')); }
      return false;
    }
    return true;
  }

  function lobbyMount() {
    if (document.getElementById('lobbyCard')) { return; }
    var card = document.createElement('div');
    card.className = 'card';
    card.id = 'lobbyCard';
    card.innerHTML =
      '<h2 class="card-title">' + escapeHtml(t('lobby.title')) + '</h2>' +
      '<div class="warn-line" id="lobbyNote">' + escapeHtml(t('lobby.codeNote')) + '</div>' +
      '<div class="warn-line" style="margin-top:4px">' + escapeHtml(t('lobby.tokenNote')) + '</div>' +
      '<div class="row" style="margin-top:8px">' +
      '  <input class="input" id="lobbyNewName" type="text" autocomplete="off" placeholder="' + escapeHtml(t('lobby.newName')) + '" style="flex:1" />' +
      '  <button type="button" class="btn btn-primary" id="lobbyCreateBtn">' + escapeHtml(t('lobby.create')) + '</button>' +
      '</div>' +
      '<div class="row" style="margin-top:8px">' +
      '  <label class="label" for="lobbyRuleset" style="min-width:56px">' + escapeHtml('规则') + '</label>' +
      '  <select id="lobbyRuleset" class="input" style="flex:1">' +
      '    <option value="coc7" selected>CoC 7e</option>' +
      '    <option value="coc6">CoC 6e</option>' +
      '    <option value="dnd35">D&D 3.5e</option>' +
      '    <option value="dnd5e">D&D 5e</option>' +
      '    <option value="custom">自定义</option>' +
      '  </select>' +
      '</div>' +
      '<div class="row" style="margin-top:8px">' +
      '  <label class="label" for="lobbyModule" style="min-width:56px">' + escapeHtml('模组') + '</label>' +
      '  <input class="input" id="lobbyModule" type="text" autocomplete="off" placeholder="' + escapeHtml('模组 id（可选，如 dead_light）') + '" style="flex:1" />' +
      '</div>' +
      '<div class="row" style="margin-top:8px">' +
      '  <input class="input" id="lobbyJoinCode" type="text" autocomplete="off" placeholder="' + escapeHtml(t('lobby.joinCode')) + '" style="flex:1" />' +
      '  <button type="button" class="btn" id="lobbyJoinBtn">' + escapeHtml(t('lobby.joinBtn')) + '</button>' +
      '</div>' +
      '<div class="row" style="margin-top:8px">' +
      '  <button type="button" class="btn" id="lobbyRefreshBtn">' + escapeHtml(t('lobby.refresh')) + '</button>' +
      '</div>' +
      '<h3 class="card-subtitle" style="margin-top:12px">' + escapeHtml(t('lobby.list')) + '</h3>' +
      '<div id="lobbyList" class="events" style="max-height:280px;overflow:auto"></div>' +
      '<div class="ok-line" id="lobbyOut"></div>' +
      '<div id="lobbyErr" class="err-bar hidden"></div>';
    var anchor = document.getElementById('viewSetup');
    var first = anchor && anchor.firstElementChild;
    if (first) { anchor.insertBefore(card, first); } else { anchor.appendChild(card); }
    document.getElementById('lobbyCreateBtn').onclick = function () { lobbyCreate(); };
    document.getElementById('lobbyJoinBtn').onclick = function () { lobbyJoinByCode(); };
    document.getElementById('lobbyRefreshBtn').onclick = function () { lobbyRefresh(); };
  }

  function lobbyRefresh() {
    lobbySyncCreds();
    if (!lobbyNeedCreds()) { return; }
    setErr($('lobbyErr'), '');
    api('/api/campaigns').then(function (res) {
      if (res.status !== 200 || !res.json) {
        setErr($('lobbyErr'), errTextFor(res.status, res.json));
        return;
      }
      var arr = Array.isArray(res.json.campaigns) ? res.json.campaigns : [];
      /* D7: 偶发空白 -> 结果为空但请求成功时，3s 后自动重拉一次 */
      if (!arr.length && !T13.campaigns.length) {
        window.setTimeout(function () { if (document.getElementById('lobbyCard')) { lobbyRefresh(); } }, 3000);
      }
      T13.campaigns = arr;
      lobbyRender();
    });
  }

  function lobbyRender() {
    var box = document.getElementById('lobbyList');
    if (!box) { return; }
    var list = T13.campaigns || [];
    if (!list.length) { box.textContent = t('lobby.empty'); return; }
    var html = '';
    for (var i = 0; i < list.length; i++) {
      (function (c) {
        var phase = String(c.phase || '');
        var cls = (phase === 'running') ? 'ok-line' : 'status-line';
        html += '<div class="item ev-item">' +
          '<div><span class="ev-kind">' + escapeHtml(c.name || c.campaign_id) + '</span>' +
          ' <span class="ev-ts">#' + escapeHtml(String(c.campaign_id)) + '</span></div>' +
          '<div class="' + cls + '">' + escapeHtml(tpl('lobby.phase', { phase: phase })) + ' · ' +
          escapeHtml(tpl('lobby.players', { n: c.players })) + ' · ' +
          escapeHtml(tpl('lobby.checkpoints', { n: c.checkpoints })) + '</div>' +
          '<div class="row" style="margin-top:4px">' +
          '  <button type="button" class="btn" data-lobby-enter="' + escapeHtml(String(c.campaign_id)) + '">' + escapeHtml(t('lobby.enter')) + '</button>' +
          '</div></div>';
      })(list[i]);
    }
    box.innerHTML = html;
    var btns = box.querySelectorAll('[data-lobby-enter]');
    for (var j = 0; j < btns.length; j++) {
      (function (b) {
        b.onclick = function () {
          window.location.hash = '#/setup/' + encodeURIComponent(b.getAttribute('data-lobby-enter'));
        };
      })(btns[j]);
    }
  }

  function lobbyCreate() {
    lobbySyncCreds();
    if (!lobbyNeedCreds()) { return; }
    var name = String(document.getElementById('lobbyNewName').value || '').trim();
    var rs = String((document.getElementById('lobbyRuleset') || {}).value || 'coc7').trim() || 'coc7';
    var mod = String((document.getElementById('lobbyModule') || {}).value || '').trim();
    setErr($('lobbyErr'), '');
    api('/api/campaigns', {
      method: 'POST',
      body: { name: name, ruleset: rs, module_ref: mod || undefined }
    }).then(function (res) {
      if (res.status === 201 && res.json && res.json.ok) {
        var id = String(res.json.campaign_id || '');
        document.getElementById('lobbyOut').textContent =
          tpl('lobby.created', { id: id, phase: String(res.json.phase || '') });
        lobbyRefresh();
        window.location.hash = '#/setup/' + encodeURIComponent(id);
      } else {
        setErr($('lobbyErr'), tpl('lobby.createFailed', { err: errTextFor(res.status, res.json) }));
      }
    });
  }

  function lobbyJoinByCode() {
    var code = String(document.getElementById('lobbyJoinCode').value || '').trim();
    if (!code) { return; }
    if (!lobbyNeedCreds()) { return; }
    setErr($('lobbyErr'), '');
    api('/api/campaigns').then(function (res) {
      if (res.status !== 200 || !res.json) {
        setErr($('lobbyErr'), errTextFor(res.status, res.json));
        return;
      }
      var found = null;
      var list = Array.isArray(res.json.campaigns) ? res.json.campaigns : [];
      for (var i = 0; i < list.length; i++) {
        if (String(list[i].campaign_id) === code) { found = list[i]; break; }
      }
      if (!found) { setErr($('lobbyErr'), t('lobby.notFound')); return; }
      window.location.hash = '#/setup/' + encodeURIComponent(code);
    });
  }


  /* ---- 开始页（#/setup/:id） ---- */
  function setupView(id) {
    if (!id) { return; }
    T13.setupId = id;
    var host = document.getElementById('viewSetup');
    if (!host) { return; }
    var existing = document.getElementById('setupView');
    if (!existing) {
      var card = document.createElement('div');
      card.className = 'card';
      card.id = 'setupView';
      card.innerHTML =
        '<div class="row"><button type="button" class="btn" id="setupBackBtn">' + escapeHtml(t('setup.back')) + '</button></div>' +
        '<h2 class="card-title" id="setupTitle"></h2>' +
        '<div class="status-line" id="setupPhase"></div>' +
        '<div class="kv"><span class="k">' + escapeHtml(t('setup.id')) + '</span><span id="setupIdKv"></span></div>' +
        '<div class="kv"><span class="k">' + escapeHtml('规则') + '</span><span id="setupRuleset"></span></div>' +
        '<div class="kv"><span class="k">' + escapeHtml('玩家座位') + '</span><span id="setupPlayers"></span></div>' +
        '<div class="kv"><span class="k">' + escapeHtml('场景数') + '</span><span id="setupScenes"></span></div>' +
        '<div class="row" style="margin-top:12px">' +
        '  <button type="button" class="btn btn-primary" id="setupStartBtn">' + escapeHtml(t('setup.start')) + '</button>' +
        '  <button type="button" class="btn" id="setupRefreshBtn">' + escapeHtml(t('gate.refreshPhase')) + '</button>' +
        '</div>' +
        '<div class="warn-line" id="setupStartHint">' + escapeHtml(t('setup.startHint')) + '</div>' +
        '<h3 class="card-subtitle" style="margin-top:12px">' + escapeHtml(t('setup.checkpoints')) + '</h3>' +
        '<div class="row" style="margin-top:8px">' +
        '  <input class="input" id="setupSaveLabel" type="text" autocomplete="off" placeholder="' + escapeHtml(t('setup.saveLabel')) + '" style="flex:1" />' +
        '  <button type="button" class="btn" id="setupSaveBtn">' + escapeHtml(t('setup.save')) + '</button>' +
        '</div>' +
        '<div id="setupCheckpoints" class="events" style="max-height:220px;overflow:auto;margin-top:8px"></div>' +
        '<div class="ok-line" id="setupOut"></div>' +
        '<div id="setupViewErr" class="err-bar hidden"></div>';
      host.appendChild(card);
      document.getElementById('setupBackBtn').onclick = function () {
        window.location.hash = '#/lobby';
      };
      document.getElementById('setupStartBtn').onclick = function () { setupStart(); };
      document.getElementById('setupRefreshBtn').onclick = function () { setupRefresh(); };
      document.getElementById('setupSaveBtn').onclick = function () { setupSave(); };
    }
    /* 每次进入都刷新（phase/players/checkpoints 会变） */
    setErr($('setupViewErr'), '');
    setupRefresh();
  }

  function setupRefresh() {
    lobbySyncCreds();
    var id = T13.setupId;
    if (!id) { return; }
    /* 与大厅一致：直接同步输入框的 server/token（避免必须先点「测试连接」） */
    lobbySyncCreds();
    setErr($('setupViewErr'), '');
    api('/api/campaigns/' + encodeURIComponent(id) + '/lobby').then(function (res) {
      if (res.status === 200 && res.json) {
        T13.lobby = res.json;
        renderSetupFromLobby(res.json);
        return;
      }
      if (res.status === 403 || res.status === 401) {
        /* 玩家端拿不到 kp-only lobby -> 用团列表兜底 phase */
        api('/api/campaigns').then(function (r2) {
          if (r2.status !== 200 || !r2.json) { if ($('setupViewErr')) { setErr($('setupViewErr'), errTextFor(r2.status, r2.json)); } return; }
          var list = Array.isArray(r2.json.campaigns) ? r2.json.campaigns : [];
          for (var i = 0; i < list.length; i++) {
            if (String(list[i].campaign_id) === id) {
              T13.lobby = { campaign_id: id, name: list[i].name, ruleset: list[i].ruleset,
                            phase: list[i].phase, players: [],
                            player_count: list[i].players,
                            checkpoint_count: list[i].checkpoints };
              renderSetupFromLobby(T13.lobby);
              return;
            }
          }
          if ($('setupViewErr')) { setErr($('setupViewErr'), t('lobby.notFound')); }
        });
        return;
      }
      if ($('setupViewErr')) { setErr($('setupViewErr'), errTextFor(res.status, res.json)); }
    });
  }

  function renderSetupFromLobby(l) {
    if (!l) { return; }
    var el = function (id) { return document.getElementById(id); };
    var phase = String(l.phase || '');
    state.phase = phase;
    if (el('setupTitle')) { el('setupTitle').textContent = tpl('setup.title', { name: l.name || l.campaign_id }); }
    if (el('setupIdKv')) { el('setupIdKv').textContent = String(l.campaign_id || ''); }
    if (el('setupRuleset')) { el('setupRuleset').textContent = tpl('setup.ruleset', { ruleset: l.ruleset || 'coc7' }); }
    var pcount = (typeof l.player_count === 'number') ? l.player_count : (l.players || []).length;
    if (el('setupPlayers')) { el('setupPlayers').textContent = tpl('setup.players', { n: pcount }); }
    if (el('setupScenes')) { el('setupScenes').textContent = tpl('setup.scenes', { n: (l.scene_count === undefined ? '-' : l.scene_count) }); }
    if (el('setupPhase')) { el('setupPhase').textContent = tpl('setup.phase', { phase: phase }); }
    var cps = Array.isArray(l.checkpoints) ? l.checkpoints : [];
    T13.checkpoints = cps;
    var box = el('setupCheckpoints');
    if (!box) { return; }
    if (!cps.length && typeof l.checkpoint_count === 'number' && l.checkpoint_count > 0) {
      box.textContent = tpl('lobby.checkpoints', { n: l.checkpoint_count }) + '（读档需主持人）';
    } else if (cps.length) {
      var html = '';
      for (var i = 0; i < cps.length; i++) {
        (function (cp) {
          html += '<div class="item ev-item">' +
            '<div><span class="ev-kind">' + escapeHtml(String(cp.label || cp.kind || '')) + '</span>' +
            ' <span class="ev-ts">#' + escapeHtml(String(cp.seq)) + '</span></div>' +
            '<div class="row" style="margin-top:4px">' +
            '  <button type="button" class="btn" data-setup-resume="' + escapeHtml(String(cp.snapshot_id || cp.file || '')) + '">' + escapeHtml(t('setup.resume')) + '</button>' +
            '</div></div>';
        })(cps[i]);
      }
      box.innerHTML = html;
      var btns = box.querySelectorAll('[data-setup-resume]');
      for (var j = 0; j < btns.length; j++) {
        (function (b) {
          b.onclick = function () { setupResume(b.getAttribute('data-setup-resume')); };
        })(btns[j]);
      }
    } else {
      box.textContent = t('setup.noCheckpoints');
    }
  }

  function setupStart() {
    lobbySyncCreds();
    var id = T13.setupId;
    if (!id) { return; }
    if ($('setupViewErr')) { setErr($('setupViewErr'), ''); }
    api('/api/campaigns/' + encodeURIComponent(id) + '/start', { method: 'POST' }).then(function (res) {
      if (res.status === 201 && res.json && res.json.ok) {
        var phase = String(res.json.phase || 'running');
        state.phase = phase;
        if ($('setupPhase')) { $('setupPhase').textContent = tpl('setup.phase', { phase: phase }); }
        if ($('setupOut')) { $('setupOut').textContent = tpl('gate.phaseUpdated', { phase: phase }); }
        applyPhaseGate();
        if (T13.pendingPlay) {
          var target = T13.pendingPlay; T13.pendingPlay = '';
          window.location.hash = '#/play/' + encodeURIComponent(target);
        }
        setupRefresh();
        return;
      }
      if (res.status === 409) {
        /* T14: phase!=configuring -> auto configure (lobby->configuring) then retry start */
        return api('/api/campaigns/' + encodeURIComponent(id) + '/configure', { method: 'POST' })
          .then(function (cr) {
            if (cr.status === 201 && cr.json && cr.json.ok) {
              state.phase = 'configuring';
              if ($('setupPhase')) { $('setupPhase').textContent = tpl('setup.phase', { phase: 'configuring' }); }
              return api('/api/campaigns/' + encodeURIComponent(id) + '/start', { method: 'POST' });
            }
            if ($('setupViewErr')) { setErr($('setupViewErr'), tpl('setup.needConfig', { phase: String(state.phase || '') })); }
            return null;
          }).then(function (res2) {
            if (!res2) { return; }
            if (res2.status === 201 && res2.json && res2.json.ok) {
              state.phase = String(res2.json.phase || 'running');
              applyPhaseGate();
              if (T13.pendingPlay) {
                var target = T13.pendingPlay; T13.pendingPlay = '';
                window.location.hash = '#/play/' + encodeURIComponent(target);
              }
              setupRefresh();
              return;
            }
            if ($('setupViewErr')) { setErr($('setupViewErr'), tpl('gate.startFailed', { err: errTextFor(res2.status, res2.json) })); }
          });
      }
      if ($('setupViewErr')) { setErr($('setupViewErr'), tpl('gate.startFailed', { err: errTextFor(res.status, res.json) })); }
    });
  }

  function setupSave() {
    lobbySyncCreds();
    var id = T13.setupId;
    if (!id) { return; }
    var label = String(document.getElementById('setupSaveLabel').value || '').trim() || '手动存档';
    if ($('setupViewErr')) { setErr($('setupViewErr'), ''); }
    api('/api/campaigns/' + encodeURIComponent(id) + '/timeline/checkpoint', {
      method: 'POST',
      body: { label: label, reason: 't13 manual save' }
    }).then(function (res) {
      if (res.status === 201 && res.json && res.json.ok) {
        if ($('setupOut')) {
          $('setupOut').textContent = tpl('setup.saved', { snapshot_id: String(res.json.snapshot_id || '') });
        }
        var lab = document.getElementById('setupSaveLabel');
        if (lab) { lab.value = ''; }
        setupRefresh();
      } else {
        if ($('setupViewErr')) { setErr($('setupViewErr'), tpl('setup.saveFailed', { err: errTextFor(res.status, res.json) })); }
      }
    });
  }

  function setupResume(checkpointId) {
    lobbySyncCreds();
    var id = T13.setupId;
    if (!id) { return; }
    if (!checkpointId) { if ($('setupViewErr')) { setErr($('setupViewErr'), t('setup.needCheckpoint')); } return; }
    if ($('setupViewErr')) { setErr($('setupViewErr'), ''); }
    api('/api/campaigns/' + encodeURIComponent(id) + '/resume', {
      method: 'POST',
      body: { checkpoint_id: checkpointId }
    }).then(function (res) {
      if (res.status === 201 && res.json && res.json.ok) {
        if ($('setupOut')) {
          $('setupOut').textContent = tpl('setup.resumed', { from: String(res.json.resumed_from || checkpointId) });
        }
        state.phase = String(res.json.phase || 'running');
        if ($('setupPhase')) { $('setupPhase').textContent = tpl('setup.phase', { phase: state.phase }); }
        applyPhaseGate();
        setupRefresh();
      } else {
        if ($('setupViewErr')) { setErr($('setupViewErr'), tpl('setup.resumeFailed', { err: errTextFor(res.status, res.json) })); }
      }
    });
  }


  /* ---- phase 门控：非 running 不渲染玩家情况 ----
     视图感知：只有当「桌面」是当前激活视图时才显示 gateBar；
     phase 变 running 时不劫持 setup/lobby 视图（避免双视图同显）。 */
  function phaseText(p) {
    if (!p) { return t('gate.waiting'); }
    if (p === 'running') { return 'running'; }
    if (p === 'lobby' || p === 'configuring') { return t('gate.waiting'); }
    if (p === 'paused') { return t('gate.preparing'); }
    if (p === 'ended') { return t('gate.ended'); }
    return String(p);
  }

  /* 玩家端同步 phase：
     主持人可读 /lobby；玩家端 403 -> 从 /access/mobile/events 找最近 PHASE_UPDATED。 */
  function syncPhaseForTable() {
    var tid = state.tableId || state.campaign;
    if (!tid) { return Promise.resolve(); }
    return api('/api/campaigns/' + encodeURIComponent(tid) + '/lobby').then(function (res) {
      if (res.status === 200 && res.json && res.json.phase) {
        state.phase = String(res.json.phase);
        T13.lobby = res.json;
        return;
      }
      /* 玩家端拿不到 kp-only /lobby：
         1) 团列表（任意端可读）带权威 phase —— 优先；
         2) 事件流 PHASE_UPDATED 兜底（仅当列表也不可读/未命中）。 */
      return api('/api/campaigns').then(function (r1) {
        if (r1.status === 200 && r1.json) {
          var list = Array.isArray(r1.json.campaigns) ? r1.json.campaigns : [];
          for (var i = 0; i < list.length; i++) {
            if (String(list[i].campaign_id) === tid) {
              state.phase = String(list[i].phase || state.phase);
              return;
            }
          }
        }
        return api('/access/mobile/events?table_id=' + encodeURIComponent(tid) +
                   '&viewer=' + encodeURIComponent(state.playerId || '') +
                   '&since=-1&limit=200&token=' + encodeURIComponent(state.token)).then(function (r2) {
          if (r2.status !== 200 || !r2.json) { return; }
          var body = (r2.json.ok === true && r2.json.data) ? r2.json.data : r2.json;
          var evs = Array.isArray(body.events) ? body.events : [];
          for (var i = evs.length - 1; i >= 0; i--) {
            if (evs[i] && evs[i].type === 'PHASE_UPDATED' && evs[i].payload && evs[i].payload.phase) {
              state.phase = String(evs[i].payload.phase);
              break;
            }
          }
        });
      });
    }, function () { /* 网络失败：保留当前 phase */ });
  }

  function applyPhaseGate() {
    var tbl = $('viewTable');
    var running = (state.phase === 'running');
    if (running) {
      /* phase=running：正常渲染现有全部区块。
         注意：首次 applyPhaseGate（sync 完成前）可能已把 viewTable 隐藏，
         故 running 分支无条件恢复桌面区块（当前视图是否为桌面由 showView 管理）。 */
      show(tbl, true);
      show($('ixCard'), true);
      show($('chatCard'), true);
      show($('t7Card'), true);
      var bar = document.getElementById('gateBar');
      if (bar) { show(bar, false); }
      return;
    }
    var tableActive = !!(tbl && !tbl.classList.contains('hidden'));
    /* 非 running：不渲染玩家情况区块（我的状态/回合/行动/事件 + 挂载面板） */
    var ids = ['viewTable', 'ixCard', 'chatCard', 't7Card'];
    for (var i = 0; i < ids.length; i++) {
      var el = document.getElementById(ids[i]);
      if (el) { show(el, false); }
    }
    var gateBar = document.getElementById('gateBar');
    if (!gateBar && tbl && tbl.parentNode) {
      gateBar = document.createElement('div');
      gateBar.className = 'card';
      gateBar.id = 'gateBar';
      gateBar.innerHTML =
        '<h2 class="card-title" id="gateTitle"></h2>' +
        '<div class="status-line" id="gateMsg"></div>' +
        '<div class="row" style="margin-top:8px">' +
        '  <button type="button" class="btn btn-primary" id="gateStartBtn">' + escapeHtml(t('setup.start')) + '</button>' +
        '</div>' +
        '<div id="gateErr" class="err-bar hidden"></div>';
      /* 作为 #viewTable 的兄弟挂到 main.pg（不在被隐藏的 viewTable 内部） */
      tbl.parentNode.appendChild(gateBar);
      var gateStart = document.getElementById('gateStartBtn');
      if (gateStart) { gateStart.onclick = function () { setupStartFromGate(); }; }
    }
    /* 每次调用都刷新门控卡标题/文案（phase 可能已从 WS/轮询更新） */
    if (gateBar) {
      var gt = document.getElementById('gateTitle');
      if (gt) { gt.textContent = phaseText(state.phase); }
      var gm = document.getElementById('gateMsg');
      if (gm) { gm.textContent = t('gate.notRunning'); }
      show(gateBar, tableActive);
    }
  }

  function setupStartFromGate() {
    lobbySyncCreds();
    var id = state.campaign || state.tableId || T13.setupId;
    if (!id) { return; }
    var errBox = document.getElementById('gateErr');
    if (errBox) { setErr(errBox, ''); }
    api('/api/campaigns/' + encodeURIComponent(id) + '/start', { method: 'POST' }).then(function (res) {
      if (res.status === 201 && res.json && res.json.ok) {
        state.phase = String(res.json.phase || 'running');
        applyPhaseGate();
        return;
      }
      if (res.status === 409) {
        /* T14: auto configure (lobby->configuring) then retry start */
        return api('/api/campaigns/' + encodeURIComponent(id) + '/configure', { method: 'POST' })
          .then(function (cr) {
            if (cr.status === 201 && cr.json && cr.json.ok) {
              state.phase = 'configuring';
              return api('/api/campaigns/' + encodeURIComponent(id) + '/start', { method: 'POST' });
            }
            if (errBox) { setErr(errBox, tpl('setup.needConfig', { phase: String(state.phase || '') })); }
            return null;
          }).then(function (res2) {
            if (!res2) { return; }
            if (res2.status === 201 && res2.json && res2.json.ok) {
              state.phase = String(res2.json.phase || 'running');
              applyPhaseGate();
              return;
            }
            if (errBox) { setErr(errBox, tpl('gate.startFailed', { err: errTextFor(res2.status, res2.json) })); }
          });
      }
      if (errBox) { setErr(errBox, tpl('gate.startFailed', { err: errTextFor(res.status, res.json) })); }
    });
  }

  /* WS STATE_DELTA(field=phase) 刷新门控（PHASE_UPDATED 已加入 KNOWN_KINDS） */
  function onPhaseDelta(frame) {
    var d = frame.delta || {};
    var value = d.value || {};
    var p = String(value.phase || '');
    if (!p) { return; }
    state.phase = p;
    applyPhaseGate();
    var setupPhase = document.getElementById('setupPhase');
    if (setupPhase) { setupPhase.textContent = tpl('setup.phase', { phase: p }); }
    var sv = document.getElementById('setupView');
    if (T13.setupId && sv && !sv.classList.contains('hidden')) { setupRefresh(); }
  }

  /* 门控兜底轮询：WS 不可用时按 15s 追平 phase（离开桌面即停） */
  function startGatePolling() {
    stopGatePolling();
    T13.gateTimer = window.setInterval(function () {
      if (state.joined) { syncPhaseForTable().then(applyPhaseGate); }
    }, T13.gatePollMs);
  }
  function stopGatePolling() {
    if (T13.gateTimer) { window.clearInterval(T13.gateTimer); T13.gateTimer = null; }
  }


  /* 门控轮询启停已直接接入 joinTable（startGatePolling）/ leaveTable（stopGatePolling） */

  /* ---------- 初始化 ---------- */

  function applyPrefs() {
    var qs = window.location.search || '';
    var q = {};
    qs.replace(/^\?/, '').split('&').forEach(function (kv) {
      if (!kv) { return; }
      var i = kv.indexOf('=');
      var k = i < 0 ? kv : kv.slice(0, i);
      var v = i < 0 ? '' : decodeURIComponent(kv.slice(i + 1).replace(/\+/g, ' '));
      q[k] = v;
    });
    var server = q.server || lsGet(LS.server) || window.location.origin;
    $('server').value = server;
    $('token').value = q.token || lsGet(LS.token) || '';
    /* R13：token 输入框 placeholder 显式化 —— 明确要求「移动端访问 token」，
       避免测试者填 webapp/recorder token（/access/info 与 /ws 放行任一启用端会假通过） */
    $('token').placeholder = t('ext.ph.token');
    $('token').title = t('ext.ph.token');
    $('code').value = q.code || lsGet(LS.code) || '';
    $('pid').value = q.pid || lsGet(LS.playerId) || '';
    $('pname').value = lsGet(LS.playerName) || '';
    state.server = normalizeServer(server);
    state.token = $('token').value;
    state.code = $('code').value;
    state.playerId = $('pid').value;
    state.playerName = $('pname').value;
  }

  function bind() {
    $('navSetup').onclick = function () { showView('setup'); lobbyMount(); showLobbyCard(true); showSetupCard(false); };
    $('navTable').onclick = function () {
      showView('table');
      /* T13 (additive): 桌面视图激活时按 phase 门控呈现（非 running 显示等待卡） */
      if (state.phase !== 'running') { applyPhaseGate(); }
    };
    $('navVoice').onclick = function () { showView('voice'); };
    $('btnTest').onclick = function () { testConnection(); };
    $('btnResolve').onclick = function () { resolveCode(); };
    $('btnJoin').onclick = function () { joinTable(); };
    $('btnLeave').onclick = function () { leaveTable(); };
    $('btnSubmit').onclick = function () { submitAction(); };
    $('btnRecStart').onclick = function () { startRecording(); };
    $('btnRecStop').onclick = function () { stopRecording(); };
    $('btnQuery').onclick = function () { queryDevice(); };
    /* T13 (additive): hash 三视图路由（只切视图，不改 showView 内部逻辑） */
    window.addEventListener('hashchange', function () { routeHash(); });
    window.addEventListener('beforeunload', function () { closeWs(); });
  }

  function init() {
    bind();
    ixMount();   /* T15 (additive): 挂载地点交互面板（纯 DOM 注入，不改 index.html） */
    applyPrefs();
    /* T13 (additive): 大厅卡片挂载 + 首次 hash 路由（无 hash 直连兼容老流程） */
    lobbyMount();
    showLobbyCard(false);
    showSetupCard(false);
    routeHash();
    renderTurn();
    render();
    setConnStatus('closed');
    $('setupStatus').textContent = t('st.closed');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
