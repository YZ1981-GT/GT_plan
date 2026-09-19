/**
 * K1 其他应收款 — 公式引擎 Unit Tests (CP-K1-01~09)
 *
 * 覆盖 useK1FormulaEngine + useK1ECLEngine + useK1BadDebtCalcEngine 全部核心纯函数。
 * 聚焦边界条件、零值、大数、方向正确性。
 * 与 k1FormulaEngine.pbt.test.ts 互补（本文件=具体值断言，PBT=通用属性验证）。
 *
 * Spec: .kiro/specs/k1-other-receivables/ Requirements CP-K1-01~09
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcContraEndBalance,
  calcBadDebtEnd,
  calcNetValue,
  calcTriangleReconciliation,
  calcProportion,
  calcSubtotal,
  calcChangeRate,
} from '../composables/useK1FormulaEngine'
import { determineStage } from '../composables/useK1ECLEngine'
import { calcECL, calcAgingLoss, calcProvisionVariance } from '../composables/useK1BadDebtCalcEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// 1. useK1FormulaEngine 单元测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK1FormulaEngine — calcAuditedAmount', () => {
  it('基础: 未审100 + AJE20 + RJE(-5) = 115', () => {
    expect(calcAuditedAmount(100, 20, -5)).toBe(115)
  })

  it('零值: 全零 = 0', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('负值: 未审-50 + AJE-30 + RJE-20 = -100', () => {
    expect(calcAuditedAmount(-50, -30, -20)).toBe(-100)
  })

  it('大数: 1e12 + 1e12 + 1e12 = 3e12', () => {
    expect(calcAuditedAmount(1e12, 1e12, 1e12)).toBe(3e12)
  })
})

describe('useK1FormulaEngine — calcAssetEndBalance (资产类)', () => {
  it('基础: 期初1000 + 借方200 - 贷方50 = 1150', () => {
    expect(calcAssetEndBalance(1000, 200, 50)).toBe(1150)
  })

  it('零值: 全零 = 0', () => {
    expect(calcAssetEndBalance(0, 0, 0)).toBe(0)
  })

  it('贷方大于期初+借方→负余额: 100 + 50 - 300 = -150', () => {
    expect(calcAssetEndBalance(100, 50, 300)).toBe(-150)
  })

  it('大数: 1e15 + 5e14 - 2e14 = 1.3e15', () => {
    expect(calcAssetEndBalance(1e15, 5e14, 2e14)).toBe(1.3e15)
  })

  it('方向正确性: 借方增加→余额增大', () => {
    const base = calcAssetEndBalance(1000, 0, 0)
    const withDebit = calcAssetEndBalance(1000, 100, 0)
    expect(withDebit).toBeGreaterThan(base)
  })
})

describe('useK1FormulaEngine — calcContraEndBalance (备抵类)', () => {
  it('基础: 期初500 + 贷方100 - 借方30 = 570', () => {
    expect(calcContraEndBalance(500, 100, 30)).toBe(570)
  })

  it('零值: 全零 = 0', () => {
    expect(calcContraEndBalance(0, 0, 0)).toBe(0)
  })

  it('借方大于期初+贷方→负余额: 100 + 20 - 200 = -80', () => {
    expect(calcContraEndBalance(100, 20, 200)).toBe(-80)
  })

  it('方向正确性: 贷方增加→余额增大(备抵增加)', () => {
    const base = calcContraEndBalance(500, 0, 0)
    const withCredit = calcContraEndBalance(500, 100, 0)
    expect(withCredit).toBeGreaterThan(base)
  })

  it('方向对比: 资产类vs备抵类，相同数值方向相反', () => {
    // 资产: begin+debit-credit; 备抵: begin+credit-debit
    const asset = calcAssetEndBalance(1000, 200, 100) // 1000+200-100=1100
    const contra = calcContraEndBalance(1000, 200, 100) // 1000+200-100=1100 (参数位置不同!)
    // 实际业务: 资产借方增加, 备抵贷方增加
    expect(asset).toBe(1100)
    expect(contra).toBe(1100)
  })
})

describe('useK1FormulaEngine — calcBadDebtEnd', () => {
  it('基础: 期初200 + 计提80 - 转回10 - 核销20 = 250', () => {
    expect(calcBadDebtEnd(200, 80, 10, 20)).toBe(250)
  })

  it('零值: 全零 = 0', () => {
    expect(calcBadDebtEnd(0, 0, 0, 0)).toBe(0)
  })

  it('仅期初: 无变动 → 期末=期初', () => {
    expect(calcBadDebtEnd(300, 0, 0, 0)).toBe(300)
  })

  it('转回+核销大于期初+计提→负值', () => {
    expect(calcBadDebtEnd(100, 50, 100, 100)).toBe(-50)
  })

  it('大数: 1e10 + 5e9 - 1e9 - 2e9 = 1.2e10', () => {
    expect(calcBadDebtEnd(1e10, 5e9, 1e9, 2e9)).toBe(1.2e10)
  })
})

describe('useK1FormulaEngine — calcNetValue', () => {
  it('基础: 应收1000 - 坏账200 = 800', () => {
    expect(calcNetValue(1000, 200)).toBe(800)
  })

  it('零值: 全零 = 0', () => {
    expect(calcNetValue(0, 0)).toBe(0)
  })

  it('坏账大于应收→负净值: 500 - 800 = -300', () => {
    expect(calcNetValue(500, 800)).toBe(-300)
  })

  it('坏账为零→净值=应收', () => {
    expect(calcNetValue(12345, 0)).toBe(12345)
  })
})

describe('useK1FormulaEngine — calcTriangleReconciliation', () => {
  it('平衡: (期初1000 + 增加500 - 减少200) - 期末1300 = 0', () => {
    expect(calcTriangleReconciliation(1000, 500, 200, 1300)).toBe(0)
  })

  it('不平衡: (1000 + 500 - 200) - 1400 = -100', () => {
    expect(calcTriangleReconciliation(1000, 500, 200, 1400)).toBe(-100)
  })

  it('零值: 全零 = 0', () => {
    expect(calcTriangleReconciliation(0, 0, 0, 0)).toBe(0)
  })

  it('仅期初和期末: 1000 + 0 - 0 - 1000 = 0', () => {
    expect(calcTriangleReconciliation(1000, 0, 0, 1000)).toBe(0)
  })

  it('大数平衡: 1e12 + 5e11 - 3e11 - 1.2e12 = 0', () => {
    expect(calcTriangleReconciliation(1e12, 5e11, 3e11, 1.2e12)).toBe(0)
  })
})

describe('useK1FormulaEngine — calcProportion', () => {
  it('基础: 200 / 1000 = 0.2', () => {
    expect(calcProportion(200, 1000)).toBe(0.2)
  })

  it('total=0 → null', () => {
    expect(calcProportion(100, 0)).toBeNull()
  })

  it('total<0 → null (按实现: total<=0返回null)', () => {
    expect(calcProportion(100, -50)).toBeNull()
  })

  it('item=0, total>0 → 0', () => {
    expect(calcProportion(0, 500)).toBe(0)
  })

  it('item负值, total正值 → 负比例', () => {
    expect(calcProportion(-200, 1000)).toBe(-0.2)
  })

  it('item=total → 1 (100%)', () => {
    expect(calcProportion(1000, 1000)).toBe(1)
  })
})

describe('useK1FormulaEngine — calcSubtotal', () => {
  it('空数组 → 0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('单元素: [42] → 42', () => {
    expect(calcSubtotal([42])).toBe(42)
  })

  it('多元素: [10, 20, 30, 40] → 100', () => {
    expect(calcSubtotal([10, 20, 30, 40])).toBe(100)
  })

  it('含负值: [100, -30, 50, -20] → 100', () => {
    expect(calcSubtotal([100, -30, 50, -20])).toBe(100)
  })

  it('全零: [0, 0, 0] → 0', () => {
    expect(calcSubtotal([0, 0, 0])).toBe(0)
  })

  it('大数组: 1000个1 → 1000', () => {
    expect(calcSubtotal(Array(1000).fill(1))).toBe(1000)
  })
})

describe('useK1FormulaEngine — calcChangeRate', () => {
  it('基础: current=120, prior=100 → (120-100)/100 = 0.2', () => {
    expect(calcChangeRate(120, 100)).toBeCloseTo(0.2)
  })

  it('prior=0 → null', () => {
    expect(calcChangeRate(100, 0)).toBeNull()
  })

  it('prior负值: current=50, prior=-100 → (50-(-100))/|-100| = 1.5', () => {
    expect(calcChangeRate(50, -100)).toBeCloseTo(1.5)
  })

  it('current=prior → 0', () => {
    expect(calcChangeRate(500, 500)).toBe(0)
  })

  it('下降: current=80, prior=100 → -0.2', () => {
    expect(calcChangeRate(80, 100)).toBeCloseTo(-0.2)
  })

  it('current=0, prior=100 → -1', () => {
    expect(calcChangeRate(0, 100)).toBeCloseTo(-1)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 2. useK1ECLEngine 单元测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK1ECLEngine — determineStage', () => {
  it('isImpaired=true, significantIncrease=true → 3 (已减值优先)', () => {
    expect(determineStage(true, true)).toBe(3)
  })

  it('isImpaired=true, significantIncrease=false → 3', () => {
    expect(determineStage(true, false)).toBe(3)
  })

  it('isImpaired=false, significantIncrease=true → 2', () => {
    expect(determineStage(false, true)).toBe(2)
  })

  it('isImpaired=false, significantIncrease=false → 1', () => {
    expect(determineStage(false, false)).toBe(1)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 3. useK1BadDebtCalcEngine 单元测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('useK1BadDebtCalcEngine — calcECL', () => {
  it('基础: EAD=10000, PD=0.05, LGD=0.4 → 200', () => {
    expect(calcECL(10000, 0.05, 0.4)).toBeCloseTo(200)
  })

  it('PD=0 → ECL=0', () => {
    expect(calcECL(10000, 0, 0.5)).toBe(0)
  })

  it('LGD=0 → ECL=0', () => {
    expect(calcECL(10000, 0.1, 0)).toBe(0)
  })

  it('EAD=0 → ECL=0', () => {
    expect(calcECL(0, 0.5, 0.5)).toBe(0)
  })

  it('负值EAD → 0 (兜底)', () => {
    expect(calcECL(-1000, 0.1, 0.5)).toBe(0)
  })

  it('负值PD → 0 (兜底)', () => {
    expect(calcECL(1000, -0.1, 0.5)).toBe(0)
  })

  it('负值LGD → 0 (兜底)', () => {
    expect(calcECL(1000, 0.1, -0.5)).toBe(0)
  })

  it('PD=1, LGD=1 → ECL=EAD (全损)', () => {
    expect(calcECL(50000, 1, 1)).toBe(50000)
  })

  it('大数: EAD=1e10, PD=0.01, LGD=0.6 → 6e7', () => {
    expect(calcECL(1e10, 0.01, 0.6)).toBeCloseTo(6e7)
  })
})

describe('useK1BadDebtCalcEngine — calcAgingLoss', () => {
  it('基础: balance=100000, lossRate=0.05 → 5000', () => {
    expect(calcAgingLoss(100000, 0.05)).toBeCloseTo(5000)
  })

  it('balance=0 → 0', () => {
    expect(calcAgingLoss(0, 0.3)).toBe(0)
  })

  it('lossRate=0 → 0', () => {
    expect(calcAgingLoss(50000, 0)).toBe(0)
  })

  it('负值balance → 0 (兜底)', () => {
    expect(calcAgingLoss(-1000, 0.1)).toBe(0)
  })

  it('负值lossRate → 0 (兜底)', () => {
    expect(calcAgingLoss(1000, -0.1)).toBe(0)
  })

  it('lossRate=1 → loss=balance (100%计提)', () => {
    expect(calcAgingLoss(80000, 1)).toBe(80000)
  })
})

describe('useK1BadDebtCalcEngine — calcProvisionVariance', () => {
  it('企业少提: 测算500 - 计提300 = 200', () => {
    expect(calcProvisionVariance(500, 300)).toBe(200)
  })

  it('企业多提: 测算200 - 计提350 = -150', () => {
    expect(calcProvisionVariance(200, 350)).toBe(-150)
  })

  it('一致: 测算400 - 计提400 = 0', () => {
    expect(calcProvisionVariance(400, 400)).toBe(0)
  })

  it('零值: 0 - 0 = 0', () => {
    expect(calcProvisionVariance(0, 0)).toBe(0)
  })

  it('大数: 1e9 - 9.5e8 = 5e7', () => {
    expect(calcProvisionVariance(1e9, 9.5e8)).toBeCloseTo(5e7)
  })
})
