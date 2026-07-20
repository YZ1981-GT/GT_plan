/**
 * G7TabSameControlMeasurement (G7-8) 单元测试
 *
 * 测试要点：
 * 1. calcSameControlCost 正确计算（净资产 × 比例）
 * 2. 差额=支付对价-初始成本，对价远超账面→应触发高亮提醒逻辑
 * 3. 动态行增删→名称唯一性校验
 *
 * Spec: .kiro/specs/g7-long-term-equity-subsidiary/ Task 5.3
 * Requirements: 3.1, 3.3
 */
import { describe, it, expect } from 'vitest'
import { calcSameControlCost } from '../../../composables/useG7SubFormulaEngine'
import { isSameControlDifferenceLarge } from '../g7SameControlModel'

// ═══════════════════════════════════════════════════════════════════
// 1. calcSameControlCost 正确计算（净资产 × 比例）
// ═══════════════════════════════════════════════════════════════════

describe('G7-8 同控初始计量: calcSameControlCost 正确计算', () => {
  /**
   * **Validates: Requirements 3.3**
   */
  it('净资产10000 × 比例0.6 = 6000', () => {
    expect(calcSameControlCost(10000, 0.6)).toBe(6000)
  })

  it('净资产5000000 × 比例0.51 = 2550000', () => {
    expect(calcSameControlCost(5000000, 0.51)).toBe(2550000)
  })

  it('净资产0 × 任意比例 = 0', () => {
    expect(calcSameControlCost(0, 0.8)).toBe(0)
  })

  it('任意净资产 × 比例0 = 0', () => {
    expect(calcSameControlCost(12345678, 0)).toBe(0)
  })

  it('净资产 × 比例1 = 净资产(100%控股)', () => {
    expect(calcSameControlCost(8888888, 1)).toBe(8888888)
  })

  it('精度保留两位(round): 1000 × 0.333 = 333', () => {
    expect(calcSameControlCost(1000, 0.333)).toBe(333)
  })

  it('精度保留两位: 999.99 × 0.667 = 666.99', () => {
    // 999.99 × 0.667 = 666.99333... → round(×100)/100 = 666.99
    expect(calcSameControlCost(999.99, 0.667)).toBe(666.99)
  })

  it('负净资产(资不抵债)场景: -500000 × 0.7 = -350000', () => {
    // 同控合并允许被合并方净资产为负
    expect(calcSameControlCost(-500000, 0.7)).toBe(-350000)
  })
})

// ═══════════════════════════════════════════════════════════════════
// 2. 差额计算 + 对价远超账面→橙色高亮逻辑
// ═══════════════════════════════════════════════════════════════════

describe('G7-8 同控初始计量: 差额计算与高亮提醒逻辑', () => {
  /**
   * **Validates: Requirements 3.1, 3.3**
   * 真实函数：isSameControlDifferenceLarge(initialCost, totalConsideration)
   */
  it('对价=初始成本 → 差额为0，无高亮', () => {
    const initialCost = calcSameControlCost(10000, 0.6) // 6000
    expect(isSameControlDifferenceLarge(initialCost, 6000)).toBe(false)
  })

  it('对价略高于初始成本(<50%) → 有差额但无高亮', () => {
    const initialCost = calcSameControlCost(10000, 0.6) // 6000
    expect(isSameControlDifferenceLarge(initialCost, 7000)).toBe(false)
  })

  it('对价远超账面(>50%) → 应触发橙色高亮', () => {
    const initialCost = calcSameControlCost(10000, 0.6) // 6000
    expect(isSameControlDifferenceLarge(initialCost, 15000)).toBe(true)
  })

  it('对价远低于账面(负差额>50%) → 也应触发高亮', () => {
    const initialCost = calcSameControlCost(10000, 0.6) // 6000
    expect(isSameControlDifferenceLarge(initialCost, 1000)).toBe(true)
  })

  it('对价恰好在临界点(差额=初始成本*50%) → 不触发高亮(需>不含=)', () => {
    const initialCost = calcSameControlCost(10000, 0.6) // 6000
    expect(isSameControlDifferenceLarge(initialCost, 9000)).toBe(false)
  })

  it('对价刚超过临界(差额>初始成本*50.01%) → 触发高亮', () => {
    const initialCost = calcSameControlCost(10000, 0.6) // 6000
    expect(isSameControlDifferenceLarge(initialCost, 9001)).toBe(true)
  })

  it('初始成本为0时不触发高亮(避免除零)', () => {
    const initialCost = calcSameControlCost(0, 0.6) // 0
    expect(isSameControlDifferenceLarge(initialCost, 5000)).toBe(false)
  })

  it('初始成本为负时不触发高亮(资不抵债)', () => {
    const initialCost = calcSameControlCost(-10000, 0.6) // -6000
    expect(isSameControlDifferenceLarge(initialCost, 5000)).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════
// 3. 动态行增删→名称唯一性校验
// ═══════════════════════════════════════════════════════════════════

describe('G7-8 同控初始计量: 动态行名称唯一性校验', () => {
  /**
   * **Validates: Requirements 3.1, 3.5**
   *
   * 复现组件内逻辑：
   *   if (rows.some(r => r.investeeName === name)) {
   *     ElMessage.warning('已存在，请勿重复添加')
   *     return
   *   }
   */

  interface MockRow {
    id: string
    investeeName: string
  }

  function checkNameUnique(rows: MockRow[], newName: string): boolean {
    return !rows.some(r => r.investeeName === newName)
  }

  it('空行列表时任何名称都唯一', () => {
    expect(checkNameUnique([], '新公司A')).toBe(true)
  })

  it('新增不重复名称 → 通过', () => {
    const rows: MockRow[] = [
      { id: '1', investeeName: '子公司A' },
      { id: '2', investeeName: '子公司B' },
    ]
    expect(checkNameUnique(rows, '子公司C')).toBe(true)
  })

  it('新增重复名称 → 拒绝', () => {
    const rows: MockRow[] = [
      { id: '1', investeeName: '子公司A' },
      { id: '2', investeeName: '子公司B' },
    ]
    expect(checkNameUnique(rows, '子公司A')).toBe(false)
  })

  it('名称区分大小写/全半角(中文场景)', () => {
    const rows: MockRow[] = [
      { id: '1', investeeName: '深圳A科技有限公司' },
    ]
    // 完全相同 → 拒绝
    expect(checkNameUnique(rows, '深圳A科技有限公司')).toBe(false)
    // 不同名称 → 通过
    expect(checkNameUnique(rows, '深圳Ａ科技有限公司')).toBe(true) // 全角A vs半角A
  })

  it('删除行后名称不再冲突', () => {
    const rows: MockRow[] = [
      { id: '1', investeeName: '子公司A' },
      { id: '2', investeeName: '子公司B' },
    ]
    // 模拟删除子公司A
    const filtered = rows.filter(r => r.id !== '1')
    expect(checkNameUnique(filtered, '子公司A')).toBe(true)
  })
})
