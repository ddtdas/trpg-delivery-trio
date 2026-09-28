/**
 * req-id.js —— 幂等请求标识（契约 §1：POST /access/mobile/action 的 req_id）
 * 同一 req_id 重复提交 → 服务端只落 1 条事件并返回 status="duplicate"。
 */
let counter = 0

function create(prefix) {
  counter = (counter + 1) % 1000000
  const random = Math.random().toString(16).slice(2, 10)
  return String(prefix || 'req') + '-' + Date.now().toString(36) + '-' + counter.toString(36) + '-' + random
}

module.exports = { create: create }
