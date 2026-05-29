/**
 * useWpNavigationHistory — 底稿间导航历史 composable
 *
 * 基于 sessionStorage 维护底稿跳转历史栈（max=5），支持：
 * - GtIndexChip 跳转时 push 历史记录
 * - 目标底稿顶部显示「← 返回 X 第 N 行」面包屑
 * - 复用 initGlobalBackspace 支持 Backspace 键返回
 *
 * @example
 * const { push, pop, lastItem, canGoBack, goBack } = useWpNavigationHistory()
 * push({ wpId: '...', wpCode: 'D2A', sheetName: '应收账款', rowRef: '第 3 行' })
 *
 * Validates: Requirements US-9
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'

// ─── 类型定义 ─────────────────────────────────────────────────────────────────

export interface NavHistoryItem {
  wpId: string
  wpCode: string
  sheetName: string
  rowRef?: string       // 如 "第 3 行"
  timestamp: number
}

// ─── 常量 ─────────────────────────────────────────────────────────────────────

const MAX_HISTORY = 5
const STORAGE_KEY = 'gt_wp_nav_history'

// ─── 内部状态（模块级单例，多组件共享） ───────────────────────────────────────

const history = ref<NavHistoryItem[]>([])

/** 从 sessionStorage 加载历史 */
function loadHistory(): NavHistoryItem[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.slice(0, MAX_HISTORY)
  } catch {
    return []
  }
}

/** 持久化到 sessionStorage */
function persistHistory() {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(history.value))
  } catch {
    // sessionStorage 满了，静默忽略
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useWpNavigationHistory() {
  const router = useRouter()

  onMounted(() => {
    // 首次挂载时从 sessionStorage 恢复
    if (history.value.length === 0) {
      history.value = loadHistory()
    }
  })

  /** 最近一条历史记录 */
  const lastItem = computed<NavHistoryItem | null>(() => {
    return history.value.length > 0 ? history.value[history.value.length - 1] : null
  })

  /** 是否可以返回 */
  const canGoBack = computed(() => history.value.length > 0)

  /** 历史栈长度 */
  const stackSize = computed(() => history.value.length)

  /**
   * 跳转前 push 当前位置到历史栈
   */
  function push(item: Omit<NavHistoryItem, 'timestamp'>) {
    const entry: NavHistoryItem = {
      ...item,
      timestamp: Date.now(),
    }
    // 避免连续重复 push 同一底稿
    const last = history.value[history.value.length - 1]
    if (last && last.wpId === entry.wpId && last.sheetName === entry.sheetName) {
      return
    }
    history.value = [...history.value, entry].slice(-MAX_HISTORY)
    persistHistory()
  }

  /**
   * 弹出最近一条历史并返回
   */
  function pop(): NavHistoryItem | null {
    if (history.value.length === 0) return null
    const item = history.value[history.value.length - 1]
    history.value = history.value.slice(0, -1)
    persistHistory()
    return item
  }

  /**
   * 返回上一个底稿（pop + 路由跳转）
   */
  async function goBack() {
    const item = pop()
    if (!item) return
    // 跳转到来源底稿编辑器
    const currentRoute = router.currentRoute.value
    const projectId = currentRoute.params.projectId as string
    if (projectId) {
      await router.push({
        path: `/projects/${projectId}/workpapers/${item.wpId}/edit`,
        query: item.sheetName ? { sheet: item.sheetName } : undefined,
      })
    }
  }

  /**
   * 清空历史
   */
  function clear() {
    history.value = []
    sessionStorage.removeItem(STORAGE_KEY)
  }

  return {
    history,
    lastItem,
    canGoBack,
    stackSize,
    push,
    pop,
    goBack,
    clear,
  }
}
