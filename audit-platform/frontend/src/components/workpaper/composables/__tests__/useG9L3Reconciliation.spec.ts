/**
 * G9-5 L3 调节：仍持有未实现软校验 + 十因子公式不变量
 */
import { describe, expect, it } from 'vitest'
import { checkG9UnrealizedHeld } from '../useG9L3Reconciliation'
import { calcL3Reconciliation, calcL3Variance } from '../useG9FormulaEngine'

describe('checkG9UnrealizedHeld', () => {
  it('有期末余额及 FV 损益但未填未实现 → 告警', () => {
    expect(checkG9UnrealizedHeld({
      unrealizedHeld: 0,
      fvChangePL: 100,
      closingFairValue: 1000,
    })).toMatch(/未填仍持有未实现/)
  })

  it('期末为 0 但仍填未实现 → 告警', () => {
    expect(checkG9UnrealizedHeld({
      unrealizedHeld: 50,
      fvChangePL: 50,
      closingFairValue: 0,
    })).toMatch(/期末余额为 0/)
  })

  it('未实现绝对值大于 FV 损益 → 告警', () => {
    expect(checkG9UnrealizedHeld({
      unrealizedHeld: 120,
      fvChangePL: 100,
      closingFairValue: 500,
    })).toMatch(/大于本期 FV 损益/)
  })

  it('合理填列 → null', () => {
    expect(checkG9UnrealizedHeld({
      unrealizedHeld: 80,
      fvChangePL: 100,
      closingFairValue: 500,
    })).toBeNull()
  })

  it('期末有余额但无 FV 损益且未填未实现 → 允许（可能均为已实现）', () => {
    expect(checkG9UnrealizedHeld({
      unrealizedHeld: 0,
      fvChangePL: 0,
      closingFairValue: 500,
    })).toBeNull()
  })
})

describe('G9-5 十因子与差异', () => {
  it('公式期末不包含 unrealizedHeld', () => {
    const closing = calcL3Reconciliation(100, 20, 10, 5, 3, 8, 2, 1, 4, 0)
    // 100+20-10+5-3+8+2+1-4+0 = 119
    expect(closing).toBe(119)
    expect(calcL3Variance(closing, 119)).toBe(0)
  })
})
