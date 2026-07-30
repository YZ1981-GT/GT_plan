/**
 * G4 债权投资披露 ↔ note_template 子表契约 + 载荷构建器单测
 *
 * spec: .kiro/specs/disclosure-sync-path-buildout/ Task 2.1
 */
import { describe, expect, it } from 'vitest'
import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import {
  G4_DISCLOSURE_SHEET_NAME,
  G4_MAIN_SUBTABLE,
  G4_NOTE_SECTION,
  G4_NOT_SYNCED_TABLES,
  G4_STAGE_SUBTABLE,
  isG4DisclosureApplicable,
  normalizeG4StageTableName,
} from '../g4NoteSectionMap'
import {
  g4ColumnsFor,
  buildG4MainRows,
  buildG4StageRows,
  buildG4SubTableData,
  buildG4SyncPayload,
  g4StageTableNames,
  type G4StageBlockLike,
} from '../g4DisclosureSyncPayload'

/** 只把**实际推送**的表纳入 P1/P3/P5 契约（未推送的表见 G4_NOT_SYNCED_TABLES） */
function syncedSubtables(variant: 'listed' | 'soe'): Record<string, string> {
  const out: Record<string, string> = { main: G4_MAIN_SUBTABLE[variant] }
  G4_STAGE_SUBTABLE[variant].forEach((name, i) => {
    out[`stage${i + 1}`] = name
  })
  return out
}

const LISTED_BLOCKS: G4StageBlockLike[] = G4_STAGE_SUBTABLE.listed.map((title, i) => ({
  title,
  rateLabel: i === 0 || i === 3 ? '未来12个月内预期信用损失率(%)' : '整个存续期预期信用损失率(%)',
  reasonHeader: i === 0 ? '理由' : '划分依据',
  individual: { details: [{ name: `单项${i + 1}`, bookBalance: 1000, impairment: 50, reason: 'r' }] },
  portfolio: { details: [{ name: `组合${i + 1}`, bookBalance: 2000, impairment: 80, reason: 'r' }] },
}))

const SOE_BLOCKS: G4StageBlockLike[] = G4_STAGE_SUBTABLE.soe.map((title, i) => ({
  title: `${title}：`, // 底稿 title 带尾部冒号 → 同步前必须归一
  rateLabel: i === 0 ? '未来12个月内预期信用损失率(%)' : '整个存续期预期信用损失率(%)',
  reasonHeader: '理由',
  individual: { details: [{ name: `单项${i + 1}`, bookBalance: 500, impairment: 20, reason: 'r' }] },
  portfolio: { details: [] },
}))

const MAIN_ROWS = [
  { item: '项目一', endingBalance: 1000, endingImpairment: 100, priorBalance: 900, priorImpairment: 80 },
  { item: '小 计', endingBalance: 1000, endingImpairment: 100, priorBalance: 900, priorImpairment: 80 },
  { item: '减：一年内到期的债权投资', endingBalance: 200, endingImpairment: 10 },
  { item: '合 计', endingBalance: 800, endingImpairment: 90 },
]

runDisclosureSubtableContract({
  cycle: 'G4',
  variants: [
    {
      variant: 'listed',
      section: G4_NOTE_SECTION.listed,
      subtables: syncedSubtables('listed'),
      columns: g4ColumnsFor('listed', LISTED_BLOCKS),
    },
    {
      variant: 'soe',
      section: G4_NOTE_SECTION.soe,
      subtables: syncedSubtables('soe'),
      columns: g4ColumnsFor('soe', SOE_BLOCKS),
    },
  ],
})

describe('G4 章节映射与 sheet_name', () => {
  it('章节号取自 variant_matrix（zhai_quan_tou_zi）', () => {
    expect(G4_NOTE_SECTION.listed).toBe('五、14')
    expect(G4_NOTE_SECTION.soe).toBe('八、15')
  })

  it('sheet 名为源 xlsx 真实 tab 名', () => {
    expect(G4_DISCLOSURE_SHEET_NAME.listed).toBe('附注披露信息（上市公司）')
    expect(G4_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露信息（国企）')
  })

  it('主表名两版不同（上市「债权投资」/ 国企「债权投资情况」）', () => {
    expect(G4_MAIN_SUBTABLE.listed).toBe('债权投资')
    expect(G4_MAIN_SUBTABLE.soe).toBe('债权投资情况')
  })

  it('上市 6 张阶段表 / 国企 3 张（国企无上年对照）', () => {
    expect(G4_STAGE_SUBTABLE.listed).toHaveLength(6)
    expect(G4_STAGE_SUBTABLE.soe).toHaveLength(3)
  })

  it('国企阶段表名带顿号、上市不带（模板逐字差异）', () => {
    expect(G4_STAGE_SUBTABLE.soe.every((n) => n.includes('，'))).toBe(true)
    expect(G4_STAGE_SUBTABLE.listed.every((n) => !n.includes('，'))).toBe(true)
  })

  it('归一化去掉底稿 title 的尾部冒号（半角 / 全角）', () => {
    expect(normalizeG4StageTableName('期末，处于第一阶段的债权投资的减值准备：')).toBe(
      '期末，处于第一阶段的债权投资的减值准备',
    )
    expect(normalizeG4StageTableName(' 期末处于第一阶段的债权投资的减值准备:: ')).toBe(
      '期末处于第一阶段的债权投资的减值准备',
    )
  })

  it('「国有企业」写法识别为国企', () => {
    expect(isG4DisclosureApplicable('soe', ['国有企业单体'])).toBe(true)
    expect(isG4DisclosureApplicable('listed', ['国有企业单体'])).toBe(false)
  })

  it('未推送表清单每条都有理由（宁缺勿造，不推错位数字）', () => {
    const blank = Object.entries(G4_NOT_SYNCED_TABLES)
      .filter(([, r]) => !String(r ?? '').trim())
      .map(([k]) => k)
    expect(blank).toEqual([])
    expect(Object.keys(G4_NOT_SYNCED_TABLES).length).toBeGreaterThan(0)
  })
})

describe('G4 载荷构建器', () => {
  it('主表按标签判定 小计 / 合计 行型 —— 源模板的「小 计」带空格也要认', () => {
    const rows = buildG4MainRows(MAIN_ROWS)
    expect(rows[1].row_type).toBe('subtotal')
    expect(rows[1].is_total).toBe(true)
    expect(rows[2].row_type).toBe('data') // 「减：一年内到期…」不是合计行
    expect(rows[3].row_type).toBe('total')
    expect(rows[3].is_total).toBe(true)
  })

  it.each([
    ['小 计', 'subtotal'],
    ['小计', 'subtotal'],
    ['合 计', 'total'],
    ['合计', 'total'],
    ['减：一年内到期的债权投资', 'data'],
    ['项目1（可改名）', 'data'],
  ])('行型判定：%s → %s', (label, expected) => {
    expect(buildG4MainRows([{ item: label }])[0].row_type).toBe(expected)
  })

  it('主表账面价值 = 账面余额 − 减值准备（逐行、逐期）', () => {
    const rows = buildG4MainRows(MAIN_ROWS)
    expect(rows[0].end_net).toBe(900)
    expect(rows[0].prior_net).toBe(820)
  })

  it('国企主表用期末数 / 期初数分组（列头两版不同）', () => {
    const listed = g4ColumnsFor('listed', LISTED_BLOCKS)[G4_MAIN_SUBTABLE.listed]
    const soe = g4ColumnsFor('soe', SOE_BLOCKS)[G4_MAIN_SUBTABLE.soe]
    expect(listed.some((c) => c.group === '期末余额')).toBe(true)
    expect(soe.some((c) => c.group === '期末数')).toBe(true)
    expect(soe.some((c) => c.group === '期初数')).toBe(true)
  })

  it('阶段表名归一后与模板逐字一致（底稿 title 带冒号也不产孤儿表）', () => {
    expect(g4StageTableNames(SOE_BLOCKS)).toEqual([...G4_STAGE_SUBTABLE.soe])
  })

  it('阶段表行序与源模板一致：单项 → 其中： → 明细 → 组合 → 其中： → 明细 → 合计', () => {
    const rows = buildG4StageRows(LISTED_BLOCKS[0])
    expect(rows.map((r) => String(r.label))).toEqual([
      '按单项计提减值准备', '其中：', '单项1',
      '按组合计提减值准备', '其中：', '组合1',
      '合计',
    ])
    expect(rows.at(-1)!.is_total).toBe(true)
  })

  it('「其中：」结构行不丢（附注是交付物，缺了看不出明细归属）且列键齐备', () => {
    const rows = buildG4StageRows(LISTED_BLOCKS[0])
    const which = rows.filter((r) => r.label === '其中：')
    expect(which).toHaveLength(2)
    const colKeys = g4ColumnsFor('listed', LISTED_BLOCKS)[G4_STAGE_SUBTABLE.listed[0]].map(
      (c) => c.key,
    )
    for (const r of which) {
      for (const k of colKeys) expect(Object.keys(r)).toContain(k)
    }
  })

  it('父行 = 其下明细之和（单项 / 组合各自）', () => {
    const rows = buildG4StageRows(LISTED_BLOCKS[0])
    expect(rows[0].gross).toBe(1000)
    expect(rows[0].provision).toBe(50)
    expect(rows[3].gross).toBe(2000)
    expect(rows.at(-1)!.gross).toBe(3000)
    expect(rows.at(-1)!.provision).toBe(130)
  })

  it('阶段表首列标 flat（源模板单级表头）', () => {
    for (const name of G4_STAGE_SUBTABLE.listed) {
      const cols = g4ColumnsFor('listed', LISTED_BLOCKS)[name]
      expect(cols.some((c) => c.flat), name).toBe(true)
      expect(cols.some((c) => c.group), name).toBe(false)
    }
  })

  it('sub_table_data 只含已推送表（未推送表不出现，避免空表覆盖）', () => {
    const data = buildG4SubTableData('soe', {
      mainRows: MAIN_ROWS,
      stageBlocks: SOE_BLOCKS,
      stageNote: '',
      sectionTexts: {},
    })
    const keys = Object.keys(data).filter((k) => !k.startsWith('_'))
    expect(keys).toEqual([G4_MAIN_SUBTABLE.soe, ...G4_STAGE_SUBTABLE.soe])
    for (const forbidden of Object.keys(G4_NOT_SYNCED_TABLES)) {
      expect(keys).not.toContain(forbidden)
    }
  })

  it('载荷字段齐备；不适用变体 / 缺 wpId 返回 null', () => {
    const snap = { mainRows: MAIN_ROWS, stageBlocks: LISTED_BLOCKS, stageNote: 'n', sectionTexts: {} }
    const payload = buildG4SyncPayload('wp-4', 'listed', [], snap)!
    expect(payload.sheet_name).toBe(G4_DISCLOSURE_SHEET_NAME.listed)
    expect(payload.section_id).toBe('五、14')
    expect(payload.current_standard).toBe('listed_standalone')
    expect(buildG4SyncPayload('wp-4', 'listed', ['soe_standalone'], snap)).toBeNull()
    expect(buildG4SyncPayload('', 'soe', [], snap)).toBeNull()
  })
})
