/**
 * GtCNoteTable.types.ts — C 类附注披露嵌套表共享类型
 *
 * 从 GtCNoteTable.vue 原 366-530 行剪切，逐字搬运 + export。
 * shell / CNoteCell / CNoteSubTableCard / CNoteInheritanceBadge / composables 共享。
 * spec: gt-c-note-table-shrink Task 1
 */

export type SubTableType = 'static_rows' | 'dynamic_rows'
export type ColumnType = 'text' | 'textarea' | 'number' | 'enum' | 'multi_enum' | 'date' | 'boolean'
export type RenderHint =
  | 'amount'
  | 'amount_formula'
  | 'percent'
  | 'percent_formula'
  | 'checkmark'
  | 'tag'
  | 'index_chip'
  | string
export type SubClass = 'listed' | 'soe'

export interface ColumnDef {
  field: string
  label: string
  type?: ColumnType
  enum?: string[]
  render?: RenderHint
  width?: number
  min?: number
  max?: number
  max_length?: number
  required?: boolean
  readonly?: boolean
  formula?: string
  default?: any
  applicable_to_sub_class?: SubClass[]
  hint?: string
  format?: string
}

export interface ColumnDefWithKey extends ColumnDef {
  _cellKey: string
}

export interface StaticRowDef {
  id: string
  label: string
  is_grand_total?: boolean
  is_subtotal?: boolean
  indent?: number
}

export interface FooterTotalDef {
  enabled?: boolean
  label?: string
  sum_columns?: string[]
  formula_columns?: Record<string, string>
}

export interface SubTableSchema {
  id: string
  title: string
  type: SubTableType
  applicable_to_sub_class?: SubClass[]
  order?: number
  columns?: Record<string, ColumnDef>
  static_rows?: StaticRowDef[]
  max_rows?: number
  add_row_button?: boolean
  description?: string
  footer_total?: FooterTotalDef
}

export interface InheritanceRuleSourceTarget {
  sub_table?: string
  row?: string
  column?: string
  sum_field?: string
  exclude_rows?: string[]
  group_by?: string
  filter?: string
  formula?: string
  external?: string
  query?: Record<string, any>
}

export interface InheritanceRule {
  id: string
  source: InheritanceRuleSourceTarget
  target: InheritanceRuleSourceTarget
  formula?: 'SUM' | string
  validation: 'equal' | 'less_than_or_equal' | string
  on_mismatch: 'error' | 'warning' | 'info' | string
  description?: string
  applicable_when?: { standard?: SubClass | string }
}

export interface VersionVariant {
  label?: string
  extra_subtables?: string[]
  extra_columns_in?: Record<string, string[]>
}

export interface ContextField {
  name: string
  label: string
  type?: ColumnType
  cell?: string
  default?: any
  enum?: string[]
  readonly?: boolean
  hint?: string
}

export interface CrossRefDef {
  ref_id: string
  source?: any
  source_cell?: string
  target_wp?: string
  target_sheet?: string
  target_section?: string
  target_field?: string
  description?: string
  severity?: 'required' | 'optional' | string
  direction?: 'inbound' | 'outbound' | string
  auto_pull?: boolean
  sync_strategy?: string
}

export interface LinkageDownstreamRule {
  target?: string
  condition?: string
  action?: string
  description?: string
}

export interface LinkageDef {
  upstream?: any[]
  downstream?: LinkageDownstreamRule[]
}

export interface CNoteTableSchema {
  component_type?: string
  applicable_standard?: string
  applicable_standards?: string[]
  fixed_cells?: Record<string, string>
  fields?: ContextField[]
  sub_tables?: SubTableSchema[]
  inheritance_rules?: InheritanceRule[]
  version_variants?: Partial<Record<SubClass, VersionVariant>>
  hidden_subtables?: { semantics?: string; default?: string[] }
  cross_refs?: CrossRefDef[]
  linkage?: LinkageDef
  [key: string]: any
}

export type RowData = Record<string, any> & { _row_id?: string }

export interface CNoteTableHtmlData {
  sub_table_data?: Record<string, RowData[]>
  hidden_subtables?: string[]
  current_standard?: string
  context?: Record<string, any>
  [key: string]: any
}

export interface SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  sub_table_data: Record<string, RowData[]>
  current_standard: string
}

export interface RuleStatus {
  ruleId: string
  subTableId: string
  status: 'ok' | 'mismatch' | 'warning' | 'na'
  label: string
  tooltip: string
  diff?: number
}
