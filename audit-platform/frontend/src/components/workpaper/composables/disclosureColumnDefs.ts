/**
 * 披露表列头元数据（ColumnDef）+ 客户端兜底投影
 *
 * spec: disclosure-table-sync-convergence — design §Data Models / §Components and Interfaces
 *
 * 列头 label 必须取自各披露组件既有 `<el-table-column label>` / C 类 schema `columns[].label`
 * （对照致同 2025 源模板编制），禁止英文字段键当列头或凭常识杜撰。
 *
 * `projectSubTablesClient` 与后端 `note_sub_table_projector.project_sub_tables` 规则一致，
 * 供过渡期后端未注入 `_tables` 时前端兜底投影，保证渲染一致（Task 6.1）。
 */

export interface ColumnDef {
  /** 对应 sub_table_data 行对象的字段键（如 'end_gross'） */
  key: string
  /** 中文列头，取自组件既有源对齐定义（如 '期末账面余额'） */
  label: string
  /** true=标签列（承载行名 label），投影为第一列 */
  is_label?: boolean
  align?: 'left' | 'center' | 'right'
  /** 渲染格式提示（可选） */
  format?: 'amount' | 'percent' | 'text'
}

export type SubTableColumns = Record<string, ColumnDef[]>

/** 视为"底稿同步来源"的 _source 标识（投影权威来源，与后端一致） */
const WORKPAPER_SOURCES = ['workpaper', 'workpaper_html']

/** 声明助手：过滤非法项，保证每个 ColumnDef 至少含 key。 */
export function defineColumns(defs: Array<Partial<ColumnDef> & { key: string; label: string }>): ColumnDef[] {
  return defs
    .filter(d => d && typeof d.key === 'string' && d.key.length > 0)
    .map(d => ({
      key: d.key,
      label: String(d.label ?? ''),
      ...(d.is_label ? { is_label: true } : {}),
      ...(d.align ? { align: d.align } : {}),
      ...(d.format ? { format: d.format } : {}),
    }))
}

export interface ProjectedTable {
  name: string
  headers: string[]
  columns: ColumnDef[]
  rows: Array<{ label: unknown; values: unknown[]; is_total: boolean }>
  _source_sub_table_key: string
  _needs_columns?: boolean
}

function isMetaKey(key: string): boolean {
  return String(key).startsWith('_')
}

function pickLabelDef(defs: ColumnDef[]): ColumnDef | null {
  return defs.find(d => d && d.is_label) ?? defs.find(d => !!d) ?? null
}

/**
 * 客户端兜底投影：sub_table_data + _sub_table_columns → 可渲染 _tables[]。
 * 规则与后端 project_sub_tables 完全一致（P1~P8）。
 *
 * @returns null=非 workpaper 来源（沿用既有 _tables/rows）；数组=投影结果（可空）
 */
export function projectSubTablesClient(tableData: Record<string, any> | null | undefined): ProjectedTable[] | null {
  if (!tableData || typeof tableData !== 'object' || Array.isArray(tableData)) return null
  const source = tableData._source
  if (!WORKPAPER_SOURCES.includes(source)) return null // P7

  const sub = tableData.sub_table_data
  if (!sub || typeof sub !== 'object' || Array.isArray(sub)) return []
  const keys = Object.keys(sub)
  if (keys.length === 0) return []

  const colsMap = (tableData._sub_table_columns && typeof tableData._sub_table_columns === 'object')
    ? tableData._sub_table_columns as SubTableColumns
    : {}

  const tables: ProjectedTable[] = []
  for (const key of keys) { // 保持键序（P6）
    if (isMetaKey(key)) continue
    const rows = sub[key]
    if (!Array.isArray(rows)) continue

    const defsRaw = colsMap[key]
    const defs: ColumnDef[] = Array.isArray(defsRaw)
      ? defsRaw.filter(d => d && typeof d.key === 'string' && d.key.length > 0)
      : []

    if (defs.length === 0) {
      // P8 / 降级：无列头 → 不用英文字段键当 header
      const hasLabel = rows.some((r: any) => r && typeof r === 'object' && 'label' in r)
      tables.push({
        name: key,
        headers: hasLabel ? ['项目'] : [],
        columns: [],
        rows: rows
          .filter((r: any) => r && typeof r === 'object')
          .map((r: any) => ({ label: r.label ?? '', values: [], is_total: !!r.is_total })),
        _source_sub_table_key: key,
        _needs_columns: true,
      })
      continue
    }

    const labelDef = pickLabelDef(defs)
    const labelKey = labelDef?.key
    const valueDefs = defs.filter(d => d !== labelDef)
    const headers = [String(labelDef?.label ?? ''), ...valueDefs.map(d => String(d.label ?? ''))]

    tables.push({
      name: key,
      headers,
      columns: defs,
      rows: rows
        .filter((r: any) => r && typeof r === 'object')
        .map((r: any) => {
          let labelVal = labelKey ? (r[labelKey] ?? '') : ''
          // 兜底：标签列键值缺失时回退通用 label（合计/小计行常用 label 而非业务键）
          if ((labelVal === '' || labelVal == null) && labelKey !== 'label') labelVal = r.label ?? labelVal
          return {
            label: labelVal,
            values: valueDefs.map(d => r[d.key] ?? null), // 缺字段→null(P3)，额外字段忽略(P4)
            is_total: !!r.is_total, // P5
          }
        }),
      _source_sub_table_key: key,
    })
  }
  return tables
}
