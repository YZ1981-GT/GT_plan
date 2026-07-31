/**
 * 披露分段表（`WpDisclosureSegmentTable`）的渲染契约类型 —— 平台共用
 *
 * 🔴 单独放 `.ts` 而不是写在 SFC 里：`<script setup>` **不允许任何 `export` 语句**
 * （含 `export interface`），会让 SFC 编译失败 —— 而 `get_diagnostics`(Volar) 查不出
 * 这类结构性错误，只有 Vite transform 会报 500。
 *
 * 起源于 N1 递延所得税披露（`n1-deferred-tax-disclosure-template-alignment`），
 * 由 `n-cycle-tax-disclosure-alignment` Task 2.1 提升为平台共用。
 */

export interface WpSegColumn {
  key: string
  label: string
  /** 父表头；相邻且相同的列合并为两级表头（源模板合并单元格如 B10:C10） */
  group?: string
  /** `'text'` 渲染为文本输入（如「备注」列），其余按金额渲染 */
  format?: 'amount' | 'text'
  minWidth?: number
  placeholder?: string
  /**
   * 只读列（公式列）。用于源模板里由行内公式算出的列，
   * 例如 N2 国企「期末余额 = 期初余额 + 本期应交 − 本期已交」。
   */
  readonly?: boolean
}

export interface WpSegRow {
  item: string
  /** true = 用户动态新增行（行名可编辑 + 可删除；源模板固定行不可删） */
  _editableLabel?: boolean
  [k: string]: unknown
}

export interface WpSegment {
  /** 段标识（回传给父组件用于定位） */
  key: string
  /** 分组标题行文案（逐字取自源模板）；空串 = 无分组标题（单段平表） */
  label: string
  rows: WpSegRow[]
  /** 段末小计（公式值，按列键给出；父组件按源模板公式算）；`null` = 无小计行 */
  subtotal?: Record<string, number | null> | null
  /** 小计 / 合计行文案（源模板写 `小  计`、`合  计`；平台统一无空格） */
  subtotalLabel?: string
}

export interface WpSegCellPayload {
  seg: string
  index: number
  key: string
  value: number | string
}

export interface WpSegLabelPayload {
  seg: string
  index: number
  value: string
}

export interface WpSegRowPayload {
  seg: string
  index: number
}

// ─── N1 兼容别名（N1 spec 已落地的引用不改名，避免无谓 churn）───────────────

export type N1SegColumn = WpSegColumn
export type N1SegRow = WpSegRow
export type N1Segment = WpSegment
export type N1SegCellPayload = WpSegCellPayload
export type N1SegLabelPayload = WpSegLabelPayload
export type N1SegRowPayload = WpSegRowPayload
