import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcQuantityDiff,
  calcFairValueDiff,
  calcMarketValueDiff,
  calcDisposalGain,
  calcDividendDiff,
  hasDifference,
} from '../useG0FormulaEngine'

// 浮点容差：公式引擎对部分函数做了 2 位小数四舍五入（误差 ≤ 0.005），
// 加/减法在 double 下的舍入误差远小于此，统一用 0.01 容差避免假失败。
const TOL = 1e-2
const approxEqual = (a: number, b: number, tol = TOL) => Math.abs(a - b) <= tol

describe('useG0FormulaEngine (PBT)', () => {
  // 🔴🔴 Property 1~3 的方向已由「回函 − 账面」改为「**账面 − 回函**」
  //
  // spec: g0-confirmation-source-alignment，Task 20（Requirement 10.2 / Property 27）
  //
  // 原断言是**测试镜像 bug**：它逐字镜像了归档 spec `g0-confirmation` 需求 2.5/2.6/2.7
  // 的「回函 − 账面」，而那三条本身照抄了源模板 `M7=J7-G7` 的**缺陷方向**。源模板事实：
  //   · `函证差异核对表G0-3（证券投资）!K5` 表头逐字 `差异③=①-②`
  //     （`B5=账面结存证券投资①` / `H5=证券投资回函②`）
  //   · 同组 `K7=E7-H7`（数量）、`L7=F7-I7`（单价）→ 账面 − 回函 ✓
  //   · `M7=J7-G7`（公允价值）→ 回函 − 账面 ✗ = 源模板唯一反向者
  //   · 姊妹表 `函证差异核对表G0-4(非证券投资)` 的 `I7=C7-F7`、`J7=D7-G7` 亦为账面 − 回函
  // 后续归档 spec `g0-investment-diff-model` 已定「数值维度差异 = 账面 − 回函（符号与口径固定）」
  // 但只在非证券表落地 → 证券表是未修遗留，纠正前两张差异表方向互相矛盾。
  //
  // 形参顺序随之改为 `(booked, reply)`（账面在前，与源模板列序 ①② 一致）。

  // --- Property 1: 数量差异 = 账面数量 − 回函数量（源 K=E−H）---
  // Validates: Requirements 10.1, 10.2
  it('Property 1: calcQuantityDiff(booked, reply) === booked - reply', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: -1_000_000, max: 1_000_000 }),
        fc.integer({ min: -1_000_000, max: 1_000_000 }),
        (booked, reply) => {
          // 整数运算无浮点误差，严格相等
          expect(calcQuantityDiff(booked, reply)).toBe(booked - reply)
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- Property 2: 市价（单价）差异 = 账面单价 − 回函单价（源 L=F−I）---
  // Validates: Requirements 10.1, 10.2
  it('Property 2: calcFairValueDiff(bookedFV, replyFV) ≈ bookedFV - replyFV', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e8, max: 1e8, noNaN: true }),
        fc.float({ min: -1e8, max: 1e8, noNaN: true }),
        (bookedFV, replyFV) => {
          expect(approxEqual(calcFairValueDiff(bookedFV, replyFV), bookedFV - replyFV)).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- Property 3: 公允价值差异 = 账面余额 − 回函公允价值（源 M 方向写反，按表头意图统一）---
  // Validates: Requirements 10.1, 10.2
  it('Property 3: calcMarketValueDiff(bookedMV, replyMV) ≈ bookedMV - replyMV', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (bookedMV, replyMV) => {
          expect(approxEqual(calcMarketValueDiff(bookedMV, replyMV), bookedMV - replyMV)).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- Property 3b（反向自检）：三列方向必须同向，且不得退回「回函 − 账面」---
  // 若有人把任一函数改回旧方向，本用例立即打红并点名源模板依据。
  // Validates: Requirements 10.2, 10.4
  it('Property 3b: 三列同向且方向为「账面 − 回函」（回退旧方向即打红）', () => {
    // 账面 > 回函 → 三个差异都应为正
    expect(calcQuantityDiff(10_000, 9_800)).toBe(200)
    expect(calcFairValueDiff(12.5, 12.0)).toBeCloseTo(0.5, 6)
    expect(calcMarketValueDiff(125_000, 117_600)).toBeCloseTo(7_400, 6)

    // 旧方向（回函 − 账面）会得到负值 → 显式排除
    expect(calcQuantityDiff(9_800, 10_000)).toBeLessThan(0)
    expect(calcMarketValueDiff(117_600, 125_000)).toBeLessThan(0)

    // 与非证券表同源：`useG0DiffNonSecurities.recalcRow` 亦为 booked − reply
    const bookedFirstSigns = [
      Math.sign(calcQuantityDiff(2, 1)),
      Math.sign(calcFairValueDiff(2, 1)),
      Math.sign(calcMarketValueDiff(2, 1)),
    ]
    expect(bookedFirstSigns).toEqual([1, 1, 1])
  })

  // --- 2.5 Property 4: 处置损益 = 成交 - 成本 - 手续费 ---
  // Validates: Requirements 3.13, 7.4
  it('Property 4: calcDisposalGain(proceeds, cost, fee) ≈ proceeds - cost - fee', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e8, noNaN: true }),
        fc.float({ min: 0, max: 1e8, noNaN: true }),
        fc.float({ min: 0, max: 1e8, noNaN: true }),
        (proceeds, cost, fee) => {
          // fee ≥ 0，不触发 fee<0→0 的钳制；引擎做 2 位四舍五入，用容差比较
          expect(approxEqual(calcDisposalGain(proceeds, cost, fee), proceeds - cost - fee)).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- 2.6 Property 5: 股利差异 = 应收 - 实收 - 税 ---
  // Validates: Requirements 7.5
  it('Property 5: calcDividendDiff(declared, received, tax) ≈ declared - received - tax', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e7, noNaN: true }),
        fc.float({ min: 0, max: 1e7, noNaN: true }),
        fc.float({ min: 0, max: 1e7, noNaN: true }),
        (declared, received, tax) => {
          expect(approxEqual(calcDividendDiff(declared, received, tax), declared - received - tax)).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- 2.7 Property 6: 差异判定定义一致性 ---
  // hasDifference 两参数语义不同（数量差异 vs 公允价值差异），阈值非对称
  // （|qty|>0 OR |fv|>0.01），故验证其与真实定义式一致，而非对称性。
  // Validates: Requirements 7.6
  it('Property 6: hasDifference(qtyDiff, fvDiff) === (|qtyDiff|>0 || |fvDiff|>0.01)', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e8, max: 1e8, noNaN: true }),
        fc.float({ min: -1e8, max: 1e8, noNaN: true }),
        (qtyDiff, fvDiff) => {
          expect(hasDifference(qtyDiff, fvDiff)).toBe(
            Math.abs(qtyDiff) > 0 || Math.abs(fvDiff) > 0.01,
          )
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- 2.8 Property 7: 零差异恒等（自身与自身差异 = 0）---
  // Validates: Requirements 7.1~7.3
  it('Property 7: calcQuantityDiff(v,v)=0 ∧ calcFairValueDiff(v,v)=0 ∧ calcMarketValueDiff(v,v)=0', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e8, max: 1e8, noNaN: true }),
        (v) => {
          expect(calcQuantityDiff(v, v)).toBe(0)
          expect(calcFairValueDiff(v, v)).toBe(0)
          expect(calcMarketValueDiff(v, v)).toBe(0)
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- 2.9 Property 8: 处置损益与手续费反比（手续费越高 → 处置损益越低）---
  // Validates: Requirements 7.4
  it('Property 8: calcDisposalGain(p, c, fee1) < calcDisposalGain(p, c, fee2) when fee1 > fee2 >= 0', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e8, noNaN: true }),
        fc.float({ min: 0, max: 1e8, noNaN: true }),
        fc.float({ min: 0, max: 1e8, noNaN: true }),
        fc.float({ min: 1, max: 1e6, noNaN: true }),
        (proceeds, cost, fee2, delta) => {
          // fee1 = fee2 + delta，delta ≥ 1 保证四舍五入后严格更高的手续费产出更低的损益
          const fee1 = fee2 + delta
          expect(calcDisposalGain(proceeds, cost, fee1)).toBeLessThan(
            calcDisposalGain(proceeds, cost, fee2),
          )
        },
      ),
      { numRuns: 200 },
    )
  })
})
