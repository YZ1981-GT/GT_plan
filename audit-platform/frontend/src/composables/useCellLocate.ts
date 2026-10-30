/**
 * useCellLocate — 底稿 HTML 渲染器单元格定位 composable
 *
 * 职责：
 * 1. 接收 LocateTarget 坐标，按 componentType 分派定位策略
 * 2. el-table 类（c-note-table / d-form-table / e-control-test）：滚动到行 + 行高亮
 * 3. GtIndexChip 类（a-program-console / b-index）：scrollIntoView + 闪烁动画
 * 4. 通用 fallback（h-static-doc / d-form-* / 未知类型）：scrollIntoView 最近匹配
 * 5. univer：委托 UniverEditorCore.onLocateCell（此处仅返回 true）
 * 6. 高亮幂等 + 3s 淡出（样式在 styles/global.css）
 *
 * 查找范围：调用方传 `root` 时只在 root 内找（GtWpRenderer 传自己的根元素，避免命中侧栏 / 其他表格）；
 * 不传时沿用整个 document。不再按单元格行号猜「第 N 个表格行」——模板行号与网页表格行没有对应关系，
 * 猜中的是别的行（spec wp-deeplink-cell-locate-closure 需求 2.2）。
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

/** 定位选项：root = 查找范围（缺省整个 document） */
export interface LocateOptions {
  root?: ParentNode | null
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

/**
 * 滚到可见并高亮任意元素（组件自己的定位钩子用；与 locateCell 共用幂等与 3s 淡出）。
 */
export function highlightElement(el: Element, targetKey: string, className: string = GT_LOCATE_HIGHLIGHT_CLASS): boolean {
  el.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
  return applyHighlight(el, className, targetKey)
}

// ─── 定位策略 ─────────────────────────────────────────────────────────────────

/**
 * el-table 类定位策略
 * 适用：c-note-table / d-form-table / e-control-test
 * 逻辑：找到目标行 → scrollIntoView → 添加高亮 class → 3s 后移除
 */
function locateElTable(target: LocateTarget, targetKey: string, root: ParentNode): boolean {
  const cellRef = target.cell_ref
  const value = target.value

  let targetRow: Element | null = null

  // 策略 1：通过 data-cell-ref 属性查找行
  if (cellRef) {
    targetRow = root.querySelector(`.el-table [data-cell-ref="${cellRef}"]`)
    // 如果找到的是 cell，向上找到 row
    if (targetRow && !targetRow.classList.contains('el-table__row')) {
      targetRow = targetRow.closest('.el-table__row')
    }
  }

  // 策略 2：通过 value 内容匹配
  if (!targetRow && value) {
    const rows = root.querySelectorAll('.el-table__body .el-table__row')
    for (const row of rows) {
      if (row.textContent?.includes(value)) {
        targetRow = row
        break
      }
    }
  }

  if (!targetRow) return false
  return highlightElement(targetRow, targetKey)
}

/**
 * GtIndexChip 类定位策略
 * 适用：a-program-console / b-index
 * 逻辑：querySelector 目标 chip → scrollIntoView → 闪烁动画 → 3s 淡出
 */
function locateChip(target: LocateTarget, targetKey: string, root: ParentNode): boolean {
  const value = target.value
  const cellRef = target.cell_ref

  let chipEl: Element | null = null

  // 策略 1：通过 data-wp-code + data-cell-ref 属性查找
  if (cellRef) {
    chipEl = root.querySelector(`[data-wp-code="${target.wp_code}"][data-cell-ref="${cellRef}"]`)
  }

  // 策略 2：通过 data-wp-code 查找
  if (!chipEl) {
    chipEl = root.querySelector(`[data-wp-code="${target.wp_code}"]`)
  }

  // 策略 3：通过 value 内容匹配 GtIndexChip
  if (!chipEl && value) {
    const chips = root.querySelectorAll('.gt-index-chip')
    for (const chip of chips) {
      if (chip.textContent?.includes(value)) {
        chipEl = chip
        break
      }
    }
  }

  if (!chipEl) return false
  return highlightElement(chipEl, targetKey, GT_LOCATE_BLINK_CLASS)
}

/**
 * 通用 fallback 定位策略
 * 适用：h-static-doc / d-form-paragraph / d-form-qa / d-form-confirmation / d-form-review / 未知类型
 * 逻辑：scrollIntoView 最近匹配元素
 */
function locateFallback(target: LocateTarget, targetKey: string, root: ParentNode): boolean {
  const value = target.value
  const cellRef = target.cell_ref

  let matchEl: Element | null = null

  // 策略 1：通过 data-cell-ref 属性查找
  if (cellRef) {
    matchEl = root.querySelector(`[data-cell-ref="${cellRef}"]`)
  }

  // 策略 2：通过 value 内容匹配
  if (!matchEl && value) {
    // 在当前渲染区域查找包含目标值的元素
    const candidates = root.querySelectorAll(
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
    const candidates = root.querySelectorAll(
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
  return highlightElement(matchEl, targetKey)
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useCellLocate() {
  /**
   * 定位到目标单元格
   * @param target 定位坐标
   * @param options root = 查找范围（缺省整个 document）
   * @returns 是否成功定位
   */
  function locateCell(target: LocateTarget, options: LocateOptions = {}): boolean {
    const componentType = target.component_type
    const targetKey = buildLocateKey(target)
    const root: ParentNode = options.root ?? document

    // univer 类型：委托给 UniverEditorCore.onLocateCell
    // 实际委托在 GtWpRenderer 层完成，此处仅返回 true 表示支持
    if (componentType === 'univer') {
      return true
    }

    // 如果 DOM 尚未渲染，调用方应在 nextTick 后调用 locateCell（GtWpRenderer 经 useRendererCellLocate 重试）

    // el-table 类定位策略
    if (componentType && EL_TABLE_TYPES.has(componentType)) {
      return locateElTable(target, targetKey, root)
    }

    // GtIndexChip 类定位策略
    if (componentType && CHIP_TYPES.has(componentType)) {
      return locateChip(target, targetKey, root)
    }

    // 通用 fallback 策略（已知 fallback 类型 + 未知类型）
    return locateFallback(target, targetKey, root)
  }

  return { locateCell }
}
