/**
 * G10 交易性金融负债披露 ↔ note_template 子表契约 + 载荷 Property 1（columns 键 ≡ 行数据键）
 *
 * R8.4 批 9b-2（2026-10-24）：G10 原先没有契约 spec，下面几处长期无人发现 ——
 * 公允价值变动表名按审计年度拼（国企模板是「202X年」⇒ 恒对不上，上市跨年对不上）、国企主表键 end_fair_value /
 * prior_fair_value ≠ 模板 end_fv / begin_fv、上市键 opening_balance ≠ 模板 begin_balance、各表都没表态 flat
 * （后端会把「本期增加 / 本期减少」反猜出「本期」父表头）；另 5914e315b 把模板 五、35 表名改成了 15 号文提示段，
 * 前端推的「衍生金融负债」成了孤儿（模板侧已改回）。
 */
import { describe, expect, it } from 'vitest'
import { runDisclosureSubtableContract, templateTable, type DisclosureVariantKey } from './_disclosureSubtableContract.helper'
import { G10_DERIVATIVE_SUBTABLE, G10_NOTE_SECTION, G10_SUBTABLE } from '../g10NoteSectionMap'
import {
  buildG10ListedColumns,
  buildG10ListedDerivativeColumns,
  buildG10ListedSyncPayloads,
  buildG10SoeColumns,
  buildG10SoeSyncPayloads,
} from '../g10DisclosureSyncPayload'
import { defaultG10ListedDiscStore, defaultG10SoeDiscStore } from '../g10DisclosureFromAdj'
import type { ColumnDef } from '../disclosureColumnDefs'

const SECTIONS: Array<[DisclosureVariantKey, string, Record<string, ColumnDef[]>]> = [
  ['listed', G10_NOTE_SECTION.listed.trading, buildG10ListedColumns(2025)],
  ['listed', G10_NOTE_SECTION.listed.derivative, buildG10ListedDerivativeColumns()],
  ['soe', G10_NOTE_SECTION.soe.trading, buildG10SoeColumns(2025)],
]

runDisclosureSubtableContract({
  cycle: 'G10',
  variants: [
    { variant: 'listed', section: SECTIONS[0][1], subtables: G10_SUBTABLE.listed, columns: SECTIONS[0][2] },
    {
      variant: 'listed',
      section: SECTIONS[1][1],
      subtables: { derivative: G10_DERIVATIVE_SUBTABLE.listed },
      columns: SECTIONS[1][2],
    },
    { variant: 'soe', section: SECTIONS[2][1], subtables: G10_SUBTABLE.soe, columns: SECTIONS[2][2] },
  ],
})

describe('G10 列键 / 列名与模板逐表一致', () => {
  it.each(SECTIONS)('%s %s', (variant, section, columns) => {
    expect(Object.keys(columns).length).toBeGreaterThan(0)
    for (const [name, defs] of Object.entries(columns)) {
      const tpl = templateTable(variant, section, name)
      expect(tpl, `${section} 模板缺「${name}」`).toBeDefined()
      expect(defs.map((c) => c.key), name).toEqual((tpl?.columns ?? []).map((c) => c.key))
      // 「XXXX年公允价值变动额」按审计年度推（模板是 Word 原文年份），其余列名逐字一致
      const labels = (cols: readonly { key?: string; label?: string }[]) =>
        cols.filter((c) => c.key !== 'fv_change_amount').map((c) => c.label)
      expect(labels(defs), name).toEqual(labels(tpl?.columns ?? []))
    }
  })
})

/** 行对象的非数据键（不参与列头映射） */
const META_KEYS = new Set(['row_type', 'is_total', 'row_key'])

function allPayloads() {
  const listed = defaultG10ListedDiscStore()
  listed.derivativeRows = [{ rowKey: 'd1', label: '利率互换', currentAmount: 50, priorAmount: 40 }]
  const soe = defaultG10SoeDiscStore()
  return [
    ...buildG10ListedSyncPayloads('wp-g10', ['listed_standalone'], { store: listed, auditNote: 'n', auditYear: 2025 }),
    ...buildG10SoeSyncPayloads('wp-g10', ['soe_standalone'], { store: soe, auditNote: 'n', auditYear: 2025 }),
  ]
}

describe('G10 Property 1：columns 键 ≡ sub_table_data 数据键（双向）', () => {
  it('三节载荷都在（上市 五、34 + 五、35、国企 八、34）', () => {
    expect(allPayloads().map((p) => p.section_id)).toEqual(['五、34', '五、35', '八、34'])
  })

  it.each(allPayloads().map((p) => [p.section_id, p] as const))('%s 每张表的列键集与行字段键集完全一致', (_sec, payload) => {
    for (const [name, tableRows] of Object.entries(payload.sub_table_data)) {
      if (name.startsWith('_')) continue
      const colKeys = new Set((payload.columns?.[name] ?? []).map((c) => c.key))
      expect(colKeys.size, `${name} 缺 columns`).toBeGreaterThan(0)
      for (const row of tableRows as Record<string, unknown>[]) {
        const dataKeys = Object.keys(row).filter((k) => !META_KEYS.has(k))
        expect(new Set(dataKeys), `${name} 行字段键 ≠ 列键`).toEqual(colKeys)
      }
    }
  })
})
