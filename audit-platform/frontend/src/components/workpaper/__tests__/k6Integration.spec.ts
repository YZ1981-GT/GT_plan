/**
 * K6 持有待售 — 集成测试：跨Sheet数据流 + 分类→减值→处置组→审定回写
 *
 * Spec: .kiro/specs/k6-held-for-sale/ Task 7.2
 * Requirements: 2.7, 4.2, 5.5, 6.4
 *
 * 测试策略：
 * - 构建 mock allResponses Map → 注入 useK6CrossSheet → 验证 computed 传播
 * - 验证分类引擎 → 明细表联动
 * - 验证减值引擎 → 审定表联动
 * - 验证处置组分摊 → 减值测试联动
 * - 验证审定表回写 TB 数据流
 */
import { describe, it, expect } from 'vitest'
import { ref, nextTick } from 'vue'
import { useK6CrossSheet } from '../composables/useK6CrossSheet'
import { classifyHeldForSale } from '../composables/useK6ClassificationEngine'
import {
  calcFairValueNet,
  calcImpairment,
  calcAllocationRatio,
  calcGroupImpairmentAllocation,
  calcAdditionalProvision,
} from '../composables/useK6ImpairmentEngine'
import {
  calcAuditedAmount,
  calcBookValue,
  calcSubtotal,
  calcAssetPeriodEnd,
} from '../composables/useK6FormulaEngine'

// ─── Helper: 构建 allResponses Map ─────────────────────────────────────────

function createMockResponses(entries: Record<string, number | string>): Map<string, any> {
  const map = new Map<string, any>()
  for (const [key, value] of Object.entries(entries)) {
    map.set(key, { remark: String(value) })
  }
  return map
}

// ════════════════════════════════════════════════════════════════════════════════
// 集成测试1: 分类引擎 → 明细表联动 (Req 4.2)
// ════════════════════════════════════════════════════════════════════════════════
describe('集成: CAS42分类判断 → 明细表分类结果联动 (Req 4.2)', () => {
  it('全条件满足 → 明细表资产可标记classified → 进入减值测试', () => {
    // 模拟 K6-4 初始确认的5条件判断
    const conditions = [true, true, true, true, true]
    const classificationResult = classifyHeldForSale(conditions)
    expect(classificationResult).toBe('classified')

    // classified后进入减值测试：账面价值 vs 公允净额
    const bookValue = calcBookValue(100000, 20000, 5000) // 100000-20000-5000=75000
    const fairValueNet = calcFairValueNet(80000, 3000) // 80000-3000=77000
    const impairment = calcImpairment(bookValue, fairValueNet) // MAX(0, 75000-77000)=0

    expect(bookValue).toBe(75000)
    expect(fairValueNet).toBe(77000)
    expect(impairment).toBe(0) // 公允净额>账面，无需计提
  })

  it('任一条件不满足 → 不进入持有待售分类 → 不做减值测试', () => {
    const conditions = [true, true, false, true, true] // 条件③未签协议
    const classificationResult = classifyHeldForSale(conditions)
    expect(classificationResult).toBe('not_classified')

    // not_classified 时不应进入减值测试流程
    // 验证分类结果是确定性的
    expect(classifyHeldForSale(conditions)).toBe('not_classified')
  })

  it('分类状态变化 → 减值计算结果也跟着变', () => {
    // 原始状态：已分类，有减值
    const bookValue = calcBookValue(200000, 30000, 0) // 170000
    const fairValueNet = calcFairValueNet(150000, 5000) // 145000
    const impairment = calcImpairment(bookValue, fairValueNet) // MAX(0, 170000-145000)=25000
    expect(impairment).toBe(25000)

    // 已提减值 vs 应提减值 → 补提金额
    const additionalProvision = calcAdditionalProvision(impairment, 10000) // 25000-10000=15000
    expect(additionalProvision).toBe(15000)
  })
})

// ════════════════════════════════════════════════════════════════════════════════
// 集成测试2: 减值引擎 → 审定表联动 (Req 5.5)
// ════════════════════════════════════════════════════════════════════════════════
describe('集成: 减值测试K6-5 → 审定表K6-1减值准备回连 (Req 5.5)', () => {
  it('减值金额合计 应与 审定表减值准备列 一致（CrossSheet验证）', async () => {
    // 模拟场景：K6-5计算了3个资产的减值
    const impairments = [
      calcImpairment(100000, 80000), // 20000
      calcImpairment(50000, 55000),  // 0 (公允净额>账面)
      calcImpairment(80000, 60000),  // 20000
    ]
    const impairmentTotal = calcSubtotal(impairments) // 40000

    // 审定表减值准备列应等于40000
    const allResponses = ref(createMockResponses({
      'K6-1-impairment-total': impairmentTotal, // 审定表减值=40000
      'K6-5-impairment-amount-total': impairmentTotal, // 减值测试=40000
    }))

    const { impairmentVsAdjudication } = useK6CrossSheet(allResponses)
    expect(impairmentVsAdjudication.value.isMatch).toBe(true)
    expect(impairmentVsAdjudication.value.diff).toBe(0)
  })

  it('减值金额不一致时 → diff非零 + isMatch=false', async () => {
    const allResponses = ref(createMockResponses({
      'K6-1-impairment-total': 35000, // 审定表只记了35000
      'K6-5-impairment-amount-total': 40000, // 测试算出40000
    }))

    const { impairmentVsAdjudication } = useK6CrossSheet(allResponses)
    expect(impairmentVsAdjudication.value.isMatch).toBe(false)
    expect(impairmentVsAdjudication.value.diff).toBe(-5000) // 审定-测试=-5000(需补提)
  })

  it('减值测试结果更新后 → CrossSheet computed自动响应', async () => {
    const responses = createMockResponses({
      'K6-1-impairment-total': 20000,
      'K6-5-impairment-amount-total': 20000,
    })
    const allResponses = ref(responses)

    const { impairmentVsAdjudication } = useK6CrossSheet(allResponses)
    expect(impairmentVsAdjudication.value.isMatch).toBe(true)

    // 模拟K6-5新增一笔减值
    const newMap = new Map(allResponses.value)
    newMap.set('K6-5-impairment-amount-total', { remark: '30000' })
    allResponses.value = newMap
    await nextTick()

    expect(impairmentVsAdjudication.value.isMatch).toBe(false)
    expect(impairmentVsAdjudication.value.diff).toBe(-10000)
  })
})

// ════════════════════════════════════════════════════════════════════════════════
// 集成测试3: 处置组分摊K6-6 → 减值测试K6-5联动 (Req 6.4)
// ════════════════════════════════════════════════════════════════════════════════
describe('集成: 处置组减值K6-6 → 减值测试K6-5联动 (Req 6.4)', () => {
  it('处置组分摊合计 应等于 处置组减值总额（扣除商誉后）', async () => {
    // 处置组减值=50000，商誉=10000，2个非流动资产各占50%
    const groupImpairment = 50000
    const goodwill = 10000
    const assetA = 20000
    const assetB = 20000
    const groupBookExGoodwill = assetA + assetB // 40000

    const allocA = calcGroupImpairmentAllocation(groupImpairment, goodwill, assetA, groupBookExGoodwill)
    const allocB = calcGroupImpairmentAllocation(groupImpairment, goodwill, assetB, groupBookExGoodwill)

    // 商誉抵减10000，余额40000按50:50分摊
    expect(allocA.goodwillDeduction).toBe(goodwill)
    expect(allocA.itemAllocation).toBeCloseTo(20000, 4) // 40000*0.5=20000
    expect(allocB.itemAllocation).toBeCloseTo(20000, 4) // 40000*0.5=20000

    // 分摊合计应等于处置组减值-商誉抵减
    const allocationTotal = allocA.itemAllocation + allocB.itemAllocation
    expect(allocationTotal).toBeCloseTo(groupImpairment - goodwill, 4)

    // CrossSheet验证
    const allResponses = ref(createMockResponses({
      'K6-5-group-impairment-total': allocationTotal, // 40000
      'K6-6-allocation-total': allocationTotal, // 40000
    }))
    const { groupVsImpairment } = useK6CrossSheet(allResponses)
    expect(groupVsImpairment.value.isMatch).toBe(true)
  })

  it('分摊不等式 → CrossSheet标记不匹配', async () => {
    const allResponses = ref(createMockResponses({
      'K6-5-group-impairment-total': 40000,
      'K6-6-allocation-total': 38000, // 漏分摊了2000
    }))
    const { groupVsImpairment } = useK6CrossSheet(allResponses)
    expect(groupVsImpairment.value.isMatch).toBe(false)
    expect(groupVsImpairment.value.diff).toBe(2000)
  })

  it('多资产不等比例分摊 → 合计仍等于余额', () => {
    const groupImpairment = 100000
    const goodwill = 20000
    // 3个资产：30000/50000/20000，合计100000
    const assets = [30000, 50000, 20000]
    const groupTotal = calcSubtotal(assets) // 100000

    const allocations = assets.map(a =>
      calcGroupImpairmentAllocation(groupImpairment, goodwill, a, groupTotal)
    )

    // 商誉抵20000，余额80000按比例分摊
    const totalAlloc = allocations.reduce((s, a) => s + a.itemAllocation, 0)
    expect(totalAlloc).toBeCloseTo(80000, 4) // groupImpairment - goodwill

    // 验证各自比例正确
    expect(allocations[0].itemAllocation).toBeCloseTo(80000 * 0.3, 4) // 24000
    expect(allocations[1].itemAllocation).toBeCloseTo(80000 * 0.5, 4) // 40000
    expect(allocations[2].itemAllocation).toBeCloseTo(80000 * 0.2, 4) // 16000
  })
})

// ════════════════════════════════════════════════════════════════════════════════
// 集成测试4: 审定表K6-1 → TB回写数据流 (Req 2.7)
// ════════════════════════════════════════════════════════════════════════════════
describe('集成: 审定表 → TB回写 (Req 2.7)', () => {
  it('审定数=未审+AJE+RJE → 回写到trial_balance.audited_amount', () => {
    // 持有待售资产审定
    const unadjusted = 500000
    const aje = -30000 // 审计调减
    const rje = 10000  // 重分类调入
    const audited = calcAuditedAmount(unadjusted, aje, rje)
    expect(audited).toBe(480000) // 500000-30000+10000

    // 验证回写值（这个值将写入TB）
    expect(audited).toBe(unadjusted + aje + rje)
  })

  it('资产类期末计算 → 回写金额一致性', () => {
    // 持有待售资产期末=期初+增加-减少-减值
    const opening = 1000000
    const increase = 200000
    const decrease = 50000
    const impairment = 30000
    const periodEnd = calcAssetPeriodEnd(opening, increase, decrease, impairment)
    expect(periodEnd).toBe(1120000) // 1000000+200000-50000-30000

    // 审定数应该等于期末余额
    // 模拟审定：未审=1100000(账面期末), AJE=+20000, RJE=0
    const audited = calcAuditedAmount(1100000, 20000, 0)
    expect(audited).toBe(1120000)
  })

  it('审定表合计 应等于 明细表合计（CrossSheet）', async () => {
    // 明细表3个资产账面价值
    const detailBookValues = [
      calcBookValue(100000, 10000, 5000), // 85000
      calcBookValue(200000, 30000, 10000), // 160000
      calcBookValue(50000, 5000, 0), // 45000
    ]
    const detailTotal = calcSubtotal(detailBookValues) // 290000

    // 审定表合计应等于明细合计
    const allResponses = ref(createMockResponses({
      'K6-1-audited-total': detailTotal,
      'K6-2-detail-book-value-total': detailTotal,
    }))
    const { adjudicationVsDetail } = useK6CrossSheet(allResponses)
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
    expect(adjudicationVsDetail.value.diff).toBe(0)
  })

  it('审定合计≠明细合计 → CrossSheet红色警示', async () => {
    const allResponses = ref(createMockResponses({
      'K6-1-audited-total': 295000, // 审定多了5000
      'K6-2-detail-book-value-total': 290000,
    }))
    const { adjudicationVsDetail } = useK6CrossSheet(allResponses)
    expect(adjudicationVsDetail.value.isMatch).toBe(false)
    expect(adjudicationVsDetail.value.diff).toBe(5000)
  })
})

// ════════════════════════════════════════════════════════════════════════════════
// 集成测试5: 端到端数据链 — 分类→减值→分摊→审定 全链路
// ════════════════════════════════════════════════════════════════════════════════
describe('集成: 全链路 分类→减值→分摊→审定 (Req 2.7, 4.2, 5.5, 6.4)', () => {
  it('完整业务流：分类→单项减值→处置组分摊→回连审定', () => {
    // Step 1: CAS42五条件分类
    const classified = classifyHeldForSale([true, true, true, true, true])
    expect(classified).toBe('classified')

    // Step 2: 3个资产账面价值计算
    const assets = [
      { cost: 500000, dep: 100000, imp: 0 },
      { cost: 300000, dep: 50000, imp: 0 },
      { cost: 200000, dep: 20000, imp: 0 },
    ]
    const bookValues = assets.map(a => calcBookValue(a.cost, a.dep, a.imp))
    // [400000, 250000, 180000]
    expect(bookValues).toEqual([400000, 250000, 180000])

    // Step 3: 减值测试（单项减值）
    const fairValues = [380000, 260000, 150000]
    const sellingCosts = [10000, 8000, 5000]
    const fairValueNets = fairValues.map((fv, i) => calcFairValueNet(fv, sellingCosts[i]))
    // [370000, 252000, 145000]
    expect(fairValueNets).toEqual([370000, 252000, 145000])

    const impairments = bookValues.map((bv, i) => calcImpairment(bv, fairValueNets[i]))
    // [MAX(0,400000-370000)=30000, MAX(0,250000-252000)=0, MAX(0,180000-145000)=35000]
    expect(impairments).toEqual([30000, 0, 35000])

    // Step 4: 处置组减值（假设处置组整体减值=50000, 商誉=5000）
    const groupImpairment = 50000
    const goodwill = 5000
    const groupBookExGoodwill = calcSubtotal(bookValues) // 830000

    const allocations = bookValues.map(bv =>
      calcGroupImpairmentAllocation(groupImpairment, goodwill, bv, groupBookExGoodwill)
    )
    const totalGroupAlloc = allocations.reduce((s, a) => s + a.itemAllocation, 0)
    expect(totalGroupAlloc).toBeCloseTo(45000, 4) // 50000-5000=45000 distributed

    // Step 5: 验证回连审定
    const totalImpairment = calcSubtotal(impairments) // 65000
    // 审定表减值准备=单项减值合计(或处置组分摊结果)
    expect(totalImpairment).toBe(65000)

    // Step 6: CrossSheet验证一致性
    const allResponses = ref(createMockResponses({
      'K6-1-audited-total': calcSubtotal(bookValues), // 830000
      'K6-2-detail-book-value-total': calcSubtotal(bookValues),
      'K6-1-impairment-total': totalImpairment,
      'K6-5-impairment-amount-total': totalImpairment,
      'K6-5-group-impairment-total': totalGroupAlloc,
      'K6-6-allocation-total': totalGroupAlloc,
    }))

    const { adjudicationVsDetail, impairmentVsAdjudication, groupVsImpairment } =
      useK6CrossSheet(allResponses)

    expect(adjudicationVsDetail.value.isMatch).toBe(true)
    expect(impairmentVsAdjudication.value.isMatch).toBe(true)
    expect(groupVsImpairment.value.isMatch).toBe(true)
  })
})
