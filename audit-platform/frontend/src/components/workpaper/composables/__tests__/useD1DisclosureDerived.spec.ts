/**
 * useD1Disclosure — 派生列推导 + 变动表「其中：」明细（第二阶段修复）
 *
 * 覆盖两个浏览器实测暴露的缺陷与一项新能力：
 * - R5 比例 / 损失率 / 账面价值读时推导（旧实现比例漂移到 162.50%）
 * - R9 国企变动表「其中：」下可新增命名明细行，期末数按公式推导（预设 F4-20 前置条件）
 *
 * spec: .kiro/specs/d1-notes-receivable-disclosure-alignment/ R5 / R9
 */
import { describe, expect, it, vi } from 'vitest'
import { ref, nextTick } from 'vue'
import { useD1Disclosure } from '../useD1Disclosure'
import type { ChecklistResponse } from '../useD1FormData'

function setup(variant: 'listed' | 'soe' = 'soe', seed: Record<string, string> = {}) {
  const map = new Map<string, ChecklistResponse>()
  for (const [k, remark] of Object.entries(seed)) {
    map.set(k, { item_id: k, conclusion: null, remark } as ChecklistResponse)
  }
  const allResponses = ref(map)
  const saveImmediate = vi.fn(async () => {})
  const api = useD1Disclosure({
    allResponses: allResponses as any,
    wpId: ref('wp-1') as any,
    projectId: ref('p-1') as any,
    variant,
    saveImmediate,
    isReadonly: ref(false) as any,
  })
  return { api, allResponses, saveImmediate }
}

const P = 'D1-disc-soe-'

describe('R5 派生列读时推导', () => {
  it('编辑后所有行的比例都按新合计重算（各行比例之和 = 1）', async () => {
    const { api } = setup('soe')
    // 商承 30 万（此刻合计 30 万）→ 银承 50 万（合计变 80 万）
    api.updateCell('classEnd', 'class-end-portfolio-commercial', 'balance', 300000)
    await nextTick()
    api.updateCell('classEnd', 'class-end-portfolio-bank', 'balance', 500000)
    await nextTick()

    const rows = api.classEndRows.value
    const bank = rows.find(r => r.rowId === 'class-end-portfolio-bank')!
    const commercial = rows.find(r => r.rowId === 'class-end-portfolio-commercial')!
    expect(api.classEndTotal.value.balance).toBe(800000)
    // 🔴 旧实现：商承录入时分母 30 万 → 1.0，银承录入时分母 80 万 → 0.625，相加 162.5%
    expect(commercial.ratio).toBeCloseTo(300000 / 800000, 10)
    expect(bank.ratio).toBeCloseTo(500000 / 800000, 10)
    expect(rows.reduce((s, r) => s + r.ratio, 0)).toBeCloseTo(1, 10)
  })

  it('损失率与账面价值随录入现算', async () => {
    const { api } = setup('soe')
    api.updateCell('classEnd', 'class-end-portfolio-bank', 'balance', 500000)
    api.updateCell('classEnd', 'class-end-portfolio-bank', 'provision', 4000)
    await nextTick()
    const bank = api.classEndRows.value.find(r => r.rowId === 'class-end-portfolio-bank')!
    expect(bank.lossRate).toBeCloseTo(4000 / 500000, 10)
    expect(bank.bookValue).toBe(496000)
  })

  it('合计行比例恒为 1（展示 100%），损失率 = 总坏账 ÷ 总余额', async () => {
    const { api } = setup('soe')
    api.updateCell('classEnd', 'class-end-portfolio-bank', 'balance', 500000)
    api.updateCell('classEnd', 'class-end-portfolio-bank', 'provision', 4000)
    api.updateCell('classEnd', 'class-end-portfolio-commercial', 'balance', 300000)
    api.updateCell('classEnd', 'class-end-portfolio-commercial', 'provision', 9000)
    await nextTick()
    expect(api.classEndTotal.value.ratio).toBe(1)
    expect(api.classEndTotal.value.lossRate).toBeCloseTo(13000 / 800000, 10)
    expect(api.classEndTotal.value.bookValue).toBe(787000)
  })

  it('持久化只写录入列；加载时的过期派生值被推导覆盖', async () => {
    // 库里存着错的 ratio/lossRate（历史数据 / 导入路径写入）
    const stale = JSON.stringify([
      { rowId: 'class-end-individual', rowType: 'fixed', label: '按单项计提', isFixed: true, balance: 200000, ratio: 9.99, provision: 1000, lossRate: 9.99, bookValue: -1 },
      { rowId: 'class-end-portfolio-bank', rowType: 'fixed', label: '按组合计提-银行承兑汇票', isFixed: true, balance: 300000, ratio: 9.99, provision: 2000, lossRate: 9.99, bookValue: -1 },
    ])
    const { api } = setup('soe', { [P + 'class-end-rows']: stale })
    const rows = api.classEndRows.value
    expect(api.classEndTotal.value.balance).toBe(500000)
    expect(rows[0].ratio).toBeCloseTo(200000 / 500000, 10)
    expect(rows[1].ratio).toBeCloseTo(300000 / 500000, 10)
    expect(rows.every(r => r.ratio !== 9.99 && r.lossRate !== 9.99 && r.bookValue !== -1)).toBe(true)
  })

  it('全为 0 时不产生 NaN / Infinity', () => {
    const { api } = setup('soe')
    for (const r of api.classEndRows.value) {
      expect(Number.isFinite(r.ratio)).toBe(true)
      expect(Number.isFinite(r.lossRate)).toBe(true)
      expect(Number.isFinite(r.bookValue)).toBe(true)
    }
    expect(api.classEndTotal.value.ratio).toBe(0)
  })
})

describe('R9 变动表「其中：」明细', () => {
  it('新增命名明细行；空名不创建', () => {
    const { api } = setup('soe')
    expect(api.hasMovementDetail.value).toBe(false)
    expect(api.addMovementDetailRow('  ')).toBe(false)
    expect(api.addMovementDetailRow('银行承兑汇票')).toBe(true)
    expect(api.movementDetailRows.value.map(r => r.label)).toEqual(['银行承兑汇票'])
    expect(api.hasMovementDetail.value).toBe(true)
  })

  it('明细行期末数按公式推导（期初 + 计提 − 收回或转回 − 核销 − 其他变动）', async () => {
    const { api } = setup('soe')
    api.addMovementDetailRow('银行承兑汇票')
    const id = api.movementDetailRows.value[0].rowId
    api.updateCell('movementDetail', id, 'priorBalance', 100)
    api.updateCell('movementDetail', id, 'provision', 50)
    api.updateCell('movementDetail', id, 'reversal', 10)
    api.updateCell('movementDetail', id, 'writeOff', 5)
    api.updateCell('movementDetail', id, 'other', 0)
    await nextTick()
    expect(api.movementDetailRows.value[0].endBalance).toBe(135)
  })

  it('明细汇总供「按组合计提」行改为只读（F4-20 结构性成立）', async () => {
    const { api } = setup('soe')
    api.addMovementDetailRow('银行承兑汇票')
    api.addMovementDetailRow('商业承兑汇票')
    const [a, b] = api.movementDetailRows.value.map(r => r.rowId)
    api.updateCell('movementDetail', a, 'provision', 50)
    api.updateCell('movementDetail', b, 'provision', 30)
    await nextTick()
    expect(api.movementDetailTotal.value.provision).toBe(80)
  })

  it('删除明细行后回落到可直接录入', () => {
    const { api } = setup('soe')
    api.addMovementDetailRow('银行承兑汇票')
    api.removeMovementDetailRow(api.movementDetailRows.value[0].rowId)
    expect(api.movementDetailRows.value).toEqual([])
    expect(api.hasMovementDetail.value).toBe(false)
  })

  it('明细行持久化到 movement-detail-rows', () => {
    const { api, saveImmediate } = setup('soe')
    api.addMovementDetailRow('银行承兑汇票')
    const ids = saveImmediate.mock.calls.flatMap((c: any) => c[0].map((i: any) => i.item_id))
    expect(ids).toContain(P + 'movement-detail-rows')
  })
})

describe('R2 固定行骨架对齐源模板', () => {
  it('转应收账款表只有商业承兑票据一行', () => {
    const { api } = setup('soe')
    expect(api.transferRows.value.map(r => r.category)).toEqual(['商业承兑票据'])
  })

  it('质押 / 背书固定行用「票据」而非「汇票」', () => {
    const { api } = setup('soe')
    expect(api.pledgedRows.value.map(r => r.category)).toEqual(['银行承兑票据', '商业承兑票据'])
    expect(api.endorsedRows.value.map(r => r.category)).toEqual(['银行承兑票据', '商业承兑票据'])
  })
})

describe('R2.6 转回表累计已计提坏账准备金额是数值列', () => {
  it('新增行带 cumulativeProvision，合计行汇总该列', async () => {
    const { api } = setup('soe')
    api.addReversalRow()
    const id = api.reversalDetailRows.value[0].rowId
    api.updateCell('reversalDetail', id, 'cumulativeProvision', 12)
    api.updateCell('reversalDetail', id, 'amount', 100)
    await nextTick()
    expect(api.reversalDetailRows.value[0].cumulativeProvision).toBe(12)
    expect(api.reversalDetailTotal.value.cumulativeProvision).toBe(12)
    expect(api.reversalDetailTotal.value.amount).toBe(100)
  })

  it('legacy 数据：数值曾误存进文本字段 reversalBasis → 加载时迁移', () => {
    const legacy = JSON.stringify([
      { rowId: 'rv-1', rowType: 'dynamic', isFixed: false, companyName: 'A公司', reversalReason: '客户回款', originalMethod: '', reversalBasis: '12', amount: 100 },
    ])
    const { api } = setup('soe', { [P + 'reversal-rows']: legacy })
    expect(api.reversalDetailRows.value[0].cumulativeProvision).toBe(12)
    expect(api.reversalDetailRows.value[0].reversalBasis).toBe('')
  })

  it('legacy 数据里是真文本时不迁移（上市「原确定坏账准备的依据」）', () => {
    const legacy = JSON.stringify([
      { rowId: 'rv-1', rowType: 'dynamic', isFixed: false, companyName: 'A公司', reversalReason: '', originalMethod: '', reversalBasis: '单项评估', amount: 100 },
    ])
    const { api } = setup('listed', {
      'D1-disc-listed-reversal-rows': legacy,
    })
    expect(api.reversalDetailRows.value[0].reversalBasis).toBe('单项评估')
    expect(api.reversalDetailRows.value[0].cumulativeProvision).toBe(0)
  })
})

describe('R2.1 上市组合计提双期成对操作', () => {
  it('addPortfolioPairRow 向期末与上年末各插一行同名行', () => {
    const { api } = setup('listed')
    expect(api.addPortfolioPairRow('bank', '1年以内（含1年）')).toBe(true)
    expect(api.bankPortfolioEndRows.value.map(r => r.drawerTypeOrAging)).toEqual(['1年以内（含1年）'])
    expect(api.bankPortfolioPriorRows.value.map(r => r.drawerTypeOrAging)).toEqual(['1年以内（含1年）'])
  })

  it('同名不重复新增；空名不新增', () => {
    const { api } = setup('listed')
    api.addPortfolioPairRow('bank', '1年以内')
    expect(api.addPortfolioPairRow('bank', '1年以内')).toBe(false)
    expect(api.addPortfolioPairRow('bank', '   ')).toBe(false)
    expect(api.bankPortfolioEndRows.value).toHaveLength(1)
  })

  it('renamePortfolioPair 同时改两期，保持按名称对齐', () => {
    const { api } = setup('listed')
    api.addPortfolioPairRow('commercial', '1至2年')
    expect(api.renamePortfolioPair('commercial', '1至2年', '2至3年')).toBe(2)
    expect(api.commercialPortfolioEndRows.value[0].drawerTypeOrAging).toBe('2至3年')
    expect(api.commercialPortfolioPriorRows.value[0].drawerTypeOrAging).toBe('2至3年')
  })

  it('fillPortfolioAgingBandsPair 两期成对补齐', () => {
    const { api } = setup('listed')
    const added = api.fillPortfolioAgingBandsPair('bank', ['1年以内', '1至2年'])
    expect(added).toBe(4) // 2 段 × 2 期
    expect(api.bankPortfolioEndRows.value).toHaveLength(2)
    expect(api.bankPortfolioPriorRows.value).toHaveLength(2)
  })

  it('removePortfolioPairRow 删两期同名行', () => {
    const { api } = setup('listed')
    api.addPortfolioPairRow('bank', '1年以内')
    expect(api.removePortfolioPairRow('bank', '1年以内')).toBe(2)
    expect(api.bankPortfolioEndRows.value).toEqual([])
    expect(api.bankPortfolioPriorRows.value).toEqual([])
  })
})


describe('主表手工兜底（两个变体一致）', () => {
  const CROSS = 'D1-disc-listed-'

  it.each([['listed'], ['soe']] as const)(
    '%s：审定表未取数时开放手工录入',
    (variant) => {
      const { api } = setup(variant)
      expect(api.crossSheetStatus.value).toBe('empty')
      expect(api.canEditCategorySummary.value).toBe(true)
    },
  )

  it.each([['listed'], ['soe']] as const)(
    '%s：审定表取到数后转为只读（以审定表为准）',
    (variant) => {
      const p = `D1-disc-${variant}-`
      const { api } = setup(variant, {
        'D1-adj-gross-bank-current-audited': '500000',
      })
      void p
      expect(api.crossSheetStatus.value).toBe('loaded')
      expect(api.canEditCategorySummary.value).toBe(false)
    },
  )

  it.each([['listed'], ['soe']] as const)(
    '%s：手工录入写入 top-summary-rows 且账面价值自动推导',
    (variant) => {
      const { api, saveImmediate } = setup(variant)
      api.updateCell('categorySummary', 'cat-bank', 'endBalance', 500000)
      api.updateCell('categorySummary', 'cat-bank', 'endProvision', 4000)
      const bank = api.categorySummaryRows.value.find(r => r.rowId === 'cat-bank')!
      expect(bank.endBalance).toBe(500000)
      expect(bank.endProvision).toBe(4000)
      expect(bank.endBookValue).toBe(496000)
      const ids = saveImmediate.mock.calls.flatMap((c: any) => c[0].map((i: any) => i.item_id))
      expect(ids).toContain(`D1-disc-${variant}-top-summary-rows`)
    },
  )

  it('🔴 上市侧回退不再被 variant 门死（旧实现写死 soe → 上市导入无效）', () => {
    const imported = JSON.stringify([
      { rowId: 'cat-import-0', category: '银行承兑汇票', endBalance: 111, endProvision: 1, endBookValue: 110, priorBalance: 0, priorProvision: 0, priorBookValue: 0 },
    ])
    const { api } = setup('listed', { [CROSS + 'top-summary-rows']: imported })
    expect(api.categorySummaryRows.value).toHaveLength(1)
    expect(api.categorySummaryRows.value[0].endBalance).toBe(111)
    expect(api.categorySummaryTotal.value.endBalance).toBe(111)
  })

  it('审定表有数时忽略导入行（审定表优先）', () => {
    const imported = JSON.stringify([
      { rowId: 'cat-import-0', category: '银行承兑汇票', endBalance: 111, endProvision: 1, endBookValue: 110, priorBalance: 0, priorProvision: 0, priorBookValue: 0 },
    ])
    const { api } = setup('listed', {
      [CROSS + 'top-summary-rows']: imported,
      'D1-adj-gross-bank-current-audited': '500000',
    })
    const bank = api.categorySummaryRows.value.find(r => r.category === '银行承兑汇票')!
    expect(bank.endBalance).toBe(500000)
  })

  it('只读时手工录入被拒（不越过 isReadonly）', () => {
    const map = new Map<string, ChecklistResponse>()
    const api = useD1Disclosure({
      allResponses: ref(map) as any,
      wpId: ref('wp-1') as any,
      projectId: ref('p-1') as any,
      variant: 'listed',
      saveImmediate: vi.fn(async () => {}),
      isReadonly: ref(true) as any,
    })
    api.updateCell('categorySummary', 'cat-bank', 'endBalance', 999)
    expect(api.categorySummaryRows.value.find(r => r.rowId === 'cat-bank')!.endBalance).toBe(0)
  })
})
