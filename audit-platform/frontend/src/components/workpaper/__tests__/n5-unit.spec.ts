/**
 * 单元测试 — N5 所得税费用三引擎
 *   useN5FormulaEngine + useN5IncomeTaxEngine + useN5TaxAdjustmentEngine
 *
 * Spec: .kiro/specs/n5-income-tax-expense/
 * Task: 7.1
 * Requirements: P1-P10
 *
 * 覆盖：
 * - calcAuditedAmount: 审定数=未审+AJE+RJE (P1)
 * - calcPeriodAmount: 损益类本期发生额=借方发生-贷方发生 (P2)
 * - calcSubtotal: 合计行=Σarr (P9)
 * - calcEffectiveTaxRate: 有效税率+除零保护 (P1补充)
 * - calcTaxableIncome: 应纳税所得额=会计利润+调增-调减 (P3)
 * - calcCurrentTax: 当期所得税=应纳税所得额×税率 (P4)
 * - calcIncomeTaxExpense: 所得税费用=当期+递延 (P5)
 * - calcDeferredTaxExpense: 递延所得税费用=负债增-资产增 (P6)
 * - calcRdSuperDeduction: 研发加计=研发费用×加计比例 (P7)
 * - calcNetAdjustment: 纳税调整净额=Σ调增-Σ调减 (P8)
 * - calcPropertyLossAdjustment: 财产损失=账面-税前扣除 (P10)
 * - Edge: 亏损(taxableIncome<0), 零利润(除零保护), 大数(1e15), 空数组, NaN/null/undefined
 *
 * 科目：6801 所得税费用（**损益类**！取本期发生额，从tb_ledger）
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcPeriodAmount,
  calcSubtotal,
  calcEffectiveTaxRate,
  parseNum,
} from '../composables/useN5FormulaEngine'
import {
  calcTaxableIncome,
  calcCurrentTax,
  calcIncomeTaxExpense,
  calcDeferredTaxExpense,
  calcRdSuperDeduction,
} from '../composables/useN5IncomeTaxEngine'
import {
  calcNetAdjustment,
  calcPropertyLossAdjustment,
} from '../composables/useN5TaxAdjustmentEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// 1. useN5FormulaEngine — 损益类公式引擎
// ═══════════════════════════════════════════════════════════════════════════════

describe('useN5FormulaEngine', () => {
  // ─── parseNum helper ───────────────────────────────────────────────────────
  describe('parseNum (安全数值解析)', () => {
    it('null → 0', () => expect(parseNum(null)).toBe(0))
    it('undefined → 0', () => expect(parseNum(undefined)).toBe(0))
    it('空字符串 → 0', () => expect(parseNum('')).toBe(0))
    it('NaN → 0', () => expect(parseNum(NaN)).toBe(0))
    it('Infinity → 0', () => expect(parseNum(Infinity)).toBe(0))
    it('数字直接返回', () => expect(parseNum(12345.67)).toBe(12345.67))
    it('字符串数字解析', () => expect(parseNum('1000000')).toBe(1000000))
  })

  // ─── P1: 审定数公式链 ─────────────────────────────────────────────────────
  describe('calcAuditedAmount (P1: 审定数=未审+AJE+RJE)', () => {
    it('正常: 未审500万 + AJE 20万 + RJE 10万 = 530万', () => {
      expect(calcAuditedAmount(5_000_000, 200_000, 100_000)).toBe(5_300_000)
    })

    it('负AJE: 所得税费用调减', () => {
      expect(calcAuditedAmount(8_000_000, -1_000_000, 0)).toBe(7_000_000)
    })

    it('all zeros → 0', () => {
      expect(calcAuditedAmount(0, 0, 0)).toBe(0)
    })

    it('NaN/null/undefined treated as 0', () => {
      expect(calcAuditedAmount(NaN, 100_000, null as any)).toBe(100_000)
      expect(calcAuditedAmount(undefined as any, undefined as any, 50_000)).toBe(50_000)
    })

    it('大数(1e15): 精度保持', () => {
      expect(calcAuditedAmount(1e15, 1e12, 1e10)).toBe(1e15 + 1e12 + 1e10)
    })
  })

  // ─── P2: 损益类本期发生额（借方发生-贷方发生！）─────────────────────────
  describe('calcPeriodAmount (P2: 损益类本期发生额=借方-贷方)', () => {
    it('正常费用发生: 借方800万 - 贷方200万 = 600万', () => {
      expect(calcPeriodAmount(8_000_000, 2_000_000)).toBe(6_000_000)
    })

    it('仅借方(费用正常增加): 借方500万 - 贷方0 = 500万', () => {
      expect(calcPeriodAmount(5_000_000, 0)).toBe(5_000_000)
    })

    it('全部冲回: 借方0 - 贷方300万 = -300万', () => {
      expect(calcPeriodAmount(0, 3_000_000)).toBe(-3_000_000)
    })

    it('借贷相等: 净额=0', () => {
      expect(calcPeriodAmount(1_000_000, 1_000_000)).toBe(0)
    })

    it('NaN处理', () => {
      expect(calcPeriodAmount(NaN, 500_000)).toBe(-500_000)
      expect(calcPeriodAmount(1_000_000, NaN)).toBe(1_000_000)
    })

    it('大数(1e15): 精度保持', () => {
      expect(calcPeriodAmount(1e15, 5e14)).toBe(5e14)
    })

    it('验证方向: 损益类≠资产类(begin+dr-cr)', () => {
      const dr = 800_000
      const cr = 200_000
      const periodAmount = calcPeriodAmount(dr, cr) // 800K-200K=600K
      const assetWouldBe = dr - cr // same formula for period but conceptually different
      expect(periodAmount).toBe(600_000)
      expect(periodAmount).toBe(assetWouldBe) // 数值相同但语义不同
    })
  })

  // ─── P9: 合计行恒等 ───────────────────────────────────────────────────────
  describe('calcSubtotal (P9: 合计行=Σarr)', () => {
    it('空数组 → 0', () => {
      expect(calcSubtotal([])).toBe(0)
    })

    it('单元素', () => {
      expect(calcSubtotal([5_000_000])).toBe(5_000_000)
    })

    it('多项合计', () => {
      expect(calcSubtotal([1_000_000, 2_000_000, 3_000_000])).toBe(6_000_000)
    })

    it('含负值(冲回)', () => {
      expect(calcSubtotal([5_000_000, -1_000_000, 2_000_000])).toBe(6_000_000)
    })

    it('NaN in array treated as 0', () => {
      expect(calcSubtotal([1_000_000, NaN, 2_000_000])).toBe(3_000_000)
    })

    it('非数组 → 0 (defensive)', () => {
      expect(calcSubtotal(null as any)).toBe(0)
      expect(calcSubtotal(undefined as any)).toBe(0)
    })

    it('大数数组(1e15)', () => {
      expect(calcSubtotal([1e15, 2e15])).toBe(3e15)
    })
  })

  // ─── 有效税率+除零保护 ────────────────────────────────────────────────────
  describe('calcEffectiveTaxRate (有效税率=所得税费用/会计利润)', () => {
    it('正常: 所得税250万 / 会计利润1000万 = 25%', () => {
      expect(calcEffectiveTaxRate(2_500_000, 10_000_000)).toBeCloseTo(0.25, 10)
    })

    it('零利润(除零保护): 会计利润=0 → null', () => {
      expect(calcEffectiveTaxRate(2_500_000, 0)).toBeNull()
    })

    it('所得税=0: 有效税率=0', () => {
      expect(calcEffectiveTaxRate(0, 10_000_000)).toBe(0)
    })

    it('NaN利润 → null(parseNum→0，除零保护)', () => {
      expect(calcEffectiveTaxRate(1_000_000, NaN)).toBeNull()
    })

    it('亏损企业: 会计利润<0, 仍有税率', () => {
      // 亏损500万但有递延所得税（特殊场景）
      const rate = calcEffectiveTaxRate(100_000, -5_000_000)
      expect(rate).toBeCloseTo(-0.02, 10)
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 2. useN5IncomeTaxEngine — 核心所得税计算引擎
// ═══════════════════════════════════════════════════════════════════════════════

describe('useN5IncomeTaxEngine', () => {
  // ─── P3: 应纳税所得额 ─────────────────────────────────────────────────────
  describe('calcTaxableIncome (P3: 应纳税所得额=会计利润+调增-调减)', () => {
    it('正常: 利润1000万 + 调增200万 - 调减50万 = 1150万', () => {
      expect(calcTaxableIncome(10_000_000, 2_000_000, 500_000)).toBe(11_500_000)
    })

    it('无调整: 应纳税=会计利润', () => {
      expect(calcTaxableIncome(5_000_000, 0, 0)).toBe(5_000_000)
    })

    it('亏损(taxableIncome<0): 利润-300万 + 调增100万 - 调减0 = -200万', () => {
      expect(calcTaxableIncome(-3_000_000, 1_000_000, 0)).toBe(-2_000_000)
    })

    it('调减大于利润+调增: 应纳税所得额为负', () => {
      expect(calcTaxableIncome(1_000_000, 500_000, 3_000_000)).toBe(-1_500_000)
    })

    it('all zeros → 0', () => {
      expect(calcTaxableIncome(0, 0, 0)).toBe(0)
    })

    it('NaN/null handling', () => {
      expect(calcTaxableIncome(NaN, 1_000_000, 500_000)).toBe(500_000)
      expect(calcTaxableIncome(5_000_000, null as any, undefined as any)).toBe(5_000_000)
    })

    it('大数(1e15)', () => {
      expect(calcTaxableIncome(1e15, 1e14, 5e13)).toBe(1e15 + 1e14 - 5e13)
    })
  })

  // ─── P4: 当期所得税 ───────────────────────────────────────────────────────
  describe('calcCurrentTax (P4: 当期所得税=应纳税所得额×税率)', () => {
    it('一般企业25%: 1000万×0.25 = 250万', () => {
      expect(calcCurrentTax(10_000_000, 0.25)).toBe(2_500_000)
    })

    it('高新15%: 1000万×0.15 = 150万', () => {
      expect(calcCurrentTax(10_000_000, 0.15)).toBe(1_500_000)
    })

    it('小微20%: 300万×0.20 = 60万', () => {
      expect(calcCurrentTax(3_000_000, 0.20)).toBe(600_000)
    })

    it('亏损: taxableIncome<0 → 负税(实际应为0，由业务层处理)', () => {
      expect(calcCurrentTax(-2_000_000, 0.25)).toBe(-500_000)
    })

    it('零所得 → 0', () => {
      expect(calcCurrentTax(0, 0.25)).toBe(0)
    })

    it('零税率 → 0', () => {
      expect(calcCurrentTax(10_000_000, 0)).toBe(0)
    })

    it('NaN handling', () => {
      expect(calcCurrentTax(NaN, 0.25)).toBe(0)
      expect(calcCurrentTax(10_000_000, NaN)).toBe(0)
    })
  })

  // ─── P5: 所得税费用=当期+递延 ─────────────────────────────────────────────
  describe('calcIncomeTaxExpense (P5: 所得税费用=当期+递延)', () => {
    it('正常: 当期250万 + 递延50万 = 300万', () => {
      expect(calcIncomeTaxExpense(2_500_000, 500_000)).toBe(3_000_000)
    })

    it('递延为负(递延资产增>负债增): 当期250万 + 递延-80万 = 170万', () => {
      expect(calcIncomeTaxExpense(2_500_000, -800_000)).toBe(1_700_000)
    })

    it('仅当期(递延=0)', () => {
      expect(calcIncomeTaxExpense(2_000_000, 0)).toBe(2_000_000)
    })

    it('仅递延(当期=0)', () => {
      expect(calcIncomeTaxExpense(0, 500_000)).toBe(500_000)
    })

    it('both zero → 0', () => {
      expect(calcIncomeTaxExpense(0, 0)).toBe(0)
    })

    it('NaN handling', () => {
      expect(calcIncomeTaxExpense(NaN, 500_000)).toBe(500_000)
      expect(calcIncomeTaxExpense(2_000_000, NaN)).toBe(2_000_000)
    })
  })

  // ─── P6: 递延所得税费用=负债增-资产增 ─────────────────────────────────────
  describe('calcDeferredTaxExpense (P6: 递延=递延税负债增-递延税资产增)', () => {
    it('正常: 负债增100万 - 资产增50万 = 递延费用50万', () => {
      expect(calcDeferredTaxExpense(1_000_000, 500_000)).toBe(500_000)
    })

    it('资产增>负债增: 递延为负(减少所得税费用)', () => {
      expect(calcDeferredTaxExpense(200_000, 800_000)).toBe(-600_000)
    })

    it('仅负债增(资产不变)', () => {
      expect(calcDeferredTaxExpense(1_000_000, 0)).toBe(1_000_000)
    })

    it('仅资产增(负债不变)', () => {
      expect(calcDeferredTaxExpense(0, 500_000)).toBe(-500_000)
    })

    it('both zero → 0', () => {
      expect(calcDeferredTaxExpense(0, 0)).toBe(0)
    })

    it('NaN handling', () => {
      expect(calcDeferredTaxExpense(NaN, 500_000)).toBe(-500_000)
      expect(calcDeferredTaxExpense(1_000_000, NaN)).toBe(1_000_000)
    })

    it('大数(1e15)', () => {
      expect(calcDeferredTaxExpense(1e15, 5e14)).toBe(5e14)
    })
  })

  // ─── P7: 研发费用加计扣除 ─────────────────────────────────────────────────
  describe('calcRdSuperDeduction (P7: 研发加计=研发费用×加计比例)', () => {
    it('100%加计(2023年起一般企业): 500万×1.0 = 500万', () => {
      expect(calcRdSuperDeduction(5_000_000, 1.0)).toBe(5_000_000)
    })

    it('120%加计(集成电路行业): 500万×1.2 = 600万', () => {
      expect(calcRdSuperDeduction(5_000_000, 1.2)).toBe(6_000_000)
    })

    it('75%加计(历史税率): 500万×0.75 = 375万', () => {
      expect(calcRdSuperDeduction(5_000_000, 0.75)).toBe(3_750_000)
    })

    it('零研发费用 → 0', () => {
      expect(calcRdSuperDeduction(0, 1.0)).toBe(0)
    })

    it('零加计比例 → 0', () => {
      expect(calcRdSuperDeduction(5_000_000, 0)).toBe(0)
    })

    it('NaN handling', () => {
      expect(calcRdSuperDeduction(NaN, 1.0)).toBe(0)
      expect(calcRdSuperDeduction(5_000_000, NaN)).toBe(0)
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 3. useN5TaxAdjustmentEngine — 纳税调整引擎
// ═══════════════════════════════════════════════════════════════════════════════

describe('useN5TaxAdjustmentEngine', () => {
  // ─── P8: 纳税调整净额 ─────────────────────────────────────────────────────
  describe('calcNetAdjustment (P8: 纳税调整净额=Σ调增-Σ调减)', () => {
    it('正常: 调增[100万,200万] - 调减[50万] = 250万', () => {
      expect(calcNetAdjustment([1_000_000, 2_000_000], [500_000])).toBe(2_500_000)
    })

    it('调减>调增: 净额为负', () => {
      expect(calcNetAdjustment([500_000], [1_000_000, 2_000_000])).toBe(-2_500_000)
    })

    it('无调增: 净额=-Σ调减', () => {
      expect(calcNetAdjustment([], [1_000_000, 500_000])).toBe(-1_500_000)
    })

    it('无调减: 净额=Σ调增', () => {
      expect(calcNetAdjustment([1_000_000, 2_000_000], [])).toBe(3_000_000)
    })

    it('both empty → 0', () => {
      expect(calcNetAdjustment([], [])).toBe(0)
    })

    it('NaN in arrays treated as 0', () => {
      expect(calcNetAdjustment([1_000_000, NaN], [500_000])).toBe(500_000)
      expect(calcNetAdjustment([1_000_000], [NaN, 500_000])).toBe(500_000)
    })

    it('大数(1e15)', () => {
      expect(calcNetAdjustment([1e15], [5e14])).toBe(5e14)
    })
  })

  // ─── P10: 财产损失纳税调整额 ──────────────────────────────────────────────
  describe('calcPropertyLossAdjustment (P10: 财产损失=账面损失-税前扣除额)', () => {
    it('正常: 账面损失300万 - 核准扣除200万 = 调增100万', () => {
      expect(calcPropertyLossAdjustment(3_000_000, 2_000_000)).toBe(1_000_000)
    })

    it('全部核准: 账面=扣除 → 调整额=0', () => {
      expect(calcPropertyLossAdjustment(1_000_000, 1_000_000)).toBe(0)
    })

    it('未核准: 账面500万 - 扣除0 = 调增500万', () => {
      expect(calcPropertyLossAdjustment(5_000_000, 0)).toBe(5_000_000)
    })

    it('异常(扣除>账面): 理论不应出现但公式有效', () => {
      expect(calcPropertyLossAdjustment(1_000_000, 2_000_000)).toBe(-1_000_000)
    })

    it('both zero → 0', () => {
      expect(calcPropertyLossAdjustment(0, 0)).toBe(0)
    })

    it('NaN handling', () => {
      expect(calcPropertyLossAdjustment(NaN, 1_000_000)).toBe(-1_000_000)
      expect(calcPropertyLossAdjustment(3_000_000, NaN)).toBe(3_000_000)
    })
  })
})
