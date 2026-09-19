/**
 * G9 其他非流动金融资产披露 ↔ note_template 子表契约 + 载荷构建器单测
 *
 * spec: .kiro/specs/disclosure-sync-path-buildout/ Task 2.5
 */
import { describe, expect, it } from 'vitest'
import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import {
  G9_DISCLOSURE_SHEET_NAME,
  G9_MAIN_SUBTABLE,
  G9_NOTE_SECTION,
  isG9DisclosureApplicable,
} from '../g9NoteSectionMap'
import {
  G9_SUBTABLE,
  G9_TEMPLATE_HEADERS,
  G9_TOTAL_LABEL,
  g9ColumnsFor,
  buildG9MainSubTableRows,
  buildG9SubTableData,
  buildG9SyncPayload,
  type G9SyncRow,
} from '../g9DisclosureSyncPayload'
import { G9_DISCLOSURE_LISTED_ROWS, G9_DISCLOSURE_SOE_ROWS } from '../g9Constants'

runDisclosureSubtableContract({
  cycle: 'G9',
  variants: [
    {
      variant: 'listed',
      section: G9_NOTE_SECTION.listed,
      subtables: G9_SUBTABLE.listed,
      columns: g9ColumnsFor('listed'),
    },
    {
      variant: 'soe',
      section: G9_NOTE_SECTION.soe,
      subtables: G9_SUBTABLE.soe,
      columns: g9ColumnsFor('soe'),
    },
  ],
})

function rowsFrom(defs: readonly { rowKey: string; label: string }[]): G9SyncRow[] {
  return defs.map((d, i) => ({
    rowKey: d.rowKey,
    label: d.label,
    currentAmount: (i + 1) * 100,
    priorAmount: (i + 1) * 10,
  }))
}

describe('G9 章节映射与 sheet_name', () => {
  it('sheet 名为源 xlsx 真实 tab 名', () => {
    expect(G9_DISCLOSURE_SHEET_NAME.listed).toBe('附注披露信息（上市公司）')
    expect(G9_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露信息（国企）')
  })

  it('章节号取自 variant_matrix（qi_ta_fei_liu_dong_jin_rong_zi_chan）', () => {
    expect(G9_NOTE_SECTION.listed).toBe('五、20')
    expect(G9_NOTE_SECTION.soe).toBe('八、20')
  })

  it('子表名不再是被 seed 拿来当表名的列头（`项  目` / `种  类`）', () => {
    for (const v of ['listed', 'soe'] as const) {
      expect(G9_MAIN_SUBTABLE[v]).toBe('其他非流动金融资产')
      expect(G9_MAIN_SUBTABLE[v]).not.toMatch(/^(项|种)\s/)
    }
  })

  it('「国有企业」写法识别为国企', () => {
    expect(isG9DisclosureApplicable('soe', ['国有企业单体'])).toBe(true)
    expect(isG9DisclosureApplicable('listed', ['国有企业单体'])).toBe(false)
  })
})

describe('G9 载荷构建器', () => {
  it('上市用 end_balance / prior_balance 键，国企用公允价值键（列头两版不同）', () => {
    const listed = buildG9MainSubTableRows('listed', rowsFrom(G9_DISCLOSURE_LISTED_ROWS))
    const soe = buildG9MainSubTableRows('soe', rowsFrom(G9_DISCLOSURE_SOE_ROWS))
    expect(listed[0]).toHaveProperty('end_balance')
    expect(listed[0]).toHaveProperty('prior_balance')
    expect(soe[0]).toHaveProperty('end_fair_value')
    expect(soe[0]).toHaveProperty('opening_fair_value')
  })

  it('4 个分类行 + 合计行；合计 = 分类行之和', () => {
    const rows = buildG9MainSubTableRows('listed', rowsFrom(G9_DISCLOSURE_LISTED_ROWS))
    expect(rows).toHaveLength(5)
    const total = rows.at(-1)!
    expect(total.is_total).toBe(true)
    expect(total.label).toBe(G9_TOTAL_LABEL)
    expect(total.end_balance).toBe(100 + 200 + 300 + 400)
    expect(total.prior_balance).toBe(10 + 20 + 30 + 40)
  })

  it('合计行 label 用模板字面量「合计」而非组件视觉写法「合  计」', () => {
    expect(G9_TOTAL_LABEL).toBe('合计')
    const rows = buildG9MainSubTableRows('soe', rowsFrom(G9_DISCLOSURE_SOE_ROWS))
    expect(rows.at(-1)!.label).not.toContain('  ')
  })

  it('列头用模板 headers（无全角空格），与组件视觉写法解耦', () => {
    expect(G9_TEMPLATE_HEADERS.listed.item).toBe('种类')
    expect(G9_TEMPLATE_HEADERS.soe.item).toBe('项目')
    const cols = g9ColumnsFor('listed')[G9_MAIN_SUBTABLE.listed]
    expect(cols.map((c) => c.label)).toEqual(['种类', '期末余额', '上年年末余额'])
  })

  it('columns 显式标 flat（源模板单级表头）', () => {
    for (const v of ['listed', 'soe'] as const) {
      const cols = g9ColumnsFor(v)[G9_MAIN_SUBTABLE[v]]
      expect(cols.some((c) => c.flat)).toBe(true)
      expect(cols.some((c) => c.group)).toBe(false)
    }
  })

  it('附注说明非空才进 _note_texts', () => {
    const rows = rowsFrom(G9_DISCLOSURE_SOE_ROWS)
    expect(buildG9SubTableData('soe', { rows, noteText: '' })).not.toHaveProperty('_note_texts')
    expect(buildG9SubTableData('soe', { rows, noteText: 'x' })._note_texts).toEqual([
      { section: 'soe-disclosure-note', text: 'x' },
    ])
  })

  it('载荷字段齐备', () => {
    const payload = buildG9SyncPayload('wp-9', 'listed', [], {
      rows: rowsFrom(G9_DISCLOSURE_LISTED_ROWS),
      noteText: '',
    })!
    expect(payload.sheet_name).toBe(G9_DISCLOSURE_SHEET_NAME.listed)
    expect(payload.section_id).toBe('五、20')
    expect(payload.current_standard).toBe('listed_standalone')
    expect(Object.keys(payload.sub_table_data)).toEqual([G9_MAIN_SUBTABLE.listed])
  })

  it('不适用变体 / 缺 wpId 返回 null', () => {
    expect(buildG9SyncPayload('wp-9', 'soe', ['listed_standalone'], { rows: [], noteText: '' })).toBeNull()
    expect(buildG9SyncPayload('', 'listed', [], { rows: [], noteText: '' })).toBeNull()
  })
})

/** 行对象的非数据键（不参与列头映射） */
const META_KEYS = new Set(['row_type', 'is_total', 'row_key'])

describe('G9 Property 1：columns 键 ≡ sub_table_data 数据键（双向）', () => {
  it.each([
    ['listed', G9_DISCLOSURE_LISTED_ROWS],
    ['soe', G9_DISCLOSURE_SOE_ROWS],
  ] as const)('%s 每张表的列键集与行字段键集完全一致', (variant, defs) => {
    const payload = buildG9SyncPayload('wp-9', variant, [], { rows: rowsFrom(defs), noteText: 'n' })!
    for (const [name, tableRows] of Object.entries(payload.sub_table_data)) {
      if (name.startsWith('_')) continue
      const colKeys = new Set((payload.columns[name] ?? []).map((c) => c.key))
      expect(colKeys.size, `${name} 缺 columns`).toBeGreaterThan(0)
      for (const row of tableRows) {
        const dataKeys = Object.keys(row).filter((k) => !META_KEYS.has(k))
        expect(new Set(dataKeys), `${name} 行字段键 ≠ 列键`).toEqual(colKeys)
      }
    }
  })
})
