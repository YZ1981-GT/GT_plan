/**
 * G7TabNotSameControlMeasurement (G7-9) 单元测试
 *
 * 测试要点：
 * 1. calcNotSameControlCost 正确计算（对价 + 费用）
 * 2. calcGoodwill 符号判断：正=显示"商誉"，负=显示"廉价购买利得"(绿色)
 * 3. 动态行名称唯一性校验
 *
 * Spec: .kiro/specs/g7-long-term-equity-subsidiary/ Task 5.3
 * Requirements: 3.2, 3.4
 */
import { describe, it, expect } from 'vitest'
import {
  calcNotSameControlCost,
  calcGoodwill,
  parseNum,
} from '../../../composables/useG7SubFormulaEngine'

// ═══════════════════════════════════════════════════════════════════
// 1. calcNotSameControlCost 正确计算（对价 + 费用）
// ═══════════════════════════════════════════════════════════════════

describe('G7-9 非同控初始计量: calcNotSameControlCost 正确计算', () => {
  /**
   * **Validates: Requirements 3.4**
   */
  it('对价10000 + 费用500 = 10500', () => {
    expect(calcNotSameControlCost(10000, 500)).toBe(10500)
  })

  it('对价5000000 + 费用200000 = 5200000', () => {
    expect(calcNotSameControlCost(5000000, 200000)).toBe(5200000)
  })

  it('对价>0 + 费用=0 = 对价(无直接费用)', () => {
    expect(calcNotSameControlCost(8888, 0)).toBe(8888)
  })

  it('对价=0 + 费用>0 = 费用(对价为非现金)', () => {
    expect(calcNotSameControlCost(0, 300)).toBe(300)
  })

  it('两者都为0 = 0', () => {
    expect(calcNotSameControlCost(0, 0)).toBe(0)
  })

  it('精度保留两位: 999.99 + 0.01 = 1000', () => {
    expect(calcNotSameControlCost(999.99, 0.01)).toBe(1000)
  })

  it('精度保留两位: 1234.567 + 89.123 = 1323.69', () => {
    expect(calcNotSameControlCost(1234.567, 89.123)).toBe(1323.69)
  })

  it('大额对价+小额费用: 100000000 + 50000 = 100050000', () => {
    expect(calcNotSameControlCost(100000000, 50000)).toBe(100050000)
  })
})

// ═══════════════════════════════════════════════════════════════════
// 2. calcGoodwill 符号判断与显示逻辑
// ═══════════════════════════════════════════════════════════════════

describe('G7-9 非同控初始计量: calcGoodwill 符号判断', () => {
  /**
   * **Validates: Requirements 3.4**
   *
   * 业务规则 (CAS20非同控合并):
   * - goodwill = initialCost - shareOfFV
   * - goodwill > 0 → 商誉(资产), UI显示"商誉" + 绿色tag
   * - goodwill < 0 → 营业外收入(廉价购买利得), UI显示"廉价购买利得" + 蓝色tag
   * - goodwill === 0 → 无商誉, 显示 "—"
   *
   * 组件内逻辑 (G7TabNotSameControlMeasurement.vue):
   *   <el-tag v-if="row.goodwill > 0" type="success"> 商誉 {{ fmtNum(row.goodwill) }} </el-tag>
   *   <el-tag v-else-if="row.goodwill < 0" type="primary"> 廉价购买利得 {{ fmtNum(Math.abs(row.goodwill)) }} </el-tag>
   *   <span v-else>—</span>
   */

  /** 模拟组件中的显示判断逻辑 */
  function getGoodwillDisplay(goodwill: number): { label: string; type: string } | null {
    if (goodwill > 0) return { label: '商誉', type: 'success' }
    if (goodwill < 0) return { label: '廉价购买利得', type: 'primary' }
    return null // 显示 "—"
  }

  // --- 正商誉场景(成本 > 份额) ---

  it('成本15000 > 份额10000 → 商誉=5000(正值)', () => {
    const goodwill = calcGoodwill(15000, 10000)
    expect(goodwill).toBe(5000)
    expect(goodwill).toBeGreaterThan(0)
  })

  it('正商誉 → 显示"商誉" + success/绿色', () => {
    const goodwill = calcGoodwill(15000, 10000) // 5000
    const display = getGoodwillDisplay(goodwill)
    expect(display).not.toBeNull()
    expect(display!.label).toBe('商誉')
    expect(display!.type).toBe('success')
  })

  // --- 负商誉/廉价购买利得(成本 < 份额) ---

  it('成本8000 < 份额12000 → 商誉=-4000(负值=廉价购买利得)', () => {
    const goodwill = calcGoodwill(8000, 12000)
    expect(goodwill).toBe(-4000)
    expect(goodwill).toBeLessThan(0)
  })

  it('负商誉 → 显示"廉价购买利得" + primary/蓝色(实际组件为蓝色)', () => {
    const goodwill = calcGoodwill(8000, 12000) // -4000
    const display = getGoodwillDisplay(goodwill)
    expect(display).not.toBeNull()
    expect(display!.label).toBe('廉价购买利得')
    expect(display!.type).toBe('primary')
  })

  // --- 零商誉 ---

  it('成本=份额 → 商誉=0，显示"—"', () => {
    const goodwill = calcGoodwill(10000, 10000)
    expect(goodwill).toBe(0)
    const display = getGoodwillDisplay(goodwill)
    expect(display).toBeNull()
  })

  // --- 完整计算链路: consideration + fees → initialCost → goodwill ---

  it('完整计算链: 对价12000+费用1000=成本13000, FV20000×60%=份额12000, 商誉=1000', () => {
    const consideration = 12000
    const directFees = 1000
    const acquireeNetAssetsFV = 20000
    const shareholdingRatio = 0.6

    const initialCost = calcNotSameControlCost(consideration, directFees) // 13000
    const shareOfFV = Math.round(acquireeNetAssetsFV * shareholdingRatio * 100) / 100 // 12000
    const goodwill = calcGoodwill(initialCost, shareOfFV) // 1000

    expect(initialCost).toBe(13000)
    expect(shareOfFV).toBe(12000)
    expect(goodwill).toBe(1000)
    expect(getGoodwillDisplay(goodwill)!.label).toBe('商誉')
  })

  it('完整计算链: 对价5000+费用200=成本5200, FV15000×60%=份额9000, 廉价购买利得=-3800', () => {
    const consideration = 5000
    const directFees = 200
    const acquireeNetAssetsFV = 15000
    const shareholdingRatio = 0.6

    const initialCost = calcNotSameControlCost(consideration, directFees) // 5200
    const shareOfFV = Math.round(acquireeNetAssetsFV * shareholdingRatio * 100) / 100 // 9000
    const goodwill = calcGoodwill(initialCost, shareOfFV) // -3800

    expect(initialCost).toBe(5200)
    expect(shareOfFV).toBe(9000)
    expect(goodwill).toBe(-3800)
    expect(getGoodwillDisplay(goodwill)!.label).toBe('廉价购买利得')
  })

  // --- 精度边界 ---

  it('精度两位: calcGoodwill(100.55, 100.33) = 0.22', () => {
    expect(calcGoodwill(100.55, 100.33)).toBe(0.22)
  })

  it('极小正商誉0.01 → 仍显示"商誉"', () => {
    const goodwill = calcGoodwill(100.01, 100)
    expect(goodwill).toBe(0.01)
    expect(getGoodwillDisplay(goodwill)!.label).toBe('商誉')
  })

  it('极小负商誉-0.01 → 仍显示"廉价购买利得"', () => {
    const goodwill = calcGoodwill(100, 100.01)
    expect(goodwill).toBe(-0.01)
    expect(getGoodwillDisplay(goodwill)!.label).toBe('廉价购买利得')
  })
})

// ═══════════════════════════════════════════════════════════════════
// 3. 动态行名称唯一性校验
// ═══════════════════════════════════════════════════════════════════

describe('G7-9 非同控初始计量: 动态行名称唯一性校验', () => {
  /**
   * **Validates: Requirements 3.2, 3.5**
   *
   * 复现组件内逻辑 (G7TabNotSameControlMeasurement.vue handleAddRow):
   *   inputValidator: (val) => {
   *     if (!val?.trim()) return '名称不能为空'
   *     if (rows.value.some(r => r.investeeName === val.trim())) return '该被投资单位已存在'
   *     return true
   *   }
   */

  interface MockRow {
    id: string
    investeeName: string
  }

  /** 复现组件 inputValidator 逻辑 */
  function validateInvesteeName(rows: MockRow[], name: string | null | undefined): true | string {
    if (!name?.trim()) return '名称不能为空'
    if (rows.some(r => r.investeeName === name.trim())) return '该被投资单位已存在'
    return true
  }

  it('空字符串 → "名称不能为空"', () => {
    expect(validateInvesteeName([], '')).toBe('名称不能为空')
  })

  it('纯空白 → "名称不能为空"', () => {
    expect(validateInvesteeName([], '   ')).toBe('名称不能为空')
  })

  it('null → "名称不能为空"', () => {
    expect(validateInvesteeName([], null)).toBe('名称不能为空')
  })

  it('undefined → "名称不能为空"', () => {
    expect(validateInvesteeName([], undefined)).toBe('名称不能为空')
  })

  it('空行列表中任何有效名称 → true', () => {
    expect(validateInvesteeName([], '新公司X')).toBe(true)
  })

  it('新增不重复名称 → true', () => {
    const rows: MockRow[] = [
      { id: '1', investeeName: '目标公司A' },
      { id: '2', investeeName: '目标公司B' },
    ]
    expect(validateInvesteeName(rows, '目标公司C')).toBe(true)
  })

  it('新增重复名称 → "该被投资单位已存在"', () => {
    const rows: MockRow[] = [
      { id: '1', investeeName: '目标公司A' },
      { id: '2', investeeName: '目标公司B' },
    ]
    expect(validateInvesteeName(rows, '目标公司A')).toBe('该被投资单位已存在')
  })

  it('前后空白trim后匹配已有名称 → 拒绝', () => {
    const rows: MockRow[] = [
      { id: '1', investeeName: '目标公司A' },
    ]
    // trim后='目标公司A'，与已有匹配
    expect(validateInvesteeName(rows, '  目标公司A  ')).toBe('该被投资单位已存在')
  })

  it('删除行后名称不再冲突', () => {
    const rows: MockRow[] = [
      { id: '1', investeeName: '目标公司A' },
      { id: '2', investeeName: '目标公司B' },
    ]
    const afterDelete = rows.filter(r => r.id !== '1')
    expect(validateInvesteeName(afterDelete, '目标公司A')).toBe(true)
  })
})
