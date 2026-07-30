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
    classWideEndRows: [
      { label: '按单项计提坏账准备', bookAmount: 500, ratio: 38.46, provision: 50, lossRate: 10, carryingValue: 450 },
      { label: '按组合计提坏账准备', bookAmount: 800, ratio: 61.54, provision: 80, lossRate: 10, carryingValue: 720 },
      { label: '合计', bookAmount: 1300, ratio: 100, provision: 130, lossRate: 10, carryingValue: 1170, isTotal: true },
    ],
    classWidePriorRows: [
      { label: '按单项计提坏账准备', bookAmount: 400, ratio: 40, provision: 40, lossRate: 10, carryingValue: 360 },
      { label: '按组合计提坏账准备', bookAmount: 600, ratio: 60, provision: 60, lossRate: 10, carryingValue: 540 },
      { label: '合计', bookAmount: 1000, ratio: 100, provision: 100, lossRate: 10, carryingValue: 900, isTotal: true },
    ],
    individualRows: [
      { name: 'A公司', endAmount: 300, priorAmount: 200, provision: 30, priorProvision: 20, lossRate: 10, priorLossRate: 10, aging: '1年以内', basis: '预计无法收回' },
      { name: 'B公司', endAmount: 200, priorAmount: 200, provision: 20, priorProvision: 20, lossRate: 10, priorLossRate: 10, aging: '1-2年', basis: '诉讼中' },
    ],
    portfolios: [
      {
        name: '应收中央企业客户',
        rows: [
          { label: '1年以内', endAmount: 600, priorAmount: 400, provision: 60, priorProvision: 40, lossRate: 10, priorLossRate: 10 },
          { label: '1-2年', endAmount: 200, priorAmount: 200, provision: 20, priorProvision: 20, lossRate: 10, priorLossRate: 10 },
        ],
      },
    ],
    otherPortfolioRows: [{ label: '余额百分比组合', endAmount: 50, priorAmount: 40 }],
    movement: { priorBalance: 100, provision: 40, reversal: 5, writeOff: 3, transfer: 2, other: 0, endBalance: 130 },
    movementByCategory: [
      { label: '按单项计提坏账准备', priorAmount: 60, provisionAmount: 14, reversalAmount: 3, writeOffAmount: 1, endAmount: 70 },
      { label: '按账龄组合计提坏账准备', priorAmount: 40, provisionAmount: 26, reversalAmount: 4, writeOffAmount: 2, endAmount: 60 },
      { label: '合计', priorAmount: 100, provisionAmount: 40, reversalAmount: 7, writeOffAmount: 3, endAmount: 130, isTotal: true },
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
    derecognizedRows: [{ companyName: '应收账款保理', transferMethod: '不附追索权保理', amount: 100, gainLoss: -2 }],
    continuedInvolvementRows: [
      { item: '附追索权保理', transferMethod: '保理', assetAmount: 60, liabilityAmount: 55 },
    ],
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
    // 源模板 r66~r67：账龄 + 双期各（应收账款/坏账准备/预期信用损失率）
    expect(p.columns[name].map((c) => c.label)).toEqual([
      '账龄', '应收账款', '坏账准备', '预期信用损失率(%)', '应收账款', '坏账准备', '预期信用损失率(%)',
    ])
    expect(p.columns[name].map((c) => c.group)).toEqual([
      undefined, '期末余额', '期末余额', '期末余额', '上年年末余额', '上年年末余额', '上年年末余额',
    ])
  })

  it('上市账龄列头用期末余额/上年年末余额，国企用期末数/期初数', () => {
    const listed = buildD2SyncPayload('listed', 'wp-1', null, snap())
    expect(listed.columns[D2_TABLE_NAMES.listed.aging].map((c) => c.label)).toEqual(['账龄', '期末余额', '上年年末余额'])
    const soe = buildD2SyncPayload('soe', 'wp-2', null, snap())
    expect(soe.columns[D2_TABLE_NAMES.soe.aging].map((c) => c.label)).toEqual(['账龄', '期末数', '期初数'])
  })

  it('上市坏账准备变动表纵向 7 行（上年年末→期末，源模板 r117~r123）', () => {
    const p = buildD2SyncPayload('listed', 'wp-1', null, snap())
    const rows = p.sub_table_data[D2_TABLE_NAMES.listed.movement] as any[]
    expect(rows).toHaveLength(7)
    expect(rows.map((r) => r.label)).toEqual([
      '上年年末余额', '本期计提', '本期收回或转回', '本期核销', '本期转销', '其他', '期末余额',
    ])
    expect(rows[0]).toMatchObject({ amount: 100 })
    expect(rows[6]).toMatchObject({ amount: 130, is_total: true })
    expect(p.columns[D2_TABLE_NAMES.listed.movement].map((c) => c.label)).toEqual(['项目', '坏账准备金额'])
  })

  it('国企变动表 6 列且「本期变动金额」跨三子列分组（源模板 r94~r95）', () => {
    const p = buildD2SyncPayload('soe', 'wp-2', null, snap())
    expect(p.columns[D2_TABLE_NAMES.soe.movement].map((c) => c.label)).toEqual([
      '类 别', '期初数', '计提', '收回或转回', '转销或核销', '期末数',
    ])
    expect(p.columns[D2_TABLE_NAMES.soe.movement].map((c) => c.group)).toEqual([
      undefined, undefined, '本期变动金额', '本期变动金额', '本期变动金额', undefined,
    ])
    const rows = p.sub_table_data[D2_TABLE_NAMES.soe.movement] as any[]
    expect(rows).toHaveLength(3)
    expect(rows[2]).toMatchObject({
      label: '合 计',
      prior_amount: 100,
      provision_amount: 40,
      reversal_amount: 7,
      writeoff_amount: 3,
      end_amount: 130,
      is_total: true,
    })
  })

  it('国企单项计提明细列含坏账准备/账龄/预期信用损失率/计提理由', () => {
    const p = buildD2SyncPayload('soe', 'wp-2', null, snap())
    expect(p.columns[D2_TABLE_NAMES.soe.individualEnd].map((c) => c.label)).toEqual([
      '债务人名称', '账面余额', '坏账准备', '账龄', '预期信用损失率（%）', '计提理由',
    ])
    const rows = p.sub_table_data[D2_TABLE_NAMES.soe.individualEnd] as any[]
    expect(rows).toHaveLength(3) // 2 明细 + 合计
    expect(rows[2]).toMatchObject({ label: '合 计', end_amount: 500, provision: 50, is_total: true })
  })

  it('上市前五名合计列自动为应收账款+合同资产', () => {
    const p = buildD2SyncPayload('listed', 'wp-1', null, snap())
    const rows = p.sub_table_data[D2_TABLE_NAMES.listed.top5] as any[]
    expect(rows[0]).toMatchObject({ label: 'A公司', ar_amount: 300, contract_asset_amount: 20, total_amount: 320 })
    expect(rows[1]).toMatchObject({ label: '合 计', total_amount: 320, is_total: true })
  })

  it('_note_texts 只收非空说明并保持子节顺序', () => {
    const p = buildD2SyncPayload('listed', 'wp-1', null, snap())
    const texts = p.sub_table_data._note_texts as any[]
    expect(texts.map((t) => t.section)).toEqual(['note-aging', 'note-movement', 'note-top5'])
    expect(texts[0]).toMatchObject({ title: '按账龄披露说明', text: '账龄说明' })
  })

  it('buildD2NoteTexts 覆盖 10 个子节 key 且跳过空白', () => {
    expect(D2_NOTE_TEXT_SECTIONS.map((s) => s.key)).toEqual([
      'aging', 'badDebtClass', 'individual', 'portfolio', 'movement', 'writeOff', 'top5',
      'top5Summary', 'derecognition', 'continuedInvolvement',
    ])
    const all: Record<string, string> = {}
    for (const s of D2_NOTE_TEXT_SECTIONS) all[s.key] = `${s.key}-文本`
    expect(buildD2NoteTexts(all)).toHaveLength(10)
    expect(buildD2NoteTexts({ aging: '  ', top5: 'x' }).map((t) => t.section)).toEqual(['note-top5'])
  })

  it('空快照也产出全部表（表名齐备，行仅合计）', () => {
    const empty: D2DisclosureSnapshot = {
      agingRows: [], classRows: [], classWideEndRows: [], classWidePriorRows: [],
      individualRows: [], portfolios: [],
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

  // ─── 源模板列头契约（spec d2-ar-disclosure-template-alignment）──────────────

  it('Property 1 分类披露双期各 6 列，列头逐字对齐源模板 r23~r24', () => {
    const p = buildD2SyncPayload('listed', 'wp-1', null, snap())
    const expected = ['类 别', '金额', '比例(%)', '金额', '预期信用损失率(%)', '账面价值']
    const expectedGroups = [undefined, '账面余额', '账面余额', '坏账准备', '坏账准备', undefined]
    for (const key of [D2_TABLE_NAMES.listed.classEnd, D2_TABLE_NAMES.listed.classPrior]) {
      expect(p.columns[key].map((c) => c.label), key).toEqual(expected)
      expect(p.columns[key].map((c) => c.group), key).toEqual(expectedGroups)
    }
    const rows = p.sub_table_data[D2_TABLE_NAMES.listed.classEnd] as any[]
    expect(rows[0]).toMatchObject({
      label: '按单项计提坏账准备', book_amount: 500, ratio: 38.46, provision: 50, loss_rate: 10, carrying_value: 450,
    })
    expect(rows[2]).toMatchObject({ label: '合 计', is_total: true })
    // Property 3：账面价值 = 账面余额 − 坏账准备
    for (const r of rows) expect(r.carrying_value).toBeCloseTo(r.book_amount - r.provision, 6)
  })

  it('Property 1 单项计提双期各 5 列，合计行计提依据为 /（源模板 E56/E63）', () => {
    const p = buildD2SyncPayload('listed', 'wp-1', null, snap())
    const expected = ['名 称', '账面余额', '坏账准备', '预期信用损失率（%）', '计提依据']
    for (const key of [D2_TABLE_NAMES.listed.individualEnd, D2_TABLE_NAMES.listed.individualPrior]) {
      expect(p.columns[key].map((c) => c.label), key).toEqual(expected)
      const rows = p.sub_table_data[key] as any[]
      expect(rows).toHaveLength(3) // 2 明细 + 合计
      expect(rows[2]).toMatchObject({ label: '合 计', basis: '/', is_total: true })
    }
    const end = p.sub_table_data[D2_TABLE_NAMES.listed.individualEnd] as any[]
    expect(end[0]).toMatchObject({ label: 'A公司', book_amount: 300, provision: 30, loss_rate: 10 })
    expect(end[2]).toMatchObject({ book_amount: 500, provision: 50, loss_rate: 10 })
    const prior = p.sub_table_data[D2_TABLE_NAMES.listed.individualPrior] as any[]
    expect(prior[0]).toMatchObject({ label: 'A公司', book_amount: 200, provision: 20 })
    expect(prior[2]).toMatchObject({ book_amount: 400, provision: 40 })
  })

  it('Property 2 期末表与续表列 key 序列等长且 label 逐字相同', () => {
    const p = buildD2SyncPayload('listed', 'wp-1', null, snap())
    const pairs: Array<[string, string]> = [
      [D2_TABLE_NAMES.listed.classEnd, D2_TABLE_NAMES.listed.classPrior],
      [D2_TABLE_NAMES.listed.individualEnd, D2_TABLE_NAMES.listed.individualPrior],
    ]
    for (const [endKey, priorKey] of pairs) {
      const a = p.columns[endKey]
      const b = p.columns[priorKey]
      expect(b.map((c) => c.key)).toEqual(a.map((c) => c.key))
      expect(b.map((c) => c.label)).toEqual(a.map((c) => c.label))
    }
  })

  it('Property 6 上市载荷含终止确认与继续涉入两表（源模板 r160/r172）', () => {
    const p = buildD2SyncPayload('listed', 'wp-1', null, snap())

    const derKey = D2_TABLE_NAMES.listed.derecognized
    expect(p.columns[derKey].map((c) => c.label)).toEqual([
      '项  目', '转移方式', '终止确认金额', '与终止确认相关的利得或损失',
    ])
    const der = p.sub_table_data[derKey] as any[]
    expect(der[0]).toMatchObject({ label: '应收账款保理', transfer_method: '不附追索权保理', amount: 100, gain_loss: -2 })
    expect(der[1]).toMatchObject({ label: '合 计', amount: 100, gain_loss: -2, is_total: true })

    const ciKey = D2_TABLE_NAMES.listed.continuedInvolvement
    expect(p.columns[ciKey].map((c) => c.label)).toEqual([
      '项  目', '资产转移方式', '继续涉入形成的资产金额', '继续涉入形成的负债金额',
    ])
    const ci = p.sub_table_data[ciKey] as any[]
    expect(ci[0]).toMatchObject({ label: '附追索权保理', transfer_method: '保理', asset_amount: 60, liability_amount: 55 })
    expect(ci[1]).toMatchObject({ label: '合 计', asset_amount: 60, liability_amount: 55, is_total: true })
  })

  it('Property 3 组合分表双期损失率随行透传，合计行标记 is_total', () => {
    const p = buildD2SyncPayload('listed', 'wp-1', null, snap({
      portfolios: [{
        name: '组合1',
        rows: [
          { label: '1年以内', endAmount: 400, priorAmount: 200, provision: 20, priorProvision: 10, lossRate: 5, priorLossRate: 5 },
          { label: '合计', endAmount: 400, priorAmount: 200, provision: 20, priorProvision: 10, lossRate: 5, priorLossRate: 5, isTotal: true },
        ],
      }],
    }))
    const rows = p.sub_table_data[portfolioTableName('组合1')] as any[]
    expect(rows[0]).toMatchObject({
      label: '1年以内', end_amount: 400, end_provision: 20, end_loss_rate: 5,
      prior_amount: 200, prior_provision: 10, prior_loss_rate: 5,
    })
    expect(rows[1]).toMatchObject({ label: '合 计', is_total: true })
  })

  // ─── 国企源模板列头契约（spec d2-ar-disclosure-soe-alignment）───────────────

  it('SOE P1/P2 组合分表 7 列，双期各（应收账款/比例（%）/坏账准备）（源模板 r36~r38）', () => {
    const p = buildD2SyncPayload('soe', 'wp-2', null, snap({
      portfolios: [{
        name: '应收中央企业客户',
        rows: [
          { label: '1年以内（含1年）', endAmount: 600, priorAmount: 400, provision: 60, priorProvision: 40, ratio: 75, priorRatio: 66.67 },
          { label: '1至2年', endAmount: 200, priorAmount: 200, provision: 20, priorProvision: 20, ratio: 25, priorRatio: 33.33 },
        ],
      }],
    }))
    const key = portfolioTableName('应收中央企业客户')
    const cols = p.columns[key]
    expect(cols.map((c) => c.label)).toEqual([
      '账 龄', '应收账款', '比例（%）', '坏账准备', '应收账款', '比例（%）', '坏账准备',
    ])
    expect(cols.map((c) => c.group)).toEqual([
      undefined, '期末数', '期末数', '期末数', '期初数', '期初数', '期初数',
    ])
    // Property 2 双期同构：期末与期初子列 label 序列相同
    expect(cols.slice(1, 4).map((c) => c.label)).toEqual(cols.slice(4, 7).map((c) => c.label))
    const rows = p.sub_table_data[key] as any[]
    expect(rows[0]).toMatchObject({
      label: '1年以内（含1年）',
      end_amount: 600, end_ratio: 75, end_provision: 60,
      prior_amount: 400, prior_ratio: 66.67, prior_provision: 40,
    })
  })

  it('SOE P1/P2 其他组合方法 7 列，计提比例合计按合计口径重算（源模板 r82~r90）', () => {
    const p = buildD2SyncPayload('soe', 'wp-2', null, snap({
      otherPortfolioRows: [
        { label: '余额百分比组合', endAmount: 200, priorAmount: 100, provision: 10, priorProvision: 4, rate: 5, priorRate: 4 },
      ],
    }))
    const key = D2_TABLE_NAMES.soe.otherPortfolio
    const cols = p.columns[key]
    expect(cols.map((c) => c.label)).toEqual([
      '组合名称', '账面余额', '计提比例（%）', '坏账准备', '账面余额', '计提比例（%）', '坏账准备',
    ])
    expect(cols.map((c) => c.group)).toEqual([
      undefined, '期末数', '期末数', '期末数', '期初数', '期初数', '期初数',
    ])
    const rows = p.sub_table_data[key] as any[]
    expect(rows).toHaveLength(2)
    expect(rows[0]).toMatchObject({
      label: '余额百分比组合',
      end_amount: 200, end_rate: 5, end_provision: 10,
      prior_amount: 100, prior_rate: 4, prior_provision: 4,
    })
    expect(rows[1]).toMatchObject({
      label: '合 计', end_amount: 200, end_provision: 10, prior_amount: 100, prior_provision: 4, is_total: true,
    })
    expect(rows[1].end_rate).toBeCloseTo(5, 6)
    expect(rows[1].prior_rate).toBeCloseTo(4, 6)
  })

  it('SOE P4 继续涉入表按资产/负债分块，2 列且小计等于对应明细之和（源模板 r129~r136）', () => {
    const p = buildD2SyncPayload('soe', 'wp-2', null, snap({
      continuedInvolvementRows: [
        { item: '附追索权保理', transferMethod: '保理', assetAmount: 60, liabilityAmount: 55 },
        { item: '应收账款证券化', transferMethod: '证券化', assetAmount: 40, liabilityAmount: 35 },
      ],
    }))
    const key = D2_TABLE_NAMES.soe.continuedInvolvement
    expect(key).toBe('（7）应收账款转移继续涉入形成的资产、负债的金额')
    expect(p.columns[key].map((c) => c.label)).toEqual(['项  目', '期末金额'])
    const rows = p.sub_table_data[key] as any[]
    expect(rows.map((r) => r.label)).toEqual([
      '资产：', '附追索权保理', '应收账款证券化', '资产小计',
      '负债：', '附追索权保理', '应收账款证券化', '负债小计',
    ])
    expect(rows[3]).toMatchObject({ label: '资产小计', amount: 100, is_total: true })
    expect(rows[7]).toMatchObject({ label: '负债小计', amount: 90, is_total: true })
    // 上市 4 列宽表不出现在国企载荷
    expect(p.sub_table_data[D2_TABLE_NAMES.listed.continuedInvolvement]).toBeUndefined()
  })

  it('SOE 每张表要么显式分组要么显式 flat（禁止落入后端前缀推断）', () => {
    const p = buildD2SyncPayload('soe', 'wp-2', null, snap())
    for (const key of dataKeys(p)) {
      const cols = p.columns[key]
      const hasGroup = cols.some((c) => !!c.group)
      const hasFlat = cols.some((c) => c.flat === true)
      expect(hasGroup || hasFlat, `${key} 既无 group 也无 flat，会被前缀推断反猜出父表头`).toBe(true)
      // 两者互斥：显式分组表不应再标 flat（flat 会让后端返回 [] 抹掉分组）
      expect(hasGroup && hasFlat, `${key} 同时声明 group 与 flat`).toBe(false)
    }
    // 实测反例锚点：核销表列头共享「核销」前缀，必须靠 flat 压制
    expect(p.columns[D2_TABLE_NAMES.soe.writeOffDetail].some((c) => c.flat)).toBe(true)
  })

  it('SOE 固定表 11 张（不含动态组合分表）', () => {
    const p = buildD2SyncPayload('soe', 'wp-2', null, snap({ portfolios: [] }))
    // aging / classEnd / classEnd续 / individualEnd / otherPortfolio / movement /
    // reversal / writeOffDetail / top5 / derecognized / continuedInvolvement
    expect(dataKeys(p)).toHaveLength(11)
  })

  it('Property 7 上市载荷上报旧表名待清理，且不含本次推送的表名', () => {
    const p = buildD2SyncPayload('listed', 'wp-1', null, snap())
    const removed = p.sub_table_data._removed_table_keys as string[]
    expect(removed).toEqual([
      '按坏账计提方法分类披露（上年年末金额）',
      '按单项计提坏账准备的应收账款（上年年末金额）',
    ])
    for (const k of removed) expect(p.sub_table_data[k]).toBeUndefined()
    // 国企无历史遗留静态种子，且无持久化时不产出该键
    expect(buildD2SyncPayload('soe', 'wp-2', null, snap()).sub_table_data._removed_table_keys).toBeUndefined()
  })

  // ─── R6 账龄标签披露口径（spec disclosure-columns-coverage-rollout）──────────

  const agingSnap = () => snap({
    agingRows: [
      { key: 'within1', label: '1年以内', endAmount: 1000, priorAmount: 800 },
      { key: 'y1to2', label: '1-2年', endAmount: 300, priorAmount: 200 },
      { key: 'y2to3', label: '2-3年', endAmount: 0, priorAmount: 0 },
      { key: 'y3to4', label: '3-4年', endAmount: 0, priorAmount: 0 },
      { key: 'y4to5', label: '4-5年', endAmount: 0, priorAmount: 0 },
      { key: 'over5', label: '5年以上', endAmount: 0, priorAmount: 0 },
      { key: '__subtotal', label: '小计', endAmount: 1300, priorAmount: 1000 },
      { key: '__badDebt', label: '减：坏账准备', endAmount: 130, priorAmount: 100 },
      { key: '__total', label: '合计', endAmount: 1170, priorAmount: 900, isTotal: true },
    ],
  })

  it('R6 国企账龄行 label 映射为披露口径，首档带（含1年）', () => {
    const p = buildD2SyncPayload('soe', 'wp-2', null, agingSnap())
    const rows = p.sub_table_data[D2_TABLE_NAMES.soe.aging] as any[]
    expect(rows.map((r) => r.label)).toEqual([
      '1年以内（含1年）', '1至2年', '2至3年', '3至4年', '4至5年', '5年以上',
      '小 计', '减：坏账准备', '合 计',
    ])
    // 映射后仍正确标记合计行（is_total 用映射前的原始 label 判定）
    expect(rows[8]).toMatchObject({ label: '合 计', is_total: true, end_amount: 1170 })
    expect(rows[6].is_total).toBeUndefined()
  })

  it('R6 上市账龄行首档不带（含1年），其余同披露口径', () => {
    const p = buildD2SyncPayload('listed', 'wp-1', null, agingSnap())
    const rows = p.sub_table_data[D2_TABLE_NAMES.listed.aging] as any[]
    expect(rows.map((r) => r.label)).toEqual([
      '1年以内', '1至2年', '2至3年', '3至4年', '4至5年', '5年以上',
      '小 计', '减：坏账准备', '合 计',
    ])
  })

  it('R6 组合分表行 label 同样映射为披露口径', () => {
    const p = buildD2SyncPayload('soe', 'wp-2', null, snap({
      portfolios: [{
        name: '应收中央企业客户',
        rows: [
          { key: 'within1', label: '1年以内', endAmount: 600, priorAmount: 400, provision: 60, priorProvision: 40 },
          { key: 'y1to2', label: '1-2年', endAmount: 200, priorAmount: 200, provision: 20, priorProvision: 20 },
        ],
      }],
    }))
    const rows = p.sub_table_data[portfolioTableName('应收中央企业客户')] as any[]
    expect(rows.map((r) => r.label)).toEqual(['1年以内（含1年）', '1至2年'])
  })

  it('R6 自定义账龄段原样透传，不杜撰披露口径', () => {
    const p = buildD2SyncPayload('soe', 'wp-2', null, snap({
      agingRows: [
        { key: 'm0to6', label: '6个月以内', endAmount: 100, priorAmount: 50 },
        { key: 'custom_x', label: '自定义分段A', endAmount: 20, priorAmount: 10 },
      ],
    }))
    const rows = p.sub_table_data[D2_TABLE_NAMES.soe.aging] as any[]
    expect(rows.map((r) => r.label)).toEqual(['6个月以内', '自定义分段A'])
  })

  it('Property 8 映射不回写快照（底稿显示口径不变）', () => {
    const s = agingSnap()
    const before = s.agingRows.map((r) => r.label)
    buildD2SyncPayload('soe', 'wp-2', null, s)
    expect(s.agingRows.map((r) => r.label)).toEqual(before)
  })

  // ─── R7 孤儿表差集（spec disclosure-columns-coverage-rollout）────────────────

  it('R7 国企组合改名后上报旧表名待删除', () => {
    const p = buildD2SyncPayload('soe', 'wp-2', null, snap({
      portfolios: [{ name: '应收政府客户', rows: [] }],
      previouslySyncedTables: [
        '组合计提项目：应收中央企业客户',
        D2_TABLE_NAMES.soe.aging,
      ],
    }))
    expect(p.sub_table_data._removed_table_keys).toEqual(['组合计提项目：应收中央企业客户'])
    // 本次推送的表不在待删除列表里
    expect(p.sub_table_data[portfolioTableName('应收政府客户')]).toBeDefined()
  })

  it('Property 10 稳态幂等：上次已同步 = 本次推送 → 无待删除', () => {
    const first = buildD2SyncPayload('soe', 'wp-2', null, snap())
    const pushed = Object.keys(first.sub_table_data).filter((k) => !k.startsWith('_'))
    const second = buildD2SyncPayload('soe', 'wp-2', null, snap({ previouslySyncedTables: pushed }))
    expect(second.sub_table_data._removed_table_keys).toBeUndefined()
    expect(Object.keys(second.sub_table_data).filter((k) => !k.startsWith('_'))).toEqual(pushed)
  })

  it('R7 上市：持久化清单与历史遗留静态种子合并上报', () => {
    const p = buildD2SyncPayload('listed', 'wp-1', null, snap({
      previouslySyncedTables: ['组合计提项目：某旧组合'],
    }))
    expect(p.sub_table_data._removed_table_keys).toEqual([
      '组合计提项目：某旧组合',
      '按坏账计提方法分类披露（上年年末金额）',
      '按单项计提坏账准备的应收账款（上年年末金额）',
    ])
  })
})
