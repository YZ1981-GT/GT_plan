/**
 * 附注语义结构 sidecar TypeScript 类型定义
 *
 * 与后端 backend/app/schemas/note_semantic_schema.py 一一对应。
 * 存储在 disclosure_notes.table_data 的 sidecar 字段中。
 *
 * Validates: Requirements 3.1, 3.2, 3.3, 3.5
 */

/**
 * 行类型枚举
 * Requirements 3.2: 至少包括 table_title, group_header, data, subtotal,
 * total, note_tip, footnote, blank, custom。
 */
export type NoteRowType =
  | 'table_title'
  | 'group_header'
  | 'data'
  | 'subtotal'
  | 'total'
  | 'note_tip'
  | 'footnote'
  | 'blank'
  | 'custom'

/**
 * 列语义定义
 * Requirements 3.3: 公式和取数绑定优先使用 col_id 而非列下标。
 */
export interface NoteSemanticColumn {
  /** 列唯一标识，如 closing_balance */
  col_id: string
  /** 列显示名称，如 期末余额 */
  label?: string
  /** 数据来源：workpaper | formula | manual | prior_note 等 */
  source?: string | null
  /** 金额角色：opening | closing | current | prior 等 */
  amount_role?: string | null
}

/** 单元格元数据 */
export interface NoteCellMeta {
  /** 绑定注册表 ID */
  binding_id?: string | null
  /** 公式 ID */
  formula_id?: string | null
  /** 数据来源标识 */
  source?: string | null
}

/**
 * 行语义定义
 * Requirements 3.2: 支持 row_id + row_type。
 * Requirements 3.5: 保持 values[] 兼容，不破坏旧代码读取。
 */
export interface NoteSemanticRow {
  /** 行唯一标识，如 within_1_year */
  row_id: string
  /** 行类型 */
  row_type: NoteRowType
  /** 行显示名称，如 1年以内 */
  label?: string
  /** 单元格值数组，保持兼容 */
  values?: any[]
  /** 单元格模式映射，如 { "0": "auto" } */
  _cell_modes?: Record<string, string> | null
  /** 单元格元数据映射 */
  _cell_meta?: Record<string, NoteCellMeta> | null
}

/**
 * 表语义定义
 * Requirements 3.1: 支持 table_id 区分同一章节内多张表。
 */
export interface NoteSemanticTable {
  /** 表唯一标识，如 aging_analysis */
  table_id: string
  /** 表显示名称，如 账龄分析 */
  name?: string
  /** 列语义定义列表 */
  columns?: NoteSemanticColumn[]
  /** 行语义定义列表 */
  rows?: NoteSemanticRow[]
}

/**
 * 章节语义元数据（_semantic 块）
 * 存储在 table_data._semantic 中。
 */
export interface NoteSemanticMeta {
  /** 章节 ID */
  section_id: string
  /** 语义章节 ID，用于跨模板版本映射 */
  semantic_section_id: string
  /** 模板变体：soe_standalone | soe_consolidated | listed_standalone | listed_consolidated */
  variant?: string | null
  /** 范围：standalone | consolidated | both */
  scope?: string | null
}

/**
 * 会计政策条款定义（_policy_clauses 数组元素）
 * Requirements 1.1: 条款化结构。
 */
export interface NotePolicyClause {
  /** 条款唯一标识，如 policy_revenue */
  clause_id: string
  /** 条款标题，如 收入确认 */
  title?: string
  /** 条款层级（1=一级标题，2=二级...） */
  level?: number
  /** 本年文本内容 */
  current_text?: string | null
  /** 模板文本内容 */
  template_text?: string | null
  /** 上年文本内容 */
  prior_year_text?: string | null
  /** 条款中使用的变量名列表 */
  variables?: string[]
  /** 差异状态：unchanged | changed | added | removed | unknown */
  diff_status?: string
  /** 确认状态：pending | confirmed | rejected */
  confirm_status?: string
}

/**
 * 附注语义结构 sidecar 顶层容器
 * 存储在 disclosure_notes.table_data 的 sidecar 字段中。
 */
export interface NoteSemanticSidecar {
  /** 章节语义元数据 */
  _semantic?: NoteSemanticMeta | null
  /** 表语义定义列表 */
  _tables?: NoteSemanticTable[]
  /** 会计政策条款列表 */
  _policy_clauses?: NotePolicyClause[]
}
