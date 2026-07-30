import { describe, it, expect } from 'vitest'
import {
  buildL3ListedColumns,
  buildL3SoeColumns,
  buildL3SyncPayload,
  type L3SyncPayloadOptions,
} from '../l3NoteSectionMap'
import type { ColumnDef } from '../disclosureColumnDefs'

/**
 * L3 长期借款披露 columns 契约
 *
 * spec `disclosure-columns-coverage-rollout` design §批 1 列头清查 §4/§5（Task 5.1 实证）
 * 口径证据：源 `L 债务循环/L3 长期借款.xlsx` 两张披露 sheet +
 *   `附注模版/上市报表附注.md` L4630~4641（+ L4554）/ `国企报表附注.md` L3677~3691（+ L3626）+
 *   `note_template_{listed,soe}.json` 五、45 / 八、49（+ 八、45）+ consol 五-50-1 / 五-46-1。
 *
 * 覆盖 Property 1 / Property 2 / Property 6 + 单行表头 `flat`（0 处 group）+ values 位置对齐
 * （后者是国企 3 列方案 A 重排 `[期末余额, 期初余额, 期末利率期间]` 的守卫）。
 */

const SNAKE_CASE = /^[a-z_][a-z0-9_]*$/

/** rateRange(rowKey, period) 桩：回显入参便于断言列序 */
const rateRange = (rowKey: string, period: 'end' | 'prior') => `${rowKey}:${period}`

const baseOpts: L3SyncPayloadOptions = {
  variant: 'listed',
  classificationRows: [
    { label: '质押借款', endAmount: 1000, priorAmount: 900, rowKey: 'pledge' },
    { label: '信用借款', endAmount: 500, priorAmount: 400, rowKey: 'credit' },
    { label: '合  计', endAmount: 1500, priorAmount: 1300, isTotal: true, rowKey: 'total' },
  ],
  currentPortionRows: [
    { label: '质押借款', endAmount: 200, priorAmount: 150 },
    { label: '合  计', endAmount: 200, priorAmount: 150, isTotal: true },
  ],
  rateRange,
  propertyNote: '以厂房抵押',
  conclusion: '核对一致',
}

function payloadOf(variant: 'listed' | 'soe', over: Partial<L3SyncPayloadOptions> = {}) {
  return buildL3SyncPayload({ ...baseOpts, variant, ...over })
}

function dataKeys(sub: Record<string, unknown>): string[] {
  return Object.keys(sub).filter(k => !k.startsWith('_')).sort()
}

describe('L3 长期借款披露 columns 契约', () => {
  it('上市：长期借款表 5 列，两个同名「利率区间」只靠 key 区分（不加期别前缀）', () => {
    const cols = buildL3ListedColumns()['长期借款']
    expect(cols.map(c => c.label)).toEqual(['项目', '期末余额', '利率区间', '上年年末余额', '利率区间'])
    expect(cols.map(c => c.key)).toEqual(['label', 'endAmount', 'endRate', 'priorAmount', 'priorRate'])
    // 附注模版 L4632 即两列同名；加「期末/期初」前缀属杜撰
    expect(cols[2].label).toBe(cols[4].label)
    expect(cols[2].key).not.toBe(cols[4].key)
    expect(cols[1].format).toBe('amount')
    expect(cols[2].format).toBe('text')
  })

  it('上市：一年内到期表 3 列（项目 / 期末余额 / 上年年末余额）', () => {
    const cols = buildL3ListedColumns()['一年内到期的长期借款']
    expect(cols.map(c => c.label)).toEqual(['项目', '期末余额', '上年年末余额'])
    expect(cols.map(c => c.key)).toEqual(['label', 'endAmount', 'priorAmount'])
    expect(cols[0].is_label).toBe(true)
  })

  it('国企：长期借款表取附注模版 4 列（方案 A），期初利率无落点被丢弃', () => {
    const cols = buildL3SoeColumns()['长期借款']
    expect(cols.map(c => c.label)).toEqual(['借款类别', '期末余额', '期初余额', '期末利率期间（%）'])
    expect(cols.map(c => c.key)).toEqual(['label', 'endAmount', 'priorAmount', 'endRate'])
    // 方案 B（保源 xlsx 5 列，含期初「利率区间」）与附注模版/consol 双双不符
    expect(cols.map(c => c.key)).not.toContain('priorRate')
    expect(cols).toHaveLength(4)
  })

  it('国企：一年内到期表标签列取附注口径「项目」（源 A21 与底稿 UI 的「借款类别」不作准）', () => {
    const cols = buildL3SoeColumns()['一年内到期的长期借款']
    expect(cols.map(c => c.label)).toEqual(['项目', '期末余额', '期初余额'])
    expect(cols[0].label).not.toBe('借款类别')
    expect(cols[0].is_label).toBe(true)
  })

  it('Property 1：两版 columns 键与 sub_table_data 数据键集合相等', () => {
    for (const variant of ['listed', 'soe'] as const) {
      const { sub_table_data, columns } = payloadOf(variant)
      expect(dataKeys(sub_table_data), variant).toEqual(['一年内到期的长期借款', '长期借款'].sort())
      expect(Object.keys(columns).sort(), variant).toEqual(dataKeys(sub_table_data))
    }
  })

  it('Property 1：说明文本为空时仍不产生键漂移（`_note_texts` 为元数据键，不参与配对）', () => {
    for (const variant of ['listed', 'soe'] as const) {
      const { sub_table_data, columns } = payloadOf(variant, { propertyNote: '', conclusion: '' })
      expect(sub_table_data._note_texts, variant).toBeUndefined()
      expect(Object.keys(columns).sort(), variant).toEqual(dataKeys(sub_table_data))
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

  it('位置对齐（国企重排守卫）：长期借款行 values = [期末余额, 期初余额, 期末利率期间]', () => {
    const { sub_table_data } = payloadOf('soe')
    const rows = sub_table_data['长期借款'] as Array<{ label: string; values: unknown[] }>
    expect(rows[0].label).toBe('质押借款')
    expect(rows[0].values).toEqual([1000, 900, 'pledge:end'])
    // 期初利率（`pledge:prior`）在附注侧无落点，不得出现
    expect(rows[0].values).not.toContain('pledge:prior')
  })

  it('位置对齐（上市）：长期借款行 values = [期末余额, 利率区间(end), 上年年末余额, 利率区间(prior)]', () => {
    const { sub_table_data } = payloadOf('listed')
    const rows = sub_table_data['长期借款'] as Array<{ label: string; values: unknown[] }>
    expect(rows[0].values).toEqual([1000, 'pledge:end', 900, 'pledge:prior'])
  })
})
