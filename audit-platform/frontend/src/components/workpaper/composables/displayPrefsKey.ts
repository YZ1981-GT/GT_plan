import type { InjectionKey } from 'vue'
import type { useDisplayPrefsStore } from '@/stores/displayPrefs'

/**
 * 底稿显示偏好注入契约 = DisplayPrefs Store 的公开返回类型
 * （响应式引用 fmtAmount/amountClass/unitSuffix/unitDivisor/tableDensity/fontConfig 等）。
 */
export type DisplayPrefsContract = ReturnType<typeof useDisplayPrefsStore>

/**
 * 类型化的 InjectionKey，替代字符串 key `'displayPrefs'`。
 *
 * 底稿主入口通过 `provide(DisplayPrefs_Key, useDisplayPrefsStore())` 注入单一真源，
 * 底稿 tab 通过 `inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()` 消费，
 * 从根上杜绝各自实现的硬编码格式化闭包。
 */
export const DisplayPrefs_Key: InjectionKey<DisplayPrefsContract> = Symbol('displayPrefs')
