/**
 * 主题切换 composable（单例模式）
 *
 * 功能：
 * - isDark ref：当前是否暗色模式
 * - toggle()：切换 light/dark
 * - localStorage 持久化（key: gt_theme）
 * - 首次加载无 localStorage 值时，读取系统 prefers-color-scheme 作为默认值
 * - onMounted 初始化 html.dark class
 *
 * 用法：
 * ```ts
 * const { isDark, toggle } = useTheme()
 * ```
 */
import { ref, onMounted, watch } from 'vue'

const STORAGE_KEY = 'gt_theme'

function getInitialDark(): boolean {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored === 'dark') return true
  if (stored === 'light') return false
  // 无存储值时，读取系统主题偏好
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

// 单例共享状态
const isDark = ref(getInitialDark())

export function useTheme() {
  function toggle() {
    isDark.value = !isDark.value
    applyTheme()
    localStorage.setItem(STORAGE_KEY, isDark.value ? 'dark' : 'light')
  }

  function applyTheme() {
    document.documentElement.classList.toggle('dark', isDark.value)
  }

  onMounted(() => {
    applyTheme()
  })

  // 监听系统主题偏好变化（仅在无 localStorage 值时跟随系统）
  onMounted(() => {
    const mql = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e: MediaQueryListEvent) => {
      if (!localStorage.getItem(STORAGE_KEY)) {
        isDark.value = e.matches
        applyTheme()
      }
    }
    mql.addEventListener('change', handler)
  })

  return { isDark, toggle }
}
