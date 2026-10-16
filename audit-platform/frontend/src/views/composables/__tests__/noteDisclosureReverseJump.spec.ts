import { describe, expect, it } from 'vitest'
import {
  DISCLOSURE_NOTE_SECTION_MAP,
  buildNoteJumpRoute,
  resolveNoteSectionForDisclosure,
} from '../noteDisclosureReverseJump'

describe('noteDisclosureReverseJump', () => {
  it('maps E1 listed → 五、1 and soe → 八、1', () => {
    expect(resolveNoteSectionForDisclosure('E1', 'listed')).toBe('五、1')
    expect(resolveNoteSectionForDisclosure('E1', 'soe')).toBe('八、1')
  })

  it('mirrors noteDisclosureJump section numbers (single source of truth)', () => {
    // 与正向 isE1MonetaryFundNoteSection 判定的 五、1 / 八、1 保持一致
    expect(DISCLOSURE_NOTE_SECTION_MAP.E1).toEqual({ listed: '五、1', soe: '八、1' })
  })

  it('maps G1 交易性 listed → 五、2 and soe → 八、2', () => {
    expect(resolveNoteSectionForDisclosure('G1', 'listed')).toBe('五、2')
    expect(resolveNoteSectionForDisclosure('G1', 'soe')).toBe('八、2')
  })

  it('maps G1_DERIVATIVE 衍生 listed → 五、3 and soe → 八、3', () => {
    expect(resolveNoteSectionForDisclosure('G1_DERIVATIVE', 'listed')).toBe('五、3')
    expect(resolveNoteSectionForDisclosure('G1_DERIVATIVE', 'soe')).toBe('八、3')
  })

  it('mirrors forward jump 衍生金融资产 section numbers (single source of truth)', () => {
    // 与正向 isDerivativeFinancialAssetNoteSection 判定的 五、3 / 八、3 保持一致
    expect(DISCLOSURE_NOTE_SECTION_MAP.G1_DERIVATIVE).toEqual({ listed: '五、3', soe: '八、3' })
  })

  it('builds 衍生金融资产 reverse jump route (listed/soe)', () => {
    expect((buildNoteJumpRoute('p1', 'G1_DERIVATIVE', 'listed') as any).query)
      .toEqual({ section: '五、3', noteTemplate: 'listed' })
    expect((buildNoteJumpRoute('p1', 'G1_DERIVATIVE', 'soe') as any).query)
      .toEqual({ section: '八、3', noteTemplate: 'soe' })
  })

  it('returns null for unknown wpCode', () => {
    expect(resolveNoteSectionForDisclosure('ZZ', 'listed')).toBeNull()
  })

  it('builds listed jump route with section + noteTemplate', () => {
    const route = buildNoteJumpRoute('p1', 'E1', 'listed') as any
    expect(route.path).toBe('/projects/p1/disclosure-notes')
    expect(route.query).toEqual({ section: '五、1', noteTemplate: 'listed' })
  })

  it('builds soe jump route (国企对国企)', () => {
    const route = buildNoteJumpRoute('p1', 'E1', 'soe') as any
    expect(route.query).toEqual({ section: '八、1', noteTemplate: 'soe' })
  })

  it('allows free switching listed↔soe from either disclosure tab', () => {
    // 无论从哪个披露 tab，都能构造上市或国企的跳转路由
    expect((buildNoteJumpRoute('p1', 'E1', 'listed') as any).query.noteTemplate).toBe('listed')
    expect((buildNoteJumpRoute('p1', 'E1', 'soe') as any).query.noteTemplate).toBe('soe')
  })

  it('includes year when provided', () => {
    const route = buildNoteJumpRoute('p1', 'E1', 'listed', 2025) as any
    expect(route.query.year).toBe('2025')
  })

  it('returns null when projectId missing', () => {
    expect(buildNoteJumpRoute('', 'E1', 'listed')).toBeNull()
  })

  // 新增：正向跳转 + 底稿→附注 sync 已具备、本轮仅补反向跳转的 6 科目
  // （章节号权威取自 note_template_variant_matrix.json，两变体均精确编号章节）
  it.each([
    ['G10', '五、34', '八、34'], // 交易性金融负债
    ['H1', '五、22', '八、22'],  // 固定资产
    ['H8', '五、25', '八、26'],  // 使用权资产
    ['H9', '五、47', '八、52'],  // 租赁负债
    ['I1', '五、26', '八、27'],  // 无形资产
    ['I5', '五、31', '八、32'],  // 其他非流动资产
  ])('maps %s listed→%s soe→%s and builds routes', (wp, listed, soe) => {
    expect(DISCLOSURE_NOTE_SECTION_MAP[wp]).toEqual({ listed, soe })
    expect((buildNoteJumpRoute('p1', wp, 'listed') as any).query).toEqual({ section: listed, noteTemplate: 'listed' })
    expect((buildNoteJumpRoute('p1', wp, 'soe') as any).query).toEqual({ section: soe, noteTemplate: 'soe' })
  })

  // 损益类：listed 用关键词标题（DB 可能截断，由 DisclosureEditor.resolveSectionInList 前缀模糊解析）；
  // soe 用清晰编号。
  it.each([
    ['G13', '五、75', '八、72'], // 公允价值变动收益
    ['G14', '五、76', '八、73'],     // 信用减值损失
    ['H10', '五、78', '八、75'], // 资产处置收益
  ])('maps 损益类 %s listed→%s soe→%s and builds routes', (wp, listed, soe) => {
    expect(DISCLOSURE_NOTE_SECTION_MAP[wp]).toEqual({ listed, soe })
    expect((buildNoteJumpRoute('p1', wp, 'listed') as any).query).toEqual({ section: listed, noteTemplate: 'listed' })
    expect((buildNoteJumpRoute('p1', wp, 'soe') as any).query).toEqual({ section: soe, noteTemplate: 'soe' })
  })

  // 对称补齐：正向已具备、本轮补反向的 11 个科目（章节号权威取自 DB note_section↔section_title）
  it.each([
    ['F1', '五、7', '八、7'],   // 预付款项
    ['F2', '五、9', '八、10'],  // 存货
    ['G11', '五、69', '八、70'], // 投资收益
    ['H2', '五、23', '八、23'], // 在建工程
    ['I2', '五、27', '八、28'], // 开发支出
    ['I3', '五、28', '八、29'], // 商誉
    ['I4', '五、29', '八、30'], // 长期待摊费用
    ['I6', '五、66', '八、67'], // 研发费用
    ['K1', '五、8', '八、9'],   // 其他应收款
    ['K11', '五、77', '八、74'], // 资产减值损失
    ['K13', '五、80', '八、77'],   // 营业外支出
  ])('对称补齐 %s listed→%s soe→%s and builds routes', (wp, listed, soe) => {
    expect(DISCLOSURE_NOTE_SECTION_MAP[wp]).toEqual({ listed, soe })
    expect((buildNoteJumpRoute('p1', wp, 'listed') as any).query).toEqual({ section: listed, noteTemplate: 'listed' })
    expect((buildNoteJumpRoute('p1', wp, 'soe') as any).query).toEqual({ section: soe, noteTemplate: 'soe' })
  })

  // D 循环其他科目（章节号权威取自 note_template listed/soe：预收款项/应收款项融资/合同资产/合同负债/营业收入）
  it.each([
    ['D3', '五、38', '八、38'], // 预收款项
    ['D5', '五、6', '八、6'],   // 应收款项融资
    ['D6', '五、10', '八、11'], // 合同资产
    ['D7', '五、39', '八、39'], // 合同负债
    ['D4', '五、62', '八、64'], // 营业收入和营业成本
  ])('D 循环 %s listed→%s soe→%s and builds routes', (wp, listed, soe) => {
    expect(DISCLOSURE_NOTE_SECTION_MAP[wp]).toEqual({ listed, soe })
    expect((buildNoteJumpRoute('p1', wp, 'listed') as any).query).toEqual({ section: listed, noteTemplate: 'listed' })
    expect((buildNoteJumpRoute('p1', wp, 'soe') as any).query).toEqual({ section: soe, noteTemplate: 'soe' })
  })
})

// 单一真源守卫：反向 map 的章节号必须被正向 isXxxNoteSection 判定接受，防两方向漂移
describe('reverse map ↔ forward jump 一致性（single source of truth）', () => {
  it('每个反向章节号都被对应正向判定接受', async () => {
    const fwd = await import('../noteDisclosureJump')
    const checks: Array<[string, (s: string) => boolean]> = [
      ['E1', fwd.isE1MonetaryFundNoteSection],
      ['D1', fwd.isD1NotesReceivableNoteSection],
      ['D3', fwd.isD3PrepaymentNoteSection],
      ['D5', fwd.isD5ReceivablesFinancingNoteSection],
      ['D6', fwd.isD6ContractAssetNoteSection],
      ['D7', fwd.isD7ContractLiabilityNoteSection],
      ['D4', fwd.isD4RevenueNoteSection],
      ['G1', fwd.isG1TradingFinancialAssetNoteSection],
      ['G1_DERIVATIVE', fwd.isDerivativeFinancialAssetNoteSection],
      ['G10', fwd.isG10TradingLiabilityNoteSection],
      ['H1', fwd.isH1FixedAssetNoteSection],
      ['H8', fwd.isH8RouNoteSection],
      ['H9', fwd.isH9LeaseLiabilityNoteSection],
      ['I1', fwd.isI1IntangibleNoteSection],
      ['I5', fwd.isI5OtherNoncurrentNoteSection],
      ['G13', fwd.isG13FairValueNoteSection],
      ['G14', fwd.isG14CreditImpairmentNoteSection],
      ['H10', fwd.isH10AssetDisposalNoteSection],
      ['F1', fwd.isF1PrepaymentNoteSection],
      ['F2', fwd.isF2InventoryNoteSection],
      ['G11', fwd.isG11InvestmentIncomeNoteSection],
      ['H2', fwd.isH2CipNoteSection],
      ['I2', fwd.isI2DevelopmentExpenseNoteSection],
      ['I3', fwd.isI3GoodwillNoteSection],
      ['I4', fwd.isI4LongTermPrepaidNoteSection],
      ['I6', fwd.isI6ResearchExpenseNoteSection],
      ['K1', fwd.isK1OtherReceivableNoteSection],
      ['K11', fwd.isK11AssetImpairmentNoteSection],
      ['K13', fwd.isK13NonOperatingExpenseNoteSection],
      ['N1', fwd.isN1DeferredTaxNoteSection],
      ['G7', fwd.isG7EquityNoteSection],
    ]
    for (const [wp, pred] of checks) {
      const entry = DISCLOSURE_NOTE_SECTION_MAP[wp]
      expect(pred(entry.listed), `${wp} listed ${entry.listed}`).toBe(true)
      expect(pred(entry.soe), `${wp} soe ${entry.soe}`).toBe(true)
    }
  })
})

// G7 长期股权投资（主节 五、18 / 八、18；国企「七、」各子节由披露表内 Note 芯片单独跳转）
describe('reverse jump · G7 长期股权投资', () => {
  it('maps G7 listed→五、18 soe→八、18 and builds routes', () => {
    expect(DISCLOSURE_NOTE_SECTION_MAP.G7).toEqual({ listed: '五、18', soe: '八、18' })
    expect((buildNoteJumpRoute('p1', 'G7', 'listed') as any).query)
      .toEqual({ section: '五、18', noteTemplate: 'listed' })
    expect((buildNoteJumpRoute('p1', 'G7', 'soe') as any).query)
      .toEqual({ section: '八、18', noteTemplate: 'soe' })
  })

  it('与 G7 披露表内 NOTE_SECTION_ID / noteSectionId 常量一致', async () => {
    const { G7_SOE_DISCLOSURE_SECTIONS } = await import(
      '@/components/workpaper/g7-long-term-equity-main/disclosure/g7SoeDisclosureModel'
    )
    const lteSection = G7_SOE_DISCLOSURE_SECTIONS.find(
      (s: any) => s.noteSectionId === DISCLOSURE_NOTE_SECTION_MAP.G7.soe,
    )
    expect(lteSection, '国企披露表应存在 八、18 长期股权投资节').toBeTruthy()
  })
})

// N1 递延所得税资产（与 N3 共用章节；反向仅导航，数据所有权见 spec Decision 1）
describe('reverse jump · N1 递延所得税资产', () => {
  it('maps N1 listed→五、30 soe→八、31 and builds routes', () => {
    expect(DISCLOSURE_NOTE_SECTION_MAP.N1).toEqual({ listed: '五、30', soe: '八、31' })
    expect((buildNoteJumpRoute('p1', 'N1', 'listed') as any).query)
      .toEqual({ section: '五、30', noteTemplate: 'listed' })
    expect((buildNoteJumpRoute('p1', 'N1', 'soe') as any).query)
      .toEqual({ section: '八、31', noteTemplate: 'soe' })
  })

  it('携年度时带 year 参数；缺 projectId 返回 null', () => {
    expect((buildNoteJumpRoute('p1', 'N1', 'soe', 2025) as any).query)
      .toEqual({ section: '八、31', noteTemplate: 'soe', year: '2025' })
    expect(buildNoteJumpRoute('', 'N1', 'listed')).toBeNull()
  })

  it('与 n1NoteSectionMap 的章节常量一致（单一真源）', async () => {
    const { N1_NOTE_SECTION } = await import(
      '@/components/workpaper/composables/n1NoteSectionMap'
    )
    expect(DISCLOSURE_NOTE_SECTION_MAP.N1.listed).toBe(N1_NOTE_SECTION.listed)
    expect(DISCLOSURE_NOTE_SECTION_MAP.N1.soe).toBe(N1_NOTE_SECTION.soe)
  })

  // 🔴 sync_from_workpaper 按 (project_id, year, note_section) 精确定位：反向跳转 / 同步用的章节号
  //    差一个字就落空、上市侧新建垃圾章节（历史上 K11/K12/K13/H10 写完整名、模板却是 md 截断值）。
  //    2026-10-16 两版模板按四版 Word 改挂（上市损益类 三→五、75~五、80 等）后，守卫从「三、章截断值
  //    必须在真源里」扩为「两个准则的全部章节号都必须在各自模板里」：模板再改编号而这里没跟上即打红。
  it('全部 listed / soe 章节号都存在于各自的 note_template（模板改编号必须同步这里）', async () => {
    const { readFileSync } = await import('node:fs')
    const { resolve } = await import('node:path')
    const load = (std: 'listed' | 'soe'): Set<string> => {
      const raw = readFileSync(resolve(__dirname, `../../../../../../backend/data/note_template_${std}.json`), 'utf-8')
      return new Set((JSON.parse(raw).sections as Array<{ section_number: string }>).map(s => s.section_number))
    }
    const known = { listed: load('listed'), soe: load('soe') }

    // 反向自检：真源解析必须真的拿到内容，否则本断言恒空转
    expect(known.listed.size).toBeGreaterThan(50)
    expect(known.soe.size).toBeGreaterThan(50)
    expect(known.listed).toContain('五、78')

    // K6 上市「持有待售资产」是标题定位（模板无独立编号节），按标题由 resolveSectionInList 解析，不在本守卫内
    const TITLE_LOCATED = new Set(['K6:listed'])
    const offenders: string[] = []
    let checked = 0
    for (const [wp, v] of Object.entries(DISCLOSURE_NOTE_SECTION_MAP)) {
      for (const std of ['listed', 'soe'] as const) {
        const code = v[std]
        if (typeof code !== 'string' || TITLE_LOCATED.has(`${wp}:${std}`)) continue
        checked += 1
        if (!known[std].has(code)) offenders.push(`${wp} ${std} -> ${code}`)
      }
    }
    expect(checked).toBeGreaterThan(60)
    expect(offenders).toEqual([])
    // 改挂前的上市旧编号（「三」章下的截断值）不得再出现在映射里
    expect(Object.values(DISCLOSURE_NOTE_SECTION_MAP).filter(v => String(v.listed ?? '').startsWith('三、'))).toEqual([])
  })
})
