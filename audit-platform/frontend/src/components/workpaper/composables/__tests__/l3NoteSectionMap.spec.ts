import { describe, it, expect } from 'vitest'
import {
  L3_LEGACY_OBSOLETE_TABLES,
  L3_NOTE_SECTION,
  L3_SUBTABLE,
  buildL3ListedColumns,
  buildL3SoeColumns,
  buildL3SyncPayload,
  buildL3Within1ySoeColumns,
  type L3SyncPayloadOptions,
} from '../l3NoteSectionMap'
import type { ColumnDef } from '../disclosureColumnDefs'

/**
 * L3 长期借款披露载荷契约（R8.4 批 9b-2 按底稿改：长期借款一层表头 5 列、两版同列；
 * 一年内到期的长期借款只推国企 八、45，上市所在 五、43 是共用节不推）。
 *
 * 口径证据：源 `L/L3 长期借款.xlsx` 两张披露 sheet（上市 A7:E7、国企 A8:E8 一行表头、无合并格；
 * 国企一年内到期 A21:C21）+ `note_template_{listed,soe}.json` 五、45 / 八、49 / 八、45。
 * 模板侧逐字对齐由 `lCycleNoteSubtableContract.spec.ts` 的共享 helper P1~P6 守。
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

function itemsOf(variant: 'listed' | 'soe', over: Partial<L3SyncPayloadOptions> = {}) {
  return buildL3SyncPayload({ ...baseOpts, variant, ...over })
}

function dataKeys(sub: Record<string, unknown>): string[] {
  return Object.keys(sub).filter(k => !k.startsWith('_')).sort()
}

describe('L3 长期借款披露载荷契约', () => {
  it('长期借款表两版同为一层 5 列，两列同名「利率区间」只靠 key 区分（不加期别前缀）', () => {
    const expected = {
      listed: ['项  目', '期末余额', '利率区间', '上年年末余额', '利率区间'],
      soe: ['借款类别', '期末余额', '利率区间', '期初余额', '利率区间'],
    }
    for (const [variant, cols] of [['listed', buildL3ListedColumns()], ['soe', buildL3SoeColumns()]] as const) {
      const main = cols[L3_SUBTABLE.main]
      expect(main.map(c => c.label), variant).toEqual(expected[variant])
      expect(main.map(c => c.key), variant).toEqual(['label', 'endAmount', 'endRate', 'priorAmount', 'priorRate'])
      expect(main[2].key).not.toBe(main[4].key)
      expect(main[1].format).toBe('amount')
      expect(main[2].format).toBe('text')
      expect(main.filter(c => c.group !== undefined), variant).toHaveLength(0)
    }
  })

  it('上市推 1 节（五、45），国企推 2 节（八、49 + 八、45）', () => {
    expect(itemsOf('listed').map(i => i.section_id)).toEqual([L3_NOTE_SECTION.listed.main])
    expect(itemsOf('soe').map(i => i.section_id)).toEqual([L3_NOTE_SECTION.soe.main, L3_NOTE_SECTION.soe.within1y])
    expect(L3_NOTE_SECTION.soe.within1y).toBe('八、45')
  })

  it('一年内到期的长期借款不再推进 五、45 / 八、49，并清掉旧载荷推进去的孤儿表', () => {
    for (const variant of ['listed', 'soe'] as const) {
      const [main] = itemsOf(variant)
      expect(dataKeys(main.sub_table_data), variant).toEqual([L3_SUBTABLE.main])
      expect(main.sub_table_data._removed_table_keys, variant).toEqual([...L3_LEGACY_OBSOLETE_TABLES])
      for (const legacy of L3_LEGACY_OBSOLETE_TABLES) {
        expect(dataKeys(main.sub_table_data), `${variant} 推送键与待删表名不得相交`).not.toContain(legacy)
      }
    }
  })

  it('国企 八、45 表名与列逐字取模板（借款类别 / 期末余额 / 期初余额）', () => {
    const [, within1y] = itemsOf('soe')
    expect(dataKeys(within1y.sub_table_data)).toEqual([L3_SUBTABLE.within1ySoe])
    expect(within1y.columns[L3_SUBTABLE.within1ySoe].map(c => c.label)).toEqual(['借款类别', '期末余额', '期初余额'])
    expect(buildL3Within1ySoeColumns()).toEqual(within1y.columns)
    const rows = within1y.sub_table_data[L3_SUBTABLE.within1ySoe] as Array<{ label: string; values: unknown[] }>
    expect(rows[0]).toEqual({ label: '质押借款', values: [200, 150] })
  })

  it('Property 1：每节 columns 键与 sub_table_data 数据键集合相等（说明文本为空时亦然）', () => {
    for (const variant of ['listed', 'soe'] as const) {
      for (const over of [{}, { propertyNote: '', conclusion: '' }]) {
        for (const item of itemsOf(variant, over)) {
          expect(Object.keys(item.columns).sort(), `${variant} ${item.section_id}`).toEqual(dataKeys(item.sub_table_data))
        }
      }
    }
    expect(itemsOf('listed', { propertyNote: '', conclusion: '' })[0].sub_table_data._note_texts).toBeUndefined()
  })

  it('Property 2 / 6：每张表恰好 1 个 is_label 且位于索引 0，列头非空且不是字段键', () => {
    for (const variant of ['listed', 'soe'] as const) {
      for (const item of itemsOf(variant)) {
        for (const [name, defs] of Object.entries(item.columns)) {
          expect(defs.filter(d => d.is_label === true), `${variant}.${name}`).toHaveLength(1)
          expect(defs[0].is_label, `${variant}.${name}`).toBe(true)
          expect(defs.some(d => d.flat === true), `${variant}.${name} 未声明 flat`).toBe(true)
          for (const d of defs) {
            expect(d.label.trim(), `${variant}.${name}.${d.key}`).not.toBe('')
            expect(SNAKE_CASE.test(d.label), `${variant}.${name}.${d.key} 用了字段键当列头`).toBe(false)
          }
        }
      }
    }
  })

  it('位置对齐：每行 values 长度 = 该表非标签列数；长期借款行 = [期末余额, 利率(期末), 期初|上年年末, 利率(期初)]', () => {
    for (const variant of ['listed', 'soe'] as const) {
      for (const item of itemsOf(variant)) {
        for (const key of dataKeys(item.sub_table_data)) {
          const defs = item.columns[key] as ColumnDef[]
          const rows = item.sub_table_data[key] as Array<{ label: unknown; values: unknown[] }>
          expect(rows.length, `${variant}.${key}`).toBeGreaterThan(0)
          for (const r of rows) expect(r.values.length, `${variant}.${key}「${String(r.label)}」`).toBe(defs.length - 1)
        }
      }
      const rows = itemsOf(variant)[0].sub_table_data[L3_SUBTABLE.main] as Array<{ values: unknown[] }>
      expect(rows[0].values, variant).toEqual([1000, 'pledge:end', 900, 'pledge:prior'])
    }
  })
})
