/**
 * useCNoteFormula.ts — C 类附注披露嵌套表公式计算 composable
 *
 * 从 GtCNoteTable.vue 剪切 `cellComputedValue` / `footerTotalColumns` / `footerTotalValue`
 * 三个公式纯函数（原 design §1.3 引用的 ~976-1045 行，Task 1 后实际位于 833-891 行）。
 * 逐字搬运，零行为改变。
 *
 * 注：`footerTotalColumns` 原实现引用 `currentStandardSubClass.value`（按当前准则过滤
 * 合计列），故除 `subTableData` 外还需接收 `currentStandardSubClass` 响应式引用，
 * 以保持 byte-for-byte 行为一致（design 原型签名遗漏了该依赖）。
 *
 * spec: gt-c-note-table-shrink Task 2
 */
import type { Ref } from 'vue'
import type {
  ColumnDef,
  ColumnDefWithKey,
  RowData,
  SubClass,
  SubTableSchema,
} from '../../GtCNoteTable.types'
import { escapeNumber } from '../cnoteHelpers'

export function useCNoteFormula(
  subTableData: Ref<Record<string, RowData[]>>,
  currentStandardSubClass: Ref<SubClass>,
) {
  function cellComputedValue(
    st: SubTableSchema,
    row: RowData,
    col: ColumnDefWithKey,
  ): number | null {
    if (col.render !== 'amount_formula' && col.render !== 'percent_formula') return null
    const formula = col.formula
    if (!formula) return null
    const cols = st.columns ?? {}
    const cellMap = new Map<string, ColumnDef>()
    for (const [cell, c] of Object.entries(cols)) {
      cellMap.set(cell, c)
    }
    const expr = formula
      .replace(/^=/, '')
      .replace(/[A-Z][a-zA-Z_]*/g, (token) => {
        // Try direct cell-letter substitution first (e.g. "B-D")
        const colDef = cellMap.get(token)
        if (colDef) {
          const v = row[colDef.field]
          const n = escapeNumber(v)
          return n == null ? '0' : String(n)
        }
        return '0'
      })
    try {
      // eslint-disable-next-line no-new-func
      const fn = new Function(`return (${expr})`)
      const result = fn()
      if (typeof result === 'number' && isFinite(result)) return result
      return null
    } catch {
      return null
    }
  }

  function footerTotalColumns(st: SubTableSchema): ColumnDef[] {
    const cellList = st.footer_total?.sum_columns ?? []
    const colMap = st.columns ?? {}
    const sub = currentStandardSubClass.value
    const result: ColumnDef[] = []
    for (const cell of cellList) {
      const c = colMap[cell]
      if (!c) continue
      if (c.applicable_to_sub_class && !c.applicable_to_sub_class.includes(sub)) continue
      result.push(c)
    }
    return result
  }

  function footerTotalValue(st: SubTableSchema, col: ColumnDef): number {
    const rows = subTableData.value[st.id] ?? []
    let sum = 0
    for (const row of rows) {
      const n = escapeNumber(row[col.field])
      if (n != null) sum += n
    }
    return sum
  }

  return { cellComputedValue, footerTotalColumns, footerTotalValue }
}
