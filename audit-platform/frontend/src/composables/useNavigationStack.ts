/**
 * useNavigationStack — 穿透导航返回栈 [enterprise-linkage 3.9]
 *
 * 记录 source_view/row_index/scroll_position，
 * Backspace 键恢复上一跳转位置（非输入框内）。
 *
 * @example
 * ```ts
 * const { push, pop, canGoBack } = useNavigationStack()
 * push({ source_view: '/projects/xxx/trial-balance', row_index: 5, scroll_position: 200 })
 * // User presses Backspace → auto pop + navigate
 * ```
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'

export interface NavigationEntry {
  source_view: string
  row_index?: number
  scroll_position?: number
  query?: Record<string, string>
}

// Shared stack across all instances (singleton pattern)
const stack = ref<NavigationEntry[]>([])

export function useNavigationStack() {
  const router = useRouter()

  const canGoBack = computed(() => stack.value.length > 0)

  function push(entry: NavigationEntry) {
    stack.value = [...stack.value, entry]
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

    // Restore scroll position after navigation
    if (entry.scroll_position != null) {
      setTimeout(() => {
        window.scrollTo({ top: entry.scroll_position, behavior: 'instant' })
      }, 100)
    }
  }

  // ─── Backspace key handler ────────────────────────────────────────────────

  function onKeyDown(e: KeyboardEvent) {
    // Only handle Backspace when not in an input/textarea/contenteditable
    if (e.key !== 'Backspace') return

    const target = e.target as HTMLElement
    const tagName = target.tagName.toLowerCase()
    if (tagName === 'input' || tagName === 'textarea' || target.isContentEditable) return

    if (canGoBack.value) {
      e.preventDefault()
      goBack()
    }
  }

  onMounted(() => {
    window.addEventListener('keydown', onKeyDown)
  })

  onUnmounted(() => {
    window.removeEventListener('keydown', onKeyDown)
  })

  return {
    push,
    pop,
    canGoBack,
    goBack,
    stack,
  }
}
