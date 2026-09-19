/**
 * 账表导入列映射契约类型定义
 *
 * 与后端 `confirmed_mapping_dto.py` 保持一致。
 * pipeline 只消费 `mapping_entries[]` 格式，以 `column_index` 为主键取值。
 *
 * @see design.md §4 / requirements 需求 4
 */

/** 表类型枚举 */
export type TableType = 'balance' | 'ledger' | 'aux_balance' | 'aux_ledger' | 'account_chart'

/**
 * 单列映射条目
 *
 * 以 `column_index` 作为主键，pipeline 按此从原始行取值。
 * `canonical_header` 保证唯一（重复原始表头如多个"借方"通过 `#N` 后缀区分）。
 */
export interface MappingEntry {
  /** 0-based 列位置 */
  column_index: number
  /** 原始表头文本 */
  original_header: string
  /** 去重后唯一表头（如 借方#3） */
  canonical_header: string
  /** 标准字段名（如 debit_amount） */
  standard_field: string
}

/**
 * 前端提交的人工确认列映射 DTO
 *
 * 对应后端 `ConfirmedMappingDTO`。前端 ColumnMappingEditor 确认后提交此结构。
 */
export interface ConfirmedMapping {
  /** detect 阶段的 artifact ID，用于 submit 校验 */
  detection_id?: string
  /** 稳定 sheet 标识，格式 {file_name}:{sheet_name} */
  sheet_key: string
  /** 文件名（含扩展名） */
  file_name: string
  /** Sheet 名称 */
  sheet_name: string
  /** 表类型 */
  table_type: TableType
  /** 列映射条目列表 */
  mapping_entries: MappingEntry[]
  /** 辅助核算维度列索引 */
  aux_dimension_columns?: number[]
  /** 文件指纹（历史映射复用） */
  file_fingerprint?: string
  /** 软件指纹（历史映射复用） */
  software_fingerprint?: string
  /** 是否经人工确认（低置信度 sheet 必须为 true） */
  confirmed_by_user?: boolean
}

/**
 * 生成稳定 sheet key
 *
 * 格式：`{file_name}:{sheet_name}`
 */
export function generateSheetKey(fileName: string, sheetName: string): string {
  return `${fileName}:${sheetName}`
}
