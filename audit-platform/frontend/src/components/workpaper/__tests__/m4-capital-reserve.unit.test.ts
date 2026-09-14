/**
 * 单元测试 — M4 资本公积公式引擎 + 变动引擎（确定性测试用例）
 *
 * Spec: .kiro/specs/m4-capital-reserve/
 * Task: 7.1
 * Requirements: P1-P6
 *
 * 与 PBT 测试（2.3~2.8）互补：PBT 验证全输入空间的性质守恒，
 * 本文件验证具体业务场景的确定性结果。
 *
 * 科目：4002 资本公积（**贷方/权益类！**）
 * 方向：期末 = 期初 + 贷方(增加) - 借方(减少)
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
} from '../composables/useM4FormulaEngine'
import {
  calcShareBasedDiff,
  aggregateReserve,
  type ReserveDetail,
} from '../composables/useM4ReserveEngine'

// ─── 1. calcAuditedAmount 审定数（P1） ──────────────────────────────────────

describe('calcAuditedAmount — 确定性用例', () => {
  it('基本场景: 1000 + 200 + (-50) = 1150', () => {
    expect(calcAuditedAmount(1000, 200, -50)).toBe(1150)
  })

  it('全零: 0 + 0 + 0 = 0', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('负AJE调减: 5000 + (-1000) + 0 = 4000', () => {
    expect(calcAuditedAmount(5000, -1000, 0)).toBe(4000)
  })
})

// ─── 2. calcEquityEndBalance 权益类期末（P2） ───────────────────────────────

describe('calcEquityEndBalance — 确定性用例（权益类！贷方）', () => {
  it('标准权益: 10000 + 5000 - 2000 = 13000', () => {
    expect(calcEquityEndBalance(10000, 5000, 2000)).toBe(13000)
  })

  it('无变动: 10000 + 0 - 0 = 10000', () => {
    expect(calcEquityEndBalance(10000, 0, 0)).toBe(10000)
  })

  it('净减少: 10000 + 1000 - 8000 = 3000', () => {
    expect(calcEquityEndBalance(10000, 1000, 8000)).toBe(3000)
  })

  it('⚠️ 验证方向: begin + credit - debit（NOT begin + debit - credit!）', () => {
    // 权益类贷方科目：贷方增加，借方减少
    // 若方向写反（begin + debit - credit），结果将是 10000 + 2000 - 5000 = 7000
    const result = calcEquityEndBalance(10000, 5000, 2000)
    expect(result).toBe(13000) // 正确：10000 + 5000 - 2000
    expect(result).not.toBe(7000) // 错误方向：10000 + 2000 - 5000
  })
})

// ─── 3. calcSubtotal 小计求和（P5） ─────────────────────────────────────────

describe('calcSubtotal — 确定性用例', () => {
  it('多项: [1000, 2000, 3000] = 6000', () => {
    expect(calcSubtotal([1000, 2000, 3000])).toBe(6000)
  })

  it('空数组: [] = 0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('单项: [500] = 500', () => {
    expect(calcSubtotal([500])).toBe(500)
  })
})

// ─── 4. calcShareBasedDiff 股份支付差异（P3） ───────────────────────────────

describe('calcShareBasedDiff — 确定性用例', () => {
  it('一致: J3=5000, booked=5000 → 0', () => {
    expect(calcShareBasedDiff(5000, 5000)).toBe(0)
  })

  it('差异: J3=5000, booked=4800 → 200', () => {
    expect(calcShareBasedDiff(5000, 4800)).toBe(200)
  })

  it('反向差异: J3=0, booked=1000 → -1000', () => {
    expect(calcShareBasedDiff(0, 1000)).toBe(-1000)
  })
})

// ─── 5. aggregateReserve 资本公积汇总（P4, P6） ─────────────────────────────

describe('aggregateReserve — 确定性用例', () => {
  it('混合分类: [{premium,1000},{other,2000},{premium,500}] → {premium:1500, other:2000, total:3500}', () => {
    const details: ReserveDetail[] = [
      { category: 'premium', amount: 1000 },
      { category: 'other', amount: 2000 },
      { category: 'premium', amount: 500 },
    ]
    const result = aggregateReserve(details)
    expect(result.premium).toBe(1500)
    expect(result.other).toBe(2000)
    expect(result.total).toBe(3500)
  })

  it('空数组: [] → {premium:0, other:0, total:0}', () => {
    const result = aggregateReserve([])
    expect(result.premium).toBe(0)
    expect(result.other).toBe(0)
    expect(result.total).toBe(0)
  })

  it('total === premium + other 不变量', () => {
    const details: ReserveDetail[] = [
      { category: 'premium', amount: 1234 },
      { category: 'other', amount: 5678 },
      { category: 'premium', amount: 910 },
      { category: 'other', amount: 1112 },
    ]
    const result = aggregateReserve(details)
    expect(result.total).toBe(result.premium + result.other)
  })
})
