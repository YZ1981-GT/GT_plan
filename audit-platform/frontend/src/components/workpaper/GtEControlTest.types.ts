// ─── GtEControlTest Types ────────────────────────────────────────────────────
// Extracted from GtEControlTest.vue for shared use across shell + sub-mode SFCs

export type FieldType =
  | 'text'
  | 'textarea'
  | 'number'
  | 'enum'
  | 'multi_enum'
  | 'attachment_list'

export interface FieldDef {
  name: string
  label: string
  type?: FieldType
  required?: boolean
  enum?: string[]
  cell?: string
  min?: number
  max?: number
  max_length?: number
  hint?: string
  conditional?: string
  render?: 'index_chip' | string
}

export interface SegmentDef {
  id: string
  title: string
  start_row?: number
  end_row?: number | string
  fields: FieldDef[]
}

export interface NextLogic {
  when?: string
  goto?: number
  reason?: string
  conclusion_hint?: string
}

export interface StepDef {
  step: number
  id: string
  title: string
  description?: string
  fields: FieldDef[]
  next_logic?: NextLogic[]
  is_terminal?: boolean
}

export interface HintItem {
  no: number
  content: string
}

export interface HintBlock {
  id: string
  label: string
  collapsible?: boolean
  default_collapsed?: boolean
  type?: 'reference_table' | string
  items?: HintItem[]
  content?: string
  columns?: string[]
  rows?: any[][]
}

export interface ConclusionOption {
  value: string
  label: string
  class?: 'success' | 'warning' | 'danger' | 'info'
  icon?: string
  description?: string
}

export interface ConclusionBlock {
  mode?: 'single' | 'per_row'
  options?: ConclusionOption[]
  mutual_exclusive?: boolean
  cell?: string
  derived_from?: string
  auto_derive?: { rule: string; editable?: boolean }
}

export interface DynamicTableColumnDef {
  field: string
  label: string
  type?: FieldType
  enum?: string[]
  min?: number
  max?: number
  max_length?: number
  pattern?: string
  render?: 'index_chip' | 'select_or_text' | string
  width?: number
}

export interface DynamicTableSchema {
  start_row?: number
  end_row?: number | string
  header_row?: number
  columns: Record<string, DynamicTableColumnDef>
}

export interface EControlTestSchema {
  test_type?: 'summary' | 'single' | 'evaluation_step'
  fixed_cells?: Record<string, string>
  fields?: FieldDef[]               // evaluation_step 顶部上下文字段
  segments?: SegmentDef[]           // single 子模式
  steps?: StepDef[]                 // evaluation_step 子模式
  dynamic_table?: DynamicTableSchema  // summary 子模式
  hints?: HintBlock[]
  conclusion?: ConclusionBlock
  [key: string]: any
}

export interface SummaryRow {
  id?: string
  conclusion?: string
  [key: string]: any
}

export interface EControlTestData {
  // summary 子模式
  rows?: SummaryRow[]
  // single + evaluation_step 共用
  fields?: Record<string, any>
  // evaluation_step：每步骤独立数据
  steps?: Record<string, Record<string, any>>
  // 终态结论
  conclusion?: string
  // 当前激活步骤
  active_step?: number
  // 折叠状态
  active_hint_ids?: string[]
  // AI 辅助标记
  ai_assisted_fields?: string[]
  [key: string]: any
}

export interface SuggestionPayload {
  wp_id: string
  sheet_name: string
  conclusion: string
  suggestion_type: 'reduce' | 'increase' | 'full' | 'none'
  confidence: 'high' | 'medium' | 'low' | 'required'
  source: string
}
