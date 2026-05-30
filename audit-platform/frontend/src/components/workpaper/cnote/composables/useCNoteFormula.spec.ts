/**
 * useCNoteFormula.spec.ts — C 类附注公式计算 composable 单元测试
 *
 * spec: gt-c-note-table-shrink Task 2
 *
 * 验证（≥5 用例）：
 * 1. amount_formula 单元格求值（cell-letter 替换 + new Function 求值）
 * 2. percent_formula 单元格求值
 * 3. 非公式列 / 无公式 / 非法公式 → null
 * 4. footerTotalColumns 按 currentStandardSubClass 过滤合计列
 * 5. footerTotalValue 跨行求和
 * 6. 空数据返回 0 / null（不抛错）
 * 7. escapeNumber 边界：null / '' / 非数字字符串忽略，数字字符串解析
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useCNoteFormula } from './useCNoteFormula'
import type {
  ColumnDef,
  ColumnDefWithKey,
  RowData,
  SubClass,
  SubTableSchema,
} from '../../GtCNoteTable.types'

// ─── Helpers ──────────────────────────────────────────────────────────────────

function makeColWithKey(cell: string, def: ColumnDef): ColumnDefWithKey {
  return { ...def, _cellKey: cell }
}

/** 构造一张带公式列的子表：B=账面余额 / D=坏账准备 / E=净值(=B-D) */
function makeSubTable(): SubTableSchema {
  return {
    id: 'single_provision',
    title: '单项计提',
    type: 'static_rows',
    columns: {
      B: { field: 'book_balance', label: '账面余额', type: 'number', render: 'amount' },
      D: { field: 'provision', label: '坏账准备', type: 'number', render: 'amount' },
      E: {
        field: 'net_value',
        label: '净值',
        type: 'number',
        render: 'amount_formula',
        formula: '=B-D',
      },
      F: {
        field: 'ratio',
        label: '计提比例',
        type: 'number',
        render: 'percent_formula',
        formula: '=D/B*100',
      },
    },
    footer_total: {
      enabled: true,
      label: '合计',
      sum_columns: ['B', 'D'],
    },
  }
}

// ─── Tests ──────────────────────────────────────────────────────────────────

describe('useCNoteFormula', () => {
  describe('cellComputedValue', () => {
    it('case 1: amount_formula 列求值（=B-D）', () => {
      const subTableData = ref<Record<string, RowData[]>>({})
      const sub = ref<SubClass>('listed')
      const { cellComputedValue } = useCNoteFormula(subTableData, sub)

      const st = makeSubTable()
      const row: RowData = { book_balance: 1000, provision: 250 }
      const col = makeColWithKey('E', st.columns!.E)

      expect(cellComputedValue(st, row, col)).toBe(750)
    })

    it('case 2: percent_formula 列求值（=D/B*100）', () => {
      const subTableData = ref<Record<string, RowData[]>>({})
      const sub = ref<SubClass>('listed')
      const { cellComputedValue } = useCNoteFormula(subTableData, sub)

      const st = makeSubTable()
      const row: RowData = { book_balance: 200, provision: 50 }
      const col = makeColWithKey('F', st.columns!.F)

      expect(cellComputedValue(st, row, col)).toBe(25)
    })

    it('case 3: 非公式列 / 无公式 → null', () => {
      const subTableData = ref<Record<string, RowData[]>>({})
      const sub = ref<SubClass>('listed')
      const { cellComputedValue } = useCNoteFormula(subTableData, sub)

      const st = makeSubTable()
      const row: RowData = { book_balance: 1000, provision: 250 }

      // 非公式列（render=amount）→ null
      expect(cellComputedValue(st, row, makeColWithKey('B', st.columns!.B))).toBeNull()

      // 标记为公式但 formula 缺失 → null
      const noFormulaCol = makeColWithKey('X', {
        field: 'x',
        label: 'X',
        type: 'number',
        render: 'amount_formula',
      })
      expect(cellComputedValue(st, row, noFormulaCol)).toBeNull()
    })

    it('case 4: 非法公式 / 结果非有限数 → null（不抛错）', () => {
      const subTableData = ref<Record<string, RowData[]>>({})
      const sub = ref<SubClass>('listed')
      const { cellComputedValue } = useCNoteFormula(subTableData, sub)

      const st = makeSubTable()
      // 除零 → Infinity → 非有限 → null（B=0）
      const row: RowData = { book_balance: 0, provision: 50 }
      const col = makeColWithKey('F', st.columns!.F)
      expect(cellComputedValue(st, row, col)).toBeNull()

      // 语法非法公式 → catch → null
      const badCol = makeColWithKey('Z', {
        field: 'z',
        label: 'Z',
        type: 'number',
        render: 'amount_formula',
        formula: '=B+',
      })
      expect(cellComputedValue(st, row, badCol)).toBeNull()
    })
  })

  describe('footerTotalColumns', () => {
    it('case 5: 按 currentStandardSubClass 过滤合计列', () => {
      const subTableData = ref<Record<string, RowData[]>>({})
      const sub = ref<SubClass>('listed')
      const { footerTotalColumns } = useCNoteFormula(subTableData, sub)

      const st = makeSubTable()
      // D 列仅适用于 soe
      st.columns!.D.applicable_to_sub_class = ['soe']

      // listed：D 被过滤掉，只剩 B
      const listedCols = footerTotalColumns(st)
      expect(listedCols.map(c => c.field)).toEqual(['book_balance'])

      // 切到 soe：B + D 都在
      sub.value = 'soe'
      const soeCols = footerTotalColumns(st)
      expect(soeCols.map(c => c.field)).toEqual(['book_balance', 'provision'])
    })

    it('case 5b: sum_columns 缺失列被跳过', () => {
      const subTableData = ref<Record<string, RowData[]>>({})
      const sub = ref<SubClass>('listed')
      const { footerTotalColumns } = useCNoteFormula(subTableData, sub)

      const st = makeSubTable()
      st.footer_total!.sum_columns = ['B', 'NONEXIST']
      expect(footerTotalColumns(st).map(c => c.field)).toEqual(['book_balance'])
    })
  })

  describe('footerTotalValue', () => {
    it('case 6: 跨行求和', () => {
      const subTableData = ref<Record<string, RowData[]>>({
        single_provision: [
          { book_balance: 1000 },
          { book_balance: 2000 },
          { book_balance: 500 },
        ],
      })
      const sub = ref<SubClass>('listed')
      const { footerTotalValue } = useCNoteFormula(subTableData, sub)

      const st = makeSubTable()
      const col: ColumnDef = st.columns!.B
      expect(footerTotalValue(st, col)).toBe(3500)
    })

    it('case 7: 空数据返回 0（子表无数据）', () => {
      const subTableData = ref<Record<string, RowData[]>>({})
      const sub = ref<SubClass>('listed')
      const { footerTotalValue } = useCNoteFormula(subTableData, sub)

      const st = makeSubTable()
      expect(footerTotalValue(st, st.columns!.B)).toBe(0)
    })

    it('case 8: escapeNumber 边界 — null/空串/非数字忽略，数字字符串解析', () => {
      const subTableData = ref<Record<string, RowData[]>>({
        single_provision: [
          { book_balance: null },
          { book_balance: '' },
          { book_balance: 'abc' },
          { book_balance: undefined },
          { book_balance: '100' }, // 数字字符串 → 100
          { book_balance: 50 }, // 数字 → 50
        ],
      })
      const sub = ref<SubClass>('listed')
      const { footerTotalValue } = useCNoteFormula(subTableData, sub)

      const st = makeSubTable()
      // 仅 '100' + 50 计入
      expect(footerTotalValue(st, st.columns!.B)).toBe(150)
    })
  })
})
