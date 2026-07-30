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
  /** 中文列头，取自组件既有源对齐定义（如 '账面余额'） */
  label: string
  /** true=标签列（承载行名 label），投影为第一列 */
  is_label?: boolean
  align?: 'left' | 'center' | 'right'
  /** 渲染格式提示（可选） */
  format?: 'amount' | 'percent' | 'text'
  /** 分组父表头（如 '期末余额'），相邻且同 group 的列在渲染时合并为两级表头 */
  group?: string
  /**
   * 显式声明「本表为单级表头」→ 后端跳过 `_infer_groups_from_headers` 前缀推断。
   *
   * 不声明时，后端会对 ≥4 列且共享前缀的 headers 反猜父表头（如把 `本期增加`/`本期减少`
   * 归到凭空的「本期」下），对源模板本就是单行表头的表属于误加。标在任意一列
   * （建议标签列）即对整表生效。
   */
  flat?: boolean
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
      // group 必须透传：后端 _extract_column_groups 据此产出 _column_groups（两级表头）
      ...(d.group ? { group: d.group } : {}),
      // flat 必须透传：显式单级声明，抑制后端前缀推断
      ...(d.flat ? { flat: true } : {}),
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
 * 归一子表值为行数组（与后端 `normalize_sub_table_data` 同规则）。
 * 容错表对象包装 `{rows:[...]}`（投影结果被回写），取不出行则返回 null。
 */
function normalizeSubTableRows(value: any): any[] | null {
  if (Array.isArray(value)) return value
  if (value && typeof value === 'object' && Array.isArray(value.rows)) return value.rows
  return null
}

/**
 * 投影态行（label/values[]/is_total）→ 业务键行（与后端 `_inverse_project_row` 同规则）。
 * 无 values 数组或无列头声明时原样返回；已有业务键不被覆盖。
 */
function inverseProjectRow(row: any, labelDef: ColumnDef | null, valueDefs: ColumnDef[]): any {
  if (!Array.isArray(row?.values) || (!labelDef && valueDefs.length === 0)) return row
  const { values, ...rest } = row
  const out: Record<string, any> = { ...rest }
  const labelKey = labelDef?.key
  if (labelKey && labelKey !== 'label' && !(labelKey in out) && 'label' in out) {
    out[labelKey] = out.label
  }
  valueDefs.forEach((d, i) => {
    if (d.key && !(d.key in out)) out[d.key] = values[i] ?? null
  })
  return out
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
    const rawRows = normalizeSubTableRows(sub[key])
    if (!rawRows) continue

    const defsRaw = colsMap[key]
    const defs: ColumnDef[] = Array.isArray(defsRaw)
      ? defsRaw.filter(d => d && typeof d.key === 'string' && d.key.length > 0)
      : []

    if (defs.length === 0) {
      // P8 / 降级：无列头 → 不用英文字段键当 header
      const hasLabel = rawRows.some((r: any) => r && typeof r === 'object' && 'label' in r)
      tables.push({
        name: key,
        headers: hasLabel ? ['项目'] : [],
        columns: [],
        rows: rawRows
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
    // 逆投影：位置化 values 行还原为业务键行，再走统一取键逻辑
    const rows = rawRows
      .filter((r: any) => r && typeof r === 'object')
      .map((r: any) => inverseProjectRow(r, labelDef, valueDefs))

    tables.push({
      name: key,
      headers,
      columns: defs,
      rows: rows
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

/**
 * legacy 单表表头补齐（前端兜底）
 *
 * 历史生成的部分附注 `table_data` 出现 `headers: []`（空）但 `rows` 非空——
 * 每行携 `values` + `_cell_meta[colIdx].semantic` 列语义却无表头，导致 el-table
 * 零列坍缩（"附注表格只有一行"）。后端 `note_header_projector` 已在 get_note_detail
 * 读时补齐；本函数为前端兜底（后端未生效/其它加载路径时保证渲染一致）。
 *
 * 语义→中文标签与后端 `note_header_projector._SEMANTIC_LABEL` 保持一致，禁止漂移。
 */
const LEGACY_HEADER_SEMANTIC_LABEL: Record<string, string> = {
  closing_balance: '期末余额',
  opening_balance: '期初余额',
  prior_year_value: '上年年末余额',
  current_year_increase: '本期增加',
  current_year_decrease: '本期减少',
  current_year_provision: '本期计提',
  current_period_acquisition: '本期购置',
  current_period_disposal: '本期处置',
  current_period_writeoff: '本期核销',
  current_period_recover: '本期收回',
  original_value: '原值',
  accumulated_depreciation: '累计折旧/摊销',
  impairment_provision: '减值准备',
  carrying_value: '账面价值',
  provision_ratio: '计提比例',
  cost: '成本',
  fair_value: '公允价值',
  category_subtotal: '小计',
  aging_bucket_within_1y: '1年以内',
  aging_bucket_1_2y: '1-2年',
  aging_bucket_2_3y: '2-3年',
  aging_bucket_3_5y: '3-5年',
  aging_bucket_over_5y: '5年以上',
  // manual_text / formula_result → 空标签（列仍渲染）
}

function valueLen(row: any): number {
  return row && typeof row === 'object' && Array.isArray(row.values) ? row.values.length : 0
}

function semanticForCol(rows: any[], colIdx: number): string | null {
  const key = String(colIdx)
  for (const r of rows) {
    if (!r || typeof r !== 'object') continue
    const cm = r._cell_meta
    if (!cm || typeof cm !== 'object') continue
    const meta = cm[key]
    if (meta && typeof meta === 'object' && typeof meta.semantic === 'string' && meta.semantic) {
      return meta.semantic
    }
  }
  return null
}

/**
 * legacy 单表 `headers` 为空时从行 `_cell_meta` 语义派生表头。
 * @returns null=不适用（沿用原 headers）；string[]=派生表头（首列"项目"+各值列语义标签）
 */
export function deriveLegacyTableHeaders(tableData: Record<string, any> | null | undefined): string[] | null {
  if (!tableData || typeof tableData !== 'object' || Array.isArray(tableData)) return null
  if (tableData._tables) return null // 多表已投影
  const rows = tableData.rows
  if (!Array.isArray(rows) || rows.length === 0) return null
  const headers = tableData.headers
  if (Array.isArray(headers) && headers.length > 0) return null // 已有表头

  const numValueCols = rows.reduce((m: number, r: any) => Math.max(m, valueLen(r)), 0)
  if (numValueCols === 0) {
    const hasLabel = rows.some((r: any) => r && typeof r === 'object' && 'label' in r)
    return hasLabel ? ['项目'] : null
  }
  const derived = ['项目']
  for (let i = 0; i < numValueCols; i++) {
    const sem = semanticForCol(rows, i)
    derived.push(LEGACY_HEADER_SEMANTIC_LABEL[sem ?? ''] ?? '')
  }
  return derived
}
