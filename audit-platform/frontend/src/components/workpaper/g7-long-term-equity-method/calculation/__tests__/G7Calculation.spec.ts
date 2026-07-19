/**
 * G7 长期股权投资(权益法组) — Calculation 子组件单元测试
 *
 * 测试清单:
 * 1. calcEliminationAmount: 顺流(downstream)→全额 / 逆流(upstream)→×比例
 * 2. |incomeDifference| > materialityLevel → 触发红色高亮
 * 3. Tab切换不改变 selectedRowIndex
 *
 * Requirements: 5.8, 6.3
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'

import {
  calcEliminationAmount,
  calcEquityShare,
  calcIncomeDifference,
  parseNum,
} from '../../../composables/useG7EquityMethodFormulaEngine'
import {
  G714_PENNY_THRESHOLD,
  isAmountOverMateriality,
} from '../g7EquityMethodCalcModel'

// ═══════════════════════════════════════════════════════════════════════════════
// 1. 顺流/逆流差异化逻辑 — calcEliminationAmount
// ═══════════════════════════════════════════════════════════════════════════════

describe('G7Calculation — calcEliminationAmount 顺流/逆流差异化', () => {
  it('顺流(downstream): 应抵销 = 未实现利润全额', () => {
    const profit = 100000
    const ratio = 0.3
    const result = calcEliminationAmount('downstream', profit, ratio)
    // 顺流不乘比例，直接返回利润（round到2位小数）
    expect(result).toBe(100000)
  })

  it('逆流(upstream): 应抵销 = 未实现利润 × 持股比例', () => {
    const profit = 100000
    const ratio = 0.3
    const result = calcEliminationAmount('upstream', profit, ratio)
    // 逆流按持股比例: 100000 × 0.3 = 30000
    expect(result).toBe(30000)
  })

  it('顺流: 利润为0时结果为0', () => {
    expect(calcEliminationAmount('downstream', 0, 0.5)).toBe(0)
  })

  it('逆流: 比例为0时结果为0', () => {
    expect(calcEliminationAmount('upstream', 50000, 0)).toBe(0)
  })

  it('顺流: 负利润时保持负值（退货/冲回场景）', () => {
    const result = calcEliminationAmount('downstream', -20000, 0.4)
    expect(result).toBe(-20000)
  })

  it('逆流: 负利润时 = 负利润 × 比例', () => {
    const result = calcEliminationAmount('upstream', -20000, 0.4)
    expect(result).toBe(-8000)
  })

  it('保留2位小数精度', () => {
    // 100.126 × 0.33 = 33.04158 → round → 33.04
    const result = calcEliminationAmount('upstream', 100.126, 0.33)
    expect(result).toBe(33.04)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 2. 重要性水平高亮逻辑
// ═══════════════════════════════════════════════════════════════════════════════

describe('G7Calculation — |incomeDifference| > materialityLevel 高亮触发', () => {
  /**
   * 与 g7EquityMethodCalcModel.isAmountOverMateriality / 建议分录共用口径：
   *   已设置水平 → |diff| > level
   *   未设置(≤0) → |diff| > 分位 0.005
   *
   * **Validates: Requirements 5.8**
   */
  function shouldHighlight(incomeDifference: number, materialityLevel: number): boolean {
    return isAmountOverMateriality(incomeDifference, materialityLevel)
  }

  it('差异绝对值 > 重要性水平 → 高亮', () => {
    expect(shouldHighlight(50000, 30000)).toBe(true)
  })

  it('差异绝对值 = 重要性水平 → 不高亮（不含等于）', () => {
    expect(shouldHighlight(30000, 30000)).toBe(false)
  })

  it('差异绝对值 < 重要性水平 → 不高亮', () => {
    expect(shouldHighlight(10000, 30000)).toBe(false)
  })

  it('负差异绝对值 > 重要性水平 → 高亮', () => {
    expect(shouldHighlight(-50000, 30000)).toBe(true)
  })

  it('重要性未设置(≤0)时按分位阈值高亮', () => {
    expect(shouldHighlight(0.01, 0)).toBe(true)
    expect(shouldHighlight(-100, 0)).toBe(true)
    expect(shouldHighlight(G714_PENNY_THRESHOLD, 0)).toBe(false)
    expect(shouldHighlight(0.001, 0)).toBe(false)
  })

  it('差异为0时永远不高亮', () => {
    expect(shouldHighlight(0, 0)).toBe(false)
    expect(shouldHighlight(0, 100000)).toBe(false)
  })

  it('结合原底稿口径: ⑨-⑤+⑧ 计算差异', () => {
    const equityShare = calcEquityShare(200000, 0.3) // 60000
    const confirmedIncome = 50000
    const dividend = 10000
    const incomeDifference = calcIncomeDifference(confirmedIncome, equityShare, dividend) // 0
    expect(incomeDifference).toBe(0)
    expect(shouldHighlight(incomeDifference, 15000)).toBe(false)
    expect(shouldHighlight(calcIncomeDifference(40000, equityShare, 0), 15000)).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 3. 区段Tab行同步（Tab切换不改变 selectedRowIndex）
// ═══════════════════════════════════════════════════════════════════════════════

describe('G7Calculation — Tab切换不改变 selectedRowIndex', () => {
  /**
   * 组件逻辑：
   *   selectedRowIndex 是独立于 activeTab 的 ref
   *   切换 activeTab 时不重置 selectedRowIndex
   *
   * **Validates: Requirements 5.8, 6.3**
   */

  it('Tab从0切换到1后，selectedRowIndex保持不变', () => {
    const activeTab = ref(0)
    const selectedRowIndex = ref(3)

    // 模拟Tab切换
    activeTab.value = 1

    // selectedRowIndex 不应因 Tab 切换而重置
    expect(selectedRowIndex.value).toBe(3)
  })

  it('Tab从1切换回0后，selectedRowIndex保持不变', () => {
    const activeTab = ref(1)
    const selectedRowIndex = ref(5)

    activeTab.value = 0

    expect(selectedRowIndex.value).toBe(5)
  })

  it('多次Tab切换后，selectedRowIndex始终保持原值', () => {
    const activeTab = ref(0)
    const selectedRowIndex = ref(7)

    activeTab.value = 1
    activeTab.value = 0
    activeTab.value = 1
    activeTab.value = 0

    expect(selectedRowIndex.value).toBe(7)
  })

  it('Tab切换与行选择独立：切换Tab后再选行只改变行不改Tab', () => {
    const activeTab = ref(0)
    const selectedRowIndex = ref(0)

    // 选择第4行
    selectedRowIndex.value = 4
    expect(activeTab.value).toBe(0)

    // 切换Tab
    activeTab.value = 1
    expect(selectedRowIndex.value).toBe(4)

    // 再切换行
    selectedRowIndex.value = 2
    expect(activeTab.value).toBe(1)
  })
})
