/**
 * Unit Tests — M7 专项储备 公式引擎 + 计提引擎
 *
 * Task 7.1: useM7FormulaEngine + useM7AccrualEngine 单元测试
 * 覆盖：权益类方向 + 按产量/收入计提 + 计提差异
 *
 * Spec: .kiro/specs/m7-special-reserve/
 * Framework: vitest (concrete examples, no fast-check)
 * Validates: Requirements P1-P6
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
} from '../useM7FormulaEngine'
import {
  calcAccrualByOutput,
  calcAccrualByRevenue,
  calcAccrualDiff,
} from '../useM7AccrualEngine'

// ═══════════════════════════════════════════════════════════════════
// P1: 审定数公式链 calcAuditedAmount(u, a, r) = u + a + r
// Validates: Requirements 2.3
// ═══════════════════════════════════════════════════════════════════

describe('P1: calcAuditedAmount — 审定数公式链', () => {
  it('正常值: 100000 + 5000 + 2000 = 107000', () => {
    expect(calcAuditedAmount(100000, 5000, 2000)).toBe(107000)
  })

  it('零AJE和RJE: 250000 + 0 + 0 = 250000', () => {
    expect(calcAuditedAmount(250000, 0, 0)).toBe(250000)
  })

  it('负AJE(调减): 100000 + (-3000) + 0 = 97000', () => {
    expect(calcAuditedAmount(100000, -3000, 0)).toBe(97000)
  })

  it('负RJE(重分类调出): 200000 + 0 + (-50000) = 150000', () => {
    expect(calcAuditedAmount(200000, 0, -50000)).toBe(150000)
  })

  it('全零: 0 + 0 + 0 = 0', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('全负: (-100) + (-200) + (-300) = -600', () => {
    expect(calcAuditedAmount(-100, -200, -300)).toBe(-600)
  })

  it('大数值: 1e9 + 5e8 + 3e8 = 1.8e9', () => {
    expect(calcAuditedAmount(1e9, 5e8, 3e8)).toBe(1.8e9)
  })
})

// ═══════════════════════════════════════════════════════════════════
// P2: 权益类贷方期末余额 calcEquityEndBalance(b, cr, dr) = b + cr - dr
// Validates: Requirements 2.4, 7.4
// ═══════════════════════════════════════════════════════════════════

describe('P2: calcEquityEndBalance — 权益类贷方期末余额', () => {
  it('正常: 期初500000 + 贷方(计提)100000 - 借方(使用)30000 = 570000', () => {
    expect(calcEquityEndBalance(500000, 100000, 30000)).toBe(570000)
  })

  it('只有计提无使用: 100000 + 50000 - 0 = 150000', () => {
    expect(calcEquityEndBalance(100000, 50000, 0)).toBe(150000)
  })

  it('只有使用无计提: 200000 + 0 - 80000 = 120000', () => {
    expect(calcEquityEndBalance(200000, 0, 80000)).toBe(120000)
  })

  it('使用超过期初+计提(余额为负): 100000 + 20000 - 200000 = -80000', () => {
    expect(calcEquityEndBalance(100000, 20000, 200000)).toBe(-80000)
  })

  it('全零: 0 + 0 - 0 = 0', () => {
    expect(calcEquityEndBalance(0, 0, 0)).toBe(0)
  })

  it('大数值: 1e9 + 5e8 - 3e8 = 1.2e9', () => {
    expect(calcEquityEndBalance(1e9, 5e8, 3e8)).toBe(1.2e9)
  })

  it('⚠️ 权益类方向验证: 贷方增加专项储备', () => {
    // 安全生产费计提100万 → 贷方增加 → 余额增加
    const begin = 5000000
    const credit = 1000000  // 计提
    const debit = 0
    expect(calcEquityEndBalance(begin, credit, debit)).toBe(6000000)
  })

  it('⚠️ 权益类方向验证: 借方减少专项储备(使用)', () => {
    // 费用性支出使用50万 → 借方减少 → 余额减少
    const begin = 5000000
    const credit = 0
    const debit = 500000  // 使用
    expect(calcEquityEndBalance(begin, credit, debit)).toBe(4500000)
  })

  it('权益类 vs 资产类方向对比: 确认 b+cr-dr 不是 b+dr-cr', () => {
    // 如果误用资产类公式(b+dr-cr)会得到不同结果
    const b = 1000, cr = 300, dr = 100
    const equityResult = b + cr - dr  // 1200 (正确)
    const assetResult = b + dr - cr   // 800 (错误)
    expect(calcEquityEndBalance(b, cr, dr)).toBe(equityResult)
    expect(calcEquityEndBalance(b, cr, dr)).not.toBe(assetResult)
  })
})

// ═══════════════════════════════════════════════════════════════════
// P3: 按产量分档计提 calcAccrualByOutput(tiers) = Σ(output × rate)
// Validates: Requirements 4.2, 7.1
// ═══════════════════════════════════════════════════════════════════

describe('P3: calcAccrualByOutput — 安全生产费按产量分档计提', () => {
  it('单档: 产量100万吨 × 5元/吨 = 500万', () => {
    expect(calcAccrualByOutput([{ output: 1000000, rate: 5 }])).toBe(5000000)
  })

  it('多档煤矿: ≤100万吨5元 + >100万吨4元', () => {
    const tiers = [
      { output: 1000000, rate: 5 },  // 前100万吨: 500万
      { output: 500000, rate: 4 },   // 超出50万吨: 200万
    ]
    expect(calcAccrualByOutput(tiers)).toBe(7000000)
  })

  it('三档分档计提', () => {
    const tiers = [
      { output: 100, rate: 10 },   // 1000
      { output: 200, rate: 8 },    // 1600
      { output: 300, rate: 6 },    // 1800
    ]
    expect(calcAccrualByOutput(tiers)).toBe(4400)
  })

  it('空数组: 无分档 = 0', () => {
    expect(calcAccrualByOutput([])).toBe(0)
  })

  it('单项产量为零: 0 × 5 = 0', () => {
    expect(calcAccrualByOutput([{ output: 0, rate: 5 }])).toBe(0)
  })

  it('单项费率为零: 1000 × 0 = 0', () => {
    expect(calcAccrualByOutput([{ output: 1000, rate: 0 }])).toBe(0)
  })

  it('全零分档: [{0,0}] = 0', () => {
    expect(calcAccrualByOutput([{ output: 0, rate: 0 }])).toBe(0)
  })

  it('负产量(冲回场景): -100 × 5 = -500', () => {
    expect(calcAccrualByOutput([{ output: -100, rate: 5 }])).toBe(-500)
  })

  it('大数值: 1e8吨 × 15元/吨 = 1.5e9', () => {
    expect(calcAccrualByOutput([{ output: 1e8, rate: 15 }])).toBe(1.5e9)
  })
})

// ═══════════════════════════════════════════════════════════════════
// P4: 按营业收入计提 calcAccrualByRevenue(rev, rate) = rev × rate
// Validates: Requirements 4.3, 7.2
// ═══════════════════════════════════════════════════════════════════

describe('P4: calcAccrualByRevenue — 安全生产费按营业收入计提', () => {
  it('建筑施工: 造价1亿 × 2% = 200万', () => {
    expect(calcAccrualByRevenue(100000000, 0.02)).toBe(2000000)
  })

  it('其他企业: 收入5000万 × 1.5% = 75万', () => {
    expect(calcAccrualByRevenue(50000000, 0.015)).toBe(750000)
  })

  it('零收入: 0 × 0.02 = 0', () => {
    expect(calcAccrualByRevenue(0, 0.02)).toBe(0)
  })

  it('零费率: 1000000 × 0 = 0', () => {
    expect(calcAccrualByRevenue(1000000, 0)).toBe(0)
  })

  it('全零: 0 × 0 = 0', () => {
    expect(calcAccrualByRevenue(0, 0)).toBe(0)
  })

  it('负收入(冲回): -500000 × 0.02 = -10000', () => {
    expect(calcAccrualByRevenue(-500000, 0.02)).toBe(-10000)
  })

  it('大数值: 1e10 × 0.01 = 1e8', () => {
    expect(calcAccrualByRevenue(1e10, 0.01)).toBe(1e8)
  })

  it('小比例: 100000 × 0.001 = 100', () => {
    expect(calcAccrualByRevenue(100000, 0.001)).toBe(100)
  })
})

// ═══════════════════════════════════════════════════════════════════
// P5: 计提差异 calcAccrualDiff(est, booked) = est - booked
// Validates: Requirements 4.4, 7.3
// ═══════════════════════════════════════════════════════════════════

describe('P5: calcAccrualDiff — 计提差异', () => {
  it('少计提(正差=审计风险): 应提500万 - 账面400万 = 100万', () => {
    expect(calcAccrualDiff(5000000, 4000000)).toBe(1000000)
  })

  it('多计提(负差): 应提300万 - 账面350万 = -50万', () => {
    expect(calcAccrualDiff(3000000, 3500000)).toBe(-500000)
  })

  it('计提准确(零差异): 200万 - 200万 = 0', () => {
    expect(calcAccrualDiff(2000000, 2000000)).toBe(0)
  })

  it('全零: 0 - 0 = 0', () => {
    expect(calcAccrualDiff(0, 0)).toBe(0)
  })

  it('应提为零(全部多提): 0 - 100000 = -100000', () => {
    expect(calcAccrualDiff(0, 100000)).toBe(-100000)
  })

  it('账面为零(全部少提): 100000 - 0 = 100000', () => {
    expect(calcAccrualDiff(100000, 0)).toBe(100000)
  })

  it('负值场景: (-50000) - (-30000) = -20000', () => {
    expect(calcAccrualDiff(-50000, -30000)).toBe(-20000)
  })

  it('大数值差异: 1e9 - 9e8 = 1e8', () => {
    expect(calcAccrualDiff(1e9, 9e8)).toBe(1e8)
  })
})

// ═══════════════════════════════════════════════════════════════════
// P6: 分类小计 calcSubtotal(arr) = Σarr
// Validates: Requirements 2.3 (审定表分类小计)
// ═══════════════════════════════════════════════════════════════════

describe('P6: calcSubtotal — 分类小计求和', () => {
  it('正常数组: [100, 200, 300] = 600', () => {
    expect(calcSubtotal([100, 200, 300])).toBe(600)
  })

  it('单元素: [500000] = 500000', () => {
    expect(calcSubtotal([500000])).toBe(500000)
  })

  it('空数组: [] = 0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('含负值: [100, -50, 200, -30] = 220', () => {
    expect(calcSubtotal([100, -50, 200, -30])).toBe(220)
  })

  it('全零: [0, 0, 0] = 0', () => {
    expect(calcSubtotal([0, 0, 0])).toBe(0)
  })

  it('全负: [-100, -200, -300] = -600', () => {
    expect(calcSubtotal([-100, -200, -300])).toBe(-600)
  })

  it('大数值数组: [1e9, 2e9, 3e9] = 6e9', () => {
    expect(calcSubtotal([1e9, 2e9, 3e9])).toBe(6e9)
  })

  it('多元素求和: 10个100 = 1000', () => {
    expect(calcSubtotal(Array(10).fill(100))).toBe(1000)
  })
})

// ═══════════════════════════════════════════════════════════════════
// 综合场景：公式链联动验证
// ═══════════════════════════════════════════════════════════════════

describe('综合场景：M7公式链联动', () => {
  it('审定表完整链: 审定数→权益类期末→小计', () => {
    // 审定期初
    const auditedBegin = calcAuditedAmount(1000000, 50000, -20000) // 1030000
    expect(auditedBegin).toBe(1030000)

    // 审定贷方(计提)
    const auditedCredit = calcAuditedAmount(800000, 0, 0) // 800000
    expect(auditedCredit).toBe(800000)

    // 审定借方(使用)
    const auditedDebit = calcAuditedAmount(300000, 0, 0) // 300000
    expect(auditedDebit).toBe(300000)

    // 权益类期末 = 审定期初 + 审定贷方 - 审定借方
    const endBalance = calcEquityEndBalance(auditedBegin, auditedCredit, auditedDebit)
    expect(endBalance).toBe(1530000)
  })

  it('计提测试完整链: 按产量计提→差异计算', () => {
    // 按产量分档计提
    const estimated = calcAccrualByOutput([
      { output: 1000000, rate: 5 },
      { output: 200000, rate: 4 },
    ])
    expect(estimated).toBe(5800000) // 500万 + 80万

    // 账面计提5500000
    const diff = calcAccrualDiff(estimated, 5500000)
    expect(diff).toBe(300000) // 少提30万 → 审计风险
  })

  it('计提测试完整链: 按收入计提→差异计算', () => {
    const estimated = calcAccrualByRevenue(200000000, 0.015)
    expect(estimated).toBe(3000000) // 收入2亿×1.5% = 300万

    const diff = calcAccrualDiff(estimated, 3000000)
    expect(diff).toBe(0) // 计提准确
  })

  it('多类别小计与审定表勾稽', () => {
    // 各类别专项储备期末
    const category1End = calcEquityEndBalance(500000, 200000, 50000)  // 650000
    const category2End = calcEquityEndBalance(300000, 100000, 30000)  // 370000
    const category3End = calcEquityEndBalance(200000, 80000, 20000)   // 260000

    // 小计 = 各类别之和
    const subtotal = calcSubtotal([category1End, category2End, category3End])
    expect(subtotal).toBe(1280000)
  })
})
