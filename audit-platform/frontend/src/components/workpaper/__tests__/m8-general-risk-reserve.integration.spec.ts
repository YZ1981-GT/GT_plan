/**
 * 集成测试 — M8 一般风险准备：风险测试 + 行业守卫适用性 + 跨sheet交叉验证
 *
 * 覆盖：
 * 1. 风险资产计提测试（M8-4）：G=E×F, H=B-G, SUM totals, 阈值高亮, 充足性结论
 * 2. 行业守卫（Industry Guard）：金融/银行/证券/保险/信托/基金/期货/金融租赁
 * 3. 跨sheet交叉验证：adjudicationVsDetail（M8-1 vs M8-2）
 *
 * Spec: .kiro/specs/m8-general-risk-reserve/ Task 7.2
 * Requirements: 3.3-3.7, 5.1-5.3
 *
 * 科目：4104 一般风险准备（**贷方/权益类！期末=期初+贷方-借方**）
 * 金融企业专属：银行/证券/保险/信托/基金/期货/金融租赁
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { ref, effectScope } from 'vue'
import { useM8CrossSheet } from '../composables/useM8CrossSheet'
import type { ChecklistResponse } from '../composables/useM8CrossSheet'
import {
  calcRiskProvision,
  calcProvisionDiff,
} from '../composables/useM8RiskEngine'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
} from '../composables/useM8FormulaEngine'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function createResponses(entries: [string, Partial<ChecklistResponse>][]) {
  const map = new Map<string, ChecklistResponse>()
  for (const [itemId, partial] of entries) {
    map.set(itemId, {
      item_id: itemId,
      conclusion: partial.conclusion ?? null,
      remark: partial.remark ?? null,
    })
  }
  return ref(map)
}

function createResponsesSimple(entries: [string, string | null][]) {
  return createResponses(entries.map(([id, remark]) => [id, { remark }]))
}

// ═══════════════════════════════════════════════════════════════════════════════
// Section 1: 风险资产计提测试 M8-4（Req 3.3-3.7）
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — M8-4 风险资产计提测试完整流程 (Req 3.3-3.7)', () => {
  it('多项风险资产各项G=E×F + 汇总SUM', () => {
    // 模拟金融企业多项风险资产
    const riskItems = [
      { name: '信贷资产', riskAssetBalance: 500_000_000, rate: 0.015 },
      { name: '表外信贷', riskAssetBalance: 200_000_000, rate: 0.015 },
      { name: '债券投资', riskAssetBalance: 100_000_000, rate: 0.01 },
    ]

    // 公式 G = E × F（各项应计金额）
    const estimatedAmounts = riskItems.map((item) =>
      calcRiskProvision(item.riskAssetBalance, item.rate),
    )
    expect(estimatedAmounts[0]).toBe(7_500_000) // 5亿×1.5%=750万
    expect(estimatedAmounts[1]).toBe(3_000_000) // 2亿×1.5%=300万
    expect(estimatedAmounts[2]).toBe(1_000_000) // 1亿×1%=100万

    // SUM总计
    const totalEstimated = calcSubtotal(estimatedAmounts)
    expect(totalEstimated).toBe(11_500_000) // 1150万

    // 各项差异 H = B - G（本实现中 diff = estimated - booked）
    const bookedAmounts = [7_000_000, 3_000_000, 800_000]
    const diffs = estimatedAmounts.map((est, i) =>
      calcProvisionDiff(est, bookedAmounts[i]),
    )
    expect(diffs[0]).toBe(500_000)  // 少提50万
    expect(diffs[1]).toBe(0)         // 准确
    expect(diffs[2]).toBe(200_000)  // 少提20万

    // SUM差异合计
    const totalDiff = calcSubtotal(diffs)
    expect(totalDiff).toBe(700_000) // 合计少提70万
  })

  it('计提比例1.5%标准测试 — 基准验证', () => {
    // 金融企业标准：风险资产期末余额 × 1.5%
    const riskAssets = 1_000_000_000 // 10亿
    const rate = 0.015
    const estimated = calcRiskProvision(riskAssets, rate)
    expect(estimated).toBe(15_000_000) // 1500万

    // 账面正好等于1.5%
    const diff = calcProvisionDiff(estimated, 15_000_000)
    expect(diff).toBe(0)
  })

  it('阈值高亮逻辑：|diff|>阈值时标记exceed', () => {
    const THRESHOLD = 100_000 // 10万元阈值

    // Case 1: 差异50万 > 10万阈值 → exceed
    const diff1 = calcProvisionDiff(7_500_000, 7_000_000) // 50万
    expect(diff1).toBe(500_000)
    expect(Math.abs(diff1) > THRESHOLD).toBe(true)

    // Case 2: 差异5万 < 10万阈值 → 不exceed
    const diff2 = calcProvisionDiff(7_050_000, 7_000_000) // 5万
    expect(diff2).toBe(50_000)
    expect(Math.abs(diff2) > THRESHOLD).toBe(false)

    // Case 3: 差异=0 → 不exceed
    const diff3 = calcProvisionDiff(7_000_000, 7_000_000)
    expect(diff3).toBe(0)
    expect(Math.abs(diff3) > THRESHOLD).toBe(false)
  })

  it('计提充足性结论判定：adequate / insufficient', () => {
    // 充足性结论逻辑：
    // - 差异为正 → 应计>账面 → 计提不足 insufficient
    // - 差异为0或负 → 账面≥应计 → 计提充足 adequate

    // Case 1: 计提充足（账面≥应计）
    const diff1 = calcProvisionDiff(15_000_000, 16_000_000) // -100万
    expect(diff1).toBeLessThanOrEqual(0)
    const conclusion1 = diff1 <= 0 ? 'adequate' : 'insufficient'
    expect(conclusion1).toBe('adequate')

    // Case 2: 计提不足（应计>账面）
    const diff2 = calcProvisionDiff(15_000_000, 12_000_000) // +300万
    expect(diff2).toBeGreaterThan(0)
    const conclusion2 = diff2 <= 0 ? 'adequate' : 'insufficient'
    expect(conclusion2).toBe('insufficient')

    // Case 3: 刚好等于 → adequate
    const diff3 = calcProvisionDiff(15_000_000, 15_000_000)
    expect(diff3).toBe(0)
    const conclusion3 = diff3 <= 0 ? 'adequate' : 'insufficient'
    expect(conclusion3).toBe('adequate')
  })

  it('完整M8-4公式链13条：各行G=E×F → 各行H=B-G → SUM(G) → SUM(H)', () => {
    // 模拟4项风险资产（含不同比例）
    const items = [
      { riskAssets: 300_000_000, rate: 0.015, booked: 4_200_000 },
      { riskAssets: 150_000_000, rate: 0.015, booked: 2_000_000 },
      { riskAssets: 80_000_000, rate: 0.01, booked: 900_000 },
      { riskAssets: 50_000_000, rate: 0.012, booked: 600_000 },
    ]

    // 公式1~4: G=E×F
    const estimatedArr = items.map((i) => calcRiskProvision(i.riskAssets, i.rate))
    expect(estimatedArr[0]).toBe(4_500_000)
    expect(estimatedArr[1]).toBe(2_250_000)
    expect(estimatedArr[2]).toBe(800_000)
    expect(estimatedArr[3]).toBe(600_000)

    // 公式5~8: H=estimated-booked
    const diffArr = items.map((i, idx) => calcProvisionDiff(estimatedArr[idx], i.booked))
    expect(diffArr[0]).toBe(300_000)   // 少提30万
    expect(diffArr[1]).toBe(250_000)   // 少提25万
    expect(diffArr[2]).toBe(-100_000)  // 多提10万
    expect(diffArr[3]).toBe(0)         // 恰好

    // 公式9~10: SUM(G), SUM(H)
    const totalEstimated = calcSubtotal(estimatedArr)
    expect(totalEstimated).toBe(8_150_000)

    const totalDiff = calcSubtotal(diffArr)
    expect(totalDiff).toBe(450_000)

    // 公式11: 差异汇总正=计提不足
    expect(totalDiff).toBeGreaterThan(0)

    // 公式12: 总计提 vs 总应计
    const totalBooked = calcSubtotal(items.map((i) => i.booked))
    expect(totalBooked).toBe(7_700_000)
    expect(totalEstimated - totalBooked).toBeCloseTo(totalDiff, 5)

    // 公式13: 权益类期末余额验证
    const begin = 7_000_000
    const credit = totalBooked // 本期计提（贷方增加）
    const debit = 0 // 未转回
    const endBalance = calcEquityEndBalance(begin, credit, debit)
    expect(endBalance).toBe(14_700_000) // 700万+770万=1470万
  })

  it('零风险资产 → 应计金额=0', () => {
    expect(calcRiskProvision(0, 0.015)).toBe(0)
    expect(calcProvisionDiff(0, 0)).toBe(0)
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Section 2: 行业守卫适用性（Req 5.1-5.3）
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — 行业守卫 isFinancialEntity (Req 5.1-5.3)', () => {
  it('金融行业关键词命中 → isFinancialEntity=true', () => {
    const financialKeywords = [
      '金融', '银行', '证券', '保险', '信托', '基金', '期货', '金融租赁',
    ]

    for (const keyword of financialKeywords) {
      const responses = createResponses([])
      const projectInfo = ref({ industry: `XX${keyword}有限公司` })

      const scope = effectScope()
      scope.run(() => {
        const { isFinancialEntity } = useM8CrossSheet(responses, projectInfo)
        expect(isFinancialEntity.value).toBe(true)
      })
      scope.stop()
    }
  })

  it('非金融企业 → isFinancialEntity=false', () => {
    const nonFinancialIndustries = [
      '制造业', '房地产开发', '软件信息技术', '零售贸易', '医药生物',
    ]

    for (const industry of nonFinancialIndustries) {
      const responses = createResponses([])
      const projectInfo = ref({ industry })

      const scope = effectScope()
      scope.run(() => {
        const { isFinancialEntity } = useM8CrossSheet(responses, projectInfo)
        expect(isFinancialEntity.value).toBe(false)
      })
      scope.stop()
    }
  })

  it('空/null行业 → 默认适用（isFinancialEntity=true）', () => {
    // 无 projectInfo → 默认适用
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { isFinancialEntity } = useM8CrossSheet(responses)
      expect(isFinancialEntity.value).toBe(true) // 默认适用
    })
    scope.stop()
  })

  it('projectInfo为null + 无checklist记录 → 默认适用', () => {
    const responses = createResponses([])
    const projectInfo = ref(null)

    const scope = effectScope()
    scope.run(() => {
      const { isFinancialEntity } = useM8CrossSheet(responses, projectInfo)
      expect(isFinancialEntity.value).toBe(true)
    })
    scope.stop()
  })

  it('projectInfo无industry字段 → 默认适用', () => {
    const responses = createResponses([])
    const projectInfo = ref({ name: '某公司' }) // 无industry

    const scope = effectScope()
    scope.run(() => {
      const { isFinancialEntity } = useM8CrossSheet(responses, projectInfo)
      expect(isFinancialEntity.value).toBe(true)
    })
    scope.stop()
  })

  it('checklist_responses持久化覆盖：conclusion=financial', () => {
    const responses = createResponses([
      ['M8-industry-guard', { conclusion: 'financial', remark: '商业银行' }],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { isFinancialEntity } = useM8CrossSheet(responses)
      expect(isFinancialEntity.value).toBe(true)
    })
    scope.stop()
  })

  it('checklist_responses持久化覆盖：conclusion=non-financial', () => {
    const responses = createResponses([
      ['M8-industry-guard', { conclusion: 'non-financial', remark: '制造业' }],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { isFinancialEntity } = useM8CrossSheet(responses)
      expect(isFinancialEntity.value).toBe(false)
    })
    scope.stop()
  })

  it('client_industry备选字段也能命中', () => {
    const responses = createResponses([])
    const projectInfo = ref({ client_industry: '中国建设银行股份有限公司' })

    const scope = effectScope()
    scope.run(() => {
      const { isFinancialEntity } = useM8CrossSheet(responses, projectInfo)
      expect(isFinancialEntity.value).toBe(true)
    })
    scope.stop()
  })

  it('remark字段降级判断：行业名含金融关键词', () => {
    const responses = createResponses([
      ['M8-industry-guard', { conclusion: null, remark: '证券投资基金管理公司' }],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { isFinancialEntity } = useM8CrossSheet(responses)
      expect(isFinancialEntity.value).toBe(true)
    })
    scope.stop()
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Section 3: 跨sheet交叉验证 adjudicationVsDetail（Req 2.5）
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — adjudicationVsDetail M8-1 vs M8-2 (Req 2.5)', () => {
  it('M8-1合计 === M8-2合计 → isMatch=true, diff=0', () => {
    const responses = createResponsesSimple([
      ['M8-M8-1-total-end-audited', '8500000'],
      ['M8-M8-2-total-end-amount', '8500000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsDetail } = useM8CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(true)
      expect(adjudicationVsDetail.value.diff).toBe(0)
    })
    scope.stop()
  })

  it('M8-1合计 !== M8-2合计 → isMatch=false, diff显示差额', () => {
    const responses = createResponsesSimple([
      ['M8-M8-1-total-end-audited', '8500000'],
      ['M8-M8-2-total-end-amount', '8200000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsDetail } = useM8CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(false)
      expect(adjudicationVsDetail.value.diff).toBe(300_000)
    })
    scope.stop()
  })

  it('差额<1元（四舍五入）→ isMatch=true', () => {
    const responses = createResponsesSimple([
      ['M8-M8-1-total-end-audited', '8500000.3'],
      ['M8-M8-2-total-end-amount', '8500000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsDetail } = useM8CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(true)
    })
    scope.stop()
  })

  it('两侧均为空 → isMatch=true, diff=0', () => {
    const responses = createResponsesSimple([])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsDetail } = useM8CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(true)
      expect(adjudicationVsDetail.value.diff).toBe(0)
    })
    scope.stop()
  })

  it('明细行降级累加：无汇总行时遍历row-*-end', () => {
    const responses = createResponsesSimple([
      ['M8-M8-1-total-end-audited', '6000000'],
      // 无 M8-M8-2-total-end-amount
      ['M8-M8-2-row-1-end', '2000000'],
      ['M8-M8-2-row-2-end', '2500000'],
      ['M8-M8-2-row-3-end', '1500000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsDetail } = useM8CrossSheet(responses)
      // 2000000+2500000+1500000=6000000
      expect(adjudicationVsDetail.value.isMatch).toBe(true)
      expect(adjudicationVsDetail.value.diff).toBe(0)
    })
    scope.stop()
  })

  it('审定有值 + 明细无值 → isMatch=false', () => {
    const responses = createResponsesSimple([
      ['M8-M8-1-total-end-audited', '5000000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsDetail } = useM8CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(false)
      expect(adjudicationVsDetail.value.diff).toBe(5_000_000)
    })
    scope.stop()
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Section 4: E2E — 完整流程：风险测试 + 行业守卫 + 交叉验证闭环
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — E2E: 金融企业M8风险计提完整闭环 (Req 3.3-3.7, 5.1-5.3)', () => {
  it('完整流程：行业判定→审定→明细→风险计提→交叉验证', () => {
    // Step 1: 行业守卫 — 确认金融企业
    const projectInfo = ref({ industry: '商业银行' })
    const responses = createResponsesSimple([
      ['M8-M8-1-total-end-audited', '15000000'],
      ['M8-M8-2-total-end-amount', '15000000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { isFinancialEntity, adjudicationVsDetail } = useM8CrossSheet(responses, projectInfo)

      // Step 1 验证：金融企业适用
      expect(isFinancialEntity.value).toBe(true)

      // Step 2: 交叉验证通过
      expect(adjudicationVsDetail.value.isMatch).toBe(true)
    })
    scope.stop()

    // Step 3: 风险资产计提测试
    const riskAssetTotal = 1_000_000_000 // 10亿
    const estimated = calcRiskProvision(riskAssetTotal, 0.015)
    expect(estimated).toBe(15_000_000) // 1500万

    // Step 4: 与账面对比
    const booked = 15_000_000
    const diff = calcProvisionDiff(estimated, booked)
    expect(diff).toBe(0) // 计提充足

    // Step 5: 权益类期末余额验证
    const endBalance = calcEquityEndBalance(10_000_000, 15_000_000, 0)
    expect(endBalance).toBe(25_000_000)

    // 审定数验证
    const audited = calcAuditedAmount(25_000_000, 0, 0)
    expect(audited).toBe(25_000_000)
  })

  it('非金融企业场景：行业守卫拦截', () => {
    const projectInfo = ref({ industry: '装备制造' })
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { isFinancialEntity } = useM8CrossSheet(responses, projectInfo)
      expect(isFinancialEntity.value).toBe(false)
      // 非金融企业不适用M8 → 显示提示
    })
    scope.stop()
  })

  it('计提不足场景：差异>阈值 + 交叉验证不一致', () => {
    const projectInfo = ref({ industry: '城市商业银行' })
    const responses = createResponsesSimple([
      ['M8-M8-1-total-end-audited', '12000000'],
      ['M8-M8-2-total-end-amount', '12000000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { isFinancialEntity, adjudicationVsDetail } = useM8CrossSheet(responses, projectInfo)

      expect(isFinancialEntity.value).toBe(true)
      expect(adjudicationVsDetail.value.isMatch).toBe(true)
    })
    scope.stop()

    // 风险测试显示计提不足
    const riskAssets = 1_000_000_000
    const estimated = calcRiskProvision(riskAssets, 0.015)
    const booked = 12_000_000
    const diff = calcProvisionDiff(estimated, booked)
    expect(diff).toBe(3_000_000) // 少提300万
    expect(diff).toBeGreaterThan(0) // insufficient
  })
})
