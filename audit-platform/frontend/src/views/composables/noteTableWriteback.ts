/**
 * 附注投影编辑反写。
 *
 * `_tables` 对 workpaper 来源只是读时投影；真正保存的数据仍是
 * `sub_table_data`。本模块只按投影携带的源坐标写 raw，不按显示行号猜源行。
 */

export const WORKPAPER_SOURCES = new Set(['workpaper', 'workpaper_html'])
export const EXPORT_DISABLED_SUB_TABLES_KEY = '_export_disabled_sub_tables'

export interface SourceRowRef {
  tableIndex: number
  rowIndex: number
  sourceSubTableKey?: string
}

export interface SourceColumnRef {
  tableIndex: number
  valueIndex: number
  key?: string
  sourceSubTableKey?: string
}

export interface SourceCellRef {
  row: SourceRowRef
  column: SourceColumnRef
}

export class NoteTableWritebackError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'NoteTableWritebackError'
  }
}

export function cloneNoteTableValue<T>(value: T): T {
  if (Array.isArray(value)) return value.map(item => cloneNoteTableValue(item)) as T
  if (value && typeof value === 'object') {
    const out: Record<string, any> = {}
    for (const [key, item] of Object.entries(value as Record<string, any>)) {
      out[key] = cloneNoteTableValue(item)
    }
    return out as T
  }
  return value
}

function rawRows(tableData: Record<string, any>, key: string): any[] | null {
  const sub = tableData.sub_table_data
  const value = sub && typeof sub === 'object' ? sub[key] : undefined
  if (Array.isArray(value)) return value
  if (value && typeof value === 'object' && Array.isArray(value.rows)) return value.rows
  return null
}

function columnDefs(tableData: Record<string, any>, key?: string): any[] {
  if (!key) return []
  const defs = tableData._sub_table_columns?.[key]
  return Array.isArray(defs) ? defs : []
}

function labelKey(tableData: Record<string, any>, key?: string): string {
  const labelDef = columnDefs(tableData, key).find(d => d && d.is_label)
  return typeof labelDef?.key === 'string' && labelDef.key ? labelDef.key : 'label'
}

function sourceRowsForRef(tableData: Record<string, any>, ref: SourceRowRef): any[] {
  if (ref.sourceSubTableKey) {
    const rows = rawRows(tableData, ref.sourceSubTableKey)
    if (!rows) throw new NoteTableWritebackError(`无法定位源子表「${ref.sourceSubTableKey}」`)
    return rows
  }
  const tables = tableData._tables
  if (Array.isArray(tables) && tables[ref.tableIndex]) {
    const rows = tables[ref.tableIndex].rows
    if (Array.isArray(rows)) return rows
  }
  if (ref.tableIndex === 0 && Array.isArray(tableData.rows)) return tableData.rows
  throw new NoteTableWritebackError(`无法定位第 ${ref.tableIndex + 1} 张源表`)
}

function setSourceValue(
  tableData: Record<string, any>,
  ref: SourceRowRef,
  valueRef: SourceColumnRef,
  value: unknown,
): void {
  const rows = sourceRowsForRef(tableData, ref)
  const row = rows[ref.rowIndex]
  if (!row || typeof row !== 'object') {
    throw new NoteTableWritebackError(`源表第 ${ref.rowIndex + 1} 行不存在，已拒绝猜测写入位置`)
  }
  if (ref.sourceSubTableKey) {
    if (!valueRef.key) {
      throw new NoteTableWritebackError(`源子表「${ref.sourceSubTableKey}」缺少业务列键，已拒绝写入`)
    }
    row[valueRef.key] = value
    return
  }
  if (!Array.isArray(row.values)) row.values = []
  row.values[valueRef.valueIndex] = value
}

function setSourceLabel(tableData: Record<string, any>, ref: SourceRowRef, value: unknown): void {
  const rows = sourceRowsForRef(tableData, ref)
  const row = rows[ref.rowIndex]
  if (!row || typeof row !== 'object') {
    throw new NoteTableWritebackError(`源表第 ${ref.rowIndex + 1} 行不存在，已拒绝写入标签`)
  }
  row[labelKey(tableData, ref.sourceSubTableKey)] = value
}

function cellRefFor(table: any, rowIndex: number, valueIndex: number): SourceCellRef | null {
  const ref = table?._sourceCellRefs?.[rowIndex]?.[valueIndex]
  return ref && typeof ref === 'object' ? ref as SourceCellRef : null
}

function labelRefFor(table: any, rowIndex: number): SourceRowRef | null {
  const ref = table?._sourceLabelRefs?.[rowIndex]
  return ref && typeof ref === 'object' ? ref as SourceRowRef : null
}

function legacyCellRefFor(table: any, rowIndex: number, valueIndex: number): SourceCellRef | null {
  const rowRef = table?._sourceRowRefs?.[rowIndex]?.find(Boolean)
  if (!rowRef) return null
  return {
    row: rowRef,
    column: table?._sourceColumnRefs?.[valueIndex] || {
      tableIndex: rowRef.tableIndex,
      valueIndex,
    },
  }
}

function requireCellRef(table: any, rowIndex: number, valueIndex: number): SourceCellRef {
  const ref = cellRefFor(table, rowIndex, valueIndex) || legacyCellRefFor(table, rowIndex, valueIndex)
  if (!ref) {
    throw new NoteTableWritebackError(
      `表「${table?.name || '未命名'}」第 ${rowIndex + 1} 行第 ${valueIndex + 1} 列缺少源坐标，已拒绝写入`,
    )
  }
  return ref
}

function requireLabelRef(table: any, rowIndex: number): SourceRowRef {
  const ref = labelRefFor(table, rowIndex) || table?._sourceRowRefs?.[rowIndex]?.find(Boolean)
  if (!ref) {
    throw new NoteTableWritebackError(`表「${table?.name || '未命名'}」第 ${rowIndex + 1} 行缺少标签源坐标，已拒绝写入`)
  }
  return ref as SourceRowRef
}

/** 把一个投影单元格写入 raw，保留 null、0、空字符串。 */
export function applyProjectedCell(
  tableData: Record<string, any>,
  table: any,
  rowIndex: number,
  valueIndex: number,
  value: unknown,
): Record<string, any> {
  const out = cloneNoteTableValue(tableData)
  const ref = requireCellRef(table, rowIndex, valueIndex)
  setSourceValue(out, ref.row, ref.column, value)
  return out
}

/** 把一个投影标签写入 raw。 */
export function applyProjectedLabel(
  tableData: Record<string, any>,
  table: any,
  rowIndex: number,
  value: unknown,
): Record<string, any> {
  const out = cloneNoteTableValue(tableData)
  setSourceLabel(out, requireLabelRef(table, rowIndex), value)
  return out
}

/**
 * 将当前投影表全部提交到 raw。
 * 这是保存前的幂等兜底，确保没有触发 change/blur 的编辑也不会丢失。
 */
export function prepareNoteTableData(
  tableData: Record<string, any> | null | undefined,
  projectedTables: any[] = [],
): Record<string, any> | null | undefined {
  if (!tableData || typeof tableData !== 'object' || Array.isArray(tableData)) return tableData
  const out = cloneNoteTableValue(tableData)
  const isWorkpaper = WORKPAPER_SOURCES.has(String(out._source || ''))

  for (const table of projectedTables) {
    if (!table || !Array.isArray(table.rows)) continue
    const sourceRows = table._sourceRowRefs
    if (!Array.isArray(sourceRows)) {
      if (isWorkpaper) throw new NoteTableWritebackError(`表「${table.name || '未命名'}」缺少完整源坐标，保存已中止`)
      continue
    }
    table.rows.forEach((row: any, rowIndex: number) => {
      const labelRef = labelRefFor(table, rowIndex)
      if (Object.prototype.hasOwnProperty.call(row, 'label')) {
        if (!labelRef) {
          if (isWorkpaper) throw new NoteTableWritebackError(`表「${table.name || '未命名'}」第 ${rowIndex + 1} 行缺少标签源坐标`)
        } else {
          setSourceLabel(out, labelRef, row.label)
        }
      }
      const values = Array.isArray(row.values) ? row.values : []
      values.forEach((value: unknown, valueIndex: number) => {
        const cellRef = cellRefFor(table, rowIndex, valueIndex) || legacyCellRefFor(table, rowIndex, valueIndex)
        // 续表补齐出来的空单元没有源坐标，不能猜测写到任意一张源表。
        if (!cellRef) {
          if (isWorkpaper && value !== null && value !== '') {
            throw new NoteTableWritebackError(`表「${table.name || '未命名'}」第 ${rowIndex + 1} 行第 ${valueIndex + 1} 列缺少源坐标`)
          }
          return
        }
        setSourceValue(out, cellRef.row, cellRef.column, value)
      })
    })
  }

  // `_tables` 是 workpaper 的读时副本，不能作为持久化结构发送回后端。
  if (isWorkpaper) delete out._tables
  return out
}

export function readExportDisabledSubTables(tableData: Record<string, any> | null | undefined): Set<string> {
  const raw = tableData && typeof tableData === 'object'
    ? tableData[EXPORT_DISABLED_SUB_TABLES_KEY]
    : null
  return new Set(Array.isArray(raw) ? raw.filter((item): item is string => typeof item === 'string') : [])
}

export function sourceKeysForProjectedTable(table: any): string[] {
  if (Array.isArray(table?._sourceTableKeys)) {
    return table._sourceTableKeys.filter((key: unknown): key is string => typeof key === 'string' && key.length > 0)
  }
  const key = table?._source_sub_table_key
  return typeof key === 'string' && key ? [key] : []
}
