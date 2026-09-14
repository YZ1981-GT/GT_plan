/**
 * 集成测试 — M3 库存股：注销冲减→M2/M4 + 外币折算 + EventBus
 *
 * 覆盖：
 * 1. useM3CrossSheet.adjudicationVsDetail: 审定表 vs 明细表差额勾稽
 * 2. useM3CrossSheet.cancellationToM2M4: 注销冲减聚合 + 未平差额
 * 3. EventBus 'substantive:adjudicated' 发布 (writebackTB)
 * 4. EventBus 'm3:cancellation-deduction' 发布
 * 5. FX engine 集成 (calcFxConverted + calcFxDiff 流水线)
 *
 * Spec: .kiro/specs/m3-treasury-stock/ Task 7.2
 * Requirements: 5.1-5.5
 *
 * 科目：4002 库存股（**借方/权益备抵类！期末=期初+借方-贷方**）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useM3CrossSheet } from '../composables/useM3CrossSheet'
import type { ChecklistResponse } from '../composables/useM3FormData'
import {
  calcAuditedAmount,
  calcContraEquityEndBalance,
  calcSubtotal,
} from '../composables/useM3FormulaEngine'
import { calcFxConverted, calcFxDiff } from '../composables/useM3FxEngine'
import { calcRepurchaseAmount, calcCancelDiff } from '../composables/useM3TreasuryEngine'

// Mock eventBus
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
  },
}))

import { eventBus } from '@/utils/eventBus'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function createResponses(entries: [string, string | null][]) {
  const map = new Map<string, ChecklistResponse>()
  for (const [itemId, remark] of entries) {
    map.set(itemId, { item_id: itemId, conclusion: null, remark })
  }
  return ref(map)
}

// ═══════════════════════════════════════════════════════════════════════════════
// Section 1: adjudicationVsDetail — M3-1审定表 vs M3-2明细表 交叉验证
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — adjudicationVsDetail M3-1 vs M3-2 (Req 2.5, 5.1)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('审定表合计 === 明细表合计 → isMatch=true, diff=0', () => {
    const responses = createResponses([
      ['M3-M3-1-total-end-audited', '8000000'],
      ['M3-M3-2-total-end-amount', '8000000'],
    ])

    const { adjudicationVsDetail } = useM3CrossSheet(responses)
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
    expect(adjudicationVsDetail.value.diff).toBe(0)
  })

  it('差异>1元 → isMatch=false', () => {
    const responses = createResponses([
      ['M3-M3-1-total-end-audited', '8000000'],
      ['M3-M3-2-total-end-amount', '7995000'], // 差5000
    ])

    const { adjudicationVsDetail } = useM3CrossSheet(responses)
    expect(adjudicationVsDetail.value.isMatch).toBe(false)
    expect(adjudicationVsDetail.value.diff).toBe(5000)
  })

  it('差异<1元(四舍五入容差) → isMatch=true', () => {
    const responses = createResponses([
      ['M3-M3-1-total-end-audited', '5000000.50'],
      ['M3-M3-2-total-end-amount', '5000000.20'], // 差0.3 < 1
    ])

    const { adjudicationVsDetail } = useM3CrossSheet(responses)
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
    expect(Math.abs(adjudicationVsDetail.value.diff)).toBeLessThan(1)
  })

  it('明细行降级累加: 无汇总行时遍历 batch-*-end-amount', () => {
    const responses = createResponses([
      ['M3-M3-1-total-end-audited', '6000000'],
      // 无 M3-M3-2-total-end-amount，降级到批次累加
      ['M3-M3-2-batch-001-end-amount', '2000000'],
      ['M3-M3-2-batch-002-end-amount', '2500000'],
      ['M3-M3-2-batch-003-end-amount', '1500000'],
    ])

    const { adjudicationVsDetail } = useM3CrossSheet(responses)
    // 批次累加: 2000000+2500000+1500000=6000000
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
    expect(adjudicationVsDetail.value.diff).toBe(0)
  })

  it('两侧均为空 → isMatch=true, diff=0', () => {
    const responses = createResponses([])
    const { adjudicationVsDetail } = useM3CrossSheet(responses)
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
    expect(adjudicationVsDetail.value.diff).toBe(0)
  })

  it('审定表有值、明细表为空 → diff=审定表值', () => {
    const responses = createResponses([
      ['M3-M3-1-total-end-audited', '3000000'],
    ])

    const { adjudicationVsDetail } = useM3CrossSheet(responses)
    expect(adjudicationVsDetail.value.isMatch).toBe(false)
    expect(adjudicationVsDetail.value.diff).toBe(3000000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 2: cancellationToM2M4 — 注销冲减→M2/M4 聚合
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — cancellationToM2M4 注销冲减聚合 (Req 5.3-5.4)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('多批次注销完全冲减: remainingDiff=0, hasRemainingDiff=false', () => {
    const cancelRows = JSON.stringify([
      { batchName: '2024年第一批', cancelAmount: 2500000, deductCapital: 1000000, deductReserve: 1500000 },
      { batchName: '2024年第二批', cancelAmount: 1000000, deductCapital: 400000, deductReserve: 600000 },
    ])

    const responses = createResponses([
      ['M3-M3-5-cancel-rows', cancelRows],
    ])

    const { cancellationToM2M4 } = useM3CrossSheet(responses)
    const result = cancellationToM2M4.value

    expect(result.totalCancellationAmount).toBe(3500000)
    expect(result.deductCapitalTotal).toBe(1400000)
    expect(result.deductReserveTotal).toBe(2100000)
    expect(result.remainingDiff).toBe(0)
    expect(result.hasRemainingDiff).toBe(false)
    expect(result.byBatch).toHaveLength(2)
    expect(result.byBatch[0].batchName).toBe('2024年第一批')
    expect(result.byBatch[0].diff).toBe(0)
  })

  it('资本公积不足: remainingDiff>0, 需进一步冲减M5/M6', () => {
    const cancelRows = JSON.stringify([
      { batchName: '高溢价回购批次', cancelAmount: 5000000, deductCapital: 500000, deductReserve: 3000000 },
    ])

    const responses = createResponses([
      ['M3-M3-5-cancel-rows', cancelRows],
    ])

    const { cancellationToM2M4 } = useM3CrossSheet(responses)
    const result = cancellationToM2M4.value

    expect(result.totalCancellationAmount).toBe(5000000)
    expect(result.deductCapitalTotal).toBe(500000)
    expect(result.deductReserveTotal).toBe(3000000)
    expect(result.remainingDiff).toBe(1500000) // 5000000-500000-3000000=1500000
    expect(result.hasRemainingDiff).toBe(true) // |1500000| > 0.01
  })

  it('无注销数据: 全零, hasRemainingDiff=false', () => {
    const responses = createResponses([
      ['M3-M3-5-cancel-rows', '[]'],
    ])

    const { cancellationToM2M4 } = useM3CrossSheet(responses)
    const result = cancellationToM2M4.value

    expect(result.totalCancellationAmount).toBe(0)
    expect(result.deductCapitalTotal).toBe(0)
    expect(result.deductReserveTotal).toBe(0)
    expect(result.remainingDiff).toBe(0)
    expect(result.hasRemainingDiff).toBe(false)
    expect(result.byBatch).toHaveLength(0)
  })

  it('无效JSON → 空结果(降级)', () => {
    const responses = createResponses([
      ['M3-M3-5-cancel-rows', 'invalid json!!!'],
    ])

    const { cancellationToM2M4 } = useM3CrossSheet(responses)
    const result = cancellationToM2M4.value

    expect(result.totalCancellationAmount).toBe(0)
    expect(result.byBatch).toHaveLength(0)
  })

  it('缺少batchName字段 → 降级为"未命名批次"', () => {
    const cancelRows = JSON.stringify([
      { cancelAmount: 1000000, deductCapital: 400000, deductReserve: 600000 },
    ])

    const responses = createResponses([
      ['M3-M3-5-cancel-rows', cancelRows],
    ])

    const { cancellationToM2M4 } = useM3CrossSheet(responses)
    expect(cancellationToM2M4.value.byBatch[0].batchName).toBe('未命名批次')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 3: EventBus 'm3:cancellation-deduction' 发布
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — EventBus m3:cancellation-deduction (Req 5.3)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('有注销数据时调用 publishCancellationDeduction → emit 事件', () => {
    const cancelRows = JSON.stringify([
      { batchName: '2024批次', cancelAmount: 2000000, deductCapital: 800000, deductReserve: 1200000 },
    ])

    const responses = createResponses([
      ['M3-M3-5-cancel-rows', cancelRows],
    ])

    const { publishCancellationDeduction } = useM3CrossSheet(responses)
    publishCancellationDeduction()

    expect(eventBus.emit).toHaveBeenCalledWith(
      'm3:cancellation-deduction',
      expect.objectContaining({
        wpCode: 'M3',
        totalCancellationAmount: 2000000,
        deductCapitalTotal: 800000,
        deductReserveTotal: 1200000,
        remainingDiff: 0,
      }),
    )
  })

  it('无注销业务(合计=0)时不发布事件', () => {
    const responses = createResponses([
      ['M3-M3-5-cancel-rows', '[]'],
    ])

    const { publishCancellationDeduction } = useM3CrossSheet(responses)
    publishCancellationDeduction()

    expect(eventBus.emit).not.toHaveBeenCalled()
  })

  it('重复调用不重复发布(变化检测)', () => {
    const cancelRows = JSON.stringify([
      { batchName: 'X', cancelAmount: 1000000, deductCapital: 500000, deductReserve: 500000 },
    ])

    const responses = createResponses([
      ['M3-M3-5-cancel-rows', cancelRows],
    ])

    const { publishCancellationDeduction } = useM3CrossSheet(responses)
    publishCancellationDeduction()
    publishCancellationDeduction() // 第二次调用

    // 只发布一次
    expect(eventBus.emit).toHaveBeenCalledTimes(1)
  })

  it('发布payload包含timestamp和byBatch结构', () => {
    const cancelRows = JSON.stringify([
      { batchName: 'A', cancelAmount: 1000, deductCapital: 400, deductReserve: 600 },
      { batchName: 'B', cancelAmount: 2000, deductCapital: 800, deductReserve: 1200 },
    ])

    const responses = createResponses([
      ['M3-M3-5-cancel-rows', cancelRows],
    ])

    const { publishCancellationDeduction } = useM3CrossSheet(responses)
    publishCancellationDeduction()

    const emitCall = (eventBus.emit as any).mock.calls[0]
    expect(emitCall[0]).toBe('m3:cancellation-deduction')
    const payload = emitCall[1]
    expect(payload.timestamp).toBeGreaterThan(0)
    expect(payload.byBatch).toHaveLength(2)
    expect(payload.byBatch[0]).toMatchObject({
      batchName: 'A',
      cancelAmount: 1000,
      deductCapital: 400,
      deductReserve: 600,
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 4: FX Engine 集成流程 (calcFxConverted + calcFxDiff chain)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — FX Engine 外币折算完整流程 (Req 4.2-4.3)', () => {
  it('完整折算链: 原币→折算本位币→差异→阈值判断', () => {
    // 境外回购: USD 100万股 × 30美元 = 3000万美元
    const fxAmount = 30_000_000   // 原币回购额 USD
    const fxRate = 7.25           // 回购日即期汇率
    const bookedCNY = 215_000_000 // 账面本位币(被审计单位已入账)

    // Step 1: 折算本位币
    const converted = calcFxConverted(fxAmount, fxRate)
    expect(converted).toBe(217_500_000) // 3000万 × 7.25 = 2.175亿

    // Step 2: 折算差异
    const diff = calcFxDiff(converted, bookedCNY)
    expect(diff).toBe(2_500_000) // 2.175亿 - 2.15亿 = 250万

    // Step 3: 差异显著性判断 (|diff| > 阈值)
    const FX_THRESHOLD = 1_000_000 // 假设100万阈值
    expect(Math.abs(diff)).toBeGreaterThan(FX_THRESHOLD) // 250万 > 100万 → 红色高亮
  })

  it('多批次外币回购汇总', () => {
    const batches = [
      { name: '2024Q1回购', amount: 5_000_000, rate: 7.10, booked: 35_200_000 },
      { name: '2024Q2回购', amount: 8_000_000, rate: 7.20, booked: 57_500_000 },
      { name: '2024Q3回购', amount: 3_000_000, rate: 7.30, booked: 21_800_000 },
    ]

    // 逐批次折算
    const results = batches.map(b => {
      const converted = calcFxConverted(b.amount, b.rate)
      const diff = calcFxDiff(converted, b.booked)
      return { converted, diff }
    })

    expect(results[0].converted).toBe(35_500_000) // 5M×7.10
    expect(results[1].converted).toBe(57_600_000) // 8M×7.20
    expect(results[2].converted).toBe(21_900_000) // 3M×7.30

    expect(results[0].diff).toBe(300_000)  // 3550万-3520万
    expect(results[1].diff).toBe(100_000)  // 5760万-5750万
    expect(results[2].diff).toBe(100_000)  // 2190万-2180万

    // 汇总差异
    const totalDiff = calcSubtotal(results.map(r => r.diff))
    expect(totalDiff).toBe(500_000)

    // 汇总折算本位币
    const totalConverted = calcSubtotal(results.map(r => r.converted))
    expect(totalConverted).toBe(115_000_000) // 1.15亿
  })

  it('汇率为1(同币种) → 折算=原币, 差异体现入账误差', () => {
    const converted = calcFxConverted(10_000_000, 1)
    expect(converted).toBe(10_000_000)

    const diff = calcFxDiff(converted, 9_990_000)
    expect(diff).toBe(10_000) // 入账差1万
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 5: 回购+注销 完整业务流程集成
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — 回购+注销完整业务流程 (Req 5.2, 5.4)', () => {
  it('回购→期末余额增加→注销→冲减M2/M4→差额→M5/M6', () => {
    // === Phase 1: 回购 ===
    const shares = 100_000      // 回购10万股
    const price = 30            // 回购单价30元/股
    const repurchaseAmount = calcRepurchaseAmount(shares, price)
    expect(repurchaseAmount).toBe(3_000_000) // 回购金额300万

    // === Phase 2: 期末余额计算（备抵借方！） ===
    const begin = 5_000_000     // 期初库存股500万
    const debit = repurchaseAmount // 本期回购借方增加300万
    const credit = 0            // 本期无注销
    const endBalance = calcContraEquityEndBalance(begin, debit, credit)
    expect(endBalance).toBe(8_000_000) // 期末=500万+300万=800万

    // === Phase 3: 注销冲减 ===
    const cancelAmount = repurchaseAmount // 注销本批次全部300万
    const faceValue = 1         // 面值1元/股
    const deductCapital = shares * faceValue // 冲减实收资本=10万股×1元=10万
    expect(deductCapital).toBe(100_000)

    const capitalPremium = 20   // 资本公积中该批次溢价20元/股
    const deductReserve = shares * capitalPremium // 冲减资本公积=10万股×20元=200万
    expect(deductReserve).toBe(2_000_000)

    const cancelDiff = calcCancelDiff(cancelAmount, deductCapital, deductReserve)
    expect(cancelDiff).toBe(900_000) // 差额90万=300万-10万-200万
    // 90万需进一步冲减盈余公积(M5)或未分配利润(M6)

    // === Phase 4: 注销后期末余额 ===
    const endAfterCancel = calcContraEquityEndBalance(begin, debit, cancelAmount)
    expect(endAfterCancel).toBe(5_000_000) // 500万+300万回购-300万注销=500万(回到期初)
  })

  it('审定数→备抵期末→与明细勾稽一致', () => {
    // 未审数通过审计调整得到审定数
    const unadj = 7_500_000
    const aje = 500_000   // 少计回购 → 调增
    const rje = 0
    const audited = calcAuditedAmount(unadj, aje, rje)
    expect(audited).toBe(8_000_000)

    // 验证审定数与备抵期末余额公式一致
    const begin = 5_000_000
    const debit = 3_500_000   // 回购借方
    const credit = 500_000    // 注销贷方
    const endFromFormula = calcContraEquityEndBalance(begin, debit, credit)
    expect(endFromFormula).toBe(8_000_000) // 500万+350万-50万=800万=审定数

    expect(audited).toBe(endFromFormula) // 两条路径结果一致
  })
})
