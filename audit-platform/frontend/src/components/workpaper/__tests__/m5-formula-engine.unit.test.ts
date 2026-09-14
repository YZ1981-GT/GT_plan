/**
 * 单元测试 — M5 盈余公积公式引擎 useM5FormulaEngine + useM5AccrualEngine
 *
 * Spec: .kiro/specs/m5-surplus-reserve/
 * Task: 7.1
 * Requirements: P1-P6
 *
 * 覆盖：
 * - calcAuditedAmount: positive/negative/zero AJE/RJE combinations
 * - calcEquityEndBalance: 权益类方向(begin+credit-debit), VERIFY NOT ASSET
 * - calcSubtotal: empty/single/multiple/negative/NaN
 * - calcStatutoryAccrual: 10% rate, zero/negative base
 * - calcAccrualDiff: positive(under-accrual), negative(over-accrual), zero
 * - isAccrualCeilingReached: exactly 50%, below, above; zero capital edge case
 *
 * 科目：4101 盈余公积（贷方/权益类！期末=期初+贷方-借方）
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
} from '../composables/useM5FormulaEngine'
import {
  calcStatutoryAccrual,
  calcAccrualDiff,
  isAccrualCeilingReached,
} from '../composables/useM5AccrualEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// 1. calcAuditedAmount — 审定数公式链 (P1)
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcAuditedAmount (P1: 审定数=未审+AJE+RJE)', () => {
  it('positive values: 100万+5万+2万=107万', () => {
    expect(calcAuditedAmount(1_000_000, 50_000, 20_000)).toBe(1_070_000)
  })

  it('negative AJE: 调减场景', () => {
    expect(calcAuditedAmount(5_000_000, -800_000, 0)).toBe(4_200_000)
  })

  it('negative RJE: 重分类调出', () => {
    expect(calcAuditedAmount(3_000_000, 0, -500_000)).toBe(2_500_000)
  })

  it('all zeros → 0', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('negative unadjusted (unusual but formula valid)', () => {
    expect(calcAuditedAmount(-100_000, 50_000, 30_000)).toBe(-20_000)
  })

  it('large values (千万级盈余公积)', () => {
    expect(calcAuditedAmount(80_000_000, 2_500_000, -1_000_000)).toBe(81_500_000)
  })

  it('NaN treated as 0 via safe()', () => {
    expect(calcAuditedAmount(NaN, 100, 50)).toBe(150)
    expect(calcAuditedAmount(1000, NaN, NaN)).toBe(1000)
  })

  it('undefined/null treated as 0 via safe()', () => {
    expect(calcAuditedAmount(undefined as any, 200, 100)).toBe(300)
    expect(calcAuditedAmount(1000, null as any, null as any)).toBe(1000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 2. calcEquityEndBalance — 权益类贷方方向 (P2)
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcEquityEndBalance (P2: 权益类期末=期初+贷方-借方)', () => {
  it('basic: 期初100万 + 贷方计提50万 - 借方转增20万 = 130万', () => {
    expect(calcEquityEndBalance(1_000_000, 500_000, 200_000)).toBe(1_300_000)
  })

  it('no movement: credit=0, debit=0 → 期末=期初', () => {
    expect(calcEquityEndBalance(500_000, 0, 0)).toBe(500_000)
  })

  it('only credit: 仅计提法定盈余公积（贷方增加）', () => {
    expect(calcEquityEndBalance(1_000_000, 300_000, 0)).toBe(1_300_000)
  })

  it('only debit: 仅转增资本（借方减少）', () => {
    expect(calcEquityEndBalance(2_000_000, 0, 500_000)).toBe(1_500_000)
  })

  it('debit exceeds begin+credit → negative (公式正确，业务异常)', () => {
    expect(calcEquityEndBalance(100, 50, 200)).toBe(-50)
  })

  it('全部转增: debit=begin+credit → 期末=0', () => {
    expect(calcEquityEndBalance(500_000, 200_000, 700_000)).toBe(0)
  })

  it('VERIFY: 权益类方向 NOT asset (begin+cr-dr ≠ begin+dr-cr)', () => {
    // 权益类: begin + credit - debit
    // 资产类: begin + debit - credit (方向相反!)
    const b = 1_000_000
    const cr = 300_000
    const dr = 100_000
    const equityEnd = calcEquityEndBalance(b, cr, dr) // 1000000+300000-100000=1200000
    const assetEndWouldBe = b + dr - cr // 1000000+100000-300000=800000
    expect(equityEnd).toBe(1_200_000)
    expect(equityEnd).not.toBe(assetEndWouldBe) // 确认不是资产方向
  })

  it('all zeros → 0', () => {
    expect(calcEquityEndBalance(0, 0, 0)).toBe(0)
  })

  it('NaN/undefined/null handling → safe()', () => {
    expect(calcEquityEndBalance(NaN, 100_000, 50_000)).toBe(50_000)
    expect(calcEquityEndBalance(1_000_000, undefined as any, null as any)).toBe(1_000_000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 3. calcStatutoryAccrual — 法定10%计提 (P3)
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcStatutoryAccrual (P3: 法定计提=计提基数×10%)', () => {
  it('standard: 计提基数100万 × 10% = 10万', () => {
    expect(calcStatutoryAccrual(1_000_000)).toBe(100_000)
  })

  it('large base: 计提基数5000万 × 10% = 500万', () => {
    expect(calcStatutoryAccrual(50_000_000)).toBe(5_000_000)
  })

  it('zero base → 0 (无利润不计提)', () => {
    expect(calcStatutoryAccrual(0)).toBe(0)
  })

  it('negative base → negative (亏损年度公式结果为负，业务层判断不计提)', () => {
    expect(calcStatutoryAccrual(-2_000_000)).toBe(-200_000)
  })

  it('custom rate: 任意盈余公积15%', () => {
    expect(calcStatutoryAccrual(1_000_000, 0.15)).toBe(150_000)
  })

  it('default rate is 0.1', () => {
    expect(calcStatutoryAccrual(500_000)).toBe(50_000)
    expect(calcStatutoryAccrual(500_000, 0.1)).toBe(50_000)
  })

  it('NaN base → 0', () => {
    expect(calcStatutoryAccrual(NaN)).toBe(0)
  })

  it('null/undefined base → 0', () => {
    expect(calcStatutoryAccrual(null as any)).toBe(0)
    expect(calcStatutoryAccrual(undefined as any)).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 4. calcAccrualDiff — 计提差异 (P4)
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcAccrualDiff (P4: 差异=应计提-账面计提)', () => {
  it('positive diff (under-accrual): 应计提10万 - 账面8万 = 差异+2万', () => {
    expect(calcAccrualDiff(100_000, 80_000)).toBe(20_000)
  })

  it('negative diff (over-accrual): 应计提10万 - 账面12万 = 差异-2万', () => {
    expect(calcAccrualDiff(100_000, 120_000)).toBe(-20_000)
  })

  it('zero diff (exact match): 应计提=账面', () => {
    expect(calcAccrualDiff(100_000, 100_000)).toBe(0)
  })

  it('both zero → 0', () => {
    expect(calcAccrualDiff(0, 0)).toBe(0)
  })

  it('estimated=0, booked>0 → negative (不应计提但已计提)', () => {
    expect(calcAccrualDiff(0, 50_000)).toBe(-50_000)
  })

  it('estimated>0, booked=0 → positive (应计提但未提)', () => {
    expect(calcAccrualDiff(100_000, 0)).toBe(100_000)
  })

  it('NaN handling → safe(NaN)=0', () => {
    expect(calcAccrualDiff(NaN, 50_000)).toBe(-50_000)
    expect(calcAccrualDiff(100_000, NaN)).toBe(100_000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 5. isAccrualCeilingReached — 注册资本50%上限 (P5)
// ═══════════════════════════════════════════════════════════════════════════════

describe('isAccrualCeilingReached (P5: 累计≥注册资本50%可停止计提)', () => {
  it('exactly at 50%: 累计500万 = 注册资本1000万×50% → true', () => {
    expect(isAccrualCeilingReached(5_000_000, 10_000_000)).toBe(true)
  })

  it('above 50%: 累计600万 > 注册资本1000万×50% → true', () => {
    expect(isAccrualCeilingReached(6_000_000, 10_000_000)).toBe(true)
  })

  it('below 50%: 累计400万 < 注册资本1000万×50% → false', () => {
    expect(isAccrualCeilingReached(4_000_000, 10_000_000)).toBe(false)
  })

  it('zero capital → false (防御性处理：不可能达到上限)', () => {
    expect(isAccrualCeilingReached(1_000_000, 0)).toBe(false)
  })

  it('negative capital → false (防御性处理)', () => {
    expect(isAccrualCeilingReached(1_000_000, -5_000_000)).toBe(false)
  })

  it('both zero → false (cap=0 → 防御返回false)', () => {
    expect(isAccrualCeilingReached(0, 0)).toBe(false)
  })

  it('accumulated=0, positive capital → false', () => {
    expect(isAccrualCeilingReached(0, 10_000_000)).toBe(false)
  })

  it('large values: 累计5亿=注册资本10亿×50% → true', () => {
    expect(isAccrualCeilingReached(500_000_000, 1_000_000_000)).toBe(true)
  })

  it('NaN accumulated → safe(NaN)=0, treated as below ceiling', () => {
    expect(isAccrualCeilingReached(NaN, 10_000_000)).toBe(false)
  })

  it('NaN capital → safe(NaN)=0 → cap<=0 → false', () => {
    expect(isAccrualCeilingReached(5_000_000, NaN)).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6. calcSubtotal — 分类小计 (P6)
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcSubtotal (P6: Σarr)', () => {
  it('empty array → 0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('single element', () => {
    expect(calcSubtotal([1_500_000])).toBe(1_500_000)
  })

  it('multiple elements (法定+任意盈余公积合计)', () => {
    // 法定盈余公积800万 + 任意盈余公积300万 + 其他200万
    expect(calcSubtotal([8_000_000, 3_000_000, 2_000_000])).toBe(13_000_000)
  })

  it('negative values (转增资本汇总)', () => {
    expect(calcSubtotal([-500_000, -200_000, -100_000])).toBe(-800_000)
  })

  it('mixed positive/negative', () => {
    expect(calcSubtotal([1_000_000, -200_000, 500_000, -100_000])).toBe(1_200_000)
  })

  it('NaN in array treated as 0', () => {
    expect(calcSubtotal([100_000, NaN, 200_000])).toBe(300_000)
  })

  it('non-array input → 0 (defensive)', () => {
    expect(calcSubtotal(null as any)).toBe(0)
    expect(calcSubtotal(undefined as any)).toBe(0)
  })
})
