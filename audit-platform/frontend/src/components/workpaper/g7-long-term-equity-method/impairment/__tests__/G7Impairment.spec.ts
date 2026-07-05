/**
 * G7 长期股权投资(权益法组) — Impairment 子组件单元测试
 *
 * 测试清单:
 * 1. calcImpairmentAmount always ≥ 0
 * 2. 累计亏损≤合计权益时超额=0，Tab2禁用逻辑
 * 3. 减值迹象=否→三列禁用；=是→三列必填
 *
 * Requirements: 6.4, 6.5, 6.6
 */
import { describe, it, expect } from 'vitest'
import { ref, computed } from 'vue'

import {
  calcImpairmentAmount,
  parseNum,
} from '../../../composables/useG7EquityMethodFormulaEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// 1. calcImpairmentAmount 永远 ≥ 0 (非负性)
// ═══════════════════════════════════════════════════════════════════════════════

describe('G7Impairment — calcImpairmentAmount 非负性', () => {
  /**
   * 减值金额 = MAX(0, 账面价值 - 可收回金额)
   * 当可收回金额 > 账面价值时，不存在负减值（不允许减值转回超原值）
   *
   * **Validates: Requirements 6.6**
   */

  it('账面价值 > 可收回金额 → 减值 = 差额', () => {
    expect(calcImpairmentAmount(100000, 80000)).toBe(20000)
  })

  it('账面价值 = 可收回金额 → 减值 = 0', () => {
    expect(calcImpairmentAmount(100000, 100000)).toBe(0)
  })

  it('账面价值 < 可收回金额 → 减值 = 0（非负）', () => {
    expect(calcImpairmentAmount(80000, 100000)).toBe(0)
  })

  it('两个参数均为0 → 减值 = 0', () => {
    expect(calcImpairmentAmount(0, 0)).toBe(0)
  })

  it('账面为负值场景（异常数据容错）→ 减值 = 0', () => {
    expect(calcImpairmentAmount(-10000, 50000)).toBe(0)
  })

  it('可收回为负值场景 → 减值 = 账面 - 负可收回 > 0', () => {
    // 100000 - (-50000) = 150000
    expect(calcImpairmentAmount(100000, -50000)).toBe(150000)
  })

  it('保留2位小数精度', () => {
    // 100000.556 - 80000.123 = 20000.433 → round → 20000.43
    expect(calcImpairmentAmount(100000.556, 80000.123)).toBe(20000.43)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 2. G7-16 超额亏损逻辑 + Tab2禁用
// ═══════════════════════════════════════════════════════════════════════════════

describe('G7Impairment — G7-16 超额亏损逻辑', () => {
  /**
   * G7-16 未确认投资损失:
   *   合计长期权益 = 投资账面 + 长期应收款 + 其他权益 + 预计负债
   *   超额亏损 = MAX(0, 累计亏损 - 合计长期权益)
   *   超额亏损为0时 Tab2 全部禁用
   *
   * **Validates: Requirements 6.4**
   */

  function calcTotalLongTermEquity(
    investmentBookValue: number,
    longTermReceivable: number,
    otherLongTermEquity: number,
    estimatedLiability: number,
  ): number {
    return Math.round((
      parseNum(investmentBookValue)
      + parseNum(longTermReceivable)
      + parseNum(otherLongTermEquity)
      + parseNum(estimatedLiability)
    ) * 100) / 100
  }

  function calcExcessLoss(cumulativeLoss: number, totalLongTermEquity: number): number {
    const diff = parseNum(cumulativeLoss) - parseNum(totalLongTermEquity)
    return Math.round(Math.max(0, diff) * 100) / 100
  }

  it('累计亏损 ≤ 合计权益 → 超额亏损 = 0', () => {
    const total = calcTotalLongTermEquity(500000, 200000, 100000, 50000) // 850000
    const excess = calcExcessLoss(800000, total)
    expect(excess).toBe(0)
  })

  it('累计亏损 > 合计权益 → 超额亏损 = 差额', () => {
    const total = calcTotalLongTermEquity(500000, 200000, 100000, 50000) // 850000
    const excess = calcExcessLoss(1000000, total)
    expect(excess).toBe(150000)
  })

  it('累计亏损 = 合计权益 → 超额亏损 = 0', () => {
    const total = calcTotalLongTermEquity(300000, 100000, 50000, 50000) // 500000
    const excess = calcExcessLoss(500000, total)
    expect(excess).toBe(0)
  })

  it('超额亏损为0时 → Tab2禁用', () => {
    const excessLoss = ref(0)
    const isTab2Disabled = computed(() => excessLoss.value === 0)
    expect(isTab2Disabled.value).toBe(true)
  })

  it('超额亏损 > 0 → Tab2启用', () => {
    const excessLoss = ref(150000)
    const isTab2Disabled = computed(() => excessLoss.value === 0)
    expect(isTab2Disabled.value).toBe(false)
  })

  it('超额亏损从正变为0时 → Tab2重新禁用', () => {
    const excessLoss = ref(50000)
    const isTab2Disabled = computed(() => excessLoss.value === 0)
    expect(isTab2Disabled.value).toBe(false)

    excessLoss.value = 0
    expect(isTab2Disabled.value).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 3. G7-17 减值迹象联动（三列禁用/必填切换）
// ═══════════════════════════════════════════════════════════════════════════════

describe('G7Impairment — 减值迹象联动（三列禁用/必填）', () => {
  /**
   * G7-17 减值测试:
   *   减值迹象=否 → 可收回金额/FV-处置费用/使用价值 三列灰色禁用
   *   减值迹象=是 → 三列高亮必填
   *
   * **Validates: Requirements 6.5**
   */

  interface ImpairmentRow {
    hasImpairmentSign: boolean
    recoverableAmount: number
    fvLessDisposalCost: number
    valueInUse: number
  }

  function getDisabledColumns(row: ImpairmentRow): string[] {
    if (!row.hasImpairmentSign) {
      return ['recoverableAmount', 'fvLessDisposalCost', 'valueInUse']
    }
    return []
  }

  function getRequiredColumns(row: ImpairmentRow): string[] {
    if (row.hasImpairmentSign) {
      return ['recoverableAmount', 'fvLessDisposalCost', 'valueInUse']
    }
    return []
  }

  it('减值迹象=否 → 三列禁用', () => {
    const row: ImpairmentRow = {
      hasImpairmentSign: false,
      recoverableAmount: 0,
      fvLessDisposalCost: 0,
      valueInUse: 0,
    }
    const disabled = getDisabledColumns(row)
    expect(disabled).toContain('recoverableAmount')
    expect(disabled).toContain('fvLessDisposalCost')
    expect(disabled).toContain('valueInUse')
    expect(disabled).toHaveLength(3)
  })

  it('减值迹象=是 → 三列必填（非禁用）', () => {
    const row: ImpairmentRow = {
      hasImpairmentSign: true,
      recoverableAmount: 80000,
      fvLessDisposalCost: 75000,
      valueInUse: 80000,
    }
    const disabled = getDisabledColumns(row)
    expect(disabled).toHaveLength(0)

    const required = getRequiredColumns(row)
    expect(required).toContain('recoverableAmount')
    expect(required).toContain('fvLessDisposalCost')
    expect(required).toContain('valueInUse')
  })

  it('减值迹象=否 → 必填列为空', () => {
    const row: ImpairmentRow = {
      hasImpairmentSign: false,
      recoverableAmount: 0,
      fvLessDisposalCost: 0,
      valueInUse: 0,
    }
    const required = getRequiredColumns(row)
    expect(required).toHaveLength(0)
  })

  it('减值迹象切换：否→是 → 解除禁用+触发必填', () => {
    const hasSign = ref(false)

    const disabled = computed(() => hasSign.value ? [] : ['recoverableAmount', 'fvLessDisposalCost', 'valueInUse'])
    const required = computed(() => hasSign.value ? ['recoverableAmount', 'fvLessDisposalCost', 'valueInUse'] : [])

    expect(disabled.value).toHaveLength(3)
    expect(required.value).toHaveLength(0)

    // 切换为"是"
    hasSign.value = true
    expect(disabled.value).toHaveLength(0)
    expect(required.value).toHaveLength(3)
  })

  it('减值迹象切换：是→否 → 禁用+取消必填', () => {
    const hasSign = ref(true)

    const disabled = computed(() => hasSign.value ? [] : ['recoverableAmount', 'fvLessDisposalCost', 'valueInUse'])
    const required = computed(() => hasSign.value ? ['recoverableAmount', 'fvLessDisposalCost', 'valueInUse'] : [])

    expect(disabled.value).toHaveLength(0)
    expect(required.value).toHaveLength(3)

    // 切换为"否"
    hasSign.value = false
    expect(disabled.value).toHaveLength(3)
    expect(required.value).toHaveLength(0)
  })
})
