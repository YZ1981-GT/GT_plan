import { beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

/**
 * 全局测试夹具：
 * - 激活 Pinia（对话框/审定表依赖 useDisplayPrefsStore）
 * - 金额单位默认「元」、showZero=true，避免默认「万元」/零值隐藏导致断言漂移
 * - 短路 fetch，减少全量并行时的真实网络/ECONNRESET 噪音
 */
beforeEach(() => {
  try {
    localStorage.removeItem('gt_display_prefs')
  } catch { /* ignore */ }
  setActivePinia(createPinia())
  try {
    const prefs = useDisplayPrefsStore()
    prefs.setUnit('yuan')
    prefs.setShowZero(true)
    prefs.setDecimals(2)
  } catch {
    // store 未加载时忽略（纯逻辑单测）
  }
})

vi.stubGlobal(
  'fetch',
  vi.fn(async () =>
    new Response(JSON.stringify({}), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  ),
)
