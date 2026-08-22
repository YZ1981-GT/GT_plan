/**
 * AI Chat 敏感缓存清理工具
 *
 * 在 logout、user switch 和首次升级时清除遗留 `doc_ai_chat_*` localStorage keys。
 * 面板宽度（`gt-dsh-panel-width`）等非敏感偏好可保留。
 *
 * Feature: dsh-agent-panel-integration / Task 10
 * Validates: Requirements 1.3, 13.3, 13.4
 * Properties: 35
 */

/** localStorage key prefix for legacy AI chat sensitive data */
const LEGACY_CACHE_PREFIX = 'doc_ai_chat_'

/** Upgrade marker to detect first load after upgrade */
const UPGRADE_MARKER_KEY = 'gt_ai_chat_cache_version'

/** Current cache version — bump to trigger cleanup on next load */
const CURRENT_CACHE_VERSION = '2'

/**
 * 清除所有 doc_ai_chat_* 开头的 localStorage key（遗留敏感对话缓存）。
 * 保留面板宽度等非敏感偏好。
 */
export function clearLegacyAiChatCache(): void {
  try {
    const keysToRemove: string[] = []
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key && key.startsWith(LEGACY_CACHE_PREFIX)) {
        keysToRemove.push(key)
      }
    }
    for (const key of keysToRemove) {
      localStorage.removeItem(key)
    }
  } catch {
    // localStorage 不可用时静默忽略
  }
}

/**
 * 首次升级检查 — 版本号不匹配时清理遗留缓存。
 * 在应用初始化时调用一次。
 */
export function clearOnUpgrade(): void {
  try {
    const storedVersion = localStorage.getItem(UPGRADE_MARKER_KEY)
    if (storedVersion !== CURRENT_CACHE_VERSION) {
      clearLegacyAiChatCache()
      localStorage.setItem(UPGRADE_MARKER_KEY, CURRENT_CACHE_VERSION)
    }
  } catch {
    // localStorage 不可用时静默忽略
  }
}

/**
 * 登出或切换用户时调用 — 清理所有 AI 聊天敏感缓存。
 * 应在 auth store logout() 执行后调用。
 */
export function clearOnLogout(): void {
  clearLegacyAiChatCache()
}
