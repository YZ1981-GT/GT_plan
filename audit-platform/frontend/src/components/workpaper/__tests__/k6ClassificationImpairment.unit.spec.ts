/**
 * Unit Tests — K6 Classification Engine + Impairment Engine（边界/边缘情况）
 *
 * Spec: .kiro/specs/k6-held-for-sale/ Task 7.1
 * Requirements: CP-K6-01~07 (4.2, 5.2-5.4, 6.2-6.3, 9.3-9.6)
 *
 * 覆盖：
 * - classifyHeldForSale: CAS42 五条件分类判断
 * - calcFairValueNet: 公允价值净额
 * - calcImpairment: 减值孰低法
 * - calcAdditionalProvision: 本期应补提
 * - calcAllocationRatio: 分摊比例
 * - calcGroupImpairmentAllocation: 处置组减值分摊（先抵商誉再按比例）
 */
import { describe, it, expect } from 'vitest'
import { classifyHeldForSale } from '../composables/useK6ClassificationEngine'
import {
  calcFairValueNet,
  calcImpairment,
  calcAdditionalProvision,
  calcAllocationRatio,
  calcGroupImpairmentAllocation,
} from '../composables/useK6ImpairmentEngine'

// ════════════════════════════════════════════════════════════════════════════════
// classifyHeldForSale — CAS42 五条件分类 (Req 4.2, 9.3)
// ════════════════════════════════════════════════════════════════════════════════
describe('classifyHeldForSale — CAS42五条件分类判断 (Req 4.2, 9.3)', () => {
  it('全部5条件为true → classified', () => {
    expect(classifyHeldForSale([true, true, true, true, true])).toBe('classified')
  })

  it('条件①不满足 → not_classified', () => {
    expect(classifyHeldForSale([false, true, true, true, true])).toBe('not_classified')
  })

  it('条件②不满足 → not_classified', () => {
    expect(classifyHeldForSale([true, false, true, true, true])).toBe('not_classified')
  })

  it('条件③不满足 → not_classified', () => {
    expect(classifyHeldForSale([true, true, false, true, true])).toBe('not_classified')
  })

  it('条件④不满足 → not_classified', () => {
    expect(classifyHeldForSale([true, true, true, false, true])).toBe('not_classified')
  })

  it('条件⑤不满足 → not_classified', () => {
    expect(classifyHeldForSale([true, true, true, true, false])).toBe('not_classified')
  })

  it('全部false → not_classified', () => {
    expect(classifyHeldForSale([false, false, false, false, false])).toBe('not_classified')
  })

  it('空数组 → not_classified（未评估）', () => {
    expect(classifyHeldForSale([])).toBe('not_classified')
  })

  it('null输入 → not_classified', () => {
    expect(classifyHeldForSale(null as any)).toBe('not_classified')
  })

  it('undefined输入 → not_classified', () => {
    expect(classifyHeldForSale(undefined as any)).toBe('not_classified')
  })

  it('多于5个条件全true → classified（兼容扩展）', () => {
    expect(classifyHeldForSale([true, true, true, true, true, true, true])).toBe('classified')
  })

  it('少于5个条件全true → classified（不强制恰好5个）', () => {
    expect(classifyHeldForSale([true, true, true])).toBe('classified')
  })

  it('包含非布尔值 → not_classified（严格检查）', () => {
    expect(classifyHeldForSale([true, true, 1 as any, true, true])).toBe('not_classified')
    expect(classifyHeldForSale([true, true, 'yes' as any, true, true])).toBe('not_classified')
  })
})

// ════════════════════════════════════════════════════════════════════════════════
// calcFairValueNet — 公允价值净额 = 公允价值 - 预计出售费用 (Req 5.2, 9.4)
// ════════════════════════════════════════════════════════════════════════════════
describe('calcFairValueNet — 公允价值净额 (Req 5.2, 9.4)', () => {
  it('标准情况: 10000 - 500 = 9500', () => {
    expect(calcFairValueNet(10000, 500)).toBe(9500)
  })

  it('出售费用为0 → 净额=公允价值', () => {
    expect(calcFairValueNet(5000, 0)).toBe(5000)
  })

  it('出售费用>公允价值 → 净额为负', () => {
    expect(calcFairValueNet(1000, 2000)).toBe(-1000)
  })

  it('公允价值为0 → 净额=-出售费用', () => {
    expect(calcFairValueNet(0, 500)).toBe(-500)
  })

  it('两者都为0 → 0', () => {
    expect(calcFairValueNet(0, 0)).toBe(0)
  })

  it('NaN输入视为0: calcFairValueNet(NaN, 500) → -500', () => {
    expect(calcFairValueNet(NaN, 500)).toBe(-500)
  })

  it('NaN第二参数: calcFairValueNet(1000, NaN) → 1000', () => {
    expect(calcFairValueNet(1000, NaN)).toBe(1000)
  })

  it('大数: 1e12 - 5e10 = 9.5e11', () => {
    expect(calcFairValueNet(1e12, 5e10)).toBe(9.5e11)
  })

  it('负数公允价值（理论不应出现但需兜底）', () => {
    expect(calcFairValueNet(-1000, 500)).toBe(-1500)
  })
})

// ════════════════════════════════════════════════════════════════════════════════
// calcImpairment — 减值 = MAX(0, 账面价值 - 公允净额) (Req 5.3, 9.5)
// ════════════════════════════════════════════════════════════════════════════════
describe('calcImpairment — 减值孰低法 (Req 5.3, 9.5)', () => {
  it('账面>公允净额 → 减值=差额', () => {
    expect(calcImpairment(10000, 8000)).toBe(2000)
  })

  it('账面=公允净额 → 减值=0', () => {
    expect(calcImpairment(5000, 5000)).toBe(0)
  })

  it('账面<公允净额 → 减值=0（不可为负）', () => {
    expect(calcImpairment(3000, 5000)).toBe(0)
  })

  it('账面为0 → 减值=0', () => {
    expect(calcImpairment(0, 5000)).toBe(0)
  })

  it('公允净额为负(出售费用>公允) → 减值=全部账面', () => {
    expect(calcImpairment(10000, -2000)).toBe(12000)
  })

  it('两者都为0 → 减值=0', () => {
    expect(calcImpairment(0, 0)).toBe(0)
  })

  it('NaN账面视为0 → 减值=0（因为0-公允净额必然≤0）', () => {
    expect(calcImpairment(NaN, 5000)).toBe(0)
  })

  it('NaN公允净额视为0 → 减值=MAX(0,账面-0)=账面', () => {
    expect(calcImpairment(8000, NaN)).toBe(8000)
  })

  it('大数: 1e12 - 5e11 = 5e11', () => {
    expect(calcImpairment(1e12, 5e11)).toBe(5e11)
  })

  it('减值结果永远非负（数学性质）', () => {
    // 即使输入奇怪组合也≥0
    expect(calcImpairment(-1000, -2000)).toBe(1000)
    expect(calcImpairment(-1000, 5000)).toBe(0)
  })
})

// ════════════════════════════════════════════════════════════════════════════════
// calcAdditionalProvision — 本期应补提 = 减值金额 - 已计提 (Req 5.4)
// ════════════════════════════════════════════════════════════════════════════════
describe('calcAdditionalProvision — 本期应补提 (Req 5.4)', () => {
  it('需补提: 减值5000 - 已提3000 = 2000', () => {
    expect(calcAdditionalProvision(5000, 3000)).toBe(2000)
  })

  it('恰好: 减值5000 - 已提5000 = 0', () => {
    expect(calcAdditionalProvision(5000, 5000)).toBe(0)
  })

  it('可转回: 减值3000 - 已提5000 = -2000（负数表示转回）', () => {
    expect(calcAdditionalProvision(3000, 5000)).toBe(-2000)
  })

  it('无减值无已提 → 0', () => {
    expect(calcAdditionalProvision(0, 0)).toBe(0)
  })

  it('NaN输入视为0', () => {
    expect(calcAdditionalProvision(NaN, 3000)).toBe(-3000)
    expect(calcAdditionalProvision(5000, NaN)).toBe(5000)
  })
})

// ════════════════════════════════════════════════════════════════════════════════
// calcAllocationRatio — 分摊比例 = 组内/组合计 (Req 6.3, 9.6)
// ════════════════════════════════════════════════════════════════════════════════
describe('calcAllocationRatio — 分摊比例 (Req 6.3, 9.6)', () => {
  it('标准: 2000/10000 = 0.2', () => {
    expect(calcAllocationRatio(2000, 10000)).toBeCloseTo(0.2, 10)
  })

  it('等于组合计: 10000/10000 = 1.0', () => {
    expect(calcAllocationRatio(10000, 10000)).toBeCloseTo(1.0, 10)
  })

  it('组合计为0 → 兜底返回0（除零保护）', () => {
    expect(calcAllocationRatio(5000, 0)).toBe(0)
  })

  it('组内为0 → 比例=0', () => {
    expect(calcAllocationRatio(0, 10000)).toBe(0)
  })

  it('组内>组合计（理论不应出现）→ 比例>1', () => {
    expect(calcAllocationRatio(15000, 10000)).toBeCloseTo(1.5, 10)
  })

  it('NaN组内视为0 → 比例=0', () => {
    expect(calcAllocationRatio(NaN, 10000)).toBe(0)
  })

  it('NaN组合计视为0 → 兜底返回0', () => {
    expect(calcAllocationRatio(5000, NaN)).toBe(0)
  })

  it('负值组内: -1000/10000 = -0.1', () => {
    expect(calcAllocationRatio(-1000, 10000)).toBeCloseTo(-0.1, 10)
  })
})

// ════════════════════════════════════════════════════════════════════════════════
// calcGroupImpairmentAllocation — 处置组减值分摊（先抵商誉再按比例）(Req 6.2, 6.3)
// ════════════════════════════════════════════════════════════════════════════════
describe('calcGroupImpairmentAllocation — 处置组减值分摊 (Req 6.2, 6.3)', () => {
  it('标准场景: 减值10000, 商誉3000, 资产2000/总7000', () => {
    const result = calcGroupImpairmentAllocation(10000, 3000, 2000, 7000)
    // 先抵商誉: min(10000,3000)=3000
    expect(result.goodwillDeduction).toBe(3000)
    // 余额: 10000-3000=7000, 比例: 2000/7000≈0.2857, 分摊: 7000*0.2857=2000
    expect(result.itemAllocation).toBeCloseTo(2000, 4)
  })

  it('商誉吸收全部减值 → 无余额分摊', () => {
    const result = calcGroupImpairmentAllocation(3000, 5000, 2000, 7000)
    expect(result.goodwillDeduction).toBe(3000) // min(3000,5000)=3000
    expect(result.itemAllocation).toBe(0)       // remaining=0
  })

  it('无商誉 → 全部减值按比例分摊', () => {
    const result = calcGroupImpairmentAllocation(7000, 0, 3000, 7000)
    expect(result.goodwillDeduction).toBe(0)
    // ratio=3000/7000, allocation=7000*(3000/7000)=3000
    expect(result.itemAllocation).toBeCloseTo(3000, 4)
  })

  it('组合计为0 → 分摊=0（除零保护）', () => {
    const result = calcGroupImpairmentAllocation(5000, 1000, 2000, 0)
    expect(result.goodwillDeduction).toBe(1000) // min(5000,1000)=1000
    expect(result.itemAllocation).toBe(0)       // ratio=0 (groupBookExGoodwill=0)
  })

  it('NaN商誉视为0', () => {
    const result = calcGroupImpairmentAllocation(5000, NaN, 2000, 10000)
    expect(result.goodwillDeduction).toBe(0)
    // remaining=5000, ratio=2000/10000=0.2, allocation=5000*0.2=1000
    expect(result.itemAllocation).toBeCloseTo(1000, 4)
  })

  it('NaN减值视为0 → 全部返回0', () => {
    const result = calcGroupImpairmentAllocation(NaN, 3000, 2000, 7000)
    expect(result.goodwillDeduction).toBe(0)
    expect(result.itemAllocation).toBe(0)
  })

  it('减值=0 → 不分摊', () => {
    const result = calcGroupImpairmentAllocation(0, 3000, 2000, 7000)
    expect(result.goodwillDeduction).toBe(0)
    expect(result.itemAllocation).toBe(0)
  })

  it('单个资产占全组 → 分摊=余额全部', () => {
    const result = calcGroupImpairmentAllocation(10000, 2000, 8000, 8000)
    expect(result.goodwillDeduction).toBe(2000) // min(10000,2000)=2000
    // remaining=8000, ratio=8000/8000=1.0, allocation=8000
    expect(result.itemAllocation).toBeCloseTo(8000, 4)
  })
})
