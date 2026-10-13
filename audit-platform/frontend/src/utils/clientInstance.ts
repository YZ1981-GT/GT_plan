/**
 * 浏览器标签页唯一实例 ID
 *
 * 需求：
 * - 同一标签页内（包括页面刷新）返回同一个 ID → 编辑锁 heartbeat 不断裂
 * - window.open 创建的新标签页必须获得不同的 ID → 编辑锁隔离
 *
 * 实现：
 * - ID 存入 sessionStorage（刷新后保留）
 * - 用模块级 `_thisTabInitialized` 标记本 JS 执行上下文是否已初始化
 *   · 刷新页面：JS 全局重建，_thisTabInitialized=false，但 sessionStorage 保留旧 ID → 直接复用
 *   · window.open 新标签页：JS 全局重建，_thisTabInitialized=false，sessionStorage 从 opener 复制
 *     → 此时需要重新生成，通过 `gt-client-instance-owner` 标记判断：如果存储里的 owner 不等于
 *       当前 window 的某个唯一属性（performance.now 精度足够区分），就重新生成
 *
 * 简化方案（当前实现）：
 * - 刷新 = sessionStorage 有值 + 模块首次加载 → 复用
 * - 新标签页 = sessionStorage 有值（从 opener 复制的） + 模块首次加载
 *   → 无法直接区分，所以用 `window.opener` 判断：有 opener 说明是被 open 出来的
 *   → 但用户手动在地址栏输入也没有 opener，这种情况 sessionStorage 为空，会生成新的
 *
 * spec: multi-window-ledger-workbench Phase 2 Task 8 + 复盘 P0-1 修复
 */

const STORAGE_KEY = 'gt-client-instance-id'

let _cached: string | null = null

export function getClientInstanceId(): string {
  if (_cached) return _cached

  // 1. 尝试从 sessionStorage 读取已有的 ID
  let existing: string | null = null
  try {
    existing = sessionStorage.getItem(STORAGE_KEY)
  } catch {
    // sessionStorage 不可用
  }

  if (existing) {
    // 有已有 ID。判断是"页面刷新"还是"window.open 创建的新标签页"
    if (window.opener && !window.opener.closed) {
      // 有活跃的 opener → 这是 window.open 打开的新标签页，必须生成新 ID
      // （opener 关闭后刷新此页面时 window.opener.closed=true，会走下面的复用路径）
      _cached = _generateAndStore()
    } else {
      // 无 opener（刷新 / 手动输入 URL / opener 已关闭） → 复用已有 ID
      _cached = existing
    }
  } else {
    // sessionStorage 里没有 ID → 全新标签页（手动输入 URL / sessionStorage 被清空）
    _cached = _generateAndStore()
  }

  return _cached
}

function _generateAndStore(): string {
  const id = crypto.randomUUID()
  try {
    sessionStorage.setItem(STORAGE_KEY, id)
  } catch {
    // sessionStorage 不可用时仅在内存中保留
  }
  return id
}
