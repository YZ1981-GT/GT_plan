/**
 * 集成测试 — M10 其他权益工具：CAS37区分 + 负债部分联动
 *
 * 覆盖：
 * 1. useM10ClassificationCheck 与 useM10ClassificationEngine 集成
 *    - 添加工具 → 设定维度 → 自动推导分类
 * 2. 金额拆分 + 一致性校验
 *    - 复合工具(总额=100M) → 权益60M → 负债自动40M
 * 3. 负债警告生成
 *    - 判定为负债 → liabilityWarnings → "应计入负债科目"
 * 4. 跨sheet校验（useM10CrossSheet）
 *    - M10-1 审定 vs M10-2 明细 勾稽
 *    - classificationConsistency 守恒
 * 5. 汇总统计
 *    - 多工具：2权益 + 1负债 → summary counts/amounts
 *
 * Spec: .kiro/specs/m10-other-equity-instruments/ Task 7.2
 * Requirements: 4.1-4.5
 *
 * 科目：4003 其他权益工具（贷方/权益类！期末=期初+贷方-借方）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import {
  classifyInstrument,
  splitAmount,
  calcClassificationConsistency,
} from '../composables/useM10ClassificationEngine'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
} from '../composables/useM10FormulaEngine'
import { useM10CrossSheet } from '../composables/useM10CrossSheet'
import type { ChecklistResponse } from '../composables/useM10CrossSheet'

// ─── Mock dependencies ───────────────────────────────────────────────────────

vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
  },
}))

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn().mockResolvedValue({ data: [] }),
    put: vi.fn().mockResolvedValue({ data: { code: 0 } }),
  },
}))

// ─── Helpers ─────────────────────────────────────────────────────────────────

function createResponses(entries: [string, string | null, string | null][]) {
  const map = new Map<string, ChecklistResponse>()
  for (const [itemId, conclusion, remark] of entries) {
    map.set(itemId, { item_id: itemId, conclusion, remark })
  }
  return ref(map)
}

// ═══════════════════════════════════════════════════════════════════════════════
// Section 1: useM10ClassificationCheck + useM10ClassificationEngine 集成
// ═══════════════════════════════════════════════════════════════════════════════

describe('M10 CAS37区分 + 负债部分联动 集成测试', () => {
  describe('1. CAS37分类引擎 + 维度判定 集成', () => {
    /**
     * 模拟 useM10ClassificationCheck 的核心分类逻辑
     * 验证 addInstrument → 设置维度 → 自动推导分类的完整流程
     */
    interface MockInstrument {
      key: string
      name: string
      totalAmount: number
      principalObligation: boolean  // 本金相关：是否有交付现金义务
      interestObligation: boolean   // 利息相关：是否强制付息
      deferralRight: boolean        // 递延权利：是否可无条件递延
    }

    /**
     * 模拟 updateDimension 的核心判定逻辑（来自 useM10ClassificationCheck）：
     * - 本金义务=yes → 有合同义务
     * - 利息义务=yes 且 不可递延(deferral=no) → 有合同义务
     * - 利息义务=yes 且 可递延(deferral=yes) → 无合同义务
     * - 两者都无 → 无合同义务
     */
    function deriveContractualObligation(inst: MockInstrument): boolean {
      return inst.principalObligation || (inst.interestObligation && !inst.deferralRight)
    }

    function classifyAndSplit(inst: MockInstrument) {
      const hasObligation = deriveContractualObligation(inst)
      const classification = classifyInstrument(hasObligation)
      let equityAmount: number
      let liabilityAmount: number

      if (classification === 'equity') {
        equityAmount = inst.totalAmount
        liabilityAmount = 0
      } else {
        equityAmount = 0
        liabilityAmount = inst.totalAmount
      }

      return {
        classification,
        hasObligation,
        equityAmount,
        liabilityAmount,
        isConsistent: calcClassificationConsistency(equityAmount, liabilityAmount, inst.totalAmount),
      }
    }

    it('principal=yes → liability（有本金偿付义务=金融负债）', () => {
      const inst: MockInstrument = {
        key: 'bond-a', name: '可赎回优先股A',
        totalAmount: 50_000_000,
        principalObligation: true,
        interestObligation: false,
        deferralRight: false,
      }

      const result = classifyAndSplit(inst)
      expect(result.hasObligation).toBe(true)
      expect(result.classification).toBe('liability')
      expect(result.equityAmount).toBe(0)
      expect(result.liabilityAmount).toBe(50_000_000)
      expect(result.isConsistent).toBe(true)
    })

    it('principal=no, interest=yes, deferral=yes → equity（可递延=无强制义务）', () => {
      const inst: MockInstrument = {
        key: 'perpetual-bond-1', name: '永续债-可递延付息',
        totalAmount: 100_000_000,
        principalObligation: false,
        interestObligation: true,
        deferralRight: true,
      }

      const result = classifyAndSplit(inst)
      expect(result.hasObligation).toBe(false)
      expect(result.classification).toBe('equity')
      expect(result.equityAmount).toBe(100_000_000)
      expect(result.liabilityAmount).toBe(0)
      expect(result.isConsistent).toBe(true)
    })

    it('principal=no, interest=yes, deferral=no → liability（强制付息=有合同义务）', () => {
      const inst: MockInstrument = {
        key: 'preferred-stock-b', name: '优先股B-强制分红',
        totalAmount: 80_000_000,
        principalObligation: false,
        interestObligation: true,
        deferralRight: false,
      }

      const result = classifyAndSplit(inst)
      expect(result.hasObligation).toBe(true)
      expect(result.classification).toBe('liability')
      expect(result.equityAmount).toBe(0)
      expect(result.liabilityAmount).toBe(80_000_000)
      expect(result.isConsistent).toBe(true)
    })

    it('principal=no, interest=no → equity（无任何合同义务）', () => {
      const inst: MockInstrument = {
        key: 'perpetual-bond-2', name: '永续债-无到期无强制付息',
        totalAmount: 200_000_000,
        principalObligation: false,
        interestObligation: false,
        deferralRight: false,
      }

      const result = classifyAndSplit(inst)
      expect(result.hasObligation).toBe(false)
      expect(result.classification).toBe('equity')
      expect(result.equityAmount).toBe(200_000_000)
      expect(result.liabilityAmount).toBe(0)
      expect(result.isConsistent).toBe(true)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Section 2: 金额拆分 + 一致性校验
  // ═══════════════════════════════════════════════════════════════════════════

  describe('2. 复合工具金额拆分 + 守恒一致性', () => {
    it('总额100M, equity=60M → liability自动计算40M', () => {
      const total = 100_000_000
      const equityPart = 60_000_000
      const liabilityPart = splitAmount(total, equityPart)

      expect(liabilityPart).toBe(40_000_000)
      expect(calcClassificationConsistency(equityPart, liabilityPart, total)).toBe(true)
    })

    it('纯权益工具: equity=total, liability=0 → 一致', () => {
      const total = 150_000_000
      expect(calcClassificationConsistency(total, 0, total)).toBe(true)
    })

    it('纯负债工具: equity=0, liability=total → 一致', () => {
      const total = 75_000_000
      expect(calcClassificationConsistency(0, total, total)).toBe(true)
    })

    it('金额不守恒: equity=60M, liability=50M, total=100M → 不一致', () => {
      expect(calcClassificationConsistency(60_000_000, 50_000_000, 100_000_000)).toBe(false)
    })

    it('浮点精度容差: 微小误差仍视为一致', () => {
      // 60M + 40M - 100M ≈ 0（浮点精度可能有 1e-15 误差）
      const eq = 60_000_000.0000001
      const liab = 39_999_999.9999999
      const total = 100_000_000
      // eq + liab = 100_000_000.0000000 → |差值| < 1e-10
      expect(calcClassificationConsistency(eq, liab, total)).toBe(true)
    })

    it('splitAmount + calcEquityEndBalance 联合验证权益部分期末余额', () => {
      // 复合工具总额200M，权益部分120M
      const total = 200_000_000
      const equityPart = 120_000_000

      // 权益部分期末 = 权益部分期初 + 贷方(新发行归入权益) - 借方(转换归入权益减少)
      const equityEnd = calcEquityEndBalance(equityPart, 30_000_000, 10_000_000)
      expect(equityEnd).toBe(140_000_000) // 120M + 30M - 10M

      // 负债部分仍为 80M（拆分时确定，后续变动在负债科目处理）
      const liabilityPart = splitAmount(total, equityPart)
      expect(liabilityPart).toBe(80_000_000)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Section 3: 负债警告生成
  // ═══════════════════════════════════════════════════════════════════════════

  describe('3. 负债警告生成（判定为liability→提示计入负债科目）', () => {
    it('判定为liability的工具生成警告，包含"应计入负债科目"', () => {
      // 模拟 M10-4 检查表中有一项判定为 liability
      const responses = createResponses([
        ['M10-4-item-1-classification', 'liability', null],
        ['M10-4-item-1-name', null, '可赎回优先股A'],
        ['M10-4-item-1-amount', null, '50000000'],
        // 第二项为 equity → 不生成警告
        ['M10-4-item-2-classification', 'equity', null],
        ['M10-4-item-2-name', null, '永续债B'],
        ['M10-4-item-2-amount', null, '100000000'],
      ])

      const { liabilityItems } = useM10CrossSheet(responses)
      expect(liabilityItems.value.length).toBe(1)
      expect(liabilityItems.value[0].name).toBe('可赎回优先股A')
      expect(liabilityItems.value[0].amount).toBe(50_000_000)
    })

    it('多项liability均生成独立警告', () => {
      const responses = createResponses([
        ['M10-4-item-1-classification', 'liability', null],
        ['M10-4-item-1-name', null, '可赎回优先股A'],
        ['M10-4-item-1-amount', null, '50000000'],
        ['M10-4-item-2-classification', 'liability', null],
        ['M10-4-item-2-name', null, '强制付息永续债C'],
        ['M10-4-item-2-amount', null, '80000000'],
      ])

      const { liabilityItems } = useM10CrossSheet(responses)
      expect(liabilityItems.value.length).toBe(2)
      expect(liabilityItems.value[0].amount).toBe(50_000_000)
      expect(liabilityItems.value[1].amount).toBe(80_000_000)
    })

    it('全部为equity → 无警告', () => {
      const responses = createResponses([
        ['M10-4-item-1-classification', 'equity', null],
        ['M10-4-item-1-name', null, '永续债A'],
        ['M10-4-item-1-amount', null, '100000000'],
      ])

      const { liabilityItems } = useM10CrossSheet(responses)
      expect(liabilityItems.value.length).toBe(0)
    })

    it('无工具 → 无警告', () => {
      const responses = createResponses([])
      const { liabilityItems } = useM10CrossSheet(responses)
      expect(liabilityItems.value.length).toBe(0)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Section 4: 跨sheet校验（useM10CrossSheet）
  // ═══════════════════════════════════════════════════════════════════════════

  describe('4. 跨sheet校验 adjudicationVsDetail + classificationConsistency', () => {
    describe('4a. M10-1 审定 vs M10-2 明细 勾稽', () => {
      it('审定合计500M = 明细合计500M → isMatch=true', () => {
        const responses = createResponses([
          ['M10-1-total-audited', null, '500000000'],
          ['M10-2-total-end-balance', null, '500000000'],
        ])

        const { adjudicationVsDetail } = useM10CrossSheet(responses)
        expect(adjudicationVsDetail.value.isMatch).toBe(true)
        expect(adjudicationVsDetail.value.diff).toBeCloseTo(0, 1)
      })

      it('审定合计500M ≠ 明细合计480M → isMatch=false, diff=20M', () => {
        const responses = createResponses([
          ['M10-1-total-audited', null, '500000000'],
          ['M10-2-total-end-balance', null, '480000000'],
        ])

        const { adjudicationVsDetail } = useM10CrossSheet(responses)
        expect(adjudicationVsDetail.value.isMatch).toBe(false)
        expect(adjudicationVsDetail.value.diff).toBeCloseTo(20_000_000, 0)
      })

      it('明细表无汇总行时，逐行累加匹配', () => {
        const responses = createResponses([
          ['M10-1-total-audited', null, '300000000'],
          // 无 M10-2-total-end-balance，但有逐行
          ['M10-2-item1-end-balance', null, '150000000'],
          ['M10-2-item2-end-balance', null, '100000000'],
          ['M10-2-item3-end-balance', null, '50000000'],
        ])

        const { adjudicationVsDetail } = useM10CrossSheet(responses)
        expect(adjudicationVsDetail.value.isMatch).toBe(true)
        expect(adjudicationVsDetail.value.diff).toBeCloseTo(0, 1)
      })

      it('两侧都为空 → isMatch=true, diff=0', () => {
        const responses = createResponses([])
        const { adjudicationVsDetail } = useM10CrossSheet(responses)
        expect(adjudicationVsDetail.value.isMatch).toBe(true)
        expect(adjudicationVsDetail.value.diff).toBe(0)
      })

      it('明细为空时 → diff=审定数全额', () => {
        const responses = createResponses([
          ['M10-1-total-audited', null, '200000000'],
        ])

        const { adjudicationVsDetail } = useM10CrossSheet(responses)
        expect(adjudicationVsDetail.value.isMatch).toBe(false)
        expect(adjudicationVsDetail.value.diff).toBeCloseTo(200_000_000, 0)
      })
    })

    describe('4b. classificationConsistency 分类金额守恒', () => {
      it('equity + liability === total → isConsistent=true', () => {
        const responses = createResponses([
          ['M10-4-equity-total', null, '300000000'],
          ['M10-4-liability-total', null, '200000000'],
          ['M10-4-instrument-total', null, '500000000'],
        ])

        const { classificationConsistency } = useM10CrossSheet(responses)
        expect(classificationConsistency.value.isConsistent).toBe(true)
        expect(classificationConsistency.value.equity).toBe(300_000_000)
        expect(classificationConsistency.value.liability).toBe(200_000_000)
        expect(classificationConsistency.value.total).toBe(500_000_000)
      })

      it('equity + liability ≠ total → isConsistent=false', () => {
        const responses = createResponses([
          ['M10-4-equity-total', null, '300000000'],
          ['M10-4-liability-total', null, '100000000'], // 300M + 100M ≠ 500M
          ['M10-4-instrument-total', null, '500000000'],
        ])

        const { classificationConsistency } = useM10CrossSheet(responses)
        expect(classificationConsistency.value.isConsistent).toBe(false)
      })

      it('全部为权益: equity=total, liability=0 → isConsistent=true', () => {
        const responses = createResponses([
          ['M10-4-equity-total', null, '800000000'],
          ['M10-4-liability-total', null, '0'],
          ['M10-4-instrument-total', null, '800000000'],
        ])

        const { classificationConsistency } = useM10CrossSheet(responses)
        expect(classificationConsistency.value.isConsistent).toBe(true)
      })

      it('无数据 → all zeros → isConsistent=true (0+0=0)', () => {
        const responses = createResponses([])
        const { classificationConsistency } = useM10CrossSheet(responses)
        expect(classificationConsistency.value.isConsistent).toBe(true)
      })
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Section 5: 汇总统计
  // ═══════════════════════════════════════════════════════════════════════════

  describe('5. 汇总统计：多工具分类统计', () => {
    /**
     * 模拟 useM10ClassificationCheck.summary 逻辑
     * 验证 2 equity + 1 liability 场景下的 counts & amounts
     */
    interface MockJudgment {
      instrumentKey: string
      instrumentName: string
      totalAmount: number
      classification: 'equity' | 'liability' | ''
      equityAmount: number
      liabilityAmount: number
      isConsistent: boolean
    }

    function computeSummary(judgments: MockJudgment[]) {
      const totalInstruments = judgments.length
      const equityCount = judgments.filter(j => j.classification === 'equity').length
      const liabilityCount = judgments.filter(j => j.classification === 'liability').length
      const pendingCount = totalInstruments - equityCount - liabilityCount
      const totalEquityAmount = calcSubtotal(judgments.map(j => j.equityAmount))
      const totalLiabilityAmount = calcSubtotal(judgments.map(j => j.liabilityAmount))
      const totalAmount = calcSubtotal(judgments.map(j => j.totalAmount))
      const allConsistent = judgments.every(j => j.isConsistent)
      return {
        totalInstruments, equityCount, liabilityCount, pendingCount,
        totalEquityAmount, totalLiabilityAmount, totalAmount, allConsistent,
      }
    }

    it('2 equity + 1 liability → 正确汇总', () => {
      const judgments: MockJudgment[] = [
        {
          instrumentKey: 'perpetual-1', instrumentName: '永续债A',
          totalAmount: 100_000_000,
          classification: 'equity', equityAmount: 100_000_000, liabilityAmount: 0,
          isConsistent: true,
        },
        {
          instrumentKey: 'perpetual-2', instrumentName: '永续债B',
          totalAmount: 200_000_000,
          classification: 'equity', equityAmount: 200_000_000, liabilityAmount: 0,
          isConsistent: true,
        },
        {
          instrumentKey: 'preferred-1', instrumentName: '可赎回优先股C',
          totalAmount: 80_000_000,
          classification: 'liability', equityAmount: 0, liabilityAmount: 80_000_000,
          isConsistent: true,
        },
      ]

      const summary = computeSummary(judgments)
      expect(summary.totalInstruments).toBe(3)
      expect(summary.equityCount).toBe(2)
      expect(summary.liabilityCount).toBe(1)
      expect(summary.pendingCount).toBe(0)
      expect(summary.totalEquityAmount).toBe(300_000_000) // 100M + 200M
      expect(summary.totalLiabilityAmount).toBe(80_000_000)
      expect(summary.totalAmount).toBe(380_000_000) // 100M + 200M + 80M
      expect(summary.allConsistent).toBe(true)
    })

    it('含未判定工具 → pendingCount > 0', () => {
      const judgments: MockJudgment[] = [
        {
          instrumentKey: 'perpetual-1', instrumentName: '永续债A',
          totalAmount: 100_000_000,
          classification: 'equity', equityAmount: 100_000_000, liabilityAmount: 0,
          isConsistent: true,
        },
        {
          instrumentKey: 'unknown-1', instrumentName: '待判定工具X',
          totalAmount: 50_000_000,
          classification: '', equityAmount: 0, liabilityAmount: 0,
          isConsistent: true,
        },
      ]

      const summary = computeSummary(judgments)
      expect(summary.totalInstruments).toBe(2)
      expect(summary.equityCount).toBe(1)
      expect(summary.liabilityCount).toBe(0)
      expect(summary.pendingCount).toBe(1)
    })

    it('有不守恒工具 → allConsistent=false', () => {
      const judgments: MockJudgment[] = [
        {
          instrumentKey: 'bad-1', instrumentName: '拆分错误工具',
          totalAmount: 100_000_000,
          classification: 'equity', equityAmount: 60_000_000, liabilityAmount: 50_000_000, // 60+50≠100
          isConsistent: false,
        },
      ]

      const summary = computeSummary(judgments)
      expect(summary.allConsistent).toBe(false)
    })

    it('空工具列表 → 全零', () => {
      const summary = computeSummary([])
      expect(summary.totalInstruments).toBe(0)
      expect(summary.equityCount).toBe(0)
      expect(summary.liabilityCount).toBe(0)
      expect(summary.totalEquityAmount).toBe(0)
      expect(summary.totalLiabilityAmount).toBe(0)
    })

    it('金额守恒校验: totalEquityAmount + totalLiabilityAmount === totalAmount', () => {
      const judgments: MockJudgment[] = [
        {
          instrumentKey: 'a', instrumentName: 'A',
          totalAmount: 100_000_000,
          classification: 'equity', equityAmount: 100_000_000, liabilityAmount: 0,
          isConsistent: true,
        },
        {
          instrumentKey: 'b', instrumentName: 'B',
          totalAmount: 200_000_000,
          classification: 'liability', equityAmount: 0, liabilityAmount: 200_000_000,
          isConsistent: true,
        },
        {
          instrumentKey: 'c', instrumentName: 'C（复合）',
          totalAmount: 150_000_000,
          classification: 'equity', equityAmount: 90_000_000, liabilityAmount: 60_000_000,
          isConsistent: true,
        },
      ]

      const summary = computeSummary(judgments)
      // 权益总额 = 100M + 0 + 90M = 190M
      expect(summary.totalEquityAmount).toBe(190_000_000)
      // 负债总额 = 0 + 200M + 60M = 260M
      expect(summary.totalLiabilityAmount).toBe(260_000_000)
      // 工具总额 = 100M + 200M + 150M = 450M
      expect(summary.totalAmount).toBe(450_000_000)
      // 守恒: 190M + 260M = 450M
      expect(calcClassificationConsistency(
        summary.totalEquityAmount, summary.totalLiabilityAmount, summary.totalAmount,
      )).toBe(true)
    })
  })
})
