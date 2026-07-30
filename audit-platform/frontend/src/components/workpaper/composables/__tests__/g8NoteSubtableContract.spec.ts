/**
 * G8 其他权益工具投资披露 ↔ note_template 子表契约 + 载荷构建器单测
 *
 * spec: .kiro/specs/disclosure-sync-path-buildout/ Task 2.4
 */
import { describe, expect, it } from 'vitest'
import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import {
  G8_DETAIL_SUBTABLE,
  G8_DISCLOSURE_SHEET_NAME,
  G8_MAIN_SUBTABLE,
  G8_NOTE_SECTION,
  isG8DisclosureApplicable,
} from '../g8NoteSectionMap'
import {
  G8_BALANCE_HEADERS,
  G8_SUBTABLE,
  G8_TOTAL_LABEL,
  buildG8BalanceRows,
  g8ColumnsFor,
  buildG8DetailRows,
  buildG8SubTableData,
  buildG8SyncPayload,
  type G8BalanceSyncRow,
  type G8DetailSyncRow,
} from '../g8DisclosureSyncPayload'
import { extractG8SheetCode } from '../g8SheetLabels'

runDisclosureSubtableContract({
  cycle: 'G8',
  variants: [
    {
      variant: 'listed',
      section: G8_NOTE_SECTION.listed,
      subtables: G8_SUBTABLE.listed,
      columns: g8ColumnsFor('listed'),
    },
    {
      variant: 'soe',
      section: G8_NOTE_SECTION.soe,
      subtables: G8_SUBTABLE.soe,
      columns: g8ColumnsFor('soe'),
    },
  ],
})

const BALANCE: G8BalanceSyncRow[] = [
  { label: '甲公司股权', closing: 1000, prior: 900 },
  { label: '乙公司股权', closing: 500, prior: 400 },
  { label: '', closing: 0, prior: 0 },
]

const DETAIL: G8DetailSyncRow[] = [
  {
    label: '甲公司股权',
    ociPeriod: 100,
    ociCumulative: 300,
    dividend: 20,
    transferAmount: 5,
    transferReason: '处置',
  },
  { label: '', ociPeriod: 0, ociCumulative: 0, dividend: 0, transferAmount: 0, transferReason: '' },
]

describe('G8 章节映射与 sheet 分发', () => {
  it('章节号取自 variant_matrix（qi_ta_quan_yi_gong_ju_tou_zi）', () => {
    expect(G8_NOTE_SECTION.listed).toBe('五、19')
    expect(G8_NOTE_SECTION.soe).toBe('八、19')
  })

  it('sheet 名为源 xlsx 真实 tab 名', () => {
    expect(G8_DISCLOSURE_SHEET_NAME.listed).toBe('附注披露信息（上市公司）')
    expect(G8_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露信息（国企）')
  })

  it('子表名不再是被 seed 拿来当表名的列头「项  目」', () => {
    expect(G8_MAIN_SUBTABLE.listed).toBe('其他权益工具投资')
    expect(G8_MAIN_SUBTABLE.soe).toBe('其他权益工具投资情况')
    expect(G8_DETAIL_SUBTABLE).toBe('期末其他权益工具投资情况')
    for (const n of [G8_MAIN_SUBTABLE.listed, G8_MAIN_SUBTABLE.soe, G8_DETAIL_SUBTABLE]) {
      expect(n).not.toMatch(/^项\s/)
    }
  })

  it('sheet 分发认「国有企业」写法（否则国企 TAB 渲染上市组件）', () => {
    expect(extractG8SheetCode('附注披露信息（国有企业）')).toBe('附注国企')
    expect(extractG8SheetCode('附注披露信息（国企）')).toBe('附注国企')
    expect(extractG8SheetCode('附注披露信息（上市公司）')).toBe('附注上市')
  })

  it('「国有企业」写法识别为国企（适用性判定）', () => {
    expect(isG8DisclosureApplicable('soe', ['国有企业单体'])).toBe(true)
    expect(isG8DisclosureApplicable('listed', ['国有企业单体'])).toBe(false)
  })
})

describe('G8 载荷构建器 — 余额表', () => {
  it('空白行被剔除，合计 = 明细之和', () => {
    const rows = buildG8BalanceRows('listed', BALANCE)
    expect(rows).toHaveLength(3) // 2 明细 + 合计
    const total = rows.at(-1)!
    expect(total.label).toBe(G8_TOTAL_LABEL)
    expect(total.end_balance).toBe(1500)
    expect(total.prior_balance).toBe(1300)
  })

  it('上市用 prior_balance（上年年末余额），国企用 opening_balance（期初余额）', () => {
    expect(G8_BALANCE_HEADERS.listed.prior).toBe('上年年末余额')
    expect(G8_BALANCE_HEADERS.soe.prior).toBe('期初余额')
    expect(buildG8BalanceRows('listed', BALANCE)[0]).toHaveProperty('prior_balance')
    expect(buildG8BalanceRows('soe', BALANCE)[0]).toHaveProperty('opening_balance')
  })
})

describe('G8 载荷构建器 — 逐项目明细表', () => {
  it('上市列键：derecognition_to_re / derecognition_reason', () => {
    const rows = buildG8DetailRows('listed', DETAIL)
    expect(rows).toHaveLength(1) // 上市源模板无合计行
    expect(rows[0]).toHaveProperty('derecognition_to_re', 5)
    expect(rows[0]).toHaveProperty('derecognition_reason', '处置')
  })

  it('国企列键：oci_to_re / oci_to_re_reason，且有合计行', () => {
    const rows = buildG8DetailRows('soe', DETAIL)
    expect(rows).toHaveLength(2) // 1 明细 + 合计
    expect(rows[0]).toHaveProperty('oci_to_re', 5)
    expect(rows[0]).toHaveProperty('oci_to_re_reason', '处置')
    const total = rows.at(-1)!
    expect(total.is_total).toBe(true)
    expect(total.oci_current).toBe(100)
    expect(total.dividend_income).toBe(20)
    expect(total.oci_to_re_reason).toBe('')
  })

  it('两版第 2 张表列头文案与列序不同（不得共用一套 ColumnDef）', () => {
    const listed = g8ColumnsFor('listed')[G8_DETAIL_SUBTABLE].map((c) => c.label)
    const soe = g8ColumnsFor('soe')[G8_DETAIL_SUBTABLE].map((c) => c.label)
    expect(listed).not.toEqual(soe)
    expect(listed[1]).toContain('利得和损失')
    expect(soe[1]).toBe('本期确认的股利收入')
    expect(soe[2]).toContain('利得或损失')
  })
})

describe('G8 载荷装配', () => {
  it('两张表都在 sub_table_data 里', () => {
    const data = buildG8SubTableData('soe', {
      balanceRows: BALANCE,
      detailRows: DETAIL,
      designationText: '',
      noteText: '',
    })
    expect(Object.keys(data)).toEqual([G8_MAIN_SUBTABLE.soe, G8_DETAIL_SUBTABLE])
  })

  it('指定原因与附注说明分别进 _note_texts（非空才进）', () => {
    const base = { balanceRows: BALANCE, detailRows: DETAIL }
    expect(
      buildG8SubTableData('listed', { ...base, designationText: ' ', noteText: '' }),
    ).not.toHaveProperty('_note_texts')
    const both = buildG8SubTableData('listed', { ...base, designationText: '战略持有', noteText: 'n' })
    expect(both._note_texts).toEqual([
      { section: 'listed-designation-reason', text: '战略持有' },
      { section: 'listed-disclosure-note', text: 'n' },
    ])
  })

  it('columns 两张表都显式标 flat', () => {
    for (const v of ['listed', 'soe'] as const) {
      for (const name of Object.values(G8_SUBTABLE[v])) {
        const cols = g8ColumnsFor(v)[name]
        expect(cols.some((c) => c.flat), `${v}/${name} 未标 flat`).toBe(true)
        expect(cols.some((c) => c.group)).toBe(false)
      }
    }
  })

  it('载荷字段齐备；不适用变体 / 缺 wpId 返回 null', () => {
    const snap = { balanceRows: BALANCE, detailRows: DETAIL, designationText: '', noteText: '' }
    const payload = buildG8SyncPayload('wp-8', 'listed', [], snap)!
    expect(payload.section_id).toBe('五、19')
    expect(payload.sheet_name).toBe(G8_DISCLOSURE_SHEET_NAME.listed)
    expect(payload.current_standard).toBe('listed_standalone')
    expect(buildG8SyncPayload('wp-8', 'listed', ['soe_standalone'], snap)).toBeNull()
    expect(buildG8SyncPayload('', 'soe', [], snap)).toBeNull()
  })
})

/** 行对象的非数据键（不参与列头映射） */
const META_KEYS = new Set(['row_type', 'is_total', 'row_key'])

describe('G8 Property 1：columns 键 ≡ sub_table_data 数据键（双向）', () => {
  it.each(['listed', 'soe'] as const)('%s 每张表的列键集与行字段键集完全一致', (variant) => {
    const payload = buildG8SyncPayload('wp-8', variant, [], {
      balanceRows: BALANCE,
      detailRows: DETAIL,
      designationText: '战略持有',
      noteText: 'n',
    })!
    for (const [name, tableRows] of Object.entries(payload.sub_table_data)) {
      if (name.startsWith('_')) continue
      const colKeys = new Set((payload.columns[name] ?? []).map((c) => c.key))
      expect(colKeys.size, `${name} 缺 columns`).toBeGreaterThan(0)
      expect(tableRows.length, `${name} 无行`).toBeGreaterThan(0)
      for (const row of tableRows) {
        const dataKeys = Object.keys(row).filter((k) => !META_KEYS.has(k))
        expect(new Set(dataKeys), `${name} 行字段键 ≠ 列键`).toEqual(colKeys)
      }
    }
  })
})
