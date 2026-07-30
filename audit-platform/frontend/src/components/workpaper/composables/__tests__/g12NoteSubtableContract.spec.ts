/**
 * G12 净敞口套期收益披露 ↔ note_template 子表契约 + 载荷构建器单测
 *
 * 5 条 Property 由共享 helper 参数化（P1 子表名逐字一致 / P2 章节号存在 /
 * P3 group·flat 表态 / P4 纯文本列头 / P5 标签列头 = headers[0]）。
 *
 * spec: .kiro/specs/disclosure-sync-path-buildout/ Task 2.8
 */
import { describe, expect, it } from 'vitest'
import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import {
  G12_DISCLOSURE_SHEET_NAME,
  G12_NOTE_SECTION,
  isG12DisclosureApplicable,
  resolveG12CurrentStandard,
  resolveG12NoteSectionTarget,
} from '../g12NoteSectionMap'
import {
  G12_LABEL_HEADER,
  G12_MAIN_SUBTABLE,
  G12_SUBTABLE,
  g12ColumnsFor,
  buildG12MainSubTableRows,
  buildG12SubTableData,
  buildG12SyncPayload,
  type G12SyncRow,
} from '../g12DisclosureSyncPayload'

runDisclosureSubtableContract({
  cycle: 'G12',
  variants: [
    {
      variant: 'listed',
      section: G12_NOTE_SECTION.listed,
      subtables: G12_SUBTABLE.listed,
      columns: g12ColumnsFor('listed'),
    },
    {
      variant: 'soe',
      section: G12_NOTE_SECTION.soe,
      subtables: G12_SUBTABLE.soe,
      columns: g12ColumnsFor('soe'),
    },
  ],
})

const LISTED_ROWS: G12SyncRow[] = [
  { rowKey: 'net_hedge', label: '净敞口套期收益', currentAmount: 1200.5, priorAmount: 800.25 },
]

const SOE_ROWS: G12SyncRow[] = [
  {
    rowKey: 'hedged_fv_to_pl',
    label: '净敞口套期下被套期项目累计公允价值变动转入当期损益的金额',
    currentAmount: 500,
    priorAmount: 300,
  },
  {
    rowKey: 'cf_reserve_to_pl',
    label: '净敞口套期下现金流量套期储备转入当期损益的金额',
    currentAmount: 700.5,
    priorAmount: 500.25,
  },
]

describe('G12 sheet_name 与章节映射', () => {
  it('sheet 名为源 xlsx 真实 tab 名（非合成标识、非短名）', () => {
    expect(G12_DISCLOSURE_SHEET_NAME.listed).toBe('附注披露信息（上市公司）')
    expect(G12_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露信息（国企）')
  })

  it('章节号取自 variant_matrix（jing_chang_kou_tao_qi_shou_yi）', () => {
    expect(G12_NOTE_SECTION.listed).toBe('五、70')
    expect(G12_NOTE_SECTION.soe).toBe('八、71')
  })

  it('未声明适用准则时两个变体都适用', () => {
    expect(isG12DisclosureApplicable('listed', [])).toBe(true)
    expect(isG12DisclosureApplicable('soe', undefined)).toBe(true)
  })

  it('声明了单一准则时另一变体不适用', () => {
    expect(isG12DisclosureApplicable('listed', ['soe_standalone'])).toBe(false)
    expect(isG12DisclosureApplicable('soe', ['listed_standalone'])).toBe(false)
  })

  it('「国有企业」写法也识别为国企（24 份源模板用此写法）', () => {
    expect(isG12DisclosureApplicable('soe', ['国有企业单体'])).toBe(true)
    expect(isG12DisclosureApplicable('listed', ['国有企业单体'])).toBe(false)
  })

  it('currentStandard 区分单体 / 合并', () => {
    expect(resolveG12CurrentStandard('listed', [])).toBe('listed_standalone')
    expect(resolveG12CurrentStandard('listed', ['listed_consolidated'])).toBe('listed_consolidated')
    expect(resolveG12CurrentStandard('soe', ['soe_consolidated'])).toBe('soe_consolidated')
  })

  it('不适用变体的 resolveTarget 返回 null', () => {
    expect(resolveG12NoteSectionTarget('listed', ['soe_standalone'])).toBeNull()
    expect(resolveG12NoteSectionTarget('soe', ['soe_standalone'])).not.toBeNull()
  })
})

describe('G12 载荷构建器', () => {
  it('合计行由明细行求和（不接受外部传入，避免双真源）', () => {
    const rows = buildG12MainSubTableRows(SOE_ROWS)
    expect(rows).toHaveLength(3)
    const total = rows.at(-1)!
    expect(total.is_total).toBe(true)
    expect(total.label).toBe('合计')
    expect(total.current_amount).toBeCloseTo(1200.5, 6)
    expect(total.prior_amount).toBeCloseTo(800.25, 6)
  })

  it('非数值金额归零，不产出 NaN', () => {
    const rows = buildG12MainSubTableRows([
      { rowKey: 'x', label: 'x', currentAmount: NaN, priorAmount: undefined as never },
    ])
    expect(rows[0].current_amount).toBe(0)
    expect(rows.at(-1)!.prior_amount).toBe(0)
  })

  it('每行带 row_key（便于附注侧回溯底稿行）', () => {
    const rows = buildG12MainSubTableRows(SOE_ROWS)
    expect(rows.slice(0, 2).map((r) => r.row_key)).toEqual(['hedged_fv_to_pl', 'cf_reserve_to_pl'])
  })

  it('附注说明非空才进 _note_texts', () => {
    expect(buildG12SubTableData('listed', { rows: LISTED_ROWS, noteText: '  ' })).not.toHaveProperty(
      '_note_texts',
    )
    const withText = buildG12SubTableData('listed', { rows: LISTED_ROWS, noteText: ' 说明 ' })
    expect(withText._note_texts).toEqual([{ section: 'listed-disclosure-note', text: '说明' }])
  })

  it('载荷字段齐备且 sheet_name / section_id 取常量', () => {
    const payload = buildG12SyncPayload('wp-1', 'soe', [], { rows: SOE_ROWS, noteText: '' })!
    expect(payload.wp_id).toBe('wp-1')
    expect(payload.sheet_name).toBe(G12_DISCLOSURE_SHEET_NAME.soe)
    expect(payload.section_id).toBe(G12_NOTE_SECTION.soe)
    expect(payload.current_standard).toBe('soe_standalone')
    expect(Object.keys(payload.sub_table_data)).toEqual([G12_MAIN_SUBTABLE])
    expect(payload.columns[G12_MAIN_SUBTABLE]).toHaveLength(3)
  })

  it('不适用变体 / 缺 wpId 时返回 null（不得同步到不适用章节）', () => {
    expect(buildG12SyncPayload('wp-1', 'listed', ['soe_standalone'], { rows: [], noteText: '' })).toBeNull()
    expect(buildG12SyncPayload('', 'soe', [], { rows: SOE_ROWS, noteText: '' })).toBeNull()
  })

  it('标签列头两版不同且与模板 headers[0] 对齐（P5 已由 helper 断言）', () => {
    expect(G12_LABEL_HEADER.listed).toBe('项目')
    expect(G12_LABEL_HEADER.soe).toBe('产生净敞口套期收益的来源')
    expect(g12ColumnsFor('soe')[G12_MAIN_SUBTABLE][0].label).toBe(G12_LABEL_HEADER.soe)
  })

  it('columns 显式标 flat（源模板单级表头，防后端前缀反猜父表头）', () => {
    for (const variant of ['listed', 'soe'] as const) {
      const cols = g12ColumnsFor(variant)[G12_MAIN_SUBTABLE]
      expect(cols.some((c) => c.flat)).toBe(true)
      expect(cols.some((c) => c.group)).toBe(false)
    }
  })
})

/** 行对象的非数据键（不参与列头映射） */
const META_KEYS = new Set(['row_type', 'is_total', 'row_key'])

describe('G12 Property 1：columns 键 ≡ sub_table_data 数据键（双向）', () => {
  it.each([
    ['listed', LISTED_ROWS],
    ['soe', SOE_ROWS],
  ] as const)('%s 每张表的列键集与行字段键集完全一致', (variant, rows) => {
    const payload = buildG12SyncPayload('wp-1', variant, [], { rows, noteText: 'n' })!
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
