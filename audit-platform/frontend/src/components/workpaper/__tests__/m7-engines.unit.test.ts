/**
 * 单元测试 — M7 专项储备 双引擎综合验证
 *
 * 覆盖：
 * 1. useM7FormulaEngine — 审定数 + 权益类期末(贷方!) + 分类小计
 * 2. useM7AccrualEngine — 按产量计提 + 按收入计提 + 计提差异
 *
 * Spec: .kiro/specs/m7-special-reserve/ Task 7.1
 * Requirements: P1-P6
 *
 * 科目：4201 专项储备（贷方/权益类！期末=期初+贷方-借方）
 *
 * ⚠️ 方向与M3库存股（借方备抵）完全相反！
 *   M7专项储备（贷方权益）：期末 = 期初 + 贷方(计提) - 借方(使用)
 *   M3库存股（借方备抵）：  期末 = 期初 + 借方(回购) - 贷方(注销)
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
} from '../composables/useM7FormulaEngine'
import {
  calcAccrualByOutput,
  calcAccrualByRevenue,
  calcAccrualDiff,
} from '../composables/useM7AccrualEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// Part 1: useM7FormulaEngine 单元测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('useM7FormulaEngine — calcAuditedAmount (P1)', () => {
  it('审定数 = 未审 + AJE + RJE：100万+5万-2万=103万', () => {
    expect(calcAuditedAmount(1_000_000, 50_000, -20_000)).toBe(1_030_000)
  })

  it('全零输入：0+0+0=0', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('负数未审数场景', () => {
    expect(calcAuditedAmount(-500_000, 100_000, 50_000)).toBe(-350_000)
  })

  it('只有AJE调增', () => {
    expect(calcAuditedAmount(2_000_000, 200_000, 0)).toBe(2_200_000)
  })

  it('只有RJE重分类', () => {
    expect(calcAuditedAmount(2_000_000, 0, -500_000)).toBe(1_500_000)
  })

  // safe helper 边界
  it('NaN作为输入被视为0', () => {
    expect(calcAuditedAmount(NaN, 100, 200)).toBe(300)
  })

  it('null作为输入被视为0', () => {
    expect(calcAuditedAmount(null as unknown as number, 100, 200)).toBe(300)
  })

  it('undefined作为输入被视为0', () => {
    expect(calcAuditedAmount(undefined as unknown as number, 500, 300)).toBe(800)
  })

  it('Infinity被视为0', () => {
    expect(calcAuditedAmount(Infinity, 100, 200)).toBe(300)
  })

  it('多个非法值均归零', () => {
    expect(calcAuditedAmount(NaN, null as unknown as number, undefined as unknown as number)).toBe(0)
  })
})

describe('useM7FormulaEngine — calcEquityEndBalance (P2)', () => {
  it('权益类贷方：期末 = 期初+贷方(计提)-借方(使用)', () => {
    // 期初500万 + 贷方(计提)300万 - 借方(使用)100万 = 700万
    expect(calcEquityEndBalance(5_000_000, 3_000_000, 1_000_000)).toBe(7_000_000)
  })

  it('全零：0+0-0=0', () => {
    expect(calcEquityEndBalance(0, 0, 0)).toBe(0)
  })

  it('仅有计提（贷方增加），无使用', () => {
    expect(calcEquityEndBalance(1_000_000, 500_000, 0)).toBe(1_500_000)
  })

  it('仅有使用（借方减少），无计提', () => {
    expect(calcEquityEndBalance(2_000_000, 0, 800_000)).toBe(1_200_000)
  })

  it('使用大于期初+计提，期末为负（公式数学正确）', () => {
    // 100万 + 50万 - 300万 = -150万
    expect(calcEquityEndBalance(1_000_000, 500_000, 3_000_000)).toBe(-1_500_000)
  })

  it('大数值不溢出：10亿级计算', () => {
    expect(calcEquityEndBalance(1_000_000_000, 500_000_000, 200_000_000)).toBe(1_300_000_000)
  })

  it('期初为0、仅贷方计提', () => {
    expect(calcEquityEndBalance(0, 10_000_000, 0)).toBe(10_000_000)
  })

  // 验证权益类方向（与资产类相反！）
  it('权益类方向验证：cr增加而非dr增加', () => {
    const begin = 1_000_000
    const credit = 200_000  // 计提增加
    const debit = 100_000   // 使用减少
    const result = calcEquityEndBalance(begin, credit, debit)
    // 权益类：期末=期初+贷-借
    expect(result).toBe(1_100_000)
    // 反证：如果错用资产类方向(期初+借-贷)结果不同
    const wrongAssetDirection = begin + debit - credit
    expect(result).not.toBe(wrongAssetDirection)
  })

  // safe helper 边界
  it('NaN参数被safe转为0', () => {
    expect(calcEquityEndBalance(NaN, 500, 200)).toBe(300)
  })

  it('null参数被safe转为0', () => {
    expect(calcEquityEndBalance(1000, null as unknown as number, 200)).toBe(800)
  })

  it('undefined参数被safe转为0', () => {
    expect(calcEquityEndBalance(1000, 500, undefined as unknown as number)).toBe(1500)
  })
})

describe('useM7FormulaEngine — calcSubtotal (P6)', () => {
  it('空数组返回0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('单元素返回自身', () => {
    expect(calcSubtotal([7_777_000])).toBe(7_777_000)
  })

  it('多元素求和', () => {
    expect(calcSubtotal([1_000_000, 2_000_000, 3_000_000, 500_000])).toBe(6_500_000)
  })

  it('含负数正确求和', () => {
    expect(calcSubtotal([1_000, -500, 200])).toBe(700)
  })

  it('NaN值被过滤为0', () => {
    expect(calcSubtotal([100, NaN, 200])).toBe(300)
  })

  it('含null/undefined被过滤为0', () => {
    expect(calcSubtotal([100, null as unknown as number, undefined as unknown as number, 200])).toBe(300)
  })

  it('非数组输入返回0', () => {
    expect(calcSubtotal(null as unknown as number[])).toBe(0)
    expect(calcSubtotal(undefined as unknown as number[])).toBe(0)
  })

  it('全NaN数组返回0', () => {
    expect(calcSubtotal([NaN, NaN, NaN])).toBe(0)
  })

  it('大数组（20个元素）正确求和', () => {
    const arr = Array.from({ length: 20 }, (_, i) => (i + 1) * 10_000)
    // sum = 10000*(1+2+...+20) = 10000*210 = 2_100_000
    expect(calcSubtotal(arr)).toBe(2_100_000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Part 2: useM7AccrualEngine 单元测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('useM7AccrualEngine — calcAccrualByOutput (P3)', () => {
  it('空tiers返回0', () => {
    expect(calcAccrualByOutput([])).toBe(0)
  })

  it('单档计提：100万吨×5元/吨=500万', () => {
    expect(calcAccrualByOutput([{ output: 1_000_000, rate: 5 }])).toBe(5_000_000)
  })

  it('多档分档计提：煤矿按产量分档', () => {
    // 第1档：≤100万吨部分 5元/吨 → 100万×5=500万
    // 第2档：>100万吨部分 4元/吨 → 50万×4=200万
    const tiers = [
      { output: 1_000_000, rate: 5 },
      { output: 500_000, rate: 4 },
    ]
    expect(calcAccrualByOutput(tiers)).toBe(7_000_000)
  })

  it('三档计提', () => {
    const tiers = [
      { output: 500_000, rate: 6 },   // 300万
      { output: 300_000, rate: 5 },   // 150万
      { output: 200_000, rate: 4 },   // 80万
    ]
    // 500000*6 + 300000*5 + 200000*4 = 3000000 + 1500000 + 800000 = 5300000
    expect(calcAccrualByOutput(tiers)).toBe(5_300_000)
  })

  it('某档output=0时该档贡献为0', () => {
    const tiers = [
      { output: 1_000_000, rate: 5 },
      { output: 0, rate: 4 },          // 零产量档
    ]
    expect(calcAccrualByOutput(tiers)).toBe(5_000_000)
  })

  it('某档rate=0时该档贡献为0', () => {
    const tiers = [
      { output: 1_000_000, rate: 0 },  // 零标准
      { output: 500_000, rate: 4 },
    ]
    expect(calcAccrualByOutput(tiers)).toBe(2_000_000)
  })

  it('非数组输入返回0', () => {
    expect(calcAccrualByOutput(null as unknown as { output: number; rate: number }[])).toBe(0)
    expect(calcAccrualByOutput(undefined as unknown as { output: number; rate: number }[])).toBe(0)
  })

  it('tier中含NaN/null被safe处理为0', () => {
    const tiers = [
      { output: NaN, rate: 5 },
      { output: 1000, rate: null as unknown as number },
    ]
    // NaN*5=0, 1000*null=0
    expect(calcAccrualByOutput(tiers)).toBe(0)
  })
})

describe('useM7AccrualEngine — calcAccrualByRevenue (P4)', () => {
  it('基本计算：营业收入1亿×1.5%=150万', () => {
    expect(calcAccrualByRevenue(100_000_000, 0.015)).toBe(1_500_000)
  })

  it('零收入：0×1.5%=0', () => {
    expect(calcAccrualByRevenue(0, 0.015)).toBe(0)
  })

  it('零比例：1亿×0=0', () => {
    expect(calcAccrualByRevenue(100_000_000, 0)).toBe(0)
  })

  it('建筑施工企业：造价5000万×2%=100万', () => {
    expect(calcAccrualByRevenue(50_000_000, 0.02)).toBe(1_000_000)
  })

  it('小规模：收入100万×1%=1万', () => {
    expect(calcAccrualByRevenue(1_000_000, 0.01)).toBe(10_000)
  })

  it('NaN收入被视为0', () => {
    expect(calcAccrualByRevenue(NaN, 0.02)).toBe(0)
  })

  it('NaN比例被视为0', () => {
    expect(calcAccrualByRevenue(100_000_000, NaN)).toBe(0)
  })

  it('null/undefined参数被视为0', () => {
    expect(calcAccrualByRevenue(null as unknown as number, 0.02)).toBe(0)
    expect(calcAccrualByRevenue(100_000_000, undefined as unknown as number)).toBe(0)
  })
})

describe('useM7AccrualEngine — calcAccrualDiff (P5)', () => {
  it('正差（少计提=应补提）：应计150万-账面100万=+50万', () => {
    const diff = calcAccrualDiff(1_500_000, 1_000_000)
    expect(diff).toBe(500_000)
    // 正差=少提=审计风险点
    expect(diff).toBeGreaterThan(0)
  })

  it('负差（多计提=需冲回）：应计100万-账面150万=-50万', () => {
    const diff = calcAccrualDiff(1_000_000, 1_500_000)
    expect(diff).toBe(-500_000)
    // 负差=多提
    expect(diff).toBeLessThan(0)
  })

  it('零差异：应计=账面', () => {
    expect(calcAccrualDiff(2_000_000, 2_000_000)).toBe(0)
  })

  it('方向验证：estimated-booked（正=应补提）', () => {
    const estimated = 500_000
    const booked = 300_000
    const diff = calcAccrualDiff(estimated, booked)
    // 设计方向：est-booked，正差=少提=需关注
    expect(diff).toBe(estimated - booked)
    expect(diff).toBe(200_000)
  })

  it('全零场景', () => {
    expect(calcAccrualDiff(0, 0)).toBe(0)
  })

  it('NaN estimated被视为0', () => {
    expect(calcAccrualDiff(NaN, 100_000)).toBe(-100_000)
  })

  it('NaN booked被视为0', () => {
    expect(calcAccrualDiff(500_000, NaN)).toBe(500_000)
  })

  it('null/undefined参数被视为0', () => {
    expect(calcAccrualDiff(null as unknown as number, 100_000)).toBe(-100_000)
    expect(calcAccrualDiff(200_000, undefined as unknown as number)).toBe(200_000)
  })
})
