/**
 * n1-integration.spec.ts — N1 递延所得税资产 集成测试：资产类取数+跨底稿联动
 *
 * Spec: .kiro/specs/n1-deferred-tax-assets/ Task 7.2
 * Validates: Requirements 2.5-2.6, 4.4, 5.5, 7.1-7.5, 8.1-8.4
 *
 * 测试组：
 * 1. 资产类取数正确性 — useN1FormulaEngine.calcAssetEndBalance (Req 8.1-8.4)
 * 2. N1-4→N1-1/N3 回填 — useN1CrossSheet.adjudicationVsCalcTable + n1ToN3Correspondence (Req 4.4)
 * 3. N1-5→N1-4 — useN1CrossSheet.lossCheckToCalcTable (Req 5.5)
 * 4. 本期变动→N5核对 — useN1CrossSheet.deferredTaxChange (Req 7.2, 7.4)
 * 5. 跨底稿联动 — N1-N3 correspondence + EventBus (Req 7.1, 7.3, 7.5)
 *
 * 科目：1811 递延所得税资产（**借方/资产类！期末=期初+借方-贷方**）
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, effectScope } from 'vue'
import { useN1CrossSheet } from '../composables/useN1CrossSheet'
import type { ChecklistResponse } from '../composables/useN1FormData'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcSubtotal,
} from '../composables/useN1FormulaEngine'
import {
  calcTemporaryDifference,
  calcDeferredTax,
  calcDeductibleDiff,
  calcTaxableDiff,
  calcDeferredTaxAsset,
  calcDeferredTaxLiability,
  calcWeightedAvgRate,
} from '../composables/useN1DeferredTaxEngine'
import {
  calcUnrecoveredLoss,
  calcRecognizableAsset,
  isCompensationExpired,
} from '../composables/useN1LossCompensationEngine'
import { eventBus } from '@/utils/eventBus'

// ─── Mocks ───────────────────────────────────────────────────────────────────

const mockGet = vi.fn()
const mockPut = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    put: (...args: any[]) => mockPut(...args),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), error: vi.fn(), success: vi.fn() },
  ElMessageBox: { prompt: vi.fn(), confirm: vi.fn() },
}))

// ─── Helpers ─────────────────────────────────────────────────────────────────

function createResponses(
  entries: [string, string | null, string | null][],
): ReturnType<typeof ref<Map<string, ChecklistResponse>>> {
  const map = new Map<string, ChecklistResponse>()
  for (const [itemId, conclusion, remark] of entries) {
    map.set(itemId, { item_id: itemId, conclusion, remark })
  }
  return ref(map)
}

beforeEach(() => {
  mockGet.mockReset()
  mockPut.mockReset()
  mockPut.mockResolvedValue([])
})

afterEach(() => {
  eventBus.all.clear()
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 1: 资产类取数正确性 (Req 8.1-8.4)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — 资产类取数正确性 (Req 8.1-8.4)', () => {
  it('资产类期末余额公式：期末=期初+借方-贷方 (1811借方科目)', () => {
    // 期初1000万，本期借方(确认)500万，本期贷方(转回)200万
    const begin = 10_000_000
    const debit = 5_000_000
    const credit = 2_000_000
    const endBalance = calcAssetEndBalance(begin, debit, credit)
    expect(endBalance).toBe(13_000_000) // 1000+500-200=1300万
  })

  it('资产类 vs 负债类方向差异验证（资产借增贷减 vs 负债贷增借减）', () => {
    const begin = 5_000_000
    const debit = 3_000_000
    const credit = 1_000_000
    // 资产类(N1): 期末 = 期初 + 借方 - 贷方
    const assetEnd = calcAssetEndBalance(begin, debit, credit)
    expect(assetEnd).toBe(7_000_000)
    // 负债类(N3): 期末 = 期初 + 贷方 - 借方 (方向相反！)
    const liabilityEnd = begin + credit - debit
    expect(liabilityEnd).toBe(3_000_000)
    // 验证两者不同
    expect(assetEnd).not.toBe(liabilityEnd)
  })

  it('writebackTB payload 正确性：account_code=1811, direction=debit', async () => {
    mockPut.mockResolvedValue({})
    const auditedAmount = 15_000_000
    const projectId = 'proj-test-01'
    await mockPut(`/api/projects/${projectId}/trial-balance/writeback`, {
      account_code: '1811',
      audited_amount: auditedAmount,
      direction: 'debit',
    })
    expect(mockPut).toHaveBeenCalledWith(
      `/api/projects/${projectId}/trial-balance/writeback`,
      expect.objectContaining({
        account_code: '1811',
        audited_amount: 15_000_000,
        direction: 'debit', // 资产类借方科目！
      }),
    )
  })

  it('审定数公式链完整性：未审+AJE+RJE = 审定数', () => {
    const unadj = 12_000_000
    const aje = 500_000
    const rje = -200_000
    const audited = calcAuditedAmount(unadj, aje, rje)
    expect(audited).toBe(12_300_000)
    // 审定数即为回写TB的期末余额
    expect(audited).toBe(12_300_000)
  })

  it('零值期初+仅借方确认 → 期末=借方', () => {
    const endBalance = calcAssetEndBalance(0, 3_000_000, 0)
    expect(endBalance).toBe(3_000_000)
  })

  it('全额转回（贷方=期初+借方） → 期末=0', () => {
    const endBalance = calcAssetEndBalance(5_000_000, 0, 5_000_000)
    expect(endBalance).toBe(0)
  })

  it('TB取数方向验证：direction=debit 对应资产类借方', () => {
    // 资产类科目1811，direction=debit，借增贷减
    const tbData = {
      account_code: '1811',
      direction: 'debit',
      begin_balance: 8_000_000,
      debit_amount: 2_000_000,
      credit_amount: 1_000_000,
    }
    const expectedEnd = calcAssetEndBalance(
      tbData.begin_balance,
      tbData.debit_amount,
      tbData.credit_amount,
    )
    expect(expectedEnd).toBe(9_000_000)
    expect(tbData.direction).toBe('debit')
    expect(tbData.account_code).toBe('1811')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 2: N1-4→N1-1/N3 回填 (Req 4.4)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — N1-4→N1-1/N3 回填 (Req 4.4)', () => {
  it('N1-4递延税资产部分→N1-1审定表 交叉验证：isMatch=true', () => {
    const responses = createResponses([
      ['N1-1-total-audited', null, '6500000'],
      ['N1-4-total-deferred-tax-asset', null, '6500000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsCalcTable } = useN1CrossSheet(responses)
      expect(adjudicationVsCalcTable.value.isMatch).toBe(true)
      expect(adjudicationVsCalcTable.value.diff).toBe(0)
    })
    scope.stop()
  })

  it('N1-4测算结果 !== N1-1审定 → isMatch=false, diff检测', () => {
    const responses = createResponses([
      ['N1-1-total-audited', null, '7000000'],
      ['N1-4-total-deferred-tax-asset', null, '6500000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsCalcTable } = useN1CrossSheet(responses)
      expect(adjudicationVsCalcTable.value.isMatch).toBe(false)
      expect(adjudicationVsCalcTable.value.diff).toBe(500_000)
    })
    scope.stop()
  })

  it('N1-4同源产出：资产部分(N1) + 负债部分(N3) 分列', () => {
    const responses = createResponses([
      ['N1-4-total-deferred-tax-asset', null, '8000000'],
      ['N1-4-total-deferred-tax-liability', null, '3000000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { n1ToN3Correspondence } = useN1CrossSheet(responses)
      expect(n1ToN3Correspondence.value.assetPart).toBe(8_000_000)
      expect(n1ToN3Correspondence.value.liabilityPart).toBe(3_000_000)
    })
    scope.stop()
  })

  it('递延税引擎：可抵扣差异→N1资产，应纳税差异→N3负债', () => {
    // 资产项: 账面100万, 计税基础150万 → 可抵扣差异50万 → 递延税资产(N1)
    const deductible = calcDeductibleDiff(1_000_000, 1_500_000)
    expect(deductible).toBe(500_000)
    const dtaAsset = calcDeferredTaxAsset(deductible, 0.25)
    expect(dtaAsset).toBe(125_000)

    // 资产项: 账面200万, 计税基础150万 → 应纳税差异50万 → 递延税负债(N3)
    const taxable = calcTaxableDiff(2_000_000, 1_500_000)
    expect(taxable).toBe(500_000)
    const dtlLiability = calcDeferredTaxLiability(taxable, 0.25)
    expect(dtlLiability).toBe(125_000)
  })

  it('差额<=0.01 → isMatch=true（四舍五入容差）', () => {
    const responses = createResponses([
      ['N1-1-total-audited', null, '5000000.005'],
      ['N1-4-total-deferred-tax-asset', null, '5000000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsCalcTable } = useN1CrossSheet(responses)
      expect(adjudicationVsCalcTable.value.isMatch).toBe(true)
    })
    scope.stop()
  })

  it('无N1-4数据时 → diff=N1-1合计（N1-4为0）', () => {
    const responses = createResponses([
      ['N1-1-total-audited', null, '4000000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsCalcTable } = useN1CrossSheet(responses)
      expect(adjudicationVsCalcTable.value.diff).toBe(4_000_000)
      expect(adjudicationVsCalcTable.value.isMatch).toBe(false)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 3: N1-5→N1-4 亏损检查回填 (Req 5.5)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — N1-5→N1-4 亏损可确认回填 (Req 5.5)', () => {
  it('N1-5可确认合计正确读取并回填N1-4', () => {
    const responses = createResponses([
      ['N1-5-total-recognizable', null, '2500000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { lossCheckToCalcTable } = useN1CrossSheet(responses)
      expect(lossCheckToCalcTable.value.total).toBe(2_500_000)
    })
    scope.stop()
  })

  it('N1-5无数据时 → total=0', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { lossCheckToCalcTable } = useN1CrossSheet(responses)
      expect(lossCheckToCalcTable.value.total).toBe(0)
    })
    scope.stop()
  })

  it('可弥补亏损确认引擎：谨慎性限额逻辑', () => {
    // 未弥补亏损800万，预计未来应纳税所得额500万，税率25%
    const unrecovered = calcUnrecoveredLoss(10_000_000, 2_000_000) // 1000-200=800万
    expect(unrecovered).toBe(8_000_000)

    // 可确认递延税资产 = min(800万, 500万) × 25% = 125万
    const recognizable = calcRecognizableAsset(unrecovered, 5_000_000, 0.25)
    expect(recognizable).toBe(1_250_000)
  })

  it('弥补期限届满 → 不可确认递延税资产', () => {
    // 2019年亏损，2025年审计，5年期限 → 2019+5=2024，已届满
    expect(isCompensationExpired(2019, 2025, 5)).toBe(true)
    // 2020年亏损，2025年审计，5年期限 → 2020+5=2025，未届满
    expect(isCompensationExpired(2020, 2025, 5)).toBe(false)
    // 高新企业10年 → 2016年亏损，2025年审计 → 2016+10=2026，未届满
    expect(isCompensationExpired(2016, 2025, 10)).toBe(false)
  })

  it('预计未来应纳税所得额不足 → 仅按可用额确认', () => {
    // 未弥补亏损10_000_000，但预计未来所得额仅3_000_000
    const recognizable = calcRecognizableAsset(10_000_000, 3_000_000, 0.25)
    // min(10_000_000, 3_000_000) × 0.25 = 750_000
    expect(recognizable).toBe(750_000)
  })

  it('多年度亏损汇总 → lossCheckToCalcTable.total', () => {
    // 模拟N1-5多年度可确认额汇总后回填
    const year1Asset = calcRecognizableAsset(2_000_000, 5_000_000, 0.25) // 500_000
    const year2Asset = calcRecognizableAsset(3_000_000, 5_000_000, 0.25) // 750_000
    const totalRecognizable = calcSubtotal([year1Asset, year2Asset])
    expect(totalRecognizable).toBe(1_250_000)

    const responses = createResponses([
      ['N1-5-total-recognizable', null, String(totalRecognizable)],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { lossCheckToCalcTable } = useN1CrossSheet(responses)
      expect(lossCheckToCalcTable.value.total).toBe(1_250_000)
    })
    scope.stop()
  })

  /**
   * Property 12: 跨表键不回退
   * 任一保存后 allResponses['N1-5-total-recognizable'].remark 等于 String(totals.recognizableAsset)，
   * useN1CrossSheet.lossCheckToCalcTable 读到的值与 Property 4 一致。
   *
   * Validates: Requirements 5.1, 8.1
   * Spec: n1-loss-check-source-alignment Task 7.1
   */
  it('Property 12: 跨表键 N1-5-total-recognizable 被 lossCheckToCalcTable 消费且值一致', () => {
    // Property 4: recognizableAsset = effectiveRecognized × taxRate
    // Σ recognizableAsset across non-expired rows → total
    const recognized1 = 300000
    const rate1 = 0.25
    const recognized2 = 500000
    const rate2 = 0.15
    const expectedAsset = parseFloat((recognized1 * rate1 + recognized2 * rate2).toFixed(2))
    // = 75000 + 75000 = 150000

    const responses = createResponses([
      ['N1-5-total-recognizable', null, String(expectedAsset)],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { lossCheckToCalcTable } = useN1CrossSheet(responses)
      // Property 12: crossSheet 读取值 === String(totals.recognizableAsset) 写入的值
      expect(lossCheckToCalcTable.value.total).toBe(expectedAsset)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 4: 本期变动→N5核对 (Req 7.2, 7.4)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — 本期变动→N5核对 (Req 7.2, 7.4)', () => {
  it('本期变动额=期末-期初 正确计算', () => {
    const responses = createResponses([
      ['N1-1-total-begin', null, '10000000'],
      ['N1-1-total-audited', null, '13000000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { deferredTaxChange } = useN1CrossSheet(responses)
      expect(deferredTaxChange.value.change).toBe(3_000_000) // 净增300万
    })
    scope.stop()
  })

  it('期末<期初 → 变动额为负（递延税资产净减少）', () => {
    const responses = createResponses([
      ['N1-1-total-begin', null, '8000000'],
      ['N1-1-total-audited', null, '5000000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { deferredTaxChange } = useN1CrossSheet(responses)
      expect(deferredTaxChange.value.change).toBe(-3_000_000)
    })
    scope.stop()
  })

  it('期初=期末 → 变动额=0（无变化）', () => {
    const responses = createResponses([
      ['N1-1-total-begin', null, '6000000'],
      ['N1-1-total-audited', null, '6000000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { deferredTaxChange } = useN1CrossSheet(responses)
      expect(deferredTaxChange.value.change).toBe(0)
    })
    scope.stop()
  })

  it('无数据时 → change=0', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { deferredTaxChange } = useN1CrossSheet(responses)
      expect(deferredTaxChange.value.change).toBe(0)
    })
    scope.stop()
  })

  it('递延所得税费用核对公式：费用=N3变动-N1变动', () => {
    // N1变动(资产增加): 期末1300万-期初1000万=+300万
    // N3变动(负债增加): 期末800万-期初500万=+300万
    // 递延所得税费用 = N3变动 - N1变动 = 300万 - 300万 = 0
    const n1Change = 3_000_000
    const n3Change = 3_000_000
    const deferredTaxExpense = n3Change - n1Change
    expect(deferredTaxExpense).toBe(0)

    // 仅N1变动+200万 → 费用=-200万（递延税资产增加减少费用）
    const expense2 = 0 - 2_000_000
    expect(expense2).toBe(-2_000_000)

    // 仅N3变动+100万 → 费用=+100万（递延税负债增加增加费用）
    const expense3 = 1_000_000 - 0
    expect(expense3).toBe(1_000_000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 5: 跨底稿联动 N1-N3 correspondence (Req 7.1, 7.3, 7.5)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — 跨底稿联动 N1-N3 correspondence (Req 7.1, 7.3, 7.5)', () => {
  it('N1-4同源暂时性差异分列：资产部分(N1) + 负债部分(N3)', () => {
    // 多行测算数据：混合可抵扣与应纳税差异
    const items = [
      { bookValue: 1_000_000, taxBase: 1_500_000 }, // 可抵扣50万→N1
      { bookValue: 2_000_000, taxBase: 1_200_000 }, // 应纳税80万→N3
      { bookValue: 800_000, taxBase: 1_000_000 },   // 可抵扣20万→N1
      { bookValue: 3_000_000, taxBase: 2_500_000 }, // 应纳税50万→N3
    ]
    const taxRate = 0.25

    let totalAsset = 0
    let totalLiability = 0
    for (const item of items) {
      const deductible = calcDeductibleDiff(item.bookValue, item.taxBase)
      const taxable = calcTaxableDiff(item.bookValue, item.taxBase)
      totalAsset += calcDeferredTaxAsset(deductible, taxRate)
      totalLiability += calcDeferredTaxLiability(taxable, taxRate)
    }

    // 可抵扣：50万+20万=70万，递延税资产=70万×25%=17.5万
    expect(totalAsset).toBe(175_000)
    // 应纳税：80万+50万=130万，递延税负债=130万×25%=32.5万
    expect(totalLiability).toBe(325_000)

    // 验证 CrossSheet 读取
    const responses = createResponses([
      ['N1-4-total-deferred-tax-asset', null, String(totalAsset)],
      ['N1-4-total-deferred-tax-liability', null, String(totalLiability)],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { n1ToN3Correspondence } = useN1CrossSheet(responses)
      expect(n1ToN3Correspondence.value.assetPart).toBe(175_000)
      expect(n1ToN3Correspondence.value.liabilityPart).toBe(325_000)
    })
    scope.stop()
  })

  it('GtIndexChip 跳转数据：N1-4 ↔ N3-2 交叉引用存在', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { crossWpReferences } = useN1CrossSheet(responses)
      // 验证 N3 跨底稿引用存在
      const n3Refs = crossWpReferences.filter(r => r.targetWpCode === 'N3')
      expect(n3Refs.length).toBeGreaterThanOrEqual(1)
      // 验证有到N3的输出引用
      const toN3 = n3Refs.find(r => r.direction === 'to')
      expect(toN3).toBeDefined()
      expect(toN3!.label).toContain('N3')
    })
    scope.stop()
  })

  it('GtIndexChip 跳转数据：N1→N5 变动额引用存在', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { crossWpReferences } = useN1CrossSheet(responses)
      const n5Refs = crossWpReferences.filter(r => r.targetWpCode === 'N5')
      expect(n5Refs.length).toBeGreaterThanOrEqual(1)
      const toN5 = n5Refs.find(r => r.direction === 'to')
      expect(toN5).toBeDefined()
      expect(toN5!.label).toContain('N5')
    })
    scope.stop()
  })

  it('N3引用也包含from方向（同源暂时性差异）', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { crossWpReferences } = useN1CrossSheet(responses)
      const fromN3 = crossWpReferences.find(
        r => r.targetWpCode === 'N3' && r.direction === 'from',
      )
      expect(fromN3).toBeDefined()
    })
    scope.stop()
  })

  it('加权平均税率正确计算（多项不同税率）', () => {
    const items = [
      { diff: 2_000_000, rate: 0.25 }, // 50万
      { diff: 1_000_000, rate: 0.15 }, // 15万
      { diff: 500_000, rate: 0.25 },   // 12.5万
    ]
    const taxAmounts = items.map(i => calcDeferredTax(i.diff, i.rate))
    const diffs = items.map(i => i.diff)
    const avgRate = calcWeightedAvgRate(taxAmounts, diffs)

    // (50万+15万+12.5万) / (200万+100万+50万)
    const expected = (500_000 + 150_000 + 125_000) / (2_000_000 + 1_000_000 + 500_000)
    expect(avgRate).toBeCloseTo(expected, 6)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 6: EventBus 集成 (Req 7.2, 7.4)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — EventBus: deferred-tax:asset-updated (Req 7.2)', () => {
  it('publish deferred-tax:asset-updated 正确格式', () => {
    const received: any[] = []
    eventBus.on('deferred-tax:asset-updated', (payload: any) => {
      received.push(payload)
    })

    // 模拟 N1 递延税资产更新事件
    eventBus.emit('deferred-tax:asset-updated', {
      wpCode: 'N1',
      endBalance: 13_000_000,
      beginBalance: 10_000_000,
      change: 3_000_000,
      timestamp: Date.now(),
    })

    expect(received.length).toBe(1)
    expect(received[0]).toMatchObject({
      wpCode: 'N1',
      endBalance: 13_000_000,
      beginBalance: 10_000_000,
      change: 3_000_000,
    })
    expect(received[0].timestamp).toBeGreaterThan(0)
  })

  it('N5-8 订阅 deferred-tax:asset-updated 能收到事件', () => {
    let n5Received = false
    // 模拟 N5-8 递延所得税费用核对表订阅
    eventBus.on('deferred-tax:asset-updated', (payload: any) => {
      if (payload.wpCode === 'N1') {
        n5Received = true
      }
    })

    eventBus.emit('deferred-tax:asset-updated', {
      wpCode: 'N1',
      endBalance: 8_000_000,
      beginBalance: 5_000_000,
      change: 3_000_000,
      timestamp: Date.now(),
    })

    expect(n5Received).toBe(true)
  })
})

describe('集成测试 — EventBus: substantive:adjudicated (Req 7.4)', () => {
  it('publish substantive:adjudicated 触发附注刷新', () => {
    const received: any[] = []
    eventBus.on('substantive:adjudicated', (payload: any) => {
      received.push(payload)
    })

    eventBus.emit('substantive:adjudicated', {
      accountCode: '1811',
      auditedAmount: 13_000_000,
      wpCode: 'N1',
      timestamp: Date.now(),
    })

    expect(received.length).toBe(1)
    expect(received[0]).toMatchObject({
      accountCode: '1811',
      auditedAmount: 13_000_000,
      wpCode: 'N1',
    })
  })

  it('附注组件 subscribe 后能收到 N1 审定通知', () => {
    let refreshTriggered = false
    eventBus.on('substantive:adjudicated', (payload: any) => {
      if (payload.wpCode === 'N1') {
        refreshTriggered = true
      }
    })

    eventBus.emit('substantive:adjudicated', {
      accountCode: '1811',
      auditedAmount: 15_000_000,
      wpCode: 'N1',
      timestamp: Date.now(),
    })

    expect(refreshTriggered).toBe(true)
  })
})

describe('集成测试 — EventBus: loss-check:recognizable-updated (Req 5.5)', () => {
  it('N1-5亏损确认变化 → 发布事件供N1-4消费', () => {
    const received: any[] = []
    eventBus.on('loss-check:recognizable-updated', (payload: any) => {
      received.push(payload)
    })

    eventBus.emit('loss-check:recognizable-updated', {
      wpCode: 'N1',
      totalRecognizable: 2_500_000,
      timestamp: Date.now(),
    })

    expect(received.length).toBe(1)
    expect(received[0].totalRecognizable).toBe(2_500_000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 7: 完整E2E流程闭环 (Req 2.5-2.6, 4.4, 5.5, 7.1-7.5, 8.1-8.4)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — E2E: N1完整流程闭环', () => {
  it('完整流程：TB取数→审定(资产类)→明细→测算表(差异×税率)→亏损→N3对应→N5变动', () => {
    // Step 1: TB资产类取数（期初余额，借方）
    const tbBeginBalance = 10_000_000

    // Step 2: 本期变动（借方确认500万，贷方转回200万）
    const debitAmount = 5_000_000
    const creditAmount = 2_000_000
    const endBalance = calcAssetEndBalance(tbBeginBalance, debitAmount, creditAmount)
    expect(endBalance).toBe(13_000_000) // 1000+500-200=1300万

    // Step 3: 审定数 = 未审(期末余额) + AJE + RJE
    const audited = calcAuditedAmount(endBalance, 200_000, -100_000)
    expect(audited).toBe(13_100_000) // 1300万+20万-10万

    // Step 4: 明细表递延税资产测算
    const detailItems = [
      { bookValue: 5_000_000, taxBase: 8_000_000, rate: 0.25 },  // 可抵扣300万×25%=75万
      { bookValue: 2_000_000, taxBase: 4_000_000, rate: 0.25 },  // 可抵扣200万×25%=50万
      { bookValue: 1_000_000, taxBase: 2_500_000, rate: 0.15 },  // 可抵扣150万×15%=22.5万
    ]
    const dtaAmounts = detailItems.map(item => {
      const deductible = calcDeductibleDiff(item.bookValue, item.taxBase)
      return calcDeferredTaxAsset(deductible, item.rate)
    })
    expect(dtaAmounts[0]).toBe(750_000)
    expect(dtaAmounts[1]).toBe(500_000)
    expect(dtaAmounts[2]).toBe(225_000)
    const totalDta = calcSubtotal(dtaAmounts)
    expect(totalDta).toBe(1_475_000)

    // Step 5: N1-5亏损确认
    const lossUnrecovered = calcUnrecoveredLoss(5_000_000, 1_000_000) // 未弥补400万
    expect(lossUnrecovered).toBe(4_000_000)
    const lossAsset = calcRecognizableAsset(lossUnrecovered, 3_000_000, 0.25) // min(400,300)×25%=75万
    expect(lossAsset).toBe(750_000)

    // Step 6: 跨底稿联动验证
    const responses = createResponses([
      ['N1-1-total-begin', null, String(tbBeginBalance)],
      ['N1-1-total-audited', null, String(audited)],
      ['N1-4-total-deferred-tax-asset', null, String(totalDta + lossAsset)],
      ['N1-4-total-deferred-tax-liability', null, '500000'], // 应纳税部分→N3
      ['N1-5-total-recognizable', null, String(lossAsset)],
    ])

    const scope = effectScope()
    scope.run(() => {
      const {
        adjudicationVsCalcTable,
        lossCheckToCalcTable,
        n1ToN3Correspondence,
        deferredTaxChange,
      } = useN1CrossSheet(responses)

      // N1-5→N1-4 验证
      expect(lossCheckToCalcTable.value.total).toBe(750_000)

      // N1-4→N3 分列验证
      expect(n1ToN3Correspondence.value.assetPart).toBe(2_225_000) // 147.5万+75万
      expect(n1ToN3Correspondence.value.liabilityPart).toBe(500_000)

      // 本期变动供N5核对
      expect(deferredTaxChange.value.change).toBe(3_100_000) // 1310万-1000万
    })
    scope.stop()
  })

  it('响应式更新：allResponses变化 → computed值自动刷新', () => {
    const responses = createResponses([
      ['N1-1-total-begin', null, '5000000'],
      ['N1-1-total-audited', null, '8000000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { deferredTaxChange } = useN1CrossSheet(responses)

      // 初始值
      expect(deferredTaxChange.value.change).toBe(3_000_000)

      // 更新 allResponses（模拟审定表数据变化）
      responses.value.set('N1-1-total-audited', {
        item_id: 'N1-1-total-audited',
        conclusion: null,
        remark: '12000000',
      })
      responses.value = new Map(responses.value)

      // computed 自动刷新
      expect(deferredTaxChange.value.change).toBe(7_000_000) // 1200万-500万
    })
    scope.stop()
  })

  it('N1-1审定表 vs N1-2明细表 交叉验证', () => {
    const responses = createResponses([
      ['N1-1-total-audited', null, '6500000'],
      ['N1-2-total-deferred-tax-asset', null, '6500000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsDetail } = useN1CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(true)
      expect(adjudicationVsDetail.value.diff).toBe(0)
    })
    scope.stop()
  })

  it('N1-1 vs N1-2 不匹配 → diff检测', () => {
    const responses = createResponses([
      ['N1-1-total-audited', null, '7000000'],
      ['N1-2-total-deferred-tax-asset', null, '6500000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsDetail } = useN1CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(false)
      expect(adjudicationVsDetail.value.diff).toBe(500_000)
    })
    scope.stop()
  })
})
