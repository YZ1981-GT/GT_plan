/**
 * G5 长期应收款披露 ↔ note_template 子表契约 + 载荷构建器单测
 *
 * spec: .kiro/specs/disclosure-sync-path-buildout/ Task 2.2
 */
import { describe, expect, it } from 'vitest'
import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import {
  G5_DISCLOSURE_SHEET_NAME,
  G5_LISTED_SUBTABLE,
  G5_NOTE_SECTION,
  G5_PORTFOLIO_PREFIX,
  G5_SOE_SUBTABLE,
  isG5DisclosureApplicable,
} from '../g5NoteSectionMap'
import {
  buildG5ContinuingRows,
  buildG5DerecogRows,
  buildG5IndividualRows,
  buildG5ListedColumns,
  buildG5ListedSubTableData,
  buildG5ListedSyncPayload,
  buildG5NatureRows,
  buildG5PortfolioRows,
  buildG5ProvisionRows,
  buildG5SoeColumns,
  buildG5SoeSyncPayload,
  g5PortfolioTableName,
  g5PortfolioTableNames,
} from '../g5DisclosureSyncPayload'

runDisclosureSubtableContract({
  cycle: 'G5',
  variants: [
    {
      variant: 'listed',
      section: G5_NOTE_SECTION.listed,
      subtables: {
        nature: G5_LISTED_SUBTABLE.nature,
        provision: G5_LISTED_SUBTABLE.provision,
        individualEnd: G5_LISTED_SUBTABLE.individualEnd,
        individualPrior: G5_LISTED_SUBTABLE.individualPrior,
        portfolioSeed: G5_LISTED_SUBTABLE.portfolioSeed,
        movement: G5_LISTED_SUBTABLE.movement,
        writeoff: G5_LISTED_SUBTABLE.writeoff,
        writeoffDetail: G5_LISTED_SUBTABLE.writeoffDetail,
      },
      columns: buildG5ListedColumns(),
    },
    {
      variant: 'soe',
      section: G5_NOTE_SECTION.soe,
      subtables: { ...G5_SOE_SUBTABLE },
      columns: buildG5SoeColumns(),
    },
  ],
})

const NATURE_ROWS = [
  { label: '融资租赁款', rowKey: 'lease', kind: 'preset', end: { balance: 1000, provision: 100 }, prior: { balance: 900, provision: 90 }, endDiscountRate: '4%~6%' },
  { label: '小计', rowKey: 'subtotal', kind: 'subtotal', end: { balance: 1000, provision: 100 }, prior: { balance: 900, provision: 90 } },
  { label: '合计', rowKey: 'total', kind: 'total', end: { balance: 800, provision: 90 }, prior: { balance: 700, provision: 80 } },
]

const METHOD_ROWS = [
  { label: '按单项计提坏账准备', rowKey: 'individual', kind: 'preset', end: { balance: 400, provision: 40 }, prior: { balance: 300, provision: 30 } },
  { label: '按组合计提坏账准备【注意：与会计政策中披露的组合保持一致】', rowKey: 'collective', kind: 'preset', end: { balance: 600, provision: 60 }, prior: { balance: 600, provision: 60 } },
  { label: '合计', rowKey: 'total', kind: 'total', end: { balance: 1000, provision: 100 }, prior: { balance: 900, provision: 90 } },
]

const INDIVIDUAL = [
  { name: '甲公司', endBalance: 400, endProvision: 40, endReason: '预计无法收回', priorBalance: 300, priorProvision: 30, priorReason: '同上' },
  { name: '', endBalance: 0, endProvision: 0, endReason: '' },
]

const PORTFOLIOS = [
  {
    name: '账龄组合',
    agingRows: [
      { label: '1年以内', kind: 'band', endBalance: 500, endProvision: 25, priorBalance: 400, priorProvision: 20 },
      { label: '1至2年', kind: 'band', endBalance: 100, endProvision: 35, priorBalance: 200, priorProvision: 40 },
      { label: '合计', kind: 'total', endBalance: 600, endProvision: 60 },
    ],
  },
  { name: '', agingRows: [] },
]

const LISTED_SNAP = {
  natureRows: NATURE_ROWS,
  methodRows: METHOD_ROWS,
  individualDetails: INDIVIDUAL,
  portfolios: PORTFOLIOS,
  movementRows: [
    { label: '期初余额', rowKey: 'opening', provision: 90 },
    { label: '期末余额', rowKey: 'closing', provision: 100 },
  ],
  writeoffRows: [{ name: '乙公司', amount: 50, reason: '破产清算', relatedParty: false }],
  unrealizedNote: '未实现融资收益按实际利率法摊销',
  noteText: '长期应收款附注说明',
}

const SOE_SNAP = {
  natureRows: NATURE_ROWS,
  derecogRows: [{ item: '应收租赁款', transferMethod: '保理', amount: 300, gainLoss: -5 }],
  continuing: { assetEnd: 120, liabilityEnd: 80 },
  provisionMethodNote: '采用简化方法计量',
  noteText: '国企口径说明',
}

describe('G5 章节映射与 sheet_name', () => {
  it('章节号取自 variant_matrix（chang_qi_ying_shou_kuan）', () => {
    expect(G5_NOTE_SECTION.listed).toBe('五、16')
    expect(G5_NOTE_SECTION.soe).toBe('八、17')
  })

  it('sheet 名为源 xlsx 真实 tab 名', () => {
    expect(G5_DISCLOSURE_SHEET_NAME.listed).toBe('附注披露信息（上市公司）')
    expect(G5_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露信息（国企）')
  })

  it('国企只 3 张表（坏账准备计提情况在国企附注模版里只有交叉引用、无表）', () => {
    expect(Object.keys(G5_SOE_SUBTABLE)).toHaveLength(3)
    expect(Object.values(G5_SOE_SUBTABLE).some((n) => n.includes('坏账准备'))).toBe(false)
  })

  it('续表名不是裸「续：」', () => {
    expect(G5_LISTED_SUBTABLE.individualPrior).toBe('按单项计提坏账准备（续：上年年末余额）')
  })

  it('「国有企业」写法识别为国企', () => {
    expect(isG5DisclosureApplicable('soe', ['国有企业单体'])).toBe(true)
    expect(isG5DisclosureApplicable('listed', ['国有企业单体'])).toBe(false)
  })
})

describe('G5 载荷构建器', () => {
  it('按性质披露：账面价值 = 账面余额 − 坏账准备；小计/合计带 is_total', () => {
    const rows = buildG5NatureRows('listed', NATURE_ROWS)
    expect(rows[0].end_net).toBe(900)
    expect(rows[0].prior_net).toBe(810)
    expect(rows[1].row_type).toBe('subtotal')
    expect(rows[1].is_total).toBe(true)
    expect(rows[2].row_type).toBe('total')
  })

  it('坏账准备计提情况：三级投影为两级，比例分母是非合计行之和', () => {
    const rows = buildG5ProvisionRows(METHOD_ROWS)
    expect(rows[0].end_gross_pct).toBeCloseTo(40, 4)
    expect(rows[1].end_gross_pct).toBeCloseTo(60, 4)
    expect(rows[0].end_provision_rate).toBeCloseTo(10, 4)
    expect(rows[0].end_net).toBe(360)
  })

  it('分母为 0 时比例写 null（不写 0，避免「0% 损失率」误读）', () => {
    const rows = buildG5ProvisionRows([
      { label: 'x', kind: 'preset', end: { balance: 0, provision: 0 }, prior: { balance: 0, provision: 0 } },
    ])
    expect(rows[0].end_provision_rate).toBeNull()
    expect(rows[0].end_gross_pct).toBeNull()
  })

  it('按单项计提：空行剔除，合计行「计提理由」列示为「/」', () => {
    const end = buildG5IndividualRows(INDIVIDUAL, 'end')
    expect(end).toHaveLength(2)
    expect(end[0].end_gross).toBe(400)
    expect(end.at(-1)!.end_reason).toBe('/')
    expect(end.at(-1)!.is_total).toBe(true)
  })

  it('续表用 prior_* 键（与期末表列键不同，防两表串键）', () => {
    const prior = buildG5IndividualRows(INDIVIDUAL, 'prior')
    expect(prior[0]).toHaveProperty('prior_gross', 300)
    expect(prior[0]).not.toHaveProperty('end_gross')
  })

  it('组合表：剔除底稿合计行后重算合计', () => {
    const rows = buildG5PortfolioRows(PORTFOLIOS[0].agingRows)
    expect(rows.map((r) => r.label)).toEqual(['1年以内', '1至2年', '合计'])
    expect(rows.at(-1)!.end_gross).toBe(600)
    expect(rows.at(-1)!.end_provision).toBe(60)
    expect(rows[1].end_rate).toBeCloseTo(35, 4)
  })

  it('组合表名 = 前缀 + 组合名；空名回退骨架名（不产 `组合计提项目：` 空后缀键）', () => {
    expect(g5PortfolioTableName('账龄组合')).toBe(`${G5_PORTFOLIO_PREFIX}账龄组合`)
    expect(g5PortfolioTableName('  ')).toBe(G5_LISTED_SUBTABLE.portfolioSeed)
    expect(g5PortfolioTableNames(PORTFOLIOS)).toEqual([
      `${G5_PORTFOLIO_PREFIX}账龄组合`,
      G5_LISTED_SUBTABLE.portfolioSeed,
    ])
  })

  it('终止确认合计行「与终止确认相关的利得或损失」为 null（源模版列示「--」）', () => {
    const rows = buildG5DerecogRows(SOE_SNAP.derecogRows)
    expect(rows.at(-1)!.derecognized_amount).toBe(300)
    expect(rows.at(-1)!.gain_or_loss).toBeNull()
  })

  it('继续涉入表：资产 / 负债两个分区各带小计', () => {
    const rows = buildG5ContinuingRows(SOE_SNAP.continuing)
    expect(rows.map((r) => r.label)).toEqual(['资产：', '资产小计', '负债：', '负债小计'])
    expect(rows[1].end_amount).toBe(120)
    expect(rows[3].end_amount).toBe(80)
  })

  it('上市 sub_table_data 含 8 张固定表 + 每个组合一张动态表', () => {
    const data = buildG5ListedSubTableData(LISTED_SNAP)
    const keys = Object.keys(data).filter((k) => !k.startsWith('_'))
    for (const name of Object.values(G5_LISTED_SUBTABLE)) {
      if (name === G5_LISTED_SUBTABLE.portfolioSeed) continue
      expect(keys, name).toContain(name)
    }
    expect(keys).toContain(`${G5_PORTFOLIO_PREFIX}账龄组合`)
  })

  it('文本域非空才进 _note_texts', () => {
    const data = buildG5ListedSubTableData({ ...LISTED_SNAP, unrealizedNote: ' ', noteText: '' })
    expect(data).not.toHaveProperty('_note_texts')
    const withText = buildG5ListedSubTableData(LISTED_SNAP)
    expect((withText._note_texts as unknown[])).toHaveLength(2)
  })

  it('组合改名 / 删除时上报 _removed_table_keys（防附注留孤儿表）', () => {
    const payload = buildG5ListedSyncPayload('wp-5', [], LISTED_SNAP, [
      `${G5_PORTFOLIO_PREFIX}旧组合`,
    ])!
    expect(payload.sub_table_data._removed_table_keys).toEqual([`${G5_PORTFOLIO_PREFIX}旧组合`])
  })

  it('载荷字段齐备；不适用变体 / 缺 wpId 返回 null', () => {
    const listed = buildG5ListedSyncPayload('wp-5', [], LISTED_SNAP)!
    expect(listed.section_id).toBe('五、16')
    expect(listed.current_standard).toBe('listed_standalone')
    const soe = buildG5SoeSyncPayload('wp-5', [], SOE_SNAP)!
    expect(soe.section_id).toBe('八、17')
    expect(buildG5ListedSyncPayload('wp-5', ['soe_standalone'], LISTED_SNAP)).toBeNull()
    expect(buildG5SoeSyncPayload('', [], SOE_SNAP)).toBeNull()
  })

  it('动态组合表也有 columns（否则附注侧降级为只显示行名）', () => {
    const payload = buildG5ListedSyncPayload('wp-5', [], LISTED_SNAP)!
    expect(payload.columns[`${G5_PORTFOLIO_PREFIX}账龄组合`]).toBeDefined()
    expect(payload.columns[`${G5_PORTFOLIO_PREFIX}账龄组合`][0].label).toBe('账龄')
  })
})
