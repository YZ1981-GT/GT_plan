/**
 * 轻量级 i18n 框架（无 vue-i18n 依赖）
 *
 * 功能：
 * - 加载 zh-CN / en-US 翻译文件
 * - 提供 t(key) 函数用于模板
 * - localStorage 持久化语言偏好
 * - 缺失 key 回退到 zh-CN
 */

import { ref, computed, type Ref, type ComputedRef } from 'vue'
import zhCN from './zh-CN.json'
import enUS from './en-US.json'

type Messages = Record<string, any>

const messages: Record<string, Messages> = {
  'zh-CN': zhCN,
  'en-US': enUS,
}

const STORAGE_KEY = 'gt-language'
const DEFAULT_LANG = 'zh-CN'

// 全局响应式语言状态
const currentLocale: Ref<string> = ref(
  (typeof localStorage !== 'undefined' && localStorage.getItem(STORAGE_KEY)) || DEFAULT_LANG
)

/**
 * 根据点分路径从嵌套对象中取值
 * 例如 resolve('nav.dashboard', zhCN) => '工作台'
 */
function resolve(key: string, obj: Messages): string | undefined {
  const parts = key.split('.')
  let current: any = obj
  for (const part of parts) {
    if (current == null || typeof current !== 'object') return undefined
    current = current[part]
  }
  return typeof current === 'string' ? current : undefined
}

/**
 * 翻译函数：根据当前语言返回翻译文本
 * 缺失时回退到 zh-CN，仍缺失则返回 key 本身
 */
function translate(key: string): string {
  const lang = currentLocale.value
  const msg = messages[lang]
  if (msg) {
    const val = resolve(key, msg)
    if (val !== undefined) return val
  }
  // 回退到 zh-CN
  if (lang !== DEFAULT_LANG) {
    const fallback = messages[DEFAULT_LANG]
    if (fallback) {
      const val = resolve(key, fallback)
      if (val !== undefined) return val
    }
  }
  return key
}

/**
 * 切换语言
 */
function setLocale(lang: string) {
  if (!messages[lang]) return
  currentLocale.value = lang
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem(STORAGE_KEY, lang)
  }
}

/**
 * useI18n composable
 */
export function useI18n() {
  const locale: ComputedRef<string> = computed(() => currentLocale.value)

  return {
    /** 当前语言 */
    locale,
    /** 翻译函数 */
    t: translate,
    /** 切换语言 */
    setLocale,
    /** 支持的语言列表 */
    availableLocales: Object.keys(messages),
  }
}

export default useI18n
