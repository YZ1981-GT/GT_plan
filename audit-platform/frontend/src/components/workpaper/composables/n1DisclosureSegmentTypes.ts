/**
 * N1DisclosureSegmentTable 的渲染契约类型
 *
 * 🔴 单独放 `.ts` 而不是写在 `N1DisclosureSegmentTable.vue` 里：
 * `<script setup>` **不允许任何 `export` 语句**（含 `export interface`），
 * 会让 SFC 编译失败 —— 而 `get_diagnostics`(Volar) 查不出这类结构性错误，
 * 只有 Vite transform 会报 500。故类型下沉到本文件，组件与 composable 共同引用。
 */

export interface N1SegColumn {
  key: string
  label: string
  /** 父表头；相邻且相同的列合并为两级表头（对齐源模板 B10:C10 / D10:E10） */
  group?: string
  /** `'text'` 渲染为文本输入（如「备注」列），其余按金额渲染 */
  format?: 'amount' | 'text'
  minWidth?: number
  placeholder?: string
}

export interface N1SegRow {
  item: string
  /** true = 用户动态新增行（行名可编辑 + 可删除；源模板固定行不可删） */
  _editableLabel?: boolean
  [k: string]: unknown
}

export interface N1Segment {
  /** 段标识（回传给父组件用于定位） */
  key: string
  /** 分组标题行文案（逐字取自源模板）；空串 = 无分组标题（单段平表） */
  label: string
  rows: N1SegRow[]
  /** 段末小计（公式值，按列键给出；父组件按源模板公式算）；`null` = 无小计行 */
  subtotal?: Record<string, number | null> | null
  /** 小计 / 合计行文案（源模板写 `小  计`、`合  计`；平台统一无空格） */
  subtotalLabel?: string
}

export interface N1SegCellPayload {
  seg: string
  index: number
  key: string
  value: number | string
}

export interface N1SegLabelPayload {
  seg: string
  index: number
  value: string
}

export interface N1SegRowPayload {
  seg: string
  index: number
}
