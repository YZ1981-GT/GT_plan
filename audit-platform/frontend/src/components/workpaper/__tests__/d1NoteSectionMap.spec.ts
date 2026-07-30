import { describe, expect, it } from 'vitest'
import {
  D1_NOTE_SECTION,
  D1_DISCLOSURE_SHEET_NAME,
  resolveD1CurrentStandard,
  buildD1SyncPayload,
  buildNoteTexts,
  type D1DisclosureSnapshot,
} from '../composables/d1NoteSectionMap'

function snap(overrides: Partial<D1DisclosureSnapshot> = {}): D1DisclosureSnapshot {
  const zeroSummary = {
    category: '', endBalance: 0, endProvision: 0, endBookValue: 0,
    priorBalance: 0, priorProvision: 0, priorBookValue: 0,
  }
  return {
    summaryRows: [
      { ...zeroSummary, category: '银行承兑汇票', endBalance: 1000, endProvision: 10, endBookValue: 990, priorBalance: 800, priorProvision: 8, priorBookValue: 792 },
      { ...zeroSummary, category: '商业承兑汇票', endBalance: 500, endProvision: 5, endBookValue: 495 },
    ],
    summaryTotal: { ...zeroSummary, category: '合计', endBalance: 1500, endProvision: 15, endBookValue: 1485, priorBalance: 800, priorProvision: 8, priorBookValue: 792 },
    pledgedRows: [{ category: '银行承兑票据', pledgedAmount: 200 }],
    pledgedTotal: { category: '合计', pledgedAmount: 200 },
    endorsedRows: [{ category: '银行承兑票据', derecognizedAmount: 300, notDerecognizedAmount: 0 }],
    endorsedTotal: { category: '合计', derecognizedAmount: 300, notDerecognizedAmount: 0 },
    transferRows: [{ category: '商业承兑票据', transferAmount: 50 }],
    transferTotal: { category: '合计', transferAmount: 50 },
    classEndRows: [
      { label: '按单项计提坏账准备', balance: 0, ratio: 0, provision: 0, lossRate: 0, bookValue: 0 },
      { label: '合计', balance: 1500, ratio: 1, provision: 15, lossRate: 0.01, bookValue: 1485 },
    ],
    classPriorRows: [{ label: '合计', balance: 800, ratio: 1, provision: 8, lossRate: 0.01, bookValue: 792 }],
    writeOffAmount: 0,
    writeOffDetailRows: [],
    notes: { top: '应收票据说明文本', pledged: '', endorsed: '背书说明', badDebtClass: '', writeOff: '' },
    ...overrides,
  }
}

describe('d1NoteSectionMap', () => {
  it('章节号冻结映射 五、4 / 八、4', () => {
    expect(D1_NOTE_SECTION.listed).toBe('五、4')
    expect(D1_NOTE_SECTION.soe).toBe('八、4')
  })

  it('resolveD1CurrentStandard 默认 standalone，含 consolidated 时升级', () => {
    expect(resolveD1CurrentStandard('listed', null)).toBe('listed_standalone')
    expect(resolveD1CurrentStandard('soe', [])).toBe('soe_standalone')
    expect(resolveD1CurrentStandard('listed', ['listed_consolidated'])).toBe('listed_consolidated')
  })

  it('listed sync payload 指向 五、4 + 主表名 应收票据 + 6 值列', () => {
    const p = buildD1SyncPayload('listed', 'wp-1', null, snap())
    expect(p.section_id).toBe('五、4')
    expect(p.sheet_name).toBe(D1_DISCLOSURE_SHEET_NAME.listed)
    const main = (p.sub_table_data['应收票据'] as any[])
    expect(main).toHaveLength(3) // 银承+商承+合计
    expect(main[0]).toMatchObject({ label: '银行承兑汇票', end_balance: 1000, end_provision: 10, end_book_value: 990 })
    expect(main[2]).toMatchObject({ label: '合计', is_total: true })
    // 列头 6 值列 + 标签列
    expect(p.columns['应收票据']).toHaveLength(7)
    expect(p.columns['应收票据'][0].is_label).toBe(true)
  })

  it('soe 主表名 应收票据分类，section 八、4', () => {
    const p = buildD1SyncPayload('soe', 'wp-2', null, snap())
    expect(p.section_id).toBe('八、4')
    expect(p.sub_table_data['应收票据分类']).toBeDefined()
    expect(p.sub_table_data['应收票据']).toBeUndefined()
  })

  it('_note_texts 只收非空说明，文本框内容与披露表一致', () => {
    const p = buildD1SyncPayload('listed', 'wp-1', null, snap())
    const texts = (p.sub_table_data._note_texts as any[])
    expect(texts.map(t => t.section)).toEqual(['note-top', 'note-endorsed'])
    expect(texts[0]).toMatchObject({ text: '应收票据说明文本' })
  })

  it('buildNoteTexts 跳过空白，保持子节顺序', () => {
    const texts = buildNoteTexts({ writeOff: '核销', top: '主表', badDebtClass: '  ' })
    expect(texts.map(t => t.section)).toEqual(['note-top', 'note-writeOff'])
  })

  it('质押/背书/转应收账款/坏账分类/核销 表格与列头齐备', () => {
    const p = buildD1SyncPayload('listed', 'wp-1', null, snap())
    expect(p.sub_table_data['期末已质押的应收票据']).toBeDefined()
    expect(p.sub_table_data['期末已背书或贴现但尚未到期的应收票据']).toBeDefined()
    expect(p.sub_table_data['期末因出票人未履约而将其转应收账款的票据']).toBeDefined()
    expect(p.sub_table_data['按坏账计提方法分类（期末余额）']).toBeDefined()
    expect(p.sub_table_data['按坏账计提方法分类（续：上年年末余额）']).toBeDefined()
    expect(p.sub_table_data['本期实际核销的应收票据情况']).toBeDefined()
    // 每张表都有对应列头
    for (const key of Object.keys(p.sub_table_data)) {
      if (key.startsWith('_')) continue
      expect(p.columns[key], `${key} 缺列头`).toBeDefined()
    }
  })

  it('listed 覆盖模板 14 张表（含单项/组合/变动/转回/核销逐项）', () => {
    const p = buildD1SyncPayload('listed', 'wp-1', null, snap())
    const keys = Object.keys(p.sub_table_data).filter(k => !k.startsWith('_'))
    expect(keys).toHaveLength(14)
    for (const name of [
      '按单项计提坏账准备的应收票据（期末余额）',
      '按单项计提坏账准备的应收票据（续：上年年末余额）',
      '组合计提项目：银行承兑汇票',
      '组合计提项目：商业承兑汇票',
      '本期计提、收回或转回的坏账准备情况',
      '本期转回或收回金额重要的坏账准备',
      '重要的应收票据核销情况（逐项披露）',
    ]) {
      expect(p.sub_table_data[name], `${name} 未推送`).toBeDefined()
      expect(p.columns[name], `${name} 缺列头`).toBeDefined()
    }
  })

  it('listed 坏账准备变动表纵向 7 行（项目/坏账准备金额）', () => {
    const p = buildD1SyncPayload('listed', 'wp-1', null, snap({
      movementTotal: { priorBalance: 8, provision: 10, reversal: 1, writeOff: 2, transfer: 0, other: 0, endBalance: 15 },
    }))
    const rows = p.sub_table_data['本期计提、收回或转回的坏账准备情况'] as any[]
    expect(rows).toHaveLength(7)
    expect(rows[0]).toMatchObject({ label: '上年年末数', amount: 8 })
    expect(rows[6]).toMatchObject({ label: '期末数', amount: 15, is_total: true })
    expect(p.columns['本期计提、收回或转回的坏账准备情况'].map(c => c.label)).toEqual(['项目', '坏账准备金额'])
  })

  it('soe 表名与模板一致（期初口径 + 组合单表 + 变动多列）', () => {
    const p = buildD1SyncPayload('soe', 'wp-2', null, snap({
      soeMovementRows: [{ label: '合计', priorBalance: 1, provision: 2, reversal: 0, writeOff: 0, transfer: 0, other: 0, endBalance: 3 }],
    }))
    const keys = Object.keys(p.sub_table_data).filter(k => !k.startsWith('_'))
    expect(keys).toHaveLength(12)
    expect(p.sub_table_data['按坏账准备计提方法分类披露应收票据（期末数）']).toBeDefined()
    expect(p.sub_table_data['按坏账准备计提方法分类披露应收票据（续：期初数）']).toBeDefined()
    expect(p.sub_table_data['按组合计提坏账准备的应收票据']).toBeDefined()
    expect(p.sub_table_data['期末因出票人未履约而其转为应收账款的票据']).toBeDefined()
    expect(p.sub_table_data['本期实际核销的应收票据']).toBeDefined()
    // 国企主表：期间由父表头承载（源模板 B6:D6「期末数」/ E6:G6「期初数」），
    // 子列名按预设 F4-3a 取「账面余额 / 坏账准备 / 账面价值」
    const mainCols = p.columns['应收票据分类']
    expect(mainCols.map(c => c.label)).toEqual([
      '票据种类', '账面余额', '坏账准备', '账面价值', '账面余额', '坏账准备', '账面价值',
    ])
    expect(mainCols.map(c => c.group ?? null)).toEqual([
      null, '期末数', '期末数', '期末数', '期初数', '期初数', '期初数',
    ])
    const mv = p.sub_table_data['本期计提、收回或转回的应收票据坏账准备情况'] as any[]
    expect(mv[0]).toMatchObject({ label: '合计', prior_balance: 1, end_balance: 3, is_total: true })
  })

  it('组合计提明细按名称合并期末/上年末，缺失侧为 0', () => {
    const p = buildD1SyncPayload('listed', 'wp-1', null, snap({
      bankPortfolioEndRows: [{ drawerTypeOrAging: '1年以内', balance: 100, provision: 1, lossRate: 0.01 }],
      bankPortfolioPriorRows: [{ drawerTypeOrAging: '1至2年', balance: 50, provision: 2, lossRate: 0.04 }],
    }))
    const rows = p.sub_table_data['组合计提项目：银行承兑汇票'] as any[]
    expect(rows).toHaveLength(3) // 1年以内 + 1至2年 + 合计
    expect(rows[0]).toMatchObject({ label: '1年以内', end_balance: 100, prior_balance: 0 })
    expect(rows[1]).toMatchObject({ label: '1至2年', end_balance: 0, prior_balance: 50 })
    expect(rows[2]).toMatchObject({ label: '合计', end_balance: 100, prior_balance: 50, is_total: true })
  })

  it('比率列同步为百分数（与披露表 fmtPct 口径一致，附注表头带 %）', () => {
    const p = buildD1SyncPayload('listed', 'wp-1', null, snap({
      classDisplayEndRows: [{ label: '按单项计提坏账准备', balance: 1000, ratio: 0.25, provision: 10, lossRate: 0.01, bookValue: 990 }],
      individualEndRows: [{ name: 'A公司', balance: 100, provision: 5, lossRate: 0.05, basis: '' }],
      bankPortfolioEndRows: [{ drawerTypeOrAging: '1年以内', balance: 100, provision: 2, lossRate: 0.02 }],
    }))
    const cls = (p.sub_table_data['按坏账计提方法分类（期末余额）'] as any[])[0]
    expect(cls).toMatchObject({ ratio: 25, loss_rate: 1 })
    const ind = (p.sub_table_data['按单项计提坏账准备的应收票据（期末余额）'] as any[])[0]
    expect(ind).toMatchObject({ loss_rate: 5 })
    const pf = (p.sub_table_data['组合计提项目：银行承兑汇票'] as any[])[0]
    expect(pf).toMatchObject({ end_loss_rate: 2 })
  })

  it('披露 sheet 名使用底稿真实 tab 名（全角括号）', () => {
    expect(D1_DISCLOSURE_SHEET_NAME.listed).toBe('附注披露信息（上市公司）')
    expect(D1_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露信息（国企）')
  })

  it('转回或收回表：上市 5 列 / 国企 4 列（各按自身模板，不互相硬套）', () => {
    const reversalRows = [
      {
        companyName: 'A公司',
        reversalReason: '客户回款',
        originalMethod: '银行转账',
        reversalBasis: '累计已计提 12',
        amount: 100,
        // 国企「转回或收回前累计已计提坏账准备金额」源模板 C59==SUM → 数值列
        cumulativeProvision: 12,
      },
    ]
    const listed = buildD1SyncPayload('listed', 'wp-1', null, snap({ reversalRows } as any))
    const lc = listed.columns['本期转回或收回金额重要的坏账准备'].map((c) => c.label)
    expect(lc).toEqual(['单位名称', '转回原因', '收回方式', '原确定坏账准备的依据', '转回或收回金额'])
    const lr = (listed.sub_table_data['本期转回或收回金额重要的坏账准备'] as any[])[0]
    expect(lr).toMatchObject({ label: 'A公司', recovery_method: '银行转账', original_basis: '累计已计提 12', amount: 100 })

    const soe = buildD1SyncPayload('soe', 'wp-2', null, snap({ reversalRows } as any))
    const sc = soe.columns['本期转回或收回金额重要的应收票据坏账准备'].map((c) => c.label)
    expect(sc).toEqual([
      '债务人名称',
      '转回或收回金额',
      '转回或收回前累计已计提坏账准备金额',
      '转回或收回原因、方式',
    ])
    const sr = (soe.sub_table_data['本期转回或收回金额重要的应收票据坏账准备'] as any[])[0]
    expect(sr).toMatchObject({
      label: 'A公司',
      amount: 100,
      cumulative_provision: 12,
      reason_method: '客户回款',
    })
    // 数值列进合计行（源模板 C59==SUM(C55:C58)）
    const st = (soe.sub_table_data['本期转回或收回金额重要的应收票据坏账准备'] as any[]).at(-1)
    expect(st).toMatchObject({ label: '合计', amount: 100, cumulative_provision: 12, is_total: true })
    expect(soe.columns['本期转回或收回金额重要的应收票据坏账准备']
      .find((c) => c.key === 'cumulative_provision')?.format).toBe('amount')
  })

  it('核销逐项披露列头按变体措辞（模板逐字）', () => {
    const rows = [{ companyName: 'B公司', noteType: '货款', amount: 20, reason: '无法收回', procedure: '已审批', relatedPartyFlag: '否' }]
    const listed = buildD1SyncPayload('listed', 'wp-1', null, snap({ writeOffDetailRows: rows } as any))
    expect(listed.columns['重要的应收票据核销情况（逐项披露）'].map((c) => c.label)).toEqual([
      '单位名称', '应收票据性质', '核销金额', '核销原因', '履行的核销程序', '款项是否由关联交易产生',
    ])
    const soe = buildD1SyncPayload('soe', 'wp-2', null, snap({ writeOffDetailRows: rows } as any))
    expect(soe.columns['重要的应收票据核销情况'].map((c) => c.label)).toEqual([
      '单位名称', '应收票据的性质', '核销金额', '核销原因', '履行的核销程序', '是否由关联交易产生',
    ])
  })
})
