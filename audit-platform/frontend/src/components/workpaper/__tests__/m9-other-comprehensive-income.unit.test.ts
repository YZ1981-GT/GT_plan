/**
 * 单元测试 — M9 其他综合收益 useM9FormulaEngine + useM9OciEngine
 *
 * Spec: .kiro/specs/m9-other-comprehensive-income/
 * Task: 7.1
 *
 * 确定性单元测试，覆盖边界条件和典型场景。
 * PBT 已验证通用性质（P1-P6），本文件补充：
 *   - 零值 / 负值 / NaN / undefined 边界
 *   - 空数组 / 单元素 / 大数组
 *   - 混合分类 + 两大类汇总一致性
 *
 * _Requirements: P1-P6_
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
} from '../composables/useM9FormulaEngine'
import {
  calcAfterTaxNet,
  calcReconcileDiff,
  aggregateOci,
} from '../composables/useM9OciEngine'
import type { OciItem } from '../composables/useM9OciEngine'

// ═══════════════════════════════════════════════════════════════
// calcAuditedAmount: 审定数 = 未审 + AJE + RJE
// ═══════════════════════════════════════════════════════════════

describe('calcAuditedAmount', () => {
  it('基本正数', () => {
    expect(calcAuditedAmount(1000, 200, 50)).toBe(1250)
  })

  it('全零', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('负值AJE（调减）', () => {
    expect(calcAuditedAmount(500, -100, 0)).toBe(400)
  })

  it('负值RJE（重分类调减）', () => {
    expect(calcAuditedAmount(500, 0, -200)).toBe(300)
  })

  it('全负', () => {
    expect(calcAuditedAmount(-100, -50, -30)).toBe(-180)
  })

  it('大金额精度', () => {
    expect(calcAuditedAmount(999999999, 1, 0)).toBe(1000000000)
  })
})

// ═══════════════════════════════════════════════════════════════
// calcEquityEndBalance: 权益类贷方 期末 = 期初 + 贷方 - 借方
// ═══════════════════════════════════════════════════════════════

describe('calcEquityEndBalance', () => {
  it('权益类方向：期末 = 期初 + 贷方 - 借方', () => {
    // 期初100, 贷方(OCI增加)50, 借方(减少)20 → 130
    expect(calcEquityEndBalance(100, 50, 20)).toBe(130)
  })

  it('全零', () => {
    expect(calcEquityEndBalance(0, 0, 0)).toBe(0)
  })

  it('仅贷方发生（OCI只增不减）', () => {
    expect(calcEquityEndBalance(200, 100, 0)).toBe(300)
  })

  it('仅借方发生（OCI只减/重分类）', () => {
    expect(calcEquityEndBalance(200, 0, 80)).toBe(120)
  })

  it('借方>贷方（期末变负数，虽不常见但公式允许）', () => {
    expect(calcEquityEndBalance(0, 10, 50)).toBe(-40)
  })

  it('大金额', () => {
    expect(calcEquityEndBalance(500000000, 300000000, 100000000)).toBe(700000000)
  })

  it('⚠️ 方向对比M3（M9是+贷-借，M3是+借-贷）', () => {
    // M9权益类：100 + 50(贷) - 20(借) = 130
    expect(calcEquityEndBalance(100, 50, 20)).toBe(130)
    // 如果是M3库存股：100 + 20(借) - 50(贷) = 70 → 不同！
    // 这里只验证M9方向正确
  })
})

// ═══════════════════════════════════════════════════════════════
// calcSubtotal: 数组求和
// ═══════════════════════════════════════════════════════════════

describe('calcSubtotal', () => {
  it('空数组', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('单元素', () => {
    expect(calcSubtotal([42])).toBe(42)
  })

  it('多元素正数', () => {
    expect(calcSubtotal([10, 20, 30])).toBe(60)
  })

  it('含负值', () => {
    expect(calcSubtotal([100, -50, 25, -10])).toBe(65)
  })

  it('大数组（50元素）', () => {
    const arr = Array.from({ length: 50 }, (_, i) => i + 1) // 1+2+...+50 = 1275
    expect(calcSubtotal(arr)).toBe(1275)
  })

  it('全零数组', () => {
    expect(calcSubtotal([0, 0, 0, 0, 0])).toBe(0)
  })

  it('含NaN元素被safe处理为0', () => {
    expect(calcSubtotal([10, NaN, 20])).toBe(30)
  })
})

// ═══════════════════════════════════════════════════════════════
// calcAfterTaxNet: 税后净额 = 税前 - 所得税影响
// ═══════════════════════════════════════════════════════════════

describe('calcAfterTaxNet', () => {
  it('基本场景：税前100-税25=75', () => {
    expect(calcAfterTaxNet(100, 25)).toBe(75)
  })

  it('零税额（免税OCI）', () => {
    expect(calcAfterTaxNet(100, 0)).toBe(100)
  })

  it('零税前（无发生额）', () => {
    expect(calcAfterTaxNet(0, 0)).toBe(0)
  })

  it('负税前（OCI减少方向）', () => {
    expect(calcAfterTaxNet(-80, -20)).toBe(-60)
  })

  it('税额大于税前（理论上异常但公式允许）', () => {
    expect(calcAfterTaxNet(50, 100)).toBe(-50)
  })

  it('大金额精度', () => {
    expect(calcAfterTaxNet(1000000, 250000)).toBe(750000)
  })
})

// ═══════════════════════════════════════════════════════════════
// calcReconcileDiff: 核对差异 = 来源金额 - 账面OCI增加
// ═══════════════════════════════════════════════════════════════

describe('calcReconcileDiff', () => {
  it('零差异（核对一致）', () => {
    expect(calcReconcileDiff(500, 500)).toBe(0)
  })

  it('正差异（来源>账面）', () => {
    expect(calcReconcileDiff(600, 500)).toBe(100)
  })

  it('负差异（来源<账面）', () => {
    expect(calcReconcileDiff(400, 500)).toBe(-100)
  })

  it('全零', () => {
    expect(calcReconcileDiff(0, 0)).toBe(0)
  })

  it('负值来源（G8公允价值下跌）', () => {
    expect(calcReconcileDiff(-200, -200)).toBe(0)
  })

  it('大金额差异', () => {
    expect(calcReconcileDiff(99999999, 100000000)).toBe(-1)
  })
})

// ═══════════════════════════════════════════════════════════════
// aggregateOci: OCI两大类汇总 total = nonReclass + reclass
// ═══════════════════════════════════════════════════════════════

describe('aggregateOci', () => {
  it('空数组', () => {
    const result = aggregateOci([])
    expect(result).toEqual({ nonReclass: 0, reclass: 0, total: 0 })
  })

  it('仅nonReclass项', () => {
    const items: OciItem[] = [
      { amount: 100, category: 'nonReclass' }, // G8公允变动
      { amount: 50, category: 'nonReclass' },  // J2重计量
    ]
    const result = aggregateOci(items)
    expect(result.nonReclass).toBe(150)
    expect(result.reclass).toBe(0)
    expect(result.total).toBe(150)
  })

  it('仅reclass项', () => {
    const items: OciItem[] = [
      { amount: 200, category: 'reclass' }, // 其他债权公允变动
      { amount: 80, category: 'reclass' },  // 现金流量套期
      { amount: 30, category: 'reclass' },  // 外币折算
    ]
    const result = aggregateOci(items)
    expect(result.nonReclass).toBe(0)
    expect(result.reclass).toBe(310)
    expect(result.total).toBe(310)
  })

  it('混合分类 + total = nonReclass + reclass', () => {
    const items: OciItem[] = [
      { amount: 100, category: 'nonReclass' }, // G8
      { amount: -30, category: 'nonReclass' }, // J2负值（重计量损失）
      { amount: 200, category: 'reclass' },    // 外币折算
      { amount: -50, category: 'reclass' },    // 套期损失
    ]
    const result = aggregateOci(items)
    expect(result.nonReclass).toBe(70)   // 100 + (-30)
    expect(result.reclass).toBe(150)     // 200 + (-50)
    expect(result.total).toBe(220)       // 70 + 150
    // 核心性质：total === nonReclass + reclass
    expect(result.total).toBe(result.nonReclass + result.reclass)
  })

  it('含负值金额', () => {
    const items: OciItem[] = [
      { amount: -500, category: 'nonReclass' },
      { amount: -300, category: 'reclass' },
    ]
    const result = aggregateOci(items)
    expect(result.nonReclass).toBe(-500)
    expect(result.reclass).toBe(-300)
    expect(result.total).toBe(-800)
  })

  it('大量项目汇总正确', () => {
    // 20个nonReclass + 20个reclass
    const items: OciItem[] = [
      ...Array.from({ length: 20 }, (_, i) => ({
        amount: (i + 1) * 10,
        category: 'nonReclass' as const,
      })),
      ...Array.from({ length: 20 }, (_, i) => ({
        amount: (i + 1) * 5,
        category: 'reclass' as const,
      })),
    ]
    const result = aggregateOci(items)
    // nonReclass: 10+20+...+200 = 10*(1+2+...+20) = 10*210 = 2100
    expect(result.nonReclass).toBe(2100)
    // reclass: 5+10+...+100 = 5*(1+2+...+20) = 5*210 = 1050
    expect(result.reclass).toBe(1050)
    expect(result.total).toBe(3150)
    expect(result.total).toBe(result.nonReclass + result.reclass)
  })
})
