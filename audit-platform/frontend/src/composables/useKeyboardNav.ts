/**
 * useKeyboardNav — 表格键盘导航 composable [R9.5]
 *
 * 功能：
 * - Tab / Shift+Tab：在单元格间水平移动
 * - Enter / Shift+Enter：在单元格间垂直移动
 * - 方向键：上下左右移动选中单元格
 * - Escape：退出编辑模式 / 清除选中
 *
 * 配合 useCellSelection 和 useCopyPaste 使用。
 *
 * @module composables/useKeyboardNav
 */
import { onMounted, onUnmounted, type Ref } from 'vue'

export interface KeyboardNavOptions {
  /** 容器元素 ref */
  containerRef: Ref<HTMLElement | { $el: HTMLElement } | null>
  /** 总行数 */
  rowCount: () => number
  /** 总列数 */
  colCount: () => number
  /** 当前选中的行列（返回 [row, col]，无选中返回 null） */
  getSelection: () => [number, number] | null
  /** 选中指定单元格 */
  selectCell: (row: number, col: number) => void
  /** 清除选中 */
  clearSelection?: () => void
  /** 进入编辑（可选，用于 Enter 键） */
  startEdit?: (row: number, col: number) => void
  /** 退出编辑（可选，用于 Escape 键） */
  stopEdit?: () => void
}

export function useKeyboardNav(options: KeyboardNavOptions) {
  function getDOM(): HTMLElement | null {
    const el = options.containerRef.value
    if (!el) return null
    return '$el' in el ? (el as any).$el : el
  }

  function handleKeyDown(e: KeyboardEvent) {
    // 忽略在 input/textarea 中的按键（除了 Tab 和 Escape）
    const target = e.target as HTMLElement
    const isInput = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable
    if (isInput && e.key !== 'Tab' && e.key !== 'Escape') return

    const current = options.getSelection()
    const rows = options.rowCount()
    const cols = options.colCount()

    switch (e.key) {
      case 'Tab': {
        e.preventDefault()
        if (!current) {
          options.selectCell(0, 0)
          return
        }
        const [r, c] = current
        if (e.shiftKey) {
          // Shift+Tab: 向左移动，到行首则跳到上一行末尾
          if (c > 0) {
            options.selectCell(r, c - 1)
          } else if (r > 0) {
            options.selectCell(r - 1, cols - 1)
          }
        } else {
          // Tab: 向右移动，到行尾则跳到下一行开头
          if (c < cols - 1) {
            options.selectCell(r, c + 1)
          } else if (r < rows - 1) {
            options.selectCell(r + 1, 0)
          }
        }
        break
      }

      case 'Enter': {
        if (!current) return
        const [r, c] = current
        if (isInput) {
          // 在编辑中按 Enter：退出编辑并移到下一行
          e.preventDefault()
          options.stopEdit?.()
          if (e.shiftKey) {
            if (r > 0) options.selectCell(r - 1, c)
          } else {
            if (r < rows - 1) options.selectCell(r + 1, c)
          }
        } else {
          // 非编辑中按 Enter：进入编辑
          e.preventDefault()
          options.startEdit?.(r, c)
        }
        break
      }

      case 'Escape': {
        if (isInput) {
          options.stopEdit?.()
        } else {
          options.clearSelection?.()
        }
        break
      }

      case 'ArrowUp': {
        if (isInput) return
        e.preventDefault()
        if (!current) { options.selectCell(0, 0); return }
        const [r, c] = current
        if (r > 0) options.selectCell(r - 1, c)
        break
      }

      case 'ArrowDown': {
        if (isInput) return
        e.preventDefault()
        if (!current) { options.selectCell(0, 0); return }
        const [r, c] = current
        if (r < rows - 1) options.selectCell(r + 1, c)
        break
      }

      case 'ArrowLeft': {
        if (isInput) return
        e.preventDefault()
        if (!current) { options.selectCell(0, 0); return }
        const [r, c] = current
        if (c > 0) options.selectCell(r, c - 1)
        break
      }

      case 'ArrowRight': {
        if (isInput) return
        e.preventDefault()
        if (!current) { options.selectCell(0, 0); return }
        const [r, c] = current
        if (c < cols - 1) options.selectCell(r, c + 1)
        break
      }
    }
  }

  onMounted(() => {
    const dom = getDOM()
    if (dom) {
      dom.addEventListener('keydown', handleKeyDown)
      // 确保容器可以接收键盘事件
      if (!dom.getAttribute('tabindex')) {
        dom.setAttribute('tabindex', '0')
      }
    }
  })

  onUnmounted(() => {
    const dom = getDOM()
    if (dom) {
      dom.removeEventListener('keydown', handleKeyDown)
    }
  })

  return { handleKeyDown }
}
