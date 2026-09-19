/**
 * 附注空表判定 —— 前端侧
 *
 * 🔴 本文件的用例与后端 `backend/tests/services/test_note_empty_table_detector.py`
 * **逐条镜像**（同名 case + 同预期）。任一侧改判定规则必须同步另一侧，否则模块页折叠
 * 与 Word 导出省略会出现两套口径。
 *
 * Spec: .kiro/specs/disclosure-note-follow-actual-content/ R4.1 / Task 1.3
 */
import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import {
  AMOUNT_FORMATS,
  SKIP_ROW_TYPES,
  emptyTableNames,
  isEmptyTable,
  type EmptyTableColumnDef,
} from '../disclosureEmptyTable'

/** 模仿 F2 存货「开发成本」（单级 7 列，4 个数值列） */
const DEV_COST_COLUMNS: EmptyTableColumnDef[] = [
  { key: 'project_name', label: '项目名称', is_label: true, flat: true },
  { key: 'start_date', label: '开工时间' },
  { key: 'expected_complete_date', label: '预计竣工时间' },
  { key: 'estimated_investment', label: '预计总投资', format: 'amount' },
  { key: 'end_balance', label: '期末数', format: 'amount' },
  { key: 'prior_balance', label: '上年年末数', format: 'amount' },
  { key: 'end_impairment', label: '期末跌价准备', format: 'amount' },
]

function row(label: string, values: unknown[], extra: Record<string, unknown> = {}) {
  return { label, values, is_total: false, ...extra }
}

const nulls = (n: number) => Array.from({ length: n }, () => null)

describe('isEmptyTable — 基本判定', () => {
  it('no rows is empty', () => {
    expect(isEmptyTable([], DEV_COST_COLUMNS)).toBe(true)
  })

  it('null rows is empty', () => {
    expect(isEmptyTable(null, DEV_COST_COLUMNS)).toBe(true)
  })

  it('模板骨架只有行标签 → 空表（标签不参与判定）', () => {
    const rows = [row('原材料', nulls(6)), row('在产品', nulls(6)), row('库存商品', nulls(6))]
    expect(isEmptyTable(rows, DEV_COST_COLUMNS)).toBe(true)
  })

  it('全零金额 → 空表', () => {
    expect(isEmptyTable([row('A 项目', ['', '', 0, 0, 0, 0])], DEV_COST_COLUMNS)).toBe(true)
  })

  it('任一非零金额 → 非空', () => {
    expect(
      isEmptyTable([row('A 项目', ['', '', 0, 1200000.55, 0, 0])], DEV_COST_COLUMNS),
    ).toBe(false)
  })

  it('文本列有内容 → 非空', () => {
    expect(isEmptyTable([row('A 项目', ['2024-03', '', 0, 0, 0, 0])], DEV_COST_COLUMNS)).toBe(false)
  })

  it('小于半分视为零 → 空表', () => {
    expect(isEmptyTable([row('A', ['', '', 0.001, -0.004, 0, 0])], DEV_COST_COLUMNS)).toBe(true)
  })

  it('一分钱 → 非空', () => {
    expect(isEmptyTable([row('A', ['', '', 0.01, 0, 0, 0])], DEV_COST_COLUMNS)).toBe(false)
  })
})

describe('isEmptyTable — 派生行 / 结构行不参与判定', () => {
  it('只有合计行 → 空表', () => {
    const rows = [
      row('原材料', nulls(6)),
      { label: '合计', values: ['', '', 0, 0, 0, 0], is_total: true },
    ]
    expect(isEmptyTable(rows, DEV_COST_COLUMNS)).toBe(true)
  })

  it('合计行有数也不使表变非空', () => {
    const rows = [
      row('原材料', nulls(6)),
      { label: '合计', values: ['', '', 0, 999, 0, 0], is_total: true },
    ]
    expect(isEmptyTable(rows, DEV_COST_COLUMNS)).toBe(true)
  })

  it.each([...SKIP_ROW_TYPES])('row_type=%s 不参与判定', (rowType) => {
    const rows = [{ label: '一、账面原值', values: ['', '', 123, 0, 0, 0], row_type: rowType }]
    expect(isEmptyTable(rows, DEV_COST_COLUMNS)).toBe(true)
  })

  it('段标题行后的数据行要算', () => {
    const rows = [
      { label: '一、账面原值', values: nulls(6), row_type: 'section' },
      row('1.期初余额', ['', '', 0, 100, 0, 0]),
    ]
    expect(isEmptyTable(rows, DEV_COST_COLUMNS)).toBe(false)
  })
})

describe('isEmptyTable — 列定义缺省 / 异常形态', () => {
  it("无列定义时按文本判定：'0' 视为有内容（保守，不吞数据）", () => {
    expect(isEmptyTable([row('A', ['0'])], null)).toBe(false)
  })

  it('无列定义 + 空串 → 空表', () => {
    expect(isEmptyTable([row('A', ['', '   ', null])], null)).toBe(true)
  })

  it('values 比列少 → 缺的按空', () => {
    expect(isEmptyTable([row('A', ['', ''])], DEV_COST_COLUMNS)).toBe(true)
  })

  it('values 比列多 → 多出的按文本', () => {
    expect(isEmptyTable([row('A', ['', '', 0, 0, 0, 0, '额外'])], DEV_COST_COLUMNS)).toBe(false)
  })

  it('非对象行被跳过', () => {
    expect(isEmptyTable(['not a dict', null, 42], DEV_COST_COLUMNS)).toBe(true)
  })

  it('values 非数组被跳过', () => {
    expect(isEmptyTable([{ label: 'A', values: 'oops' }], DEV_COST_COLUMNS)).toBe(true)
  })

  it('无 is_label 时剔除第一列（与投影器同规则）', () => {
    const cols: EmptyTableColumnDef[] = [
      { key: 'name', label: '项目' },
      { key: 'amt', label: '金额', format: 'amount' },
    ]
    expect(isEmptyTable([row('A', [0])], cols)).toBe(true)
    expect(isEmptyTable([row('A', [5])], cols)).toBe(false)
  })
})

describe('isEmptyTable — 数值文本形态', () => {
  const cols: EmptyTableColumnDef[] = [
    { key: 'label', label: '项目', is_label: true },
    { key: 'amt', label: '金额', format: 'amount' },
  ]

  it.each([
    ['0', true],
    ['0.00', true],
    ['1,234.50', false],
    ['1，234.50', false],
    ['(500)', false],
    ['(0)', true],
    ['  ', true],
    ['不适用', false],
  ] as const)('金额文本 %s → empty=%s', (val, expected) => {
    expect(isEmptyTable([row('A', [val])], cols)).toBe(expected)
  })

  it.each([...AMOUNT_FORMATS])('format=%s 时 0 视为空、1 视为非空', (fmt) => {
    const c: EmptyTableColumnDef[] = [
      { key: 'label', label: '项目', is_label: true },
      { key: 'v', label: '值', format: fmt },
    ]
    expect(isEmptyTable([row('A', [0])], c)).toBe(true)
    expect(isEmptyTable([row('A', [1])], c)).toBe(false)
  })
})

describe('emptyTableNames', () => {
  it('保持原顺序', () => {
    const tables = [
      { name: '存货分类', columns: DEV_COST_COLUMNS, rows: [row('原材料', ['', '', 0, 100, 0, 0])] },
      { name: '开发成本', columns: DEV_COST_COLUMNS, rows: [row('A', nulls(6))] },
      { name: '开发产品', columns: DEV_COST_COLUMNS, rows: [] },
      { name: '周转房', columns: DEV_COST_COLUMNS, rows: [row('B', nulls(6))] },
    ]
    expect(emptyTableNames(tables)).toEqual(['开发成本', '开发产品', '周转房'])
  })

  it('容忍垃圾输入', () => {
    expect(emptyTableNames(null)).toEqual([])
    expect(emptyTableNames(['x', 1, null])).toEqual([])
  })
})

describe('isEmptyTable — PBT（Property 8）', () => {
  const AMOUNT_COLS: EmptyTableColumnDef[] = [
    { key: 'label', label: '项目', is_label: true },
    { key: 'a', label: 'A', format: 'amount' },
    { key: 'b', label: 'B', format: 'amount' },
  ]

  it('任一非零金额 → 必非空', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.tuple(
            fc.double({ min: -1e9, max: 1e9, noNaN: true }),
            fc.double({ min: -1e9, max: 1e9, noNaN: true }),
          ),
          { minLength: 1, maxLength: 6 },
        ),
        (pairs) => {
          const rows = pairs.map(([a, b], i) => row(`r${i}`, [a, b]))
          const hasNonzero = pairs.some(([a, b]) => Math.abs(a) >= 0.005 || Math.abs(b) >= 0.005)
          expect(isEmptyTable(rows, AMOUNT_COLS)).toBe(!hasNonzero)
        },
      ),
      { numRuns: 40 },
    )
  })

  it('任一非空文本 → 必非空', () => {
    const cols: EmptyTableColumnDef[] = [
      { key: 'label', label: '项目', is_label: true },
      { key: 't', label: '说明' },
    ]
    fc.assert(
      fc.property(fc.array(fc.string({ maxLength: 8 }), { minLength: 1, maxLength: 6 }), (texts) => {
        const rows = texts.map((t, i) => row(`r${i}`, [t]))
        const hasContent = texts.some((t) => t.trim())
        expect(isEmptyTable(rows, cols)).toBe(!hasContent)
      }),
      { numRuns: 40 },
    )
  })

  it('合计行无论填什么都不改变判定', () => {
    fc.assert(
      fc.property(
        fc.array(fc.double({ min: -1e6, max: 1e6, noNaN: true }), { minLength: 1, maxLength: 5 }),
        (vals) => {
          const base = [row('r0', [0, 0])]
          const withTotal = [
            ...base,
            ...vals.map((v) => ({ label: '合计', values: [v, v], is_total: true })),
          ]
          expect(isEmptyTable(withTotal, AMOUNT_COLS)).toBe(isEmptyTable(base, AMOUNT_COLS))
        },
      ),
      { numRuns: 40 },
    )
  })
})
