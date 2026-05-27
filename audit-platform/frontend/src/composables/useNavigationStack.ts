/**
 * useNavigationStack — 穿透导航返回栈（全局 Backspace 返回）
 *
 * 全局支持：任何页面按 Backspace（非输入框内）自动返回上一跳转位置。
 * 各视图只需在跳转前调用 push() 记录来源即可。
 *
 * Backspace 监听器在 initGlobalBackspace() 中注册一次（由 DefaultLayout 调用）。
 *
 * @example
 * ```ts
 * const { push } = useNavigationStack()
 * push({ source_view: '/projects/xxx/trial-balance', query: { tab: 'detail' } })
 * router.push('/projects/xxx/workpapers')
 * // 用户在任何页面按 Backspace → 自动返回 /projects/xxx/trial-balance?tab=detail
 * ```
 */
import { ref, computed } from 'vue'
import { useRouter, type Router } from 'vue-router'

export interface NavigationEntry {
  source_view: string
  label?: string  // Phase 1 F3: 面包屑显示文本
  direction?: 'down' | 'up'  // Phase 3 F1.5: 穿透方向标记（↓下钻 / ↑上钻）
  row_index?: number
  scroll_position?: number
  query?: Record<string, string>
}

// Shared stack (singleton)
export const MAX_STACK_DEPTH = 20
const stack = ref<NavigationEntry[]>([])
let _globalListenerInstalled = false
let _router: Router | null = null

/**
 * 全局 Backspace 监听器（DefaultLayout 调用一次）
 */
export function initGlobalBackspace(router: Router) {
  if (_globalListenerInstalled) return
  _router = router
  _globalListenerInstalled = true

  window.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key !== 'Backspace') return

    const target = e.target as HTMLElement
    const tagName = target.tagName.toLowerCase()
    if (tagName === 'input' || tagName === 'textarea' || target.isContentEditable) return

    // el-select dropdown 等弹出层内不拦截
    if (target.closest('.el-select-dropdown, .el-picker-panel, .el-dialog')) return

    if (stack.value.length > 0) {
      e.preventDefault()
      const entry = stack.value[stack.value.length - 1]
      stack.value = stack.value.slice(0, -1)
      _router!.push({ path: entry.source_view, query: entry.query })
      // Restore scroll
      if (entry.scroll_position != null) {
        setTimeout(() => {
          window.scrollTo({ top: entry.scroll_position, behavior: 'instant' })
        }, 100)
      }
    }
  })
}

export function useNavigationStack() {
  const router = useRouter()
  if (!_router) _router = router

  const canGoBack = computed(() => stack.value.length > 0)

  function push(entry: NavigationEntry) {
    const newStack = [...stack.value, entry]
    // Enforce max depth: shift oldest entries if exceeded
    if (newStack.length > MAX_STACK_DEPTH) {
      stack.value = newStack.slice(newStack.length - MAX_STACK_DEPTH)
    } else {
      stack.value = newStack
    }
  }

  function pop(): NavigationEntry | undefined {
    if (stack.value.length === 0) return undefined
    const entry = stack.value[stack.value.length - 1]
    stack.value = stack.value.slice(0, -1)
    return entry
  }

  async function goBack() {
    const entry = pop()
    if (!entry) return
    await router.push({ path: entry.source_view, query: entry.query })
    if (entry.scroll_position != null) {
      setTimeout(() => {
        window.scrollTo({ top: entry.scroll_position, behavior: 'instant' })
      }, 100)
    }
  }

  /** Phase 1 F3: 跳转到 stack 中指定位置（截断后续层级） */
  async function jumpTo(index: number) {
    if (index < 0 || index >= stack.value.length) return
    const entry = stack.value[index]
    stack.value = stack.value.slice(0, index)
    await router.push({ path: entry.source_view, query: entry.query })
    if (entry.scroll_position != null) {
      setTimeout(() => {
        window.scrollTo({ top: entry.scroll_position, behavior: 'instant' })
      }, 100)
    }
  }

  /** V3 Req 8.3: 清空导航栈 */
  function clear() {
    stack.value = []
  }

  return { push, pop, canGoBack, goBack, jumpTo, clear, stack }
}
