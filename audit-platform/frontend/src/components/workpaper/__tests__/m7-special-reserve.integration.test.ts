/**
 * 集成测试 — M7 专项储备：计提测试 + 资本化支出→H1联动
 *
 * 覆盖：
 * 1. 计提测试流程：M7-4按产量/收入分档计提安全生产费 + 差异高亮
 * 2. 资本化支出→H1联动：useM7CrossSheet capitalExpToH1 + cross_wp_ref + EventBus
 * 3. adjudicationVsDetail：M7-1审定 vs M7-2明细 交叉验证
 * 4. EventBus闭环：h1:fixed-asset-confirmed → 持久化 → 一致性校验
 * 5. 计提差异阈值高亮：|diff|>阈值→红色
 *
 * Spec: .kiro/specs/m7-special-reserve/ Task 7.2
 * Requirements: 4.1-4.6, 5.1
 *
 * 科目：4201 专项储备（**贷方/权益类！期末=期初+贷方-借方**）
 * 安全生产费：高危行业按产量分档 / 建筑施工按营收比例
 * 资本化支出：形成固定资产联动H1 + 全额折旧冲减专项储备
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, effectScope } from 'vue'
import { useM7CrossSheet } from '../composables/useM7CrossSheet'
import type { ChecklistResponse } from '../composables/useM7CrossSheet'
import {
  calcAccrualByOutput,
  calcAccrualByRevenue,
  calcAccrualDiff,
} from '../composables/useM7AccrualEngine'
import {
  calcEquityEndBalance,
  calcSubtotal,
} from '../composables/useM7FormulaEngine'

// ─── Mock EventBus ───────────────────────────────────────────────────────────
const onHandlers = new Map<string, Function[]>()
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: vi.fn((event: string, payload: any) => {
      const handlers = onHandlers.get(event)
      if (handlers) {
        handlers.forEach((h) => h(payload))
      }
    }),
    on: vi.fn((event: string, handler: Function) => {
      if (!onHandlers.has(event)) onHandlers.set(event, [])
      onHandlers.get(event)!.push(handler)
    }),
    off: vi.fn((event: string, handler: Function) => {
      const handlers = onHandlers.get(event)
      if (handlers) {
        const idx = handlers.indexOf(handler)
        if (idx >= 0) handlers.splice(idx, 1)
      }
    }),
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
// Section 1: 计提测试流程 — 按产量分档计提安全生产费 (Req 4.1-4.4, 4.6)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — M7-4 安全生产费按产量分档计提流程 (Req 4.2, 4.6)', () => {
  it('煤矿企业三档计提：≤100万吨5元 + >100~500万吨4元 + >500万吨3元', () => {
    // 模拟煤矿企业：年产量650万吨
    const tiers = [
      { output: 1_000_000, rate: 5 },   // ≤100万吨×5元=500万
      { output: 4_000_000, rate: 4 },   // 100~500万吨×4元=1600万
      { output: 1_500_000, rate: 3 },   // >500万吨×3元=450万
    ]

    const estimated = calcAccrualByOutput(tiers)
    expect(estimated).toBe(5_000_000 + 16_000_000 + 4_500_000) // 2550万
    expect(estimated).toBe(25_500_000)

    // 账面计提2400万（企业少提了）
    const booked = 24_000_000
    const diff = calcAccrualDiff(estimated, booked)
    expect(diff).toBe(1_500_000) // 少提150万，正差=风险
    expect(diff).toBeGreaterThan(0) // 正差=少提=需关注
  })

  it('非煤矿山单档计提：产量×标准', () => {
    const tiers = [{ output: 800_000, rate: 6 }] // 80万吨×6元/吨
    const estimated = calcAccrualByOutput(tiers)
    expect(estimated).toBe(4_800_000)

    // 账面已足额计提
    const diff = calcAccrualDiff(estimated, 4_800_000)
    expect(diff).toBe(0)
  })

  it('危险品企业超额累退三档', () => {
    // 营业收入1.2亿，按超额累退分档（类似个税梯度）
    const tiers = [
      { output: 10_000_000, rate: 0.04 },    // ≤1000万×4%=40万
      { output: 90_000_000, rate: 0.02 },    // 1000~10000万×2%=180万
      { output: 20_000_000, rate: 0.01 },    // >1亿×1%=20万
    ]
    const estimated = calcAccrualByOutput(tiers)
    expect(estimated).toBe(400_000 + 1_800_000 + 200_000)
    expect(estimated).toBe(2_400_000)
  })

  it('9公式实时计算链路：各档G=E×F → 合计=SUM(G) → 差异=合计-账面', () => {
    const tiers = [
      { output: 2_000_000, rate: 5 },   // G1=1000万
      { output: 1_000_000, rate: 4 },   // G2=400万
      { output: 500_000, rate: 3 },     // G3=150万
    ]

    // 公式1-3: G=E×F（各档应计金额）
    const g1 = tiers[0].output * tiers[0].rate
    const g2 = tiers[1].output * tiers[1].rate
    const g3 = tiers[2].output * tiers[2].rate
    expect(g1).toBe(10_000_000)
    expect(g2).toBe(4_000_000)
    expect(g3).toBe(1_500_000)

    // 公式4: G_total = SUM(G)
    const gTotal = calcAccrualByOutput(tiers)
    expect(gTotal).toBe(g1 + g2 + g3)
    expect(gTotal).toBe(15_500_000)

    // 公式5: diff = estimated - booked
    const booked = 14_000_000
    const diff = calcAccrualDiff(gTotal, booked)
    expect(diff).toBe(1_500_000) // 少提150万

    // 验证 calcSubtotal 与 calcAccrualByOutput 结果一致
    const amounts = tiers.map(t => t.output * t.rate)
    expect(calcSubtotal(amounts)).toBe(gTotal)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 2: 计提测试流程 — 按营业收入计提 (Req 4.3)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — M7-4 安全生产费按营业收入计提 (Req 4.3)', () => {
  it('建筑施工企业：建安造价5亿×2%=1000万', () => {
    const revenue = 500_000_000
    const rate = 0.02
    const estimated = calcAccrualByRevenue(revenue, rate)
    expect(estimated).toBe(10_000_000)

    const booked = 9_500_000
    const diff = calcAccrualDiff(estimated, booked)
    expect(diff).toBe(500_000) // 少提50万
  })

  it('交通运输—铁路：营收8亿×1.5%=1200万', () => {
    const estimated = calcAccrualByRevenue(800_000_000, 0.015)
    expect(estimated).toBe(12_000_000)
  })

  it('两种计提方式可切换：同一企业产量vs收入结果比较', () => {
    // 产量方式
    const tierEstimated = calcAccrualByOutput([
      { output: 500_000, rate: 6 },
      { output: 200_000, rate: 5 },
    ])
    expect(tierEstimated).toBe(4_000_000)

    // 收入方式
    const revenueEstimated = calcAccrualByRevenue(200_000_000, 0.02)
    expect(revenueEstimated).toBe(4_000_000)

    // 同一账面计提，差异不同
    const booked = 3_800_000
    expect(calcAccrualDiff(tierEstimated, booked)).toBe(200_000)
    expect(calcAccrualDiff(revenueEstimated, booked)).toBe(200_000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 3: 计提差异阈值高亮 (Req 4.5)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — 计提差异阈值高亮 (Req 4.5)', () => {
  // 阈值逻辑：|diff| > absolute(1000) 且 相对差异 > relative(5%)
  const THRESHOLD_ABSOLUTE = 1000
  const THRESHOLD_RELATIVE = 0.05

  function isDiffExceedThreshold(diffValue: number, estimatedValue: number): boolean {
    if (Math.abs(diffValue) <= THRESHOLD_ABSOLUTE) return false
    if (estimatedValue === 0) return Math.abs(diffValue) > THRESHOLD_ABSOLUTE
    return Math.abs(diffValue / estimatedValue) > THRESHOLD_RELATIVE
  }

  it('差异150万/应计2550万=5.88%>5% → 红色高亮', () => {
    const diff = 1_500_000
    const estimated = 25_500_000
    expect(isDiffExceedThreshold(diff, estimated)).toBe(true)
  })

  it('差异500元<1000元绝对阈值 → 不高亮', () => {
    expect(isDiffExceedThreshold(500, 10_000_000)).toBe(false)
  })

  it('差异2000元/应计1亿=0.002%<5% → 不高亮（虽超绝对但未超相对）', () => {
    expect(isDiffExceedThreshold(2000, 100_000_000)).toBe(false)
  })

  it('差异=0 → 不高亮', () => {
    expect(isDiffExceedThreshold(0, 5_000_000)).toBe(false)
  })

  it('应计=0 + 差异>1000 → 高亮（防御性）', () => {
    expect(isDiffExceedThreshold(5000, 0)).toBe(true)
  })

  it('负差异(多提)-6%>5% → 高亮', () => {
    const diff = -600_000
    const estimated = 10_000_000
    expect(isDiffExceedThreshold(diff, estimated)).toBe(true)
  })

  it('完整计提流程→高亮判断', () => {
    const tiers = [
      { output: 1_000_000, rate: 5 },
      { output: 500_000, rate: 4 },
    ]
    const estimated = calcAccrualByOutput(tiers) // 500万+200万=700万
    expect(estimated).toBe(7_000_000)

    const booked = 6_500_000
    const diff = calcAccrualDiff(estimated, booked) // 50万
    expect(diff).toBe(500_000)

    // 50万/700万=7.1%>5%，且>1000元 → 红色高亮
    expect(isDiffExceedThreshold(diff, estimated)).toBe(true)
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Section 4: 资本化支出→H1联动 — useM7CrossSheet capitalExpToH1 (Req 5.1)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — 资本化支出→H1固定资产联动 (Req 5.1)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    onHandlers.clear()
  })

  it('M7-2资本化支出 === H1已确认转固 → isConsistent=true', () => {
    const responses = createResponses([
      ['M7-M7-2-total-capital-exp', '3000000'],
      ['M7-cross-h1-confirmed-amount', '3000000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { capitalExpToH1 } = useM7CrossSheet(responses)
      expect(capitalExpToH1.value.capitalExpTotal).toBe(3_000_000)
      expect(capitalExpToH1.value.h1ConfirmedAmount).toBe(3_000_000)
      expect(capitalExpToH1.value.diff).toBe(0)
      expect(capitalExpToH1.value.isConsistent).toBe(true)
    })
    scope.stop()
  })

  it('M7-2资本化支出 > H1确认 → isConsistent=false, 差额>0', () => {
    const responses = createResponses([
      ['M7-M7-2-total-capital-exp', '5000000'],
      ['M7-cross-h1-confirmed-amount', '4500000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { capitalExpToH1 } = useM7CrossSheet(responses)
      expect(capitalExpToH1.value.isConsistent).toBe(false)
      expect(capitalExpToH1.value.diff).toBe(500_000)
    })
    scope.stop()
  })

  it('H1尚未确认(金额=0) → diff=资本化支出全额', () => {
    const responses = createResponses([
      ['M7-M7-2-total-capital-exp', '2000000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { capitalExpToH1 } = useM7CrossSheet(responses)
      expect(capitalExpToH1.value.h1ConfirmedAmount).toBe(0)
      expect(capitalExpToH1.value.diff).toBe(2_000_000)
      expect(capitalExpToH1.value.isConsistent).toBe(false)
    })
    scope.stop()
  })

  it('M7-2明细行降级累加：无汇总行时遍历row-*-capital-exp', () => {
    const responses = createResponses([
      // 无 M7-M7-2-total-capital-exp 汇总行
      ['M7-M7-2-row-1-capital-exp', '800000'],
      ['M7-M7-2-row-2-capital-exp', '1200000'],
      ['M7-M7-2-row-3-capital-exp', '500000'],
      ['M7-cross-h1-confirmed-amount', '2500000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { capitalExpToH1 } = useM7CrossSheet(responses)
      // 800000+1200000+500000=2500000
      expect(capitalExpToH1.value.capitalExpTotal).toBe(2_500_000)
      expect(capitalExpToH1.value.isConsistent).toBe(true)
    })
    scope.stop()
  })

  it('差额在H1_DIFF_THRESHOLD(1元)内 → isConsistent=true', () => {
    const responses = createResponses([
      ['M7-M7-2-total-capital-exp', '1000000.5'],
      ['M7-cross-h1-confirmed-amount', '1000000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { capitalExpToH1 } = useM7CrossSheet(responses)
      expect(capitalExpToH1.value.isConsistent).toBe(true)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 5: EventBus H1→M7 — 'h1:fixed-asset-confirmed' (Req 5.1)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — EventBus h1:fixed-asset-confirmed → M7 (Req 5.1)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    onHandlers.clear()
  })

  it('H1发布转固确认 → _h1ConfirmedAmount更新 + 持久化allResponses', () => {
    const responses = createResponses([
      ['M7-M7-2-total-capital-exp', '3000000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { capitalExpToH1, _h1ConfirmedAmount } = useM7CrossSheet(responses)

      // 初始H1未确认
      expect(_h1ConfirmedAmount.value).toBe(0)
      expect(capitalExpToH1.value.isConsistent).toBe(false)

      // H1发布转固确认事件
      eventBus.emit('h1:fixed-asset-confirmed' as any, {
        wpCode: 'H1',
        amount: 3_000_000,
        source: 'M7专项储备资本化',
        timestamp: Date.now(),
      })

      // 更新
      expect(_h1ConfirmedAmount.value).toBe(3_000_000)
      expect(capitalExpToH1.value.isConsistent).toBe(true)
      expect(capitalExpToH1.value.diff).toBe(0)

      // 持久化到 allResponses
      const persisted = responses.value.get('M7-cross-h1-confirmed-amount')
      expect(persisted).toBeDefined()
      expect(persisted!.remark).toBe('3000000')
    })
    scope.stop()
  })

  it('H1 payload降级兼容：capitalExpAmount 字段', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { _h1ConfirmedAmount } = useM7CrossSheet(responses)

      eventBus.emit('h1:fixed-asset-confirmed' as any, {
        capitalExpAmount: 2_500_000,
      })

      expect(_h1ConfirmedAmount.value).toBe(2_500_000)
    })
    scope.stop()
  })

  it('从allResponses恢复已持久化的H1确认金额', () => {
    const responses = createResponses([
      ['M7-cross-h1-confirmed-amount', '4000000'],
      ['M7-M7-2-total-capital-exp', '4000000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { capitalExpToH1, _h1ConfirmedAmount } = useM7CrossSheet(responses)

      // 应从 allResponses 恢复
      expect(_h1ConfirmedAmount.value).toBe(4_000_000)
      expect(capitalExpToH1.value.isConsistent).toBe(true)
    })
    scope.stop()
  })

  it('M7→H1 发布资本化支出事件：publishCapitalExpToH1', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { publishCapitalExpToH1 } = useM7CrossSheet(responses)

      publishCapitalExpToH1(3_000_000, ['安全设备购置', '防护设施改造'])

      expect(eventBus.emit).toHaveBeenCalledWith(
        'm7:capital-exp-to-h1',
        expect.objectContaining({
          wpCode: 'M7',
          capitalExpAmount: 3_000_000,
          items: ['安全设备购置', '防护设施改造'],
        }),
      )
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 6: adjudicationVsDetail — M7-1审定 vs M7-2明细 交叉验证 (Req 2.5)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — adjudicationVsDetail M7-1 vs M7-2 (Req 2.5)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    onHandlers.clear()
  })

  it('审定表合计 === 明细表合计 → isMatch=true, diff=0', () => {
    const responses = createResponses([
      ['M7-M7-1-total-end-audited', '15000000'],
      ['M7-M7-2-total-end-amount', '15000000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsDetail } = useM7CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(true)
      expect(adjudicationVsDetail.value.diff).toBe(0)
    })
    scope.stop()
  })

  it('差额>1元 → isMatch=false', () => {
    const responses = createResponses([
      ['M7-M7-1-total-end-audited', '15000000'],
      ['M7-M7-2-total-end-amount', '14990000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsDetail } = useM7CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(false)
      expect(adjudicationVsDetail.value.diff).toBe(10_000)
    })
    scope.stop()
  })

  it('明细行降级累加：无汇总行时遍历row-*-end', () => {
    const responses = createResponses([
      ['M7-M7-1-total-end-audited', '8000000'],
      // 无 M7-M7-2-total-end-amount
      ['M7-M7-2-row-1-end', '3000000'],
      ['M7-M7-2-row-2-end', '2500000'],
      ['M7-M7-2-row-3-end', '2500000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsDetail } = useM7CrossSheet(responses)
      // 明细行累加：3000000+2500000+2500000=8000000
      expect(adjudicationVsDetail.value.isMatch).toBe(true)
      expect(adjudicationVsDetail.value.diff).toBe(0)
    })
    scope.stop()
  })

  it('两侧均为空 → isMatch=true, diff=0', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsDetail } = useM7CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(true)
      expect(adjudicationVsDetail.value.diff).toBe(0)
    })
    scope.stop()
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Section 7: E2E — 完整闭环 计提→验证→资本化→H1 (Req 4.1-4.6, 5.1)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — E2E: 计提→审定→资本化→H1闭环 (Req 4.1-4.6, 5.1)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    onHandlers.clear()
  })

  it('完整业务流程：产量计提→差异→权益期末→明细勾稽→资本化→H1确认', () => {
    // Step 1: 安全生产费按产量计提（煤矿）
    const tiers = [
      { output: 1_000_000, rate: 5 },   // 500万
      { output: 2_000_000, rate: 4 },   // 800万
    ]
    const estimated = calcAccrualByOutput(tiers)
    expect(estimated).toBe(13_000_000)

    // Step 2: 计提差异
    const booked = 12_500_000
    const diff = calcAccrualDiff(estimated, booked)
    expect(diff).toBe(500_000) // 少提50万

    // Step 3: 权益类期末余额计算
    const begin = 20_000_000    // 期初
    const credit = 12_500_000   // 贷方(账面计提)
    const debit = 5_000_000     // 借方(使用=费用化3M+资本化2M)
    const endBalance = calcEquityEndBalance(begin, credit, debit)
    expect(endBalance).toBe(27_500_000) // 期末=20M+12.5M-5M=27.5M

    // Step 4: 审定与明细勾稽（模拟useM7CrossSheet）
    const responses = createResponses([
      ['M7-M7-1-total-end-audited', '27500000'],
      ['M7-M7-2-total-end-amount', '27500000'],
      ['M7-M7-2-total-capital-exp', '2000000'], // 资本化支出200万
    ])

    const scope = effectScope()
    scope.run(() => {
      const crossSheet = useM7CrossSheet(responses)

      // 审定 vs 明细一致
      expect(crossSheet.adjudicationVsDetail.value.isMatch).toBe(true)

      // Step 5: H1确认资本化支出
      eventBus.emit('h1:fixed-asset-confirmed' as any, {
        wpCode: 'H1',
        amount: 2_000_000,
        source: 'M7专项储备转固',
        timestamp: Date.now(),
      })

      // 资本化联动一致
      expect(crossSheet.capitalExpToH1.value.isConsistent).toBe(true)
      expect(crossSheet.capitalExpToH1.value.capitalExpTotal).toBe(2_000_000)
      expect(crossSheet.capitalExpToH1.value.h1ConfirmedAmount).toBe(2_000_000)
    })
    scope.stop()
  })

  it('ADR-3验证：资本性支出双分录 — M7借方减少+H1固定资产增加', () => {
    // ADR-3: 借:固定资产 贷:在建工程；借:专项储备 贷:累计折旧
    // 验证M7借方(使用-资本化)对应H1增加

    const capitalExpAmount = 5_000_000

    // M7权益类：使用(借方)导致减少
    const m7Begin = 30_000_000
    const m7Credit = 10_000_000  // 本期计提
    const m7Debit = 8_000_000    // 本期使用(含资本化5M+费用化3M)
    const m7End = calcEquityEndBalance(m7Begin, m7Credit, m7Debit)
    expect(m7End).toBe(32_000_000) // 30M+10M-8M=32M

    // 资本化部分应与H1联动
    const responses = createResponses([
      ['M7-M7-2-total-capital-exp', String(capitalExpAmount)],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { capitalExpToH1, publishCapitalExpToH1 } = useM7CrossSheet(responses)

      // M7发布资本化支出通知
      publishCapitalExpToH1(capitalExpAmount, ['矿山安全设备'])

      expect(eventBus.emit).toHaveBeenCalledWith(
        'm7:capital-exp-to-h1',
        expect.objectContaining({
          capitalExpAmount: 5_000_000,
          items: ['矿山安全设备'],
        }),
      )

      // H1尚未确认 → 不一致
      expect(capitalExpToH1.value.isConsistent).toBe(false)

      // H1确认
      eventBus.emit('h1:fixed-asset-confirmed' as any, { amount: 5_000_000 })
      expect(capitalExpToH1.value.isConsistent).toBe(true)
    })
    scope.stop()
  })

  it('cross_wp_references 包含H1双向引用', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { crossWpReferences } = useM7CrossSheet(responses)

      // 应有M7→H1 和 H1→M7 两条引用
      expect(crossWpReferences.length).toBeGreaterThanOrEqual(2)

      const toH1 = crossWpReferences.find(r => r.targetWpCode === 'H1' && r.direction === 'to')
      expect(toH1).toBeDefined()
      expect(toH1!.label).toContain('资本化')

      const fromH1 = crossWpReferences.find(r => r.targetWpCode === 'H1' && r.direction === 'from')
      expect(fromH1).toBeDefined()
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 8: EventBus cleanup — scope dispose 取消订阅 (Req 5.1)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — EventBus cleanup on scope dispose', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    onHandlers.clear()
  })

  it('scope.stop() 后 eventBus.off 被调用（h1:fixed-asset-confirmed）', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      useM7CrossSheet(responses)
    })

    expect(eventBus.on).toHaveBeenCalledWith('h1:fixed-asset-confirmed', expect.any(Function))

    scope.stop()

    expect(eventBus.off).toHaveBeenCalledWith('h1:fixed-asset-confirmed', expect.any(Function))
  })

  it('scope.stop() 后H1事件不再触发更新', () => {
    const responses = createResponses([])

    const scope = effectScope()
    let crossSheet: ReturnType<typeof useM7CrossSheet> | undefined
    scope.run(() => {
      crossSheet = useM7CrossSheet(responses)
    })

    // scope active 时事件有效
    eventBus.emit('h1:fixed-asset-confirmed' as any, { amount: 5_000_000 })
    expect(crossSheet!._h1ConfirmedAmount.value).toBe(5_000_000)

    // 停止 scope
    scope.stop()

    // 再次 emit 不应更新（handler 已移除）
    eventBus.emit('h1:fixed-asset-confirmed' as any, { amount: 9_999_999 })
    expect(crossSheet!._h1ConfirmedAmount.value).toBe(5_000_000) // 值不变
  })
})
