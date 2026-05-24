/**
 * CustomQueryTemplateConfig — 模板 config JSONB 完整 schema
 * Validates: Requirements 15.3 (advanced-query-enhancements-p1p2)
 *
 * 保存时从 SheetCellRangePicker 选区状态序列化，加载时反序列化还原所有控件状态。
 */
export interface CustomQueryTemplateConfig {
  /** 项目 ID（可选，模板浏览模式可缺省） */
  project_id?: string | null
  /** 审计年度 */
  year?: number | null
  /** 数据源 URI（必填），如 workpaper:D2|审定表D2-1 */
  source: string
  /** Sheet 名称 */
  sheet_name?: string | null
  /** 选区表达式，如 A1:B10,C1:C5 */
  cell_range?: string | null
  /** 文本筛选 */
  filter_text?: string | null
  /** 结构化条件 */
  conditions?: Array<{ field: string; op: string; value: any }>
  /** 已选列 */
  selected_columns?: string[]
  /** 可用列（保存时快照） */
  available_columns?: string[]
  /** 每页行数 */
  page_size?: 50 | 100 | 200 | 500
  /** 排序字段 */
  sort_field?: string | null
  /** 排序方向 */
  sort_order?: 'asc' | 'desc'
}
