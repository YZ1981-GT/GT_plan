/**
 * useDshPanelLayout — AI 面板三档响应式布局管理
 *
 * 三档布局策略：
 * - `>1400px`（column）：独立列，面板嵌入布局流（flex-shrink:0），可拖拽调整宽度
 * - `769–1400px`（drawer）：fixed drawer 从右侧滑入，半透明遮罩
 * - `≤768px`（fullscreen）：全屏覆盖 + safe-area-inset
 *
 * Feature: dsh-agent-panel-integration / Task 11
 * Validates: Requirements 1.2, 1.6, 1.7
 * Property: 37
 */
import { ref, computed, onMounted, onBeforeUnmount, type Ref } from 'vue'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type PanelLayoutMode = 'column' | 'drawer' | 'fullscreen'

export interface UseDshPanelLayoutReturn {
  /** 当前布局模式（响应式） */
  layoutMode: Ref<PanelLayoutMode>
  /** 面板是否打开 */
  isOpen: Ref<boolean>
  /** 面板宽度（仅 column/drawer 模式有效） */
  panelWidth: Ref<number>
  /** 打开面板 */
  open: () => void
  /** 关闭面板 */
  close: () => void
  /** 切换面板 */
  toggle: () => void
  /** 开始拖拽 resize（column/drawer 模式） */
  startResize: (e: MouseEvent | TouchEvent) => void
  /** 键盘微调 resize（左右箭头） */
  keyboardResize: (direction: 'narrower' | 'wider') => void
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STORAGE_KEY = 'gt-dsh-panel-width'
const MIN_WIDTH = 320
const MAX_WIDTH = 800
const DEFAULT_WIDTH = 420
const KEYBOARD_STEP = 20

/** 断点阈值 */
const BP_COLUMN = 1401 // viewport > 1400 → column
const BP_DRAWER = 769  // viewport 769–1400 → drawer
                       // viewport ≤ 768 → fullscreen

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useDshPanelLayout(): UseDshPanelLayoutReturn {
  const layoutMode = ref<PanelLayoutMode>('column')
  const isOpen = ref(false)
  const panelWidth = ref(DEFAULT_WIDTH)

  // ── 视口监测 ──

  function updateMode() {
    const w = window.innerWidth
    if (w >= BP_COLUMN) {
      layoutMode.value = 'column'
    } else if (w >= BP_DRAWER) {
      layoutMode.value = 'drawer'
    } else {
      layoutMode.value = 'fullscreen'
    }
  }

  let resizeObserverId: ReturnType<typeof setTimeout> | null = null
  function debouncedUpdate() {
    if (resizeObserverId !== null) clearTimeout(resizeObserverId)
    resizeObserverId = setTimeout(updateMode, 100)
  }

  onMounted(() => {
    updateMode()
    window.addEventListener('resize', debouncedUpdate, { passive: true })

    // 恢复持久化宽度
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      const w = Number(saved)
      if (w >= MIN_WIDTH && w <= MAX_WIDTH) panelWidth.value = w
    }
  })

  onBeforeUnmount(() => {
    window.removeEventListener('resize', debouncedUpdate)
    if (resizeObserverId !== null) clearTimeout(resizeObserverId)
  })

  // ── 面板开关 ──

  function open() { isOpen.value = true }
  function close() { isOpen.value = false }
  function toggle() { isOpen.value = !isOpen.value }

  // ── 拖拽 resize（支持鼠标和触摸） ──

  function startResize(e: MouseEvent | TouchEvent) {
    // fullscreen 模式下不可拖拽
    if (layoutMode.value === 'fullscreen') return

    e.preventDefault()
    const startX = 'touches' in e ? e.touches[0].clientX : e.clientX
    const startWidth = panelWidth.value

    function onMove(ev: MouseEvent | TouchEvent) {
      const clientX = 'touches' in ev ? ev.touches[0].clientX : (ev as MouseEvent).clientX
      // 面板在右侧，向左拖 = 加宽
      const delta = startX - clientX
      const newWidth = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth + delta))
      panelWidth.value = newWidth
    }

    function onEnd() {
      localStorage.setItem(STORAGE_KEY, String(panelWidth.value))
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onEnd)
      document.removeEventListener('touchmove', onMove)
      document.removeEventListener('touchend', onEnd)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }

    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onEnd)
    document.addEventListener('touchmove', onMove, { passive: false })
    document.addEventListener('touchend', onEnd)
  }

  // ── 键盘微调 resize ──

  function keyboardResize(direction: 'narrower' | 'wider') {
    if (layoutMode.value === 'fullscreen') return
    const delta = direction === 'wider' ? KEYBOARD_STEP : -KEYBOARD_STEP
    panelWidth.value = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, panelWidth.value + delta))
    localStorage.setItem(STORAGE_KEY, String(panelWidth.value))
  }

  return {
    layoutMode,
    isOpen,
    panelWidth,
    open,
    close,
    toggle,
    startResize,
    keyboardResize,
  }
}
