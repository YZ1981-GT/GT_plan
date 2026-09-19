/**
 * useReviewContextMenu — el-table 单元格右键激活复核对话
 *
 * 为任意 el-table 提供 `onCellContextMenu` 处理器，右键单元格时弹出
 * "📝 发起复核对话" 菜单项，点击后调用 provider 的 openReviewDialog。
 *
 * @see .kiro/specs/audit-review-dialog/design.md §右键菜单集成
 */
import { ref, onUnmounted } from 'vue'
import { useReviewDialogInject, type ReviewDialogActivation } from './useReviewDialogProvider'

export interface ReviewContextMenuOptions {
  /** sectionId 前缀，如 'D1-adj' → 生成 'D1-adj-{rowKey}-{field}' */
  prefix: string
  /** 底稿 ID */
  wpId: string
  /** 当前用户（传给 openReviewDialog） */
  currentUser: ReviewDialogActivation['currentUser']
  /** 行 key 字段名，默认 'rowKey' */
  rowKeyField?: string
  /** 格式化单元格值函数，默认 String(value) */
  formatValue?: (value: unknown) => string
}

export function useReviewContextMenu(options: ReviewContextMenuOptions) {
  const { openReviewDialog } = useReviewDialogInject()
  const menuVisible = ref(false)
  const menuPosition = ref({ x: 0, y: 0 })

  let menuEl: HTMLElement | null = null

  function removeMenu() {
    if (menuEl) {
      menuEl.remove()
      menuEl = null
    }
    menuVisible.value = false
  }

  function handleDocClick() {
    removeMenu()
  }

  /**
   * el-table @cell-contextmenu handler
   */
  function onCellContextMenu(row: any, column: any, _cell: any, event: MouseEvent): void {
    event.preventDefault()
    removeMenu()

    const rowKey = row[options.rowKeyField || 'rowKey'] || row.id || 'unknown'
    const field = column?.property || 'unknown'
    const value = row[field]
    const fmtValue = options.formatValue ? options.formatValue(value) : String(value ?? '')

    const sectionId = `${options.prefix}-${rowKey}-${field}`
    const sectionLabel = `${row.label || row.name || rowKey} - ${column?.label || field}: ${fmtValue}`

    menuPosition.value = { x: event.clientX, y: event.clientY }
    menuVisible.value = true

    // 创建简易右键菜单 DOM
    menuEl = document.createElement('div')
    menuEl.className = 'gt-review-context-menu'
    menuEl.style.cssText = `
      position: fixed; left: ${event.clientX}px; top: ${event.clientY}px;
      z-index: 9999; background: #fff; border: 1px solid #e4e7ed;
      border-radius: 4px; box-shadow: 0 2px 12px rgba(0,0,0,.1);
      padding: 4px 0; min-width: 160px;
    `

    const item = document.createElement('div')
    item.textContent = '📝 发起复核对话'
    item.style.cssText = `
      padding: 8px 16px; cursor: pointer; font-size: 13px; color: #303133;
      transition: background 0.15s;
    `
    item.onmouseenter = () => { item.style.background = '#f5f7fa' }
    item.onmouseleave = () => { item.style.background = '' }
    item.onclick = () => {
      openReviewDialog({
        wpId: options.wpId,
        sectionId,
        sectionLabel,
        currentUser: options.currentUser,
        relatedData: { rowKey, field, value, cellLabel: column?.label },
      })
      removeMenu()
    }

    menuEl.appendChild(item)
    document.body.appendChild(menuEl)

    // 点击其他区域关闭
    setTimeout(() => document.addEventListener('click', handleDocClick, { once: true }), 0)
  }

  onUnmounted(() => {
    removeMenu()
    document.removeEventListener('click', handleDocClick)
  })

  return {
    onCellContextMenu,
    menuVisible,
    menuPosition,
  }
}
