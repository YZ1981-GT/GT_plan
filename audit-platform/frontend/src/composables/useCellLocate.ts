/**
 * useCellLocate — 底稿 HTML 渲染器单元格定位 composable
 *
 * 职责：
 * 1. 接收 LocateTarget 坐标，按 componentType 分派定位策略
 * 2. el-table 类（c-note-table / d-form-table / e-control-test）：滚动到行 + 行高亮
 * 3. GtIndexChip 类（a-program-console / b-index）：scrollIntoView + 闪烁动画
 * 4. 通用 fallback（h-static-doc / d-form-* / 未知类型）：scrollIntoView 最近匹配
 * 5. univer：委托 UniverEditorCore.onLocateCell（此处仅返回 true）
 * 6. 高亮幂等 + 3s CSS transition 淡出
 *
 * Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 5.1, 5.2
 *
 * @example
 * const { locateCell } = useCellLocate()
 * const success = locateCell({ wp_code: 'D2-1', sheet_name: '应收账款', cell_ref: 'B5', component_type: 'c-note-table' })
 */
// nextTick 由调用方（GtWpRenderer）在切 sheet 后使用，确保 DOM 已更新再调 locateCell

// ─── 常量 ─────────────────────────────────────────────────────────────────────

/** 高亮 CSS class（行高亮） */
export const GT_LOCATE_HIGHLIGHT_CLASS = 'gt-locate-highlight'

/** 闪烁 CSS class（chip 闪烁动画） */
export const GT_LOCATE_BLINK_CLASS = 'gt-locate-blink'

/** 高亮持续时间（ms） */
export const HIGHLIGHT_DURATION_MS = 3000

// ─── 类型定义 ─────────────────────────────────────────────────────────────────

/** 定位坐标（对齐后端 LocateTarget dataclass） */
export interface LocateTarget {
  wp_code: string
  wp_id?: string | null
  sheet_name?: string | null
  cell_ref?: string | null
  component_type?: string | null
  value?: string | null
  label?: string | null
}

// ─── componentType 分组 ────────────────────────────────────────────────────────

/** el-table 类组件（滚动到行 + 行高亮） */
const EL_TABLE_TYPES = new Set(['c-note-table', 'd-form-table', 'e-control-test'])

/** GtIndexChip 类组件（scrollIntoView + 闪烁） */
const CHIP_TYPES = new Set(['a-program-console', 'b-index'])

/**
 * 通用 fallback 类组件（scrollIntoView 最近匹配）
 * 包括：h-static-doc / d-form-paragraph / d-form-qa / d-form-confirmation / d-form-review / 未知类型
 * 不需要显式 Set 判定——所有不属于 EL_TABLE_TYPES / CHIP_TYPES / univer 的类型都走 fallback
 */

// ─── 内部状态 ─────────────────────────────────────────────────────────────────

/** 当前高亮目标 key（幂等判定） */
let _currentHighlightKey: string | null = null

/** 当前高亮定时器 */
let _highlightTimer: ReturnType<typeof setTimeout> | null = null

// ─── 工具函数 ─────────────────────────────────────────────────────────────────

/** 生成定位目标唯一 key */
function buildLocateKey(target: LocateTarget): string {
  return `${target.wp_code}:${target.sheet_name ?? ''}:${target.cell_ref ?? ''}`
}

/** 清除之前的高亮（如果存在） */
function clearPreviousHighlight(): void {
  // 清除 highlight class
  const highlighted = document.querySelectorAll(`.${GT_LOCATE_HIGHLIGHT_CLASS}`)
  highlighted.forEach((el) => el.classList.remove(GT_LOCATE_HIGHLIGHT_CLASS))

  // 清除 blink class
  const blinking = document.querySelectorAll(`.${GT_LOCATE_BLINK_CLASS}`)
  blinking.forEach((el) => el.classList.remove(GT_LOCATE_BLINK_CLASS))

  // 清除定时器
  if (_highlightTimer) {
    clearTimeout(_highlightTimer)
    _highlightTimer = null
  }
}

/**
 * 添加高亮 class 并设置 3s 后自动移除
 * 返回是否成功添加（幂等：同一目标不重复添加）
 */
function applyHighlight(el: Element, className: string, targetKey: string): boolean {
  // 幂等：同一目标已高亮则跳过
  if (_currentHighlightKey === targetKey && el.classList.contains(className)) {
    return true
  }

  // 清除之前的高亮
  clearPreviousHighlight()

  // 添加新高亮
  el.classList.add(className)
  _currentHighlightKey = targetKey

  // 3s 后自动移除
  _highlightTimer = setTimeout(() => {
    el.classList.remove(className)
    _currentHighlightKey = null
    _highlightTimer = null
  }, HIGHLIGHT_DURATION_MS)

  return true
}

// ─── 定位策略 ─────────────────────────────────────────────────────────────────

/**
 * el-table 类定位策略
 * 适用：c-note-table / d-form-table / e-control-test
 * 逻辑：找到目标行 → scrollIntoView → 添加高亮 class → 3s 后移除
 */
function locateElTable(target: LocateTarget, targetKey: string): boolean {
  // 策略 1：通过 data-cell-ref 属性查找行
  const cellRef = target.cell_ref
  const value = target.value

  let targetRow: Element | null = null

  if (cellRef) {
    // 尝试通过 data-cell-ref 属性定位
    targetRow = document.querySelector(
      `.el-table [data-cell-ref="${cellRef}"]`
    )
    // 如果找到的是 cell，向上找到 row
    if (targetRow && !targetRow.classList.contains('el-table__row')) {
      targetRow = targetRow.closest('.el-table__row')
    }
  }

  // 策略 2：通过 data-row-index 或内容匹配
  if (!targetRow && cellRef) {
    // 从 cell_ref 提取行号（如 "B5" → row 5）
    const rowMatch = cellRef.match(/\d+/)
    if (rowMatch) {
      const rowIndex = parseInt(rowMatch[0], 10) - 1 // 0-based
      const rows = document.querySelectorAll('.el-table__body .el-table__row')
      if (rowIndex >= 0 && rowIndex < rows.length) {
        targetRow = rows[rowIndex]
      }
    }
  }

  // 策略 3：通过 value 内容匹配
  if (!targetRow && value) {
    const rows = document.querySelectorAll('.el-table__body .el-table__row')
    for (const row of rows) {
      if (row.textContent?.includes(value)) {
        targetRow = row
        break
      }
    }
  }

  if (!targetRow) return false

  // 滚动到目标行
  targetRow.scrollIntoView({ behavior: 'smooth', block: 'center' })

  // 添加高亮
  return applyHighlight(targetRow, GT_LOCATE_HIGHLIGHT_CLASS, targetKey)
}

/**
 * GtIndexChip 类定位策略
 * 适用：a-program-console / b-index
 * 逻辑：querySelector 目标 chip → scrollIntoView → 闪烁动画 → 3s 淡出
 */
function locateChip(target: LocateTarget, targetKey: string): boolean {
  const value = target.value
  const cellRef = target.cell_ref

  let chipEl: Element | null = null

  // 策略 1：通过 data-wp-code + data-cell-ref 属性查找
  if (cellRef) {
    chipEl = document.querySelector(
      `[data-wp-code="${target.wp_code}"][data-cell-ref="${cellRef}"]`
    )
  }

  // 策略 2：通过 data-wp-code 查找
  if (!chipEl) {
    chipEl = document.querySelector(`[data-wp-code="${target.wp_code}"]`)
  }

  // 策略 3：通过 value 内容匹配 GtIndexChip
  if (!chipEl && value) {
    const chips = document.querySelectorAll('.gt-index-chip')
    for (const chip of chips) {
      if (chip.textContent?.includes(value)) {
        chipEl = chip
        break
      }
    }
  }

  if (!chipEl) return false

  // 滚动到目标 chip
  chipEl.scrollIntoView({ behavior: 'smooth', block: 'center' })

  // 添加闪烁动画
  return applyHighlight(chipEl, GT_LOCATE_BLINK_CLASS, targetKey)
}

/**
 * 通用 fallback 定位策略
 * 适用：h-static-doc / d-form-paragraph / d-form-qa / d-form-confirmation / d-form-review / 未知类型
 * 逻辑：scrollIntoView 最近匹配元素
 */
function locateFallback(target: LocateTarget, targetKey: string): boolean {
  const value = target.value
  const cellRef = target.cell_ref

  let matchEl: Element | null = null

  // 策略 1：通过 data-cell-ref 属性查找
  if (cellRef) {
    matchEl = document.querySelector(`[data-cell-ref="${cellRef}"]`)
  }

  // 策略 2：通过 value 内容匹配
  if (!matchEl && value) {
    // 在当前渲染区域查找包含目标值的元素
    const candidates = document.querySelectorAll(
      '.gt-wp-renderer [data-field], .gt-wp-renderer td, .gt-wp-renderer .el-form-item'
    )
    for (const el of candidates) {
      if (el.textContent?.includes(value)) {
        matchEl = el
        break
      }
    }
  }

  // 策略 3：通过 label 匹配
  if (!matchEl && target.label) {
    const candidates = document.querySelectorAll(
      '.gt-wp-renderer label, .gt-wp-renderer .el-form-item__label, .gt-wp-renderer th'
    )
    for (const el of candidates) {
      if (el.textContent?.includes(target.label)) {
        matchEl = el
        break
      }
    }
  }

  if (!matchEl) return false

  // 滚动到目标元素
  matchEl.scrollIntoView({ behavior: 'smooth', block: 'center' })

  // 添加高亮
  return applyHighlight(matchEl, GT_LOCATE_HIGHLIGHT_CLASS, targetKey)
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useCellLocate() {
  /**
   * 定位到目标单元格
   * @param target 定位坐标
   * @returns 是否成功定位
   */
  function locateCell(target: LocateTarget): boolean {
    const componentType = target.component_type
    const targetKey = buildLocateKey(target)

    // univer 类型：委托给 UniverEditorCore.onLocateCell
    // 实际委托在 GtWpRenderer 层完成，此处仅返回 true 表示支持
    if (componentType === 'univer') {
      return true
    }

    // 使用 nextTick 确保 DOM 已更新后再执行定位
    // 但 locateCell 本身是同步返回，DOM 操作在当前 tick 执行
    // 如果 DOM 尚未渲染，调用方应在 nextTick 后调用 locateCell

    // el-table 类定位策略
    if (componentType && EL_TABLE_TYPES.has(componentType)) {
      return locateElTable(target, targetKey)
    }

    // GtIndexChip 类定位策略
    if (componentType && CHIP_TYPES.has(componentType)) {
      return locateChip(target, targetKey)
    }

    // 通用 fallback 策略（已知 fallback 类型 + 未知类型）
    return locateFallback(target, targetKey)
  }

  return { locateCell }
}
