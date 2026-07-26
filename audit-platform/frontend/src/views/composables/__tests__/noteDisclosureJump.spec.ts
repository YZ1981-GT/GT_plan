import { describe, expect, it } from 'vitest'
import {
  D1_DISCLOSURE_SHEET_LISTED,
  D1_DISCLOSURE_SHEET_SOE,
  E1_DISCLOSURE_SHEET_LISTED,
  E1_DISCLOSURE_SHEET_SOE,
  G1_DISCLOSURE_SHEET_LISTED,
  G1_DISCLOSURE_SHEET_SOE,
  G7_DISCLOSURE_SHEET_LISTED,
  G7_DISCLOSURE_SHEET_SOE,
  G10_DISCLOSURE_SHEET_LISTED,
  G10_DISCLOSURE_SHEET_SOE,
  I5_DISCLOSURE_SHEET_LISTED,
  I5_DISCLOSURE_SHEET_SOE,
  K11_DISCLOSURE_SHEET_LISTED,
  K11_DISCLOSURE_SHEET_SOE,
  K13_DISCLOSURE_SHEET_LISTED,
  K13_DISCLOSURE_SHEET_SOE,
  N1_DISCLOSURE_SHEET_LISTED,
  N1_DISCLOSURE_SHEET_SOE,
  isN1DeferredTaxNoteSection,
  isD1NotesReceivableNoteSection,
  isDerivativeFinancialAssetNoteSection,
  isE1MonetaryFundNoteSection,
  isG1TradingFinancialAssetNoteSection,
  isG7EquityNoteSection,
  isG10TradingLiabilityNoteSection,
  isG14CreditImpairmentNoteSection,
  isI5OtherNoncurrentNoteSection,
  isK11AssetImpairmentNoteSection,
  isK13NonOperatingExpenseNoteSection,
  isF1PrepaymentNoteSection,
  isF2InventoryNoteSection,
  isG11InvestmentIncomeNoteSection,
  isH2CipNoteSection,
  isI2DevelopmentExpenseNoteSection,
  isI3GoodwillNoteSection,
  isI4LongTermPrepaidNoteSection,
  isI6ResearchExpenseNoteSection,
  isK1OtherReceivableNoteSection,
  resolveNoteDisclosureJumpTarget,
} from '../noteDisclosureJump'

describe('noteDisclosureJump', () => {
  it('detects G7 equity note sections', () => {
    expect(isG7EquityNoteSection('五、18')).toBe(true)
    expect(isG7EquityNoteSection('八、18')).toBe(true)
    expect(isG7EquityNoteSection('七、本期纳入合并报表')).toBe(true)
    expect(isG7EquityNoteSection('四、货币资金')).toBe(false)
  })

  it('detects G10 trading liability note sections', () => {
    expect(isG10TradingLiabilityNoteSection('五、34')).toBe(true)
    expect(isG10TradingLiabilityNoteSection('八、35')).toBe(true)
    expect(isG10TradingLiabilityNoteSection('五、18')).toBe(false)
  })

  it('detects G14 credit impairment note sections', () => {
    expect(isG14CreditImpairmentNoteSection('三、信用减值损失')).toBe(true)
    expect(isG14CreditImpairmentNoteSection('八、73')).toBe(true)
    expect(isG14CreditImpairmentNoteSection('八、72')).toBe(false)
  })

  it('infers G14 listed disclosure from 三、信用减值损失', () => {
    const target = resolveNoteDisclosureJumpTarget({
      note_section: '三、信用减值损失',
      last_sync_wp_id: 'wp-g14',
    })
    expect(target?.wpCode).toBe('G14')
    expect(target?.variant).toBe('listed')
  })

  it('infers G14 SOE disclosure from 八、73', () => {
    expect(resolveNoteDisclosureJumpTarget({
      note_section: '八、73',
      source_template: 'soe',
    })?.wpCode).toBe('G14')
  })

  it('prefers synced listed disclosure sheet', () => {
    const target = resolveNoteDisclosureJumpTarget({
      note_section: '五、18',
      last_sync_wp_id: 'wp-1',
      table_data: {
        _last_sync_sheet: '附注披露信息（上市公司）',
        _current_standard: 'listed',
      },
    })
    expect(target).toEqual({
      sheet: G7_DISCLOSURE_SHEET_LISTED,
      wpId: 'wp-1',
      variant: 'listed',
      reason: '章节 五、18',
      wpCode: 'G7',
    })
  })

  it('infers G10 listed disclosure from 五、34', () => {
    const target = resolveNoteDisclosureJumpTarget({
      note_section: '五、34',
      last_sync_wp_id: 'wp-g10',
      table_data: { _last_sync_sheet: G10_DISCLOSURE_SHEET_LISTED },
    })
    expect(target?.sheet).toBe(G10_DISCLOSURE_SHEET_LISTED)
    expect(target?.wpCode).toBe('G10')
  })

  it('infers G10 SOE disclosure from 八、34', () => {
    expect(resolveNoteDisclosureJumpTarget({
      note_section: '八、34',
      source_template: 'soe',
    })?.sheet).toBe(G10_DISCLOSURE_SHEET_SOE)
  })

  it('detects G1 trading financial asset note sections (精确匹配 五、2/八、2)', () => {
    expect(isG1TradingFinancialAssetNoteSection('五、2')).toBe(true)
    expect(isG1TradingFinancialAssetNoteSection('八、2')).toBe(true)
    expect(isG1TradingFinancialAssetNoteSection('交易性金融资产')).toBe(true)
    // 精确匹配，不误伤 五、20~五、29
    expect(isG1TradingFinancialAssetNoteSection('五、20')).toBe(false)
    expect(isG1TradingFinancialAssetNoteSection('八、23')).toBe(false)
    // 不误伤 交易性金融负债（G10）
    expect(isG1TradingFinancialAssetNoteSection('交易性金融负债')).toBe(false)
  })

  it('infers G1 listed disclosure from 五、2', () => {
    const target = resolveNoteDisclosureJumpTarget({
      note_section: '五、2',
      last_sync_wp_id: 'wp-g1',
    })
    expect(target?.wpCode).toBe('G1')
    expect(target?.variant).toBe('listed')
    expect(target?.sheet).toBe(G1_DISCLOSURE_SHEET_LISTED)
  })

  it('infers G1 SOE disclosure from 八、2', () => {
    const target = resolveNoteDisclosureJumpTarget({
      note_section: '八、2',
      source_template: 'soe',
    })
    expect(target?.wpCode).toBe('G1')
    expect(target?.variant).toBe('soe')
    expect(target?.sheet).toBe(G1_DISCLOSURE_SHEET_SOE)
  })

  it('G1 五、2 不被 G10 syncedSheet(附注上市) 抢占', () => {
    // G1 与 G10 共用 sheet 名，章节 五、2 须解析为 G1 而非 G10
    const target = resolveNoteDisclosureJumpTarget({
      note_section: '五、2',
      table_data: { _last_sync_sheet: '附注上市' },
    })
    expect(target?.wpCode).toBe('G1')
  })

  it('G10 五、34 不被 G1 抢占', () => {
    expect(resolveNoteDisclosureJumpTarget({
      note_section: '五、34',
    })?.wpCode).toBe('G10')
  })

  it('detects 衍生金融资产 note sections (精确匹配 五、3/八、3)', () => {
    expect(isDerivativeFinancialAssetNoteSection('五、3')).toBe(true)
    expect(isDerivativeFinancialAssetNoteSection('八、3')).toBe(true)
    expect(isDerivativeFinancialAssetNoteSection('衍生金融资产')).toBe(true)
    // 精确匹配，不误伤 五、30~五、39
    expect(isDerivativeFinancialAssetNoteSection('五、30')).toBe(false)
    expect(isDerivativeFinancialAssetNoteSection('八、35')).toBe(false)
    // 不误伤 衍生金融负债（G10 五、35/八、35）
    expect(isDerivativeFinancialAssetNoteSection('衍生金融负债')).toBe(false)
  })

  it('infers G1 listed disclosure from 五、3 衍生金融资产', () => {
    const target = resolveNoteDisclosureJumpTarget({
      note_section: '五、3',
      last_sync_wp_id: 'wp-g1',
    })
    expect(target?.wpCode).toBe('G1')
    expect(target?.variant).toBe('listed')
    expect(target?.sheet).toBe(G1_DISCLOSURE_SHEET_LISTED)
    expect(target?.reason).toBe('章节 五、3')
  })

  it('infers G1 SOE disclosure from 八、3 衍生金融资产', () => {
    const target = resolveNoteDisclosureJumpTarget({
      note_section: '八、3',
      source_template: 'soe',
    })
    expect(target?.wpCode).toBe('G1')
    expect(target?.variant).toBe('soe')
    expect(target?.sheet).toBe(G1_DISCLOSURE_SHEET_SOE)
  })

  it('衍生金融资产 五、3 不被 G1 交易性 五、2 或 G10 抢占', () => {
    // 五、3 须命中衍生金融资产分支（wpCode G1）而非误落其他分支
    expect(resolveNoteDisclosureJumpTarget({
      note_section: '五、3',
      table_data: { _last_sync_sheet: '附注上市' },
    })?.reason).toBe('章节 五、3')
    // 五、2 仍是交易性金融资产
    expect(resolveNoteDisclosureJumpTarget({
      note_section: '五、2',
    })?.reason).toBe('章节 五、2')
  })

  it('infers SOE disclosure sheet from 七 / 八 chapters', () => {
    expect(resolveNoteDisclosureJumpTarget({
      note_section: '八、18',
      source_template: 'soe',
    })?.sheet).toBe(G7_DISCLOSURE_SHEET_SOE)

    expect(resolveNoteDisclosureJumpTarget({
      note_section: '七、本期发生的同一控',
      table_data: { _current_standard: 'soe' },
    })?.variant).toBe('soe')
  })

  it('infers H10 listed disclosure from 三、资产处置收益', () => {
    const target = resolveNoteDisclosureJumpTarget({
      note_section: '三、资产处置收益',
      last_sync_wp_id: 'wp-h10',
    })
    expect(target?.wpCode).toBe('H10')
    expect(target?.variant).toBe('listed')
    expect(target?.sheet).toBe('附注披露信息（上市公司）')
  })

  it('infers H10 SOE disclosure from 八、75', () => {
    const target = resolveNoteDisclosureJumpTarget({
      note_section: '八、75',
      source_template: 'soe',
    })
    expect(target?.wpCode).toBe('H10')
    expect(target?.variant).toBe('soe')
    expect(target?.sheet).toBe('附注披露信息（国有企业）')
  })

  it('detects I5 other noncurrent note sections', () => {
    expect(isI5OtherNoncurrentNoteSection('五、31')).toBe(true)
    expect(isI5OtherNoncurrentNoteSection('八、32')).toBe(true)
    expect(isI5OtherNoncurrentNoteSection('五、29')).toBe(false)
  })

  it('infers I5 listed disclosure from 五、31', () => {
    const target = resolveNoteDisclosureJumpTarget({
      note_section: '五、31',
      last_sync_wp_id: 'wp-i5',
    })
    expect(target?.wpCode).toBe('I5')
    expect(target?.variant).toBe('listed')
    expect(target?.sheet).toBe(I5_DISCLOSURE_SHEET_LISTED)
  })

  it('infers I5 SOE disclosure from 八、32', () => {
    expect(resolveNoteDisclosureJumpTarget({
      note_section: '八、32',
      source_template: 'soe',
    })?.sheet).toBe(I5_DISCLOSURE_SHEET_SOE)
  })

  it('detects K11 asset impairment note sections (区别于信用减值损失)', () => {
    expect(isK11AssetImpairmentNoteSection('资产减值损失（损失以“—”号填列）')).toBe(true)
    expect(isK11AssetImpairmentNoteSection('三、资产减值损失（损失以"-"号填列）')).toBe(true)
    expect(isK11AssetImpairmentNoteSection('八、74')).toBe(true)
    // 五、73 实为「外币货币性项目」，不得再误判为 K11（已修正历史错误映射）
    expect(isK11AssetImpairmentNoteSection('五、73')).toBe(false)
    // 不得误伤 G14 信用减值损失
    expect(isK11AssetImpairmentNoteSection('三、信用减值损失')).toBe(false)
  })

  it('infers K11 listed disclosure from 资产减值损失 keyword', () => {
    const target = resolveNoteDisclosureJumpTarget({
      note_section: '资产减值损失（损失以“—”号填列）',
      last_sync_wp_id: 'wp-k11',
    })
    expect(target?.wpCode).toBe('K11')
    expect(target?.variant).toBe('listed')
    expect(target?.sheet).toBe(K11_DISCLOSURE_SHEET_LISTED)
  })

  it('infers K11 SOE disclosure from 八、74 / soe 准则', () => {
    const target = resolveNoteDisclosureJumpTarget({
      note_section: '八、74',
      source_template: 'soe',
    })
    expect(target?.wpCode).toBe('K11')
    expect(target?.variant).toBe('soe')
    expect(target?.sheet).toBe(K11_DISCLOSURE_SHEET_SOE)
  })

  it('K11 资产减值损失 不与 G14 信用减值损失 冲突', () => {
    // G14 信用减值损失仍解析为 G14，不被 K11 抢占
    expect(resolveNoteDisclosureJumpTarget({
      note_section: '三、信用减值损失',
    })?.wpCode).toBe('G14')
  })

  it('detects K13 营业外支出 note sections (区别于营业外收入)', () => {
    expect(isK13NonOperatingExpenseNoteSection('营业外支出')).toBe(true)
    expect(isK13NonOperatingExpenseNoteSection('五、营业外支出')).toBe(true)
    // 不得误伤 K12 营业外收入
    expect(isK13NonOperatingExpenseNoteSection('营业外收入')).toBe(false)
  })

  it('infers K13 listed disclosure from 营业外支出 keyword', () => {
    const target = resolveNoteDisclosureJumpTarget({
      note_section: '营业外支出',
      last_sync_wp_id: 'wp-k13',
    })
    expect(target?.wpCode).toBe('K13')
    expect(target?.variant).toBe('listed')
    expect(target?.sheet).toBe(K13_DISCLOSURE_SHEET_LISTED)
  })

  it('infers K13 SOE disclosure from 八 章节 / soe 准则', () => {
    const target = resolveNoteDisclosureJumpTarget({
      note_section: '八、营业外支出',
      source_template: 'soe',
    })
    expect(target?.wpCode).toBe('K13')
    expect(target?.variant).toBe('soe')
    expect(target?.sheet).toBe(K13_DISCLOSURE_SHEET_SOE)
  })

  it('K13 营业外支出 不误伤 营业外收入(K12)', () => {
    expect(resolveNoteDisclosureJumpTarget({
      note_section: '营业外收入',
    })?.wpCode).not.toBe('K13')
  })

  it('detects E1 货币资金 note sections (五、1 精确匹配，不误伤 五、18=G7)', () => {
    expect(isE1MonetaryFundNoteSection('五、1')).toBe(true)
    expect(isE1MonetaryFundNoteSection('八、1')).toBe(true)
    expect(isE1MonetaryFundNoteSection('货币资金')).toBe(true)
    // 精确匹配：五、1 不得 startsWith 误伤 五、10~五、19
    expect(isE1MonetaryFundNoteSection('五、18')).toBe(false)
    expect(isE1MonetaryFundNoteSection('五、10')).toBe(false)
  })

  it('infers E1 listed disclosure from 五、1', () => {
    const target = resolveNoteDisclosureJumpTarget({
      note_section: '五、1',
      last_sync_wp_id: 'wp-e1',
    })
    expect(target?.wpCode).toBe('E1')
    expect(target?.variant).toBe('listed')
    expect(target?.sheet).toBe(E1_DISCLOSURE_SHEET_LISTED)
    expect(target?.wpId).toBe('wp-e1')
  })

  it('infers E1 SOE disclosure from 八、1', () => {
    const target = resolveNoteDisclosureJumpTarget({
      note_section: '八、1',
      source_template: 'soe',
    })
    expect(target?.wpCode).toBe('E1')
    expect(target?.variant).toBe('soe')
    expect(target?.sheet).toBe(E1_DISCLOSURE_SHEET_SOE)
  })

  it('E1 五、1 不被 G10 syncedSheet(附注上市) 抢占', () => {
    // E1 与 G1/G10 共用 sheet 名（附注上市），章节 五、1 须解析为 E1 而非 G10
    const target = resolveNoteDisclosureJumpTarget({
      note_section: '五、1',
      table_data: { _last_sync_sheet: '附注上市' },
    })
    expect(target?.wpCode).toBe('E1')
  })

  it('E1 五、1 不与 G7 五、18 冲突', () => {
    // 五、18 仍解析为 G7，不被 E1 五、1 抢占
    expect(resolveNoteDisclosureJumpTarget({
      note_section: '五、18',
    })?.wpCode).toBe('G7')
  })

  it('detects D1 应收票据 note sections (五、4 精确匹配，不误伤 五、40~五、49)', () => {
    expect(isD1NotesReceivableNoteSection('五、4')).toBe(true)
    expect(isD1NotesReceivableNoteSection('八、4')).toBe(true)
    expect(isD1NotesReceivableNoteSection('应收票据')).toBe(true)
    expect(isD1NotesReceivableNoteSection('五、40')).toBe(false)
    expect(isD1NotesReceivableNoteSection('五、44')).toBe(false)
    // 不误伤应收账款/应收款项融资
    expect(isD1NotesReceivableNoteSection('应收账款')).toBe(false)
  })

  it('infers D1 listed disclosure from 五、4', () => {
    const target = resolveNoteDisclosureJumpTarget({
      note_section: '五、4',
      last_sync_wp_id: 'wp-d1',
    })
    expect(target?.wpCode).toBe('D1')
    expect(target?.sheet).toBe(D1_DISCLOSURE_SHEET_LISTED)
    expect(target?.variant).toBe('listed')
  })

  it('infers D1 SOE disclosure from 八、4', () => {
    const target = resolveNoteDisclosureJumpTarget({
      note_section: '八、4',
      source_template: 'soe',
    })
    expect(target?.wpCode).toBe('D1')
    expect(target?.sheet).toBe(D1_DISCLOSURE_SHEET_SOE)
    expect(target?.variant).toBe('soe')
  })

  it('D1 五、4 不与 G7 五、18 / E1 五、1 冲突', () => {
    expect(resolveNoteDisclosureJumpTarget({ note_section: '五、18' })?.wpCode).toBe('G7')
    expect(resolveNoteDisclosureJumpTarget({ note_section: '五、1' })?.wpCode).toBe('E1')
  })

  it('returns null for unrelated notes', () => {
    expect(resolveNoteDisclosureJumpTarget({
      note_section: '一、货币资金',
    })).toBeNull()
  })
})

// ── 9 个专有章节科目正向跳转（F1/F2/G11/H2/I2/I3/I4/I6/K1） ──
describe('noteDisclosureJump · 9 个专有章节科目', () => {
  it.each([
    ['五、7', '八、7', 'F1', '附注披露信息(上市公司)', '附注披露信息(国企)'],
    ['五、9', '八、10', 'F2', '附注披露信息（上市公司）', '附注披露信息（国企）'],
    ['五、69', '八、70', 'G11', '附注披露信息（上市公司）', '附注披露信息（国企）'],
    ['五、23', '八、23', 'H2', '附注披露信息（上市公司）', '附注披露信息（国有企业）'],
    ['五、27', '八、28', 'I2', '附注披露（上市公司）', '附注披露（国有企业）'],
    ['五、28', '八、29', 'I3', '附注披露（上市公司）', '附注披露（国有企业）'],
    ['五、29', '八、30', 'I4', '附注披露（上市公司）', '附注披露（国有企业）'],
    ['五、66', '八、67', 'I6', '附注披露（上市公司）', '附注披露（国有企业）'],
    ['五、8', '八、9', 'K1', '附注披露信息(上市公司）', '附注披露信息（国企）'],
  ])('章节 %s(listed)/%s(soe) → %s，正确 sheet', (listed, soe, wp, listedSheet, soeSheet) => {
    const t1 = resolveNoteDisclosureJumpTarget({ note_section: listed })
    expect(t1?.wpCode).toBe(wp)
    expect(t1?.variant).toBe('listed')
    expect(t1?.sheet).toBe(listedSheet)
    const t2 = resolveNoteDisclosureJumpTarget({ note_section: soe, source_template: 'soe' })
    expect(t2?.wpCode).toBe(wp)
    expect(t2?.variant).toBe('soe')
    expect(t2?.sheet).toBe(soeSheet)
  })

  it('🔴 纯编号精确匹配：八、7(F1) 与 八、70(G11) 不互相抢占', () => {
    expect(resolveNoteDisclosureJumpTarget({ note_section: '八、7', source_template: 'soe' })?.wpCode).toBe('F1')
    expect(resolveNoteDisclosureJumpTarget({ note_section: '八、70', source_template: 'soe' })?.wpCode).toBe('G11')
    // startsWith 反模式：八、7 不应命中 八、70
    expect(isF1PrepaymentNoteSection('八、70')).toBe(false)
    expect(isG11InvestmentIncomeNoteSection('八、7')).toBe(false)
  })

  it('🔴 五、8(K1)/五、9(F2) 精确匹配，不误伤 五、80+/五、90+', () => {
    expect(isK1OtherReceivableNoteSection('五、8')).toBe(true)
    expect(isK1OtherReceivableNoteSection('五、80')).toBe(false)
    expect(isF2InventoryNoteSection('五、9')).toBe(true)
    expect(isF2InventoryNoteSection('五、90')).toBe(false)
  })

  it('关键词兜底 & 排除项（应收利息/应收股利/工程物资/固定资产清理 无专有章节 → 不误配）', () => {
    expect(isH2CipNoteSection('在建工程')).toBe(true)
    expect(isH2CipNoteSection('工程物资')).toBe(false) // H4 工程物资并入或不适用，非在建工程
    expect(isI3GoodwillNoteSection('商誉')).toBe(true)
    expect(isI4LongTermPrepaidNoteSection('长期待摊费用')).toBe(true)
    expect(isI2DevelopmentExpenseNoteSection('开发支出')).toBe(true)
    expect(isK1OtherReceivableNoteSection('其他应收款')).toBe(true)
    // 应收利息/应收股利并入 K1 五、8（其他应收款），无独立跳转目标 → 关键词不匹配任何科目
    expect(resolveNoteDisclosureJumpTarget({ note_section: '应收利息' })).toBeNull()
    expect(resolveNoteDisclosureJumpTarget({ note_section: '应收股利' })).toBeNull()
  })

  it('新增章节不与既有 H1(五、22)/H8(五、25)/I1(五、26)/I5(五、31) 冲突', () => {
    expect(resolveNoteDisclosureJumpTarget({ note_section: '五、22' })?.wpCode).toBe('H1')
    expect(resolveNoteDisclosureJumpTarget({ note_section: '五、23' })?.wpCode).toBe('H2')
    expect(resolveNoteDisclosureJumpTarget({ note_section: '五、26' })?.wpCode).toBe('I1')
    expect(resolveNoteDisclosureJumpTarget({ note_section: '五、27' })?.wpCode).toBe('I2')
  })
})

// ── N1 递延所得税资产（五、30 / 八、31，与 N3 共用章节，默认落 N1） ──
describe('noteDisclosureJump · N1 递延所得税资产', () => {
  it('detects N1 note sections（精确匹配，不误伤 五、3 衍生金融资产）', () => {
    expect(isN1DeferredTaxNoteSection('五、30')).toBe(true)
    expect(isN1DeferredTaxNoteSection('八、31')).toBe(true)
    expect(isN1DeferredTaxNoteSection('递延所得税资产和递延所得税负债')).toBe(true)
    // 🔴 精确匹配：不得与 五、3（衍生金融资产）/ 八、3 混淆，也不吞 五、300 类未来章节
    expect(isN1DeferredTaxNoteSection('五、3')).toBe(false)
    expect(isN1DeferredTaxNoteSection('八、3')).toBe(false)
    expect(isN1DeferredTaxNoteSection('五、31')).toBe(false)  // 五、31 = I5 其他非流动资产
    expect(isN1DeferredTaxNoteSection('八、32')).toBe(false)  // 八、32 = I5 soe
    expect(isN1DeferredTaxNoteSection('五、300')).toBe(false)
  })

  it('infers N1 listed disclosure from 五、30', () => {
    const target = resolveNoteDisclosureJumpTarget({
      note_section: '五、30',
      last_sync_wp_id: 'wp-n1',
    })
    expect(target?.wpCode).toBe('N1')
    expect(target?.variant).toBe('listed')
    expect(target?.sheet).toBe(N1_DISCLOSURE_SHEET_LISTED)
    expect(target?.wpId).toBe('wp-n1')
  })

  it('infers N1 SOE disclosure from 八、31', () => {
    const target = resolveNoteDisclosureJumpTarget({
      note_section: '八、31',
      source_template: 'soe',
    })
    expect(target?.wpCode).toBe('N1')
    expect(target?.variant).toBe('soe')
    expect(target?.sheet).toBe(N1_DISCLOSURE_SHEET_SOE)
  })

  it('N1 五、30 不被通用披露 sheet 名回退抢占', () => {
    // 各循环披露 sheet 同名，须靠章节号精确命中
    expect(resolveNoteDisclosureJumpTarget({
      note_section: '五、30',
      table_data: { _last_sync_sheet: '附注披露信息（上市公司）' },
    })?.wpCode).toBe('N1')
  })

  it('N1 不抢占相邻章节（五、3 衍生=G1 / 五、31=I5 / 八、32=I5）', () => {
    expect(resolveNoteDisclosureJumpTarget({ note_section: '五、3' })?.wpCode).toBe('G1')
    expect(resolveNoteDisclosureJumpTarget({ note_section: '五、31' })?.wpCode).toBe('I5')
    expect(resolveNoteDisclosureJumpTarget({
      note_section: '八、32', source_template: 'soe',
    })?.wpCode).toBe('I5')
  })
})
