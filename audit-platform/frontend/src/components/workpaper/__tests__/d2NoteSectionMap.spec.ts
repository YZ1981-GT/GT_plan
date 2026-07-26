import { describe, expect, it } from 'vitest'
import {
  D2_NOTE_SECTION,
  D2_DISCLOSURE_SHEET_NAME,
  D2_TABLE_NAMES,
  D2_NOTE_TEXT_SECTIONS,
  portfolioTableName,
  resolveD2CurrentStandard,
  buildD2SyncPayload,
  buildD2NoteTexts,
  type D2DisclosureSnapshot,
} from '../composables/d2NoteSectionMap'

function snap(overrides: Partial<D2DisclosureSnapshot> = {}): D2DisclosureSnapshot {
  return {
    agingRows: [
      { label: '1年以内', endAmount: 1000, priorAmount: 800 },
      { label: '1-2年', endAmount: 300, priorAmount: 200 },
      { label: '1年以内小计', endAmount: 1000, priorAmount: 800 },
      { label: '小计', endAmount: 1300, priorAmount: 1000 },
      { label: '减：坏账准备', endAmount: 130, priorAmount: 100 },
      { label: '合计', endAmount: 1170, priorAmount: 900, isTotal: true },
    ],
    classRows: [
      { label: '按单项计提坏账准备', endAmount: 500, priorAmount: 400 },
      { label: '其中：', endAmount: 0, priorAmount: 0 },
      { label: '按组合计提坏账准备', endAmount: 800, priorAmount: 600 },
      { label: '合计', endAmount: 1300, priorAmount: 1000, isTotal: true },
    ],
    individualRows: [
      { name: 'A公司', endAmount: 300, priorAmount: 200, provision: 30, aging: '1年以内', lossRate: 10, basis: '预计无法收回' },
      { name: 'B公司', endAmount: 200, priorAmount: 200, provision: 20, aging: '1-2年', lossRate: 10, basis: '诉讼中' },
    ],
    portfolios: [
      {
        name: '应收中央企业客户',
        rows: [
          { label: '1年以内', endAmount: 600, priorAmount: 400 },
          { label: '1-2年', endAmount: 200, priorAmount: 200 },
        ],
      },
    ],
    otherPortfolioRows: [{ label: '余额百分比组合', endAmount: 50, priorAmount: 40 }],
    movement: { priorBalance: 100, provision: 40, reversal: 5, writeOff: 3, transfer: 2, other: 0, endBalance: 130 },
    movementByCategory: [
      { label: '按单项计提坏账准备', priorAmount: 60, changeAmount: 10, endAmount: 70 },
      { label: '按账龄组合计提坏账准备', priorAmount: 40, changeAmount: 20, endAmount: 60 },
      { label: '合计', priorAmount: 100, changeAmount: 30, endAmount: 130, isTotal: true },
    ],
    reversalRows: [
      { companyName: 'C公司', reversalReason: '款项收回', recoveryMethod: '银行转账', originalBasis: '账龄组合', cumulativeProvision: 12, amount: 5 },
    ],
    writeOffAmount: 3,
    writeOffRows: [
      { companyName: 'D公司', nature: '货款', amount: 3, reason: '破产清算', procedure: '董事会审批', relatedParty: '否' },
    ],
    top5Rows: [
      { companyName: 'A公司', arAmount: 300, contractAssetAmount: 20, ratio: 24.62, provision: 30 },
    ],
    derecognizedRows: [{ companyName: 'E公司', amount: 100, gainLoss: -2 }],
    notes: { aging: '账龄说明', badDebtClass: '', individual: '  ', movement: '变动说明', top5: '前五名说明' },
    ...overrides,
  }
}

const dataKeys = (p: { sub_table_data: Record<string, unknown> }) =>
  Object.keys(p.sub_table_data).filter((k) => !k.startsWith('_'))

describe('d2NoteSectionMap', () => {
  it('章节号冻结映射 五、5 / 八、5', () => {
    expect(D2_NOTE_SECTION.listed).toBe('五、5')
    expect(D2_NOTE_SECTION.soe).toBe('八、5')
  })

  it('披露 sheet 名使用底稿真实 tab 名（半角括号）', () => {
    expect(D2_DISCLOSURE_SHEET_NAME.listed).toBe('附注披露信息(上市公司)')
    expect(D2_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露信息(国企)')
  })

  it('resolveD2CurrentStandard 默认 standalone，含 consolidated 时升级', () => {
    expect(resolveD2CurrentStandard('listed', null)).toBe('listed_standalone')
    expect(resolveD2CurrentStandard('soe', [])).toBe('soe_standalone')
    expect(resolveD2CurrentStandard('listed', ['listed_consolidated'])).toBe('listed_consolidated')
    expect(resolveD2CurrentStandard('soe', ['soe_consolidated'])).toBe('soe_consolidated')
  })

  it('listed payload 指向 五、5 且上市表名齐备', () => {
    const p = buildD2SyncPayload('listed', 'wp-1', null, snap())
    expect(p.section_id).toBe('五、5')
    expect(p.sheet_name).toBe(D2_DISCLOSURE_SHEET_NAME.listed)
    expect(p.wp_id).toBe('wp-1')
    for (const name of Object.values(D2_TABLE_NAMES.listed)) {
      expect(p.sub_table_data[name], `${name} 未推送`).toBeDefined()
    }
    // 国企专有表不应出现在上市载荷
    expect(p.sub_table_data[D2_TABLE_NAMES.soe.derecognized]).toBeUndefined()
    expect(p.sub_table_data[D2_TABLE_NAMES.soe.otherPortfolio]).toBeUndefined()
  })

  it('soe payload 指向 八、5 且国企表名齐备（含终止确认/其他组合）', () => {
    const p = buildD2SyncPayload('soe', 'wp-2', null, snap())
    expect(p.section_id).toBe('八、5')
    expect(p.sheet_name).toBe(D2_DISCLOSURE_SHEET_NAME.soe)
    for (const name of Object.values(D2_TABLE_NAMES.soe)) {
      expect(p.sub_table_data[name], `${name} 未推送`).toBeDefined()
    }
    // 上市拆表（续：上年年末余额）不应出现在国企载荷
    expect(p.sub_table_data[D2_TABLE_NAMES.listed.classPrior]).toBeUndefined()
    expect(p.sub_table_data[D2_TABLE_NAMES.listed.individualPrior]).toBeUndefined()
  })

  it('每张 sub_table 都有列头，且列头首列为标签列', () => {
    for (const variant of ['listed', 'soe'] as const) {
      const p = buildD2SyncPayload(variant, 'wp-1', null, snap())
      for (const key of dataKeys(p)) {
        const cols = p.columns[key]
        expect(cols, `${variant}/${key} 缺列头`).toBeDefined()
        expect(cols.length, `${variant}/${key} 列头为空`).toBeGreaterThan(1)
        expect(cols[0].is_label, `${variant}/${key} 首列非标签列`).toBe(true)
      }
    }
  })

  it('组合计提分表名为「组合计提项目：X」并随组合名动态生成', () => {
    expect(portfolioTableName('应收中央企业客户')).toBe('组合计提项目：应收中央企业客户')
    expect(portfolioTableName('  ')).toBe('组合计提项目：未命名组合')
    const p = buildD2SyncPayload('listed', 'wp-1', null, snap())
    const name = portfolioTableName('应收中央企业客户')
    expect(p.sub_table_data[name]).toBeDefined()
    expect(p.columns[name].map((c) => c.label)).toEqual(['账龄', '期末余额', '上年年末余额'])
  })

  it('上市账龄列头用期末余额/上年年末余额，国企用期末数/期初数', () => {
    const listed = buildD2SyncPayload('listed', 'wp-1', null, snap())
    expect(listed.columns[D2_TABLE_NAMES.listed.aging].map((c) => c.label)).toEqual(['账龄', '期末余额', '上年年末余额'])
    const soe = buildD2SyncPayload('soe', 'wp-2', null, snap())
    expect(soe.columns[D2_TABLE_NAMES.soe.aging].map((c) => c.label)).toEqual(['账龄', '期末数', '期初数'])
  })

  it('上市坏账准备变动表纵向 7 行（期初→期末）', () => {
    const p = buildD2SyncPayload('listed', 'wp-1', null, snap())
    const rows = p.sub_table_data[D2_TABLE_NAMES.listed.movement] as any[]
    expect(rows).toHaveLength(7)
    expect(rows.map((r) => r.label)).toEqual([
      '期初余额', '本期计提', '本期收回或转回', '本期核销', '本期转销', '其他', '期末余额',
    ])
    expect(rows[0]).toMatchObject({ amount: 100 })
    expect(rows[6]).toMatchObject({ amount: 130, is_total: true })
    expect(p.columns[D2_TABLE_NAMES.listed.movement].map((c) => c.label)).toEqual(['项目', '坏账准备金额'])
  })

  it('国企变动表列为 类别/期初数/本期变动金额/期末数（按类别行）', () => {
    const p = buildD2SyncPayload('soe', 'wp-2', null, snap())
    expect(p.columns[D2_TABLE_NAMES.soe.movement].map((c) => c.label)).toEqual([
      '类别', '期初数', '本期变动金额', '期末数',
    ])
    const rows = p.sub_table_data[D2_TABLE_NAMES.soe.movement] as any[]
    expect(rows).toHaveLength(3)
    expect(rows[2]).toMatchObject({ label: '合计', prior_amount: 100, change_amount: 30, end_amount: 130, is_total: true })
  })

  it('国企单项计提明细列含坏账准备/账龄/预期信用损失率/计提理由', () => {
    const p = buildD2SyncPayload('soe', 'wp-2', null, snap())
    expect(p.columns[D2_TABLE_NAMES.soe.individualEnd].map((c) => c.label)).toEqual([
      '债务人名称', '账面余额', '坏账准备', '账龄', '预期信用损失率（%）', '计提理由',
    ])
    const rows = p.sub_table_data[D2_TABLE_NAMES.soe.individualEnd] as any[]
    expect(rows).toHaveLength(3) // 2 明细 + 合计
    expect(rows[2]).toMatchObject({ label: '合计', end_amount: 500, provision: 50, is_total: true })
  })

  it('上市前五名合计列自动为应收账款+合同资产', () => {
    const p = buildD2SyncPayload('listed', 'wp-1', null, snap())
    const rows = p.sub_table_data[D2_TABLE_NAMES.listed.top5] as any[]
    expect(rows[0]).toMatchObject({ label: 'A公司', ar_amount: 300, contract_asset_amount: 20, total_amount: 320 })
    expect(rows[1]).toMatchObject({ label: '合计', total_amount: 320, is_total: true })
  })

  it('_note_texts 只收非空说明并保持子节顺序', () => {
    const p = buildD2SyncPayload('listed', 'wp-1', null, snap())
    const texts = p.sub_table_data._note_texts as any[]
    expect(texts.map((t) => t.section)).toEqual(['note-aging', 'note-movement', 'note-top5'])
    expect(texts[0]).toMatchObject({ title: '按账龄披露说明', text: '账龄说明' })
  })

  it('buildD2NoteTexts 覆盖 7 个子节 key 且跳过空白', () => {
    expect(D2_NOTE_TEXT_SECTIONS.map((s) => s.key)).toEqual([
      'aging', 'badDebtClass', 'individual', 'portfolio', 'movement', 'writeOff', 'top5',
    ])
    const all: Record<string, string> = {}
    for (const s of D2_NOTE_TEXT_SECTIONS) all[s.key] = `${s.key}-文本`
    expect(buildD2NoteTexts(all)).toHaveLength(7)
    expect(buildD2NoteTexts({ aging: '  ', top5: 'x' }).map((t) => t.section)).toEqual(['note-top5'])
  })

  it('空快照也产出全部表（表名齐备，行仅合计）', () => {
    const empty: D2DisclosureSnapshot = {
      agingRows: [], classRows: [], individualRows: [], portfolios: [],
      movement: { priorBalance: 0, provision: 0, reversal: 0, writeOff: 0, transfer: 0, other: 0, endBalance: 0 },
      reversalRows: [], writeOffAmount: 0, writeOffRows: [], top5Rows: [], notes: {},
    }
    const p = buildD2SyncPayload('soe', 'wp-3', null, empty)
    for (const name of Object.values(D2_TABLE_NAMES.soe)) {
      expect(p.sub_table_data[name], `${name} 未推送`).toBeDefined()
      expect(p.columns[name], `${name} 缺列头`).toBeDefined()
    }
    expect(p.sub_table_data._note_texts).toEqual([])
  })
})
