/**
 * useNoteTableProjection — 附注多表投影 + 两级分组表头解析
 *
 * 从 `DisclosureEditor.vue` 抽出（该宿主 3278 行 / HARD_CAPS ceiling 1800，
 * 见 `backend/scripts/check/check_file_size.py`）。**纯派生**：只从 `currentNote`
 * 读，不写任何状态，逻辑逐字搬迁未做行为改动。
 *
 * 三层兜底顺序（顺序即优先级，不可调换）：
 *   1. `table_data._tables`         —— 新格式，后端已为 workpaper 来源注入投影表
 *   2. `projectSubTablesClient(td)` —— 客户端兜底投影（sub_table_data + _sub_table_columns）
 *   3. `table_data.rows`            —— 旧格式单表
 *
 * 🔴 续表合并规则（渲染期合并，不改库内结构）：表名以「续」开头或含「（续：」的表，
 * 把其列并入**同名主表**。三条例外必须保留：
 *   · 续表自带独立列定义（`_column_groups` / `columns`）⇒ 它是完整独立子表，不合并
 *   · 找不到对应主表 ⇒ 作为独立 tab 保留，**不能**默认并到上一张（否则串表）
 *   · 续表首列通常是重复的标签列（与主表首列同名 / 「类别」/「名称」）⇒ 跳过该列
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'

export interface UseNoteTableProjectionOptions {
  currentNote: Ref<any> | ComputedRef<any>
  /** 客户端兜底投影（sub_table_data → 表数组） */
  projectSubTablesClient: (td: any) => any[] | null
  /** 旧格式表头推导 */
  deriveLegacyTableHeaders: (td: any) => string[] | null
}

export type FlatCol = { type: 'flat'; headerIdx: number; label: string }
export type GroupedCol = {
  type: 'grouped'
  group: string
  children: Array<{ headerIdx: number; label: string }>
}
export type NoteTableCol = FlatCol | GroupedCol

export function useNoteTableProjection(options: UseNoteTableProjectionOptions) {
  const { currentNote, projectSubTablesClient, deriveLegacyTableHeaders } = options

  /** 当前激活的表 Tab 下标（字符串，el-tabs 约定） */
  const activeTableTab = ref('0')

  const currentNoteTables = computed<any[]>(() => {
    if (!currentNote.value?.table_data) return []
    const td = currentNote.value.table_data
    // workpaper 的 sub_table_data 是持久化真源。只要 raw 字段存在，就优先从
    // raw 重新投影，避免保存前/单元格即时反写后继续显示后端注入的旧 `_tables`。
    // `_tables` 只作为服务端附加元数据来源，不覆盖 raw 的 rows/headers/sidecar。
    const isWorkpaperSource = td._source === 'workpaper' || td._source === 'workpaper_html'
    const hasRawSubTables = isWorkpaperSource && Object.prototype.hasOwnProperty.call(td, 'sub_table_data')
    const clientProjected = hasRawSubTables ? projectSubTablesClient(td) : null
    let rawTables: any[] | null = null
    if (Array.isArray(clientProjected)) {
      const serverTables = Array.isArray(td._tables) ? td._tables : []
      const serverByKey = new Map(serverTables.map((table: any) => [
        table?._source_sub_table_key || table?.name,
        table,
      ]))
      rawTables = clientProjected.map((table: any) => {
        const serverTable = serverByKey.get(table?._source_sub_table_key || table?.name)
        const metadata = serverTable && typeof serverTable === 'object' ? { ...serverTable } : {}
        // 导出开关以 raw 顶层清单为准，不能让旧投影的 false 残留覆盖已恢复的状态。
        delete metadata.export_enabled
        return { ...metadata, ...table }
      })
    }
    if (!rawTables && td._tables && Array.isArray(td._tables) && td._tables.length > 0) {
      rawTables = td._tables
    }
    if (!rawTables) {
      // 客户端兜底投影：workpaper 来源的 sub_table_data + _sub_table_columns
      if (clientProjected && clientProjected.length > 0) {
        rawTables = clientProjected
      }
    }
    if (!rawTables) {
      // 旧格式：单表格
      if (td.rows) {
        const headers = (Array.isArray(td.headers) && td.headers.length > 0)
          ? td.headers
          : (deriveLegacyTableHeaders(td) || td.headers || [])
        rawTables = [{ name: currentNote.value.section_title, headers, rows: td.rows }]
      } else {
        return []
      }
    }

    // 渲染时合并续表：表名以"续"开头 或 含"（续："的表，把其列合并到同名主表
    //
    // 🔴 必须先深拷贝再合并（2026-09-28 修，原实现是真实缺陷）：
    // 原码 `merged.push(t)` 推的是**源对象引用**，随后 `prev.headers = [...]` /
    // `prev.rows = prevRows` 直接写在 `currentNote.table_data._tables` 上。
    // 后果 = computed 改写自己的响应式依赖 ⇒ 每次重算把续表列再追加一遍。
    // 实测（探针）：首次求值后源 headers 由 ['项目','期末余额'] 变成
    // ['项目','期末余额','期初余额']；第二次求值再变成 [... ,'期初余额','期初余额']。
    // 触发路径：有续表的章节里改一次单元格 → 依赖变化 → 重算 → 列重复。
    // 故这里对参与合并的表做**逐层拷贝**（表壳 + headers 数组 + 每行 + 每行 values），
    // 合并只发生在副本上，源数据只读。
    const sourceRowRef = (sourceIndex: number, rowIndex: number, sourceSubTableKey?: string) => ({
      tableIndex: sourceIndex,
      rowIndex,
      ...(sourceSubTableKey ? { sourceSubTableKey } : {}),
    })
    const cloneRefs = (value: any): any => {
      if (!Array.isArray(value)) return value
      return value.map((item: any) => Array.isArray(item)
        ? item.map((nested: any) => nested && typeof nested === 'object' ? { ...nested } : nested)
        : (item && typeof item === 'object' ? { ...item } : item))
    }
    const enrichSourceCoordinates = (table: any, sourceIndex: number, sourceKey?: string) => {
      const rows = Array.isArray(table?.rows) ? table.rows : []
      const valueCount = Math.max(0, (Array.isArray(table?.headers) ? table.headers.length : 0) - 1)
      const sourceIndexes = Array.isArray(table?._source_row_indexes)
        ? table._source_row_indexes
        : rows.map((_row: any, rowIndex: number) => rowIndex)
      const rowRefs = Array.isArray(table?._sourceRowRefs)
        ? cloneRefs(table._sourceRowRefs)
        : rows.map((_row: any, rowIndex: number) => [sourceRowRef(sourceIndex, sourceIndexes[rowIndex], sourceKey)])
      const labelRefs = Array.isArray(table?._sourceLabelRefs)
        ? table._sourceLabelRefs.map((ref: any) => ref && { ...ref })
        : rows.map((_row: any, rowIndex: number) => sourceRowRef(sourceIndex, sourceIndexes[rowIndex], sourceKey))
      const valueDefs = Array.isArray(table?.columns)
        ? table.columns.filter((def: any) => def && !def.is_label)
        : []
      const columnRefs = Array.isArray(table?._sourceColumnRefs)
        ? table._sourceColumnRefs.map((ref: any) => ref && { ...ref })
        : Array.from({ length: valueCount }, (_unused, valueIndex) => ({
            tableIndex: sourceIndex,
            valueIndex,
            ...(sourceKey ? {
              sourceSubTableKey: sourceKey,
              key: valueDefs[valueIndex]?.key,
            } : {}),
          }))
      const cellRefs = Array.isArray(table?._sourceCellRefs)
        ? cloneRefs(table._sourceCellRefs)
        : rows.map((_row: any, rowIndex: number) => columnRefs.map((column: any) => ({
          row: sourceRowRef(sourceIndex, sourceIndexes[rowIndex], sourceKey),
          column: { ...column },
        })))
      return {
        _sourceRowRefs: rowRefs,
        _sourceLabelRefs: labelRefs,
        _sourceColumnRefs: columnRefs,
        _sourceCellRefs: cellRefs,
        _sourceTableIndexes: Array.isArray(table?._sourceTableIndexes) ? [...table._sourceTableIndexes] : [sourceIndex],
        _sourceTableKeys: Array.isArray(table?._sourceTableKeys)
          ? [...table._sourceTableKeys]
          : (sourceKey ? [sourceKey] : []),
      }
    }

    const cloneTable = (t: any, sourceIndex: number) => ({
      ...t,
      ...enrichSourceCoordinates(t, sourceIndex, t?._source_sub_table_key),
      _sourceTableIndexes: Array.isArray(t?._sourceTableIndexes) ? [...t._sourceTableIndexes] : [sourceIndex],
      _sourceTableKeys: Array.isArray(t?._sourceTableKeys)
        ? [...t._sourceTableKeys]
        : (t?._source_sub_table_key ? [t._source_sub_table_key] : []),
      headers: Array.isArray(t?.headers) ? [...t.headers] : t?.headers,
      rows: Array.isArray(t?.rows)
        ? t.rows.map((r: any) => ({
            ...r,
            values: Array.isArray(r?.values) ? [...r.values] : r?.values,
          }))
        : t?.rows,
    })

    const merged: any[] = []
    for (let i = 0; i < rawTables.length; i++) {
      const t = rawTables[i]
      const name = (t.name || '') as string
      // 判定是否为续表：以"续"开头（模板格式）或含"（续："（sub_table_data 格式）
      const isContinuation = name.startsWith('续') || name.includes('（续：') || name.includes('(续：')
      if (isContinuation && merged.length > 0) {
        // 有独立列定义（_column_groups 或 columns）的续表不合并——它是完整独立子表
        if (t._column_groups || (t.columns && Array.isArray(t.columns) && t.columns.length > 0)) {
          merged.push(cloneTable(t, i))
          continue
        }
        // 找到对应主表（续表名通常含主表名前缀）
        let prevIdx = merged.length - 1
        // 尝试精确匹配：续表名去掉"（续：...）"后 === 某已有表名
        const baseName = name.replace(/[（(]续[：:].*$/, '').trim()
        if (baseName) {
          const matchIdx = merged.findIndex((m) => (m.name || '').trim() === baseName)
          if (matchIdx >= 0) prevIdx = matchIdx
          else {
            // 找不到对应主表，作为独立 tab 保留不合并
            merged.push(cloneTable(t, i))
            continue
          }
        }
        const prev = merged[prevIdx]
        const prevHeaders: string[] = prev.headers || []
        const nextHeaders: string[] = t.headers || []
        // 续表 headers 第一列通常是重复的标签列（类别/名称），跳过
        const skipFirst = nextHeaders.length > 0 && prevHeaders.length > 0 &&
          (nextHeaders[0] === prevHeaders[0] || nextHeaders[0] === '类别' || nextHeaders[0] === '名称')
        const appendHeaders = skipFirst ? nextHeaders.slice(1) : nextHeaders
        prev.headers = [...prevHeaders, ...appendHeaders]

        const prevRows: any[] = prev.rows || []
        const nextRows: any[] = t.rows || []
        const prevRowRefs: Array<Array<any>> = prev._sourceRowRefs || []
        const nextRowRefs: Array<Array<any>> = t._sourceRowRefs || []
        const prevLabelRefs: Array<any> = prev._sourceLabelRefs || []
        const nextLabelRefs: Array<any> = t._sourceLabelRefs || []
        const prevCellRefs: Array<Array<any>> = prev._sourceCellRefs || []
        const nextCellRefs: Array<Array<any>> = t._sourceCellRefs || []
        const nextColumnRefs: Array<any> = t._sourceColumnRefs || []
        const nextValueStart = 0
        const appendValueCount = appendHeaders.length
        // headers 含标签列，但 rows.values 与两类 value sidecar 不含标签列；
        // 因此 skipFirst 只影响表头，不能对业务值坐标再做 slice(1)。
        const appendColumnRefs = Array.from({ length: appendValueCount }, (_unused, offset) =>
          nextColumnRefs[offset + nextValueStart] ?? null,
        )
        const appendCellCount = appendValueCount
        const previousValueCount = Math.max(0, prevHeaders.length - 1)
        for (let ri = 0; ri < Math.max(prevRows.length, nextRows.length); ri++) {
          const hasPrev = ri < prevRows.length
          const hasNext = ri < nextRows.length
          const prevRow = hasPrev ? prevRows[ri] : { label: '', values: [] }
          const nextRow = hasNext ? nextRows[ri] : { values: [] }
          const nextVals = Array.isArray(nextRow.values) ? nextRow.values : []
          const appendVals = nextVals.slice(nextValueStart, nextValueStart + appendCellCount)
          if (!Array.isArray(prevRow.values)) prevRow.values = []
          // 续表多出新行时，先占住主表列位，不能让续表值左移到主表列。
          while (prevRow.values.length < previousValueCount) prevRow.values.push(null)
          while (appendVals.length < appendCellCount) appendVals.push(null)
          prevRow.values = [...prevRow.values, ...appendVals]
          if (!hasPrev) prevRows.push(prevRow)

          const prevRefs = hasPrev && Array.isArray(prevRowRefs[ri]) ? prevRowRefs[ri] : []
          const nextRefs = Array.isArray(nextRowRefs[ri]) ? nextRowRefs[ri] : []
          prevRowRefs[ri] = [...prevRefs, ...(hasNext ? nextRefs : [])]
          if (!hasPrev) prevLabelRefs[ri] = null
          else if (!prevLabelRefs[ri] && hasNext) prevLabelRefs[ri] = nextLabelRefs[ri] || null
          const prevCells = hasPrev && Array.isArray(prevCellRefs[ri]) ? prevCellRefs[ri] : []
          const nextCells = Array.isArray(nextCellRefs[ri]) ? nextCellRefs[ri] : []
          const appendCells = Array.from({ length: appendCellCount }, (_unused, offset) =>
            nextCells[offset + nextValueStart] ?? null,
          )
          while (prevCells.length < previousValueCount) prevCells.push(null)
          prevCellRefs[ri] = [...prevCells, ...(hasNext ? appendCells : Array(appendCellCount).fill(null))]
        }
        prev.rows = prevRows
        prev._sourceRowRefs = prevRowRefs
        prev._sourceLabelRefs = prevLabelRefs
        const previousColumnRefs = Array.from({ length: previousValueCount }, (_unused, valueIndex) =>
          (Array.isArray(prev._sourceColumnRefs) ? prev._sourceColumnRefs[valueIndex] : null) ?? null,
        )
        prev._sourceColumnRefs = [...previousColumnRefs, ...appendColumnRefs]
        prev._sourceCellRefs = prevCellRefs
        prev._sourceTableIndexes = Array.from(new Set([
          ...(Array.isArray(prev._sourceTableIndexes) ? prev._sourceTableIndexes : []),
          ...(Array.isArray(t._sourceTableIndexes) ? t._sourceTableIndexes : [i]),
        ]))
        prev._sourceTableKeys = Array.from(new Set([
          ...(Array.isArray(prev._sourceTableKeys) ? prev._sourceTableKeys : []),
          ...(Array.isArray(t._sourceTableKeys) ? t._sourceTableKeys : []),
        ]))
      } else {
        merged.push(cloneTable(t, i))
      }
    }
    return merged
  })

  /**
   * 把后端/URL 使用的原始 table_index 映射到投影后的 el-tabs 下标。
   * 续表合并后多个源下标可能共同指向同一张投影表；所有非法值统一回退第 0 张。
   */
  const resolveProjectedTableIndex = (tableIndex: unknown): number => {
    let sourceIndex: number
    if (typeof tableIndex === 'number') {
      sourceIndex = tableIndex
    } else if (typeof tableIndex === 'string' && tableIndex.trim()) {
      sourceIndex = Number(tableIndex)
    } else {
      return 0
    }
    if (!Number.isInteger(sourceIndex) || sourceIndex < 0) return 0

    const projectedIndex = currentNoteTables.value.findIndex((table) =>
      Array.isArray(table?._sourceTableIndexes) && table._sourceTableIndexes.includes(sourceIndex),
    )
    return projectedIndex >= 0 ? projectedIndex : 0
  }

  const activeTableData = computed<any>(() => {
    const idx = parseInt(activeTableTab.value) || 0
    return currentNoteTables.value[idx] || currentNoteTables.value[0] || null
  })

  /**
   * 解析当前表的列结构，支持两级分组表头（el-table-column 嵌套）。
   *
   * 返回 `null` 表示**无分组信息 ⇒ 调用方走旧的扁平列逻辑**（不是"无列"）。
   * 这个 null 语义是模板 `v-if` 的分支依据，不可改成空数组。
   */
  const activeTableColumns = computed<NoteTableCol[] | null>(() => {
    const table = activeTableData.value
    if (!table?.headers?.length) return []
    const headers = table.headers as string[]
    const groups: Array<{ group: string; start: number; span: number }> | null =
      (table as any)?._column_groups ?? null

    if (!groups || groups.length === 0) {
      // 无分组信息 → 全部扁平列（走旧逻辑兼容）
      return null
    }

    const result: NoteTableCol[] = []
    // 标记哪些索引被分组占用
    const grouped = new Set<number>()
    for (const g of groups) {
      for (let i = g.start; i < g.start + g.span; i++) grouped.add(i)
    }

    for (let i = 0; i < headers.length; i++) {
      if (grouped.has(i)) {
        // 找到对应的 group 定义
        const g = groups.find((gg) => gg.start === i)
        if (g) {
          const children: Array<{ headerIdx: number; label: string }> = []
          for (let j = g.start; j < g.start + g.span && j < headers.length; j++) {
            children.push({ headerIdx: j, label: headers[j] })
          }
          result.push({ type: 'grouped', group: g.group, children })
          i = g.start + g.span - 1 // 跳到分组末尾
        }
      } else {
        result.push({ type: 'flat', headerIdx: i, label: headers[i] })
      }
    }
    return result
  })

  return {
    activeTableTab,
    currentNoteTables,
    activeTableData,
    activeTableColumns,
    resolveProjectedTableIndex,
  }
}
