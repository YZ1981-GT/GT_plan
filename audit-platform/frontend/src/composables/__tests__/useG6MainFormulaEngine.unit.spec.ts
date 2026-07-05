/**
 * Unit Tests — G6 其他债权投资(main组) 公式引擎
 *
 * Task 4.3: G6-1审定表分组折叠与公式计算（具体示例）
 * Task 5.3: ECL公式链与区段Tab行同步（具体示例）
 *
 * Spec: .kiro/specs/g6-other-bond-investment-main/
 * Framework: vitest (concrete examples, no fast-check)
 */
import { describe, it, expect } from 'vitest'
import {
  parseNum,
  calcDebitBalance,
  calcAdjustedAmount,
  calcSubtotal,
  calcEndingSubtotal,
  calcUnadjustedProvision,
  calcImpairmentAdjustment,
  calcAdjustedBookValue,
  calcChangeRate,
  isDebitCreditBalanced,
  calcReportAmount,
} from '../useG6MainFormulaEngine'

// ═══════════════════════════════════════════════════════════════════
// Task 4.3: G6-1审定表分组折叠与公式计算
// Validates: Requirements 3.1, 3.4, 3.5
// ═══════════════════════════════════════════════════════════════════

describe('Task 4.3: G6-1审定表分组折叠与公式计算', () => {
  describe('calcAdjustedAmount — 审定数公式', () => {
    it('100000 + 5000 = 105000', () => {
      expect(calcAdjustedAmount(100000, 5000)).toBe(105000)
    })

    it('零调整: 250000 + 0 = 250000', () => {
      expect(calcAdjustedAmount(250000, 0)).toBe(250000)
    })

    it('负调整(冲减): 100000 + (-3000) = 97000', () => {
      expect(calcAdjustedAmount(100000, -3000)).toBe(97000)
    })
  })

  describe('calcSubtotal — 余额小计(成本+利息调整+应计利息)', () => {
    it('成本500000 + 利息调整-20000 + 应计利息8000 = 488000', () => {
      expect(calcSubtotal(500000, -20000, 8000)).toBe(488000)
    })

    it('全正: 300000 + 10000 + 5000 = 315000', () => {
      expect(calcSubtotal(300000, 10000, 5000)).toBe(315000)
    })

    it('利息调整为零: 100000 + 0 + 2000 = 102000', () => {
      expect(calcSubtotal(100000, 0, 2000)).toBe(102000)
    })
  })

  describe('calcReportAmount — 报表列示数(七组公式)', () => {
    it('小计488000 + 公允价值变动12000 - 减值5000 = 495000', () => {
      expect(calcReportAmount(488000, 12000, 5000)).toBe(495000)
    })

    it('无公允价值变动和减值: 500000 + 0 - 0 = 500000', () => {
      expect(calcReportAmount(500000, 0, 0)).toBe(500000)
    })

    it('公允价值负变动: 488000 + (-15000) - 5000 = 468000', () => {
      expect(calcReportAmount(488000, -15000, 5000)).toBe(468000)
    })

    it('减值大于公允价值变动: 488000 + 3000 - 50000 = 441000', () => {
      expect(calcReportAmount(488000, 3000, 50000)).toBe(441000)
    })
  })

  describe('calcChangeRate — 变动率计算', () => {
    it('期初100000 → 期末120000 = 0.2 (20%)', () => {
      expect(calcChangeRate(100000, 120000)).toBe(0.2)
    })

    it('期初0 → 期末50000 = null (除零保护)', () => {
      expect(calcChangeRate(0, 50000)).toBeNull()
    })

    it('期初200000 → 期末180000 = -0.1 (下降10%)', () => {
      expect(calcChangeRate(200000, 180000)).toBe(-0.1)
    })

    it('无变动: 期初100000 → 期末100000 = 0', () => {
      expect(calcChangeRate(100000, 100000)).toBe(0)
    })

    it('|变动率|>20% 触发必填(增长25%)', () => {
      const rate = calcChangeRate(100000, 125000)
      expect(rate).toBe(0.25)
      expect(Math.abs(rate!)).toBeGreaterThan(0.2)
    })

    it('|变动率|<20% 不触发必填(增长15%)', () => {
      const rate = calcChangeRate(100000, 115000)
      expect(rate).toBe(0.15)
      expect(Math.abs(rate!)).toBeLessThanOrEqual(0.2)
    })
  })

  describe('calcDebitBalance — 借方余额公式', () => {
    it('100000 + 30000 - 10000 = 120000', () => {
      expect(calcDebitBalance(100000, 30000, 10000)).toBe(120000)
    })

    it('零发生额: 500000 + 0 - 0 = 500000', () => {
      expect(calcDebitBalance(500000, 0, 0)).toBe(500000)
    })

    it('贷方大于借方(净减少): 200000 + 10000 - 50000 = 160000', () => {
      expect(calcDebitBalance(200000, 10000, 50000)).toBe(160000)
    })
  })

  describe('8层分组结构逻辑验证', () => {
    it('四小计 = 一成本 + 二利息调整 + 三应计利息', () => {
      const costSubtotal = 1000000       // 一、成本合计
      const interestAdjSubtotal = -50000 // 二、利息调整合计
      const accruedSubtotal = 30000      // 三、应计利息合计
      const fourthSubtotal = calcSubtotal(costSubtotal, interestAdjSubtotal, accruedSubtotal)
      expect(fourthSubtotal).toBe(980000)
    })

    it('七报表列示数 = 四小计 + 五公允价值变动 - 六减值', () => {
      const fourthSubtotal = 980000      // 四、小计
      const fvChangeSubtotal = 25000     // 五、公允价值变动合计(OCI)
      const impairmentSubtotal = 15000   // 六、减值准备合计
      const reportAmount = calcReportAmount(fourthSubtotal, fvChangeSubtotal, impairmentSubtotal)
      expect(reportAmount).toBe(990000)
    })

    it('变动额 = 期末审定 - 期初审定', () => {
      const openingAdjusted = calcAdjustedAmount(480000, 8000) // 488000
      const closingAdjusted = calcAdjustedAmount(495000, 5000) // 500000
      const changeAmount = closingAdjusted - openingAdjusted
      expect(openingAdjusted).toBe(488000)
      expect(closingAdjusted).toBe(500000)
      expect(changeAmount).toBe(12000)
    })
  })
})

// ═══════════════════════════════════════════════════════════════════
// Task 5.3: ECL公式链与区段Tab行同步
// Validates: Requirements 5.2, 5.3, 6.2, 6.3
// ═══════════════════════════════════════════════════════════════════

describe('Task 5.3: ECL公式链与区段Tab行同步', () => {
  describe('ECL公式链完整流程', () => {
    it('基础: ①=100000, ②=0.05 → ③=5000', () => {
      const result = calcUnadjustedProvision(100000, 0.05)
      expect(result).toBe(5000)
    })

    it('完整链: ⑤=20000, ②A=0.08, ①=100000, ②=0.05 → ⑥=4600', () => {
      // ⑥ = ⑤×②A + ①×(②A-②) = 20000×0.08 + 100000×(0.08-0.05) = 1600 + 3000 = 4600
      const result = calcImpairmentAdjustment(20000, 0.08, 100000, 0.05)
      expect(result).toBe(4600)
    })

    it('⑦ = ① + ⑤ = 100000 + 20000 = 120000', () => {
      const adjustedBalance = 100000 + 20000
      expect(adjustedBalance).toBe(120000)
    })

    it('⑧ = ③ + ⑥ = 5000 + 4600 = 9600', () => {
      const prov = calcUnadjustedProvision(100000, 0.05)        // ③ = 5000
      const impAdj = calcImpairmentAdjustment(20000, 0.08, 100000, 0.05) // ⑥ = 4600
      const adjustedProvision = prov + impAdj                   // ⑧ = 9600
      expect(adjustedProvision).toBe(9600)
    })

    it('⑨ = ⑦ - ⑧ = 120000 - 9600 = 110400', () => {
      const adjustedBalance = 120000
      const adjustedProvision = 9600
      const bookValue = calcAdjustedBookValue(adjustedBalance, adjustedProvision)
      expect(bookValue).toBe(110400)
    })

    it('恒等式验证: ⑧ ≈ ⑦×②A → 120000×0.08 = 9600 ✓', () => {
      const adjustedBalance = 120000  // ⑦
      const adjRate = 0.08            // ②A
      const expectedProvision = adjustedBalance * adjRate // 9600
      const actualProvision = 9600    // ⑧ (from ③+⑥)
      expect(actualProvision).toBe(expectedProvision)
    })

    it('恒等式验证: ⑨ ≈ ⑦×(1-②A) → 120000×0.92 = 110400 ✓', () => {
      const adjustedBalance = 120000  // ⑦
      const adjRate = 0.08            // ②A
      const expectedBookValue = adjustedBalance * (1 - adjRate) // 110400
      const actualBookValue = calcAdjustedBookValue(120000, 9600) // ⑨
      expect(actualBookValue).toBe(expectedBookValue)
    })
  })

  describe('ECL公式链边界值', () => {
    it('rate=0: ③=0, ⑥=⑤×②A (无原始损失率)', () => {
      const prov = calcUnadjustedProvision(100000, 0)         // ③ = 0
      expect(prov).toBe(0)
      const impAdj = calcImpairmentAdjustment(10000, 0.05, 100000, 0)
      // ⑥ = 10000×0.05 + 100000×(0.05-0) = 500 + 5000 = 5500
      expect(impAdj).toBe(5500)
    })

    it('rate=1: ③=①(全额计提)', () => {
      const prov = calcUnadjustedProvision(100000, 1)         // ③ = 100000
      expect(prov).toBe(100000)
    })

    it('adj=0(无余额调整): ⑥ = ①×(②A-②)', () => {
      // ⑥ = 0×②A + 100000×(0.08-0.05) = 0 + 3000 = 3000
      const impAdj = calcImpairmentAdjustment(0, 0.08, 100000, 0.05)
      expect(impAdj).toBe(3000)
    })

    it('②A=② (损失率不变): ⑥ = ⑤×②', () => {
      // ⑥ = 20000×0.05 + 100000×(0.05-0.05) = 1000 + 0 = 1000
      const impAdj = calcImpairmentAdjustment(20000, 0.05, 100000, 0.05)
      expect(impAdj).toBe(1000)
    })

    it('负余额调整(减少): ⑤=-10000', () => {
      // ⑥ = -10000×0.1 + 200000×(0.1-0.05) = -1000 + 10000 = 9000
      const impAdj = calcImpairmentAdjustment(-10000, 0.1, 200000, 0.05)
      expect(impAdj).toBe(9000)
    })
  })

  describe('G6-2明细表期末小计公式', () => {
    it('期初小计480000 + 增加50000 - 减少20000 + 利息收入15000 = 525000', () => {
      expect(calcEndingSubtotal(480000, 50000, 20000, 15000)).toBe(525000)
    })

    it('无变动: 期初小计300000 + 0 - 0 + 0 = 300000', () => {
      expect(calcEndingSubtotal(300000, 0, 0, 0)).toBe(300000)
    })

    it('净减少: 期初500000 + 0 - 100000 + 10000 = 410000', () => {
      expect(calcEndingSubtotal(500000, 0, 100000, 10000)).toBe(410000)
    })
  })

  describe('借贷平衡校验(G6-4调整分录)', () => {
    it('平衡: 借方[100000, 50000] 贷方[150000] → true', () => {
      expect(isDebitCreditBalanced([100000, 50000], [150000])).toBe(true)
    })

    it('不平衡: 借方[100000] 贷方[99000] → false (差额1000)', () => {
      expect(isDebitCreditBalanced([100000], [99000])).toBe(false)
    })

    it('空分录: 借方[] 贷方[] → true', () => {
      expect(isDebitCreditBalanced([], [])).toBe(true)
    })

    it('微小差异(精度容差): 借方[100000.005] 贷方[100000] → true (<0.01)', () => {
      expect(isDebitCreditBalanced([100000.005], [100000])).toBe(true)
    })

    it('刚好超出容差: 借方[100000.02] 贷方[100000] → false (差额0.02)', () => {
      expect(isDebitCreditBalanced([100000.02], [100000])).toBe(false)
    })
  })

  describe('parseNum边界', () => {
    it('正常数值直通', () => {
      expect(parseNum(12345.67)).toBe(12345.67)
      expect(parseNum(-999)).toBe(-999)
      expect(parseNum(0)).toBe(0)
    })

    it('字符串数值解析', () => {
      expect(parseNum('100000')).toBe(100000)
      expect(parseNum('3.14')).toBe(3.14)
      expect(parseNum('-50')).toBe(-50)
    })

    it('无效输入返回0', () => {
      expect(parseNum(null)).toBe(0)
      expect(parseNum(undefined)).toBe(0)
      expect(parseNum('')).toBe(0)
      expect(parseNum('abc')).toBe(0)
      expect(parseNum(NaN)).toBe(0)
    })
  })
})
