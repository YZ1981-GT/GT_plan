/**
 * auditSheetTypes — 审定表组件共享类型（spec workpaper-frontend-large-component-split, Req 3）
 *
 * 从 GtAuditSheet.vue 抽出的类型定义，供主组件 / composable 复用。
 * 仅类型（无运行时），依赖单向：主组件 / composable → 本文件。
 */

// ─── Types ───
export interface AuditSheetSchema {
  [key: string]: any
}

/**
 * 审定表行（结构化）
 * - 持久化部分：item/indent/bold/isSection/isComputed/account_code +
 *   用户编辑列 adj_amount/reclass_amount/reason
 * - 运行时合并（不持久化）：TB 实时取数 opening_unadjusted/current_unadjusted/sys_aje/sys_rje
 */
export interface AuditSheetRow {
  id: string
  item: string
  indent?: number
  bold?: boolean
  isComputed?: boolean
  isSection?: boolean
  /** 用户自定义新增行（Task 17）：项目名可编辑，持久化完整数据 */
  isCustom?: boolean
  account_code?: string | null
  // ─── 用户编辑列（持久化）───
  adj_amount?: number | null
  reclass_amount?: number | null
  reason?: string
  // ─── TB 实时值（运行时合并，不持久化）───
  opening_unadjusted?: number | null
  current_unadjusted?: number | null
  sys_aje?: number | null
  sys_rje?: number | null
  [key: string]: any
}

/** TB 实时取数值（运行时合并，不持久化） */
export interface AuditSheetTbValue {
  opening_unadjusted?: number | null
  current_unadjusted?: number | null
  sys_aje?: number | null
  sys_rje?: number | null
}

/**
 * 审计说明 / 审计结论区（持久化）。
 */
export interface AuditSheetSections {
  notes?: string
  conclusion?: string
  notes_label?: string
  conclusion_label?: string
}

/** 动态列定义（多列明细表用） */
export interface AuditSheetColumnDef {
  key: string
  label: string
  col_idx: number
}

export interface AuditSheetHtmlData {
  audit_rows?: AuditSheetRow[]
  audit_sections?: AuditSheetSections
  tb_values?: Record<string, AuditSheetTbValue>
  column_defs?: AuditSheetColumnDef[]
  [key: string]: any
}
