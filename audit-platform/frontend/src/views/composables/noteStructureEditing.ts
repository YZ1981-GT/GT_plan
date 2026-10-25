/**
 * 附注表格结构编辑的源对象解析。
 *
 * 投影表只用于渲染，结构编辑必须拿到稳定的 raw 对象；跨源续表和业务键
 * sub_table_data 没有安全的一对一结构映射，统一禁用，避免把投影副本误保存。
 */

const WORKPAPER_SOURCES = new Set(['workpaper', 'workpaper_html'])

export interface NoteStructureEditState {
  table: any | null
  reason: string | null
}

export function resolveNoteStructureEditState(
  tableData: any,
  projectedTable: any,
): NoteStructureEditState {
  if (!tableData || typeof tableData !== 'object' || !projectedTable) {
    return { table: null, reason: '当前没有可编辑的表格结构' }
  }

  const source = String(tableData._source || '')
  const sourceIndexes = Array.isArray(projectedTable._sourceTableIndexes)
    ? projectedTable._sourceTableIndexes.filter((value: unknown) => Number.isInteger(value))
    : []
  const sourceKey = typeof projectedTable._source_sub_table_key === 'string'
    ? projectedTable._source_sub_table_key
    : ''
  const hasRawSubTables = Object.prototype.hasOwnProperty.call(tableData, 'sub_table_data')

  if (WORKPAPER_SOURCES.has(source) && (hasRawSubTables || sourceKey)) {
    return {
      table: null,
      reason: '底稿来源的业务键子表暂不支持结构编辑，请使用表样编辑器调整结构',
    }
  }

  if (sourceIndexes.length === 0) {
    return {
      table: null,
      reason: '当前表格缺少稳定的源结构，暂不支持直接编辑',
    }
  }

  if (sourceIndexes.length > 1) {
    return {
      table: null,
      reason: '合并续表涉及多个源表，暂不支持结构编辑，请分别调整源表结构',
    }
  }

  const sourceIndex = sourceIndexes[0]
  if (Array.isArray(tableData._tables) && tableData._tables[sourceIndex]) {
    const table = tableData._tables[sourceIndex]
    if (Array.isArray(table.headers) && Array.isArray(table.rows)) {
      return { table, reason: null }
    }
  }

  if (sourceIndex === 0 && Array.isArray(tableData.headers) && Array.isArray(tableData.rows)) {
    return { table: tableData, reason: null }
  }

  return {
    table: null,
    reason: '当前表格缺少稳定的源结构，暂不支持直接编辑',
  }
}
