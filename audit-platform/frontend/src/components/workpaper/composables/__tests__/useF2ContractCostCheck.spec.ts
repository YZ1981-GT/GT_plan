import { describe, it, expect } from 'vitest'
import { nextTick, ref } from 'vue'
import { calcSubtotal, calcImpairment, isLossContract } from '../useF2SpecialFormulaEngine'
import { useF2ContractCostCheck } from '../useF2ContractCostCheck'
import type { ChecklistResponse } from '../useF2SpecialFormData'

describe('F2-56 contract check coverage logic', () => {
  it('coverage = checked / population × 100', () => {
    const checked = calcSubtotal([100, 200, 50])
    const population = 1000
    expect((checked / population) * 100).toBe(35)
  })
})

describe('F2-56 addSample survives persist echo', () => {
  it('new blank sample is not pruned by the reload watcher', async () => {
    const allResponses = ref(new Map<string, ChecklistResponse>())
    const chk = useF2ContractCostCheck({ allResponses })
    expect(chk.sheet.value.samples).toHaveLength(1)

    chk.addSample()
    // persist() 同步写回 ROWS_KEY，触发 watcher 重新 load；
    // 自回声守卫应保住刚新增的空行（此前会被 migrate 的空行裁剪吃掉）。
    await nextTick()
    expect(chk.sheet.value.samples).toHaveLength(2)

    chk.addSample()
    await nextTick()
    expect(chk.sheet.value.samples).toHaveLength(3)
  })
})

describe('contract impairment/loss formulas', () => {
  it('impairment non-negative', () => {
    expect(calcImpairment(500, 300)).toBe(200)
    expect(calcImpairment(100, 200)).toBe(0)
  })

  it('loss contract', () => {
    expect(isLossContract(1000, 1200)).toBe(true)
  })
})
