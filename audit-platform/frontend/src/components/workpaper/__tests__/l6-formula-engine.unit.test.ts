/**
 * 单元测试 — L6 专项应付款公式引擎 useL6FormulaEngine
 *
 * Spec: .kiro/specs/l6-special-payables/
 * Task: 7.1
 * Requirements: P1-P5
 *
 * 覆盖：
 * - calcAuditedAmount: positive/negative/zero/null/undefined/NaN
 * - calcLiabilityEndBalance: 负债类方向(begin+credit-debit), edge cases, VERIFY NOT ASSET
 * - calcSubtotal: empty/single/multiple/NaN/non-array
 * - calcVariance: positive/negative/zero
 * - calcVarianceRate: zero denominator (xlsx IF logic), normal ratio
 * - calcDetailEndBalance: 4 params (begin+creditIn-carryForward-refund), verify direction
 * - calcCheckRatio: zero denominator, normal ratio
 * - validateAdjudicationVsDetail: match/mismatch
 *
 * 科目：2601 专项应付款（贷方/负债类！期末=期初+贷方-借方）
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
  calcVariance,
  calcVarianceRate,
  calcDetailEndBalance,
  calcCheckRatio,
  validateAdjudicationVsDetail,
} from '../composables/useL6FormulaEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// 1. calcAuditedAmount — 审定数公式链
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcAuditedAmount', () => {
  it('positive values: 审定数=未审+AJE+RJE', () => {
    expect(calcAuditedAmount(1000, 200, 50)).toBe(1250)
  })

  it('negative AJE: 调减场景', () => {
    expect(calcAuditedAmount(5000, -800, 0)).toBe(4200)
  })

  it('negative RJE: 重分类调出', () => {
    expect(calcAuditedAmount(3000, 0, -500)).toBe(2500)
  })

  it('all zeros → 0', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('negative unadjusted (unusual but formula still correct)', () => {
    expect(calcAuditedAmount(-100, 50, 30)).toBe(-20)
  })

  it('large values (千万级专项拨款)', () => {
    expect(calcAuditedAmount(80_000_000, 2_500_000, -1_000_000)).toBe(81_500_000)
  })

  it('NaN treated as 0 via safe()', () => {
    expect(calcAuditedAmount(NaN, 100, 50)).toBe(150)
    expect(calcAuditedAmount(1000, NaN, NaN)).toBe(1000)
  })

  it('undefined treated as 0 via safe()', () => {
    expect(calcAuditedAmount(undefined as any, 200, 100)).toBe(300)
  })

  it('null treated as 0 via safe()', () => {
    expect(calcAuditedAmount(1000, null as any, null as any)).toBe(1000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 2. calcLiabilityEndBalance — 负债类方向（贷方！）
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcLiabilityEndBalance (负债类期末=期初+贷方-借方)', () => {
  it('basic: begin + credit - debit (专项拨入场景)', () => {
    // 期初100万 + 本期拨入50万 - 本期结转20万 = 130万
    expect(calcLiabilityEndBalance(1_000_000, 500_000, 200_000)).toBe(1_300_000)
  })

  it('no movement: credit=0, debit=0 → 期末=期初', () => {
    expect(calcLiabilityEndBalance(500_000, 0, 0)).toBe(500_000)
  })

  it('debit exceeds begin+credit → negative (公式正确，业务异常)', () => {
    expect(calcLiabilityEndBalance(10, 5, 20)).toBe(-5)
  })

  it('begin=0, only credit → 新收到政府专项拨款', () => {
    expect(calcLiabilityEndBalance(0, 3_000_000, 0)).toBe(3_000_000)
  })

  it('全部结转: debit=begin+credit → 期末=0', () => {
    expect(calcLiabilityEndBalance(500, 200, 700)).toBe(0)
  })

  it('VERIFY: 负债类方向 NOT asset (begin+cr-dr ≠ begin+dr-cr)', () => {
    // 负债类: begin + credit - debit
    // 资产类: begin + debit - credit (方向相反!)
    const b = 1000
    const cr = 300
    const dr = 100
    const liabilityEnd = calcLiabilityEndBalance(b, cr, dr) // 1000+300-100=1200
    const assetEndWouldBe = b + dr - cr // 1000+100-300=800
    expect(liabilityEnd).toBe(1200)
    expect(liabilityEnd).not.toBe(assetEndWouldBe) // 确认不是资产方向
  })

  it('all zeros → 0', () => {
    expect(calcLiabilityEndBalance(0, 0, 0)).toBe(0)
  })

  it('NaN/undefined/null handling → 0', () => {
    expect(calcLiabilityEndBalance(NaN, 100, 50)).toBe(50)
    expect(calcLiabilityEndBalance(1000, undefined as any, null as any)).toBe(1000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 3. calcSubtotal — 分类小计
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcSubtotal', () => {
  it('empty array → 0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('single element', () => {
    expect(calcSubtotal([42_000])).toBe(42_000)
  })

  it('multiple elements (专项项目分类汇总)', () => {
    // 科研拨款 + 基建拨款 + 技改拨款
    expect(calcSubtotal([500_000, 800_000, 200_000])).toBe(1_500_000)
  })

  it('mixed positive/negative', () => {
    expect(calcSubtotal([1000, -200, 500, -100])).toBe(1200)
  })

  it('NaN in array treated as 0', () => {
    expect(calcSubtotal([100, NaN, 200])).toBe(300)
  })

  it('undefined/null in array treated as 0', () => {
    expect(calcSubtotal([100, undefined as any, null as any, 200])).toBe(300)
  })

  it('non-array input → 0 (defensive)', () => {
    expect(calcSubtotal(null as any)).toBe(0)
    expect(calcSubtotal(undefined as any)).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 4. calcVariance — 变动额
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcVariance', () => {
  it('positive change: 本期拨入大于结转', () => {
    expect(calcVariance(1_500_000, 1_000_000)).toBe(500_000)
  })

  it('negative change: 本期结转大于拨入', () => {
    expect(calcVariance(800_000, 1_200_000)).toBe(-400_000)
  })

  it('no change: current = prior', () => {
    expect(calcVariance(1000, 1000)).toBe(0)
  })

  it('both zero', () => {
    expect(calcVariance(0, 0)).toBe(0)
  })

  it('NaN handling: treated as 0', () => {
    expect(calcVariance(NaN, 100)).toBe(-100)
    expect(calcVariance(500, NaN)).toBe(500)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 5. calcVarianceRate — xlsx公式 IF逻辑
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcVarianceRate (xlsx: IF(AND(E=0,J=0),0, IF(AND(E=0,J>0),1, J/E)))', () => {
  it('prior=0, current=0 → 0 (无变动)', () => {
    expect(calcVarianceRate(0, 0)).toBe(0)
  })

  it('prior=0, current>0 → 1 (100%增长兜底)', () => {
    // 上期无余额，本期新拨入 → 100%
    expect(calcVarianceRate(500_000, 0)).toBe(1)
  })

  it('prior=0, current<0 → variance (保护性处理)', () => {
    // prior=0, variance<0 → 直接返回variance值
    expect(calcVarianceRate(-200, 0)).toBe(-200)
  })

  it('normal: 增长20%', () => {
    // variance = 1200-1000 = 200; rate = 200/1000 = 0.2
    expect(calcVarianceRate(1200, 1000)).toBeCloseTo(0.2, 5)
  })

  it('normal: 减少40%', () => {
    // variance = 600-1000 = -400; rate = -400/1000 = -0.4
    expect(calcVarianceRate(600, 1000)).toBeCloseTo(-0.4, 5)
  })

  it('double: current=2*prior → 100%增长', () => {
    expect(calcVarianceRate(2000, 1000)).toBeCloseTo(1.0, 5)
  })

  it('NaN handling: safe(NaN)=0', () => {
    // calcVarianceRate(0, 100): variance=0-100=-100, rate=-100/100=-1
    expect(calcVarianceRate(NaN, 100)).toBeCloseTo(-1, 5)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6. calcDetailEndBalance — 明细表4参数版
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcDetailEndBalance (明细期末=期初+拨入-结转-返还)', () => {
  it('all four params: basic scenario', () => {
    // 期初500 + 拨入300 - 结转100 - 返还50 = 650
    expect(calcDetailEndBalance(500_000, 300_000, 100_000, 50_000)).toBe(650_000)
  })

  it('no movement', () => {
    expect(calcDetailEndBalance(1_000_000, 0, 0, 0)).toBe(1_000_000)
  })

  it('only creditIn (新拨入)', () => {
    expect(calcDetailEndBalance(0, 2_000_000, 0, 0)).toBe(2_000_000)
  })

  it('only carryForward (项目完工结转)', () => {
    expect(calcDetailEndBalance(1_000_000, 0, 1_000_000, 0)).toBe(0)
  })

  it('only refund (退还未使用拨款)', () => {
    expect(calcDetailEndBalance(800_000, 0, 0, 300_000)).toBe(500_000)
  })

  it('verify direction: begin + creditIn - carryForward - refund (负债类贷方)', () => {
    const b = 1000
    const cIn = 500
    const cf = 200
    const rf = 100
    // 负债类：期初+贷方-借方 → 1000+500-200-100=1200
    expect(calcDetailEndBalance(b, cIn, cf, rf)).toBe(1200)
    // 等价于 calcLiabilityEndBalance(begin, credit, debit) where debit=cf+rf
    expect(calcDetailEndBalance(b, cIn, cf, rf)).toBe(
      calcLiabilityEndBalance(b, cIn, cf + rf),
    )
  })

  it('debit exceeds available → negative (公式正确)', () => {
    expect(calcDetailEndBalance(100, 50, 200, 100)).toBe(-150)
  })

  it('NaN/null/undefined handling', () => {
    expect(calcDetailEndBalance(NaN, 100, null as any, undefined as any)).toBe(100)
    expect(calcDetailEndBalance(1000, NaN, NaN, NaN)).toBe(1000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 7. calcCheckRatio — 检查比例
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcCheckRatio', () => {
  it('zero denominator: total=0 → 0 (避免除零)', () => {
    expect(calcCheckRatio(500, 0)).toBe(0)
  })

  it('both zero → 0', () => {
    expect(calcCheckRatio(0, 0)).toBe(0)
  })

  it('normal: 50% checked', () => {
    expect(calcCheckRatio(500_000, 1_000_000)).toBeCloseTo(0.5, 5)
  })

  it('100% checked', () => {
    expect(calcCheckRatio(1_000_000, 1_000_000)).toBeCloseTo(1.0, 5)
  })

  it('over 100% (checked > total, unusual)', () => {
    expect(calcCheckRatio(1_500_000, 1_000_000)).toBeCloseTo(1.5, 5)
  })

  it('checked=0, total>0 → 0 (未检查)', () => {
    expect(calcCheckRatio(0, 2_000_000)).toBe(0)
  })

  it('NaN handling', () => {
    expect(calcCheckRatio(NaN, 1000)).toBe(0)
    expect(calcCheckRatio(500, NaN)).toBe(0) // safe(NaN)=0 → total=0 → return 0
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 8. validateAdjudicationVsDetail — 审定vs明细勾稽
// ═══════════════════════════════════════════════════════════════════════════════

describe('validateAdjudicationVsDetail', () => {
  it('match: adjTotal === detailTotal → isMatch=true, diff=0', () => {
    const result = validateAdjudicationVsDetail(5_000_000, 5_000_000)
    expect(result.isMatch).toBe(true)
    expect(result.diff).toBe(0)
  })

  it('mismatch: adjTotal > detailTotal → positive diff', () => {
    const result = validateAdjudicationVsDetail(5_000_000, 4_500_000)
    expect(result.isMatch).toBe(false)
    expect(result.diff).toBe(500_000)
  })

  it('mismatch: adjTotal < detailTotal → negative diff', () => {
    const result = validateAdjudicationVsDetail(3_000_000, 3_200_000)
    expect(result.isMatch).toBe(false)
    expect(result.diff).toBe(-200_000)
  })

  it('both zero → match', () => {
    const result = validateAdjudicationVsDetail(0, 0)
    expect(result.isMatch).toBe(true)
    expect(result.diff).toBe(0)
  })

  it('NaN/null treated as 0 → match (both become 0)', () => {
    const result = validateAdjudicationVsDetail(NaN, null as any)
    expect(result.isMatch).toBe(true)
    expect(result.diff).toBe(0)
  })

  it('tiny diff still counts as mismatch (no epsilon tolerance)', () => {
    const result = validateAdjudicationVsDetail(1_000_001, 1_000_000)
    expect(result.isMatch).toBe(false)
    expect(result.diff).toBe(1)
  })
})
