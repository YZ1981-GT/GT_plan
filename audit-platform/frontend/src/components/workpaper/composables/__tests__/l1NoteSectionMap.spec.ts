import { describe, it, expect } from 'vitest'
import {
  buildL1ListedColumns,
  buildL1SoeColumns,
  buildL1SyncPayload,
  type L1SyncPayloadOptions,
} from '../l1NoteSectionMap'
import type { ColumnDef } from '../disclosureColumnDefs'

/**
 * L1 短期借款披露 columns 契约
 *
 * spec `disclosure-columns-coverage-rollout` design §批 1 列头清查 §2/§3（Task 5.1 实证）
 * 口径证据：源 `L 债务循环/L1 短期借款.xlsx` 两张披露 sheet +
 *   `附注模版/上市报表附注.md` L4198~4223 / `国企报表附注.md` L3337~3360 +
 *   `note_template_{listed,soe}.json` 五、33 / 八、33。
 *
 * 覆盖 Property 1（columns ↔ sub_table_data 键一一对应，含空逾期分支）/
 *      Property 2（标签列唯一且居首）/ Property 6（无 snake_case 列头）+
 *      单行表头 `flat` 声明（批 1 全表 0 处 group）+ values 位置对齐。
 */

const SNAKE_CASE = /^[a-z_][a-z0-9_]*$/

const baseOpts: L1SyncPayloadOptions = {
  variant: 'listed',
  categoryRows: [
    { category: '信用借款', endBalance: 1000, beginBalance: 800 },
    { category: '抵押借款', endBalance: 500, beginBalance: 400 },
  ],
  categoryTotal: { begin: 1200, end: 1500 },
  overdueRows: [
    { borrower: '甲银行', endBalance: 300, rate: 4.35, overdueTime: '3个月', penaltyRate: 6.5 },
  ],
  conclusionText: '核对一致',
}

function payloadOf(variant: 'listed' | 'soe', over: Partial<L1SyncPayloadOptions> = {}) {
  return buildL1SyncPayload({ ...baseOpts, variant, ...over })
}

/** 非元数据（非 `_` 前缀）的数据子表键 */
function dataKeys(sub: Record<string, unknown>): string[] {
  return Object.keys(sub).filter(k => !k.startsWith('_')).sort()
}

describe('L1 短期借款披露 columns 契约', () => {
  it('上市：分类表 3 列（项目 / 期末余额 / 上年年末余额）', () => {
    const cols = buildL1ListedColumns()['短期借款分类']
    expect(cols.map(c => c.label)).toEqual(['项目', '期末余额', '上年年末余额'])
    expect(cols.map(c => c.key)).toEqual(['category', 'endBalance', 'beginBalance'])
    expect(cols[0].is_label).toBe(true)
    expect(cols[1].format).toBe('amount')
    expect(cols[2].format).toBe('amount')
  })

  it('上市：逾期表 5 列且标 flat（抑制凭空「逾期」父表头）', () => {
    const cols = buildL1ListedColumns({ includeOverdue: true })['逾期借款情况']
    // 利率列取附注模版口径：均无 `(%)`（底稿 UI 的 `借款利率(%)` 不作准）
    expect(cols.map(c => c.label)).toEqual(['借款单位', '期末余额', '借款利率', '逾期时间', '逾期利率'])
    expect(cols.map(c => c.key)).toEqual(['borrower', 'endBalance', 'rate', 'overdueTime', 'penaltyRate'])
    // 源 A18:E18 单行表头；不标 flat 时后端会把「逾期时间/逾期利率」并到假父表头「逾期」下
    expect(cols.some(c => c.flat === true)).toBe(true)
    expect(cols.every(c => c.group === undefined)).toBe(true)
    expect(cols[2].format).toBe('percent')
    expect(cols[3].format).toBe('text')
    expect(cols[4].format).toBe('percent')
  })

  it('国企：分类表标签列为「借款类别」，第 3 列取附注口径「期初余额」（非源 xlsx 的「年初余额」）', () => {
    const cols = buildL1SoeColumns()['短期借款分类']
    expect(cols.map(c => c.label)).toEqual(['借款类别', '期末余额', '期初余额'])
    expect(cols[0].is_label).toBe(true)
    expect(cols.map(c => c.label)).not.toContain('年初余额')
  })

  it('国企：逾期表 3 列，标签列为「债权单位」、利率列全角括号「借款利率（%）」', () => {
    const cols = buildL1SoeColumns({ includeOverdue: true })['逾期借款情况']
    expect(cols.map(c => c.label)).toEqual(['债权单位', '期末余额', '借款利率（%）'])
    // 标签列头必须 = 附注 headers[0]，写「借款单位」会出孤儿列
    expect(cols[0].label).not.toBe('借款单位')
    // 源 A16:C16 仅 3 列 → 禁凭空补「逾期时间（月）」「逾期利率」录入列
    expect(cols).toHaveLength(3)
  })

  it('Property 1：两版 columns 键与 sub_table_data 数据键集合相等', () => {
    for (const variant of ['listed', 'soe'] as const) {
      const { sub_table_data, columns } = payloadOf(variant)
      expect(dataKeys(sub_table_data), variant).toEqual(['短期借款分类', '逾期借款情况'].sort())
      expect(Object.keys(columns).sort(), variant).toEqual(dataKeys(sub_table_data))
    }
  })

  it('Property 1（空逾期分支）：无逾期数据时「逾期借款情况」在两侧同时缺席', () => {
    for (const variant of ['listed', 'soe'] as const) {
      // 空数组 + 全空行（`borrower || endBalance` 均为假）两种入参都应落到同一分支
      for (const overdueRows of [[], [{ borrower: '', endBalance: 0, rate: 0 }]]) {
        const { sub_table_data, columns } = payloadOf(variant, { overdueRows })
        expect(sub_table_data['逾期借款情况'], variant).toBeUndefined()
        expect(columns['逾期借款情况'], variant).toBeUndefined()
        expect(Object.keys(columns).sort(), variant).toEqual(dataKeys(sub_table_data))
        expect(dataKeys(sub_table_data), variant).toEqual(['短期借款分类'])
      }
    }
  })

  it('Property 2：每张表恰好 1 个 is_label 且位于索引 0', () => {
    for (const variant of ['listed', 'soe'] as const) {
      const { columns } = payloadOf(variant)
      for (const [name, defs] of Object.entries(columns)) {
        expect(defs.length, name).toBeGreaterThan(0)
        expect(defs.filter(d => d.is_label === true), `${variant}.${name}`).toHaveLength(1)
        expect(defs[0].is_label, `${variant}.${name}`).toBe(true)
      }
    }
  })

  it('Property 6：无 snake_case 字段键泄漏为列头，且 label 非空', () => {
    for (const variant of ['listed', 'soe'] as const) {
      const { columns } = payloadOf(variant)
      for (const [name, defs] of Object.entries(columns)) {
        for (const d of defs) {
          expect(d.label.trim(), `${variant}.${name}.${d.key}`).not.toBe('')
          expect(SNAKE_CASE.test(d.label), `${variant}.${name}.${d.key} 用了字段键当列头`).toBe(false)
        }
      }
    }
  })

  it('批 1 全为单行表头：每表至少一列 flat，且无一列带 group', () => {
    for (const variant of ['listed', 'soe'] as const) {
      const { columns } = payloadOf(variant)
      expect(Object.keys(columns).length, variant).toBe(2)
      for (const [name, defs] of Object.entries(columns)) {
        expect(defs.some(d => d.flat === true), `${variant}.${name} 未声明 flat`).toBe(true)
        expect(defs.filter(d => d.group !== undefined), `${variant}.${name}`).toHaveLength(0)
      }
    }
  })

  it('位置对齐：每行 values 长度 = 该表非标签列数', () => {
    for (const variant of ['listed', 'soe'] as const) {
      const { sub_table_data, columns } = payloadOf(variant)
      for (const key of dataKeys(sub_table_data)) {
        const defs = columns[key] as ColumnDef[]
        const valueColCount = defs.filter(d => !d.is_label).length
        const rows = sub_table_data[key] as Array<{ label: unknown; values: unknown[] }>
        expect(rows.length, `${variant}.${key}`).toBeGreaterThan(0)
        for (const r of rows) {
          expect(r.values.length, `${variant}.${key} 行「${String(r.label)}」`).toBe(valueColCount)
        }
      }
    }
  })
})
