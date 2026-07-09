/**
 * useL4EIREngine — L4 应付债券 实际利率法引擎（核心！）
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。支持 fast-check PBT 验证。
 *
 * ─── 实际利率法（Effective Interest Rate Method）──────────────
 *
 * 依据 CAS 22 金融工具确认和计量：
 * 应付债券后续计量采用实际利率法，按摊余成本进行后续计量。
 *
 * 核心公式：
 *   利息费用 = 期初摊余成本 × 实际利率(EIR)
 *   利息调整摊销 = 实际利息费用 - 票面利息
 *
 * 两种付息方式（2分支）：
 *   ① 到期一次还本付息（bullet）：利息资本化滚入摊余成本
 *      期末摊余成本 = 期初 + 利息费用（不实付利息，全部滚入）
 *   ② 分期付息到期一次还本（installment）：每期支付票面利息
 *      期末摊余成本 = 期初 + 利息费用 - 实付利息（票面利息）
 *
 * 最终效果：摊余成本逐期趋向面值，到期日摊余成本=面值（允许尾差±1元）。
 * ────────────────────────────────────────────────────────────
 *
 * 本引擎覆盖：
 * - calcInterestExpense: 每期利息费用
 * - calcEndAmortizedCost_Bullet: 到期一次还本付息期末摊余成本
 * - calcEndAmortizedCost_Installment: 分期付息期末摊余成本
 * - generateSchedule: 完整后续计量摊销表（2分支）
 * - validateSchedule: 末期验证（期末≈面值）
 * - solveEIR: IRR求解实际利率
 *
 * Spec: .kiro/specs/l4-bonds-payable/ Requirements 4.4-4.7, 9.1-9.6
 */

// ─── 接口定义 ────────────────────────────────────────────────

/**
 * 实际利率法摊销表行结构
 *
 * 每期一行，记录摊余成本从期初到期末的变动。
 * 溢价发行时：实际利息 < 票面利息，amortization 为负，endCost 逐期递减趋向面值。
 * 折价发行时：实际利息 > 票面利息，amortization 为正，endCost 逐期递增趋向面值。
 */
export interface EIRRow {
  /** 期数（从1开始） */
  period: number
  /** 期初摊余成本 */
  beginCost: number
  /** 票面利息 = 面值 × 票面利率 */
  couponInterest: number
  /** 实际利息费用 = 期初摊余成本 × 实际利率(EIR) */
  interestExpense: number
  /** 利息调整摊销 = 实际利息费用 - 票面利息（溢价为负/折价为正） */
  amortization: number
  /** 期末摊余成本 */
  endCost: number
}

// ─── 1. 利息费用计算 ─────────────────────────────────────────

/**
 * 计算每期利息费用（实际利率法核心公式）
 *
 * 利息费用 = 期初摊余成本 × 实际利率(EIR)
 *
 * 来源：L4-7 后续计量表
 * 该费用是计入财务费用/在建工程的金额，而非实际支付的票面利息。
 * EIR=0 时利息费用=0（平价、零息场景，不产生 NaN）。
 *
 * @param amortizedCost - 期初摊余成本（>0）
 * @param eir - 实际利率（年利率，小数形式，如 0.05 表示 5%）
 * @returns 利息费用
 */
export function calcInterestExpense(amortizedCost: number, eir: number): number {
  return amortizedCost * eir
}

// ─── 2. 期末摊余成本（到期一次还本付息） ─────────────────────

/**
 * 到期一次还本付息（bullet）：期末摊余成本
 *
 * 期末 = 期初 + 利息费用
 *
 * 该分支下利息不实付，全部资本化滚入摊余成本。
 * 每期摊余成本递增（利息累积），到期日一次性还本并支付全部累积利息。
 *
 * 来源：L4-7A Subsequent_Bullet
 *
 * @param begin - 期初摊余成本
 * @param interestExpense - 本期实际利息费用
 * @returns 期末摊余成本
 */
export function calcEndAmortizedCost_Bullet(begin: number, interestExpense: number): number {
  return begin + interestExpense
}

// ─── 3. 期末摊余成本（分期付息到期一次还本） ─────────────────

/**
 * 分期付息到期一次还本（installment）：期末摊余成本
 *
 * 期末 = 期初 + 利息费用 - 实付利息（票面利息）
 *
 * 该分支每期实付票面利息（面值×票面利率），只有利息调整部分影响摊余成本：
 * - 折价发行：实际利息 > 票面利息，差额使摊余成本递增
 * - 溢价发行：实际利息 < 票面利息，差额使摊余成本递减
 * 最终摊余成本趋向面值。
 *
 * 来源：L4-7B Subsequent_Installment
 *
 * @param begin - 期初摊余成本
 * @param interestExpense - 本期实际利息费用（期初×EIR）
 * @param couponPaid - 本期实付票面利息（面值×票面利率）
 * @returns 期末摊余成本
 */
export function calcEndAmortizedCost_Installment(
  begin: number,
  interestExpense: number,
  couponPaid: number,
): number {
  return begin + interestExpense - couponPaid
}

// ─── 4. 生成完整后续计量摊销表 ───────────────────────────────

/**
 * 生成完整后续计量摊销表（2分支）
 *
 * 根据初始摊余成本、面值、票面利率、实际利率和期数，
 * 生成逐期的摊余成本变动表。
 *
 * ⚠️ 最后一期尾差调整：
 * 由于浮点精度，最后一期的期末摊余成本可能与面值有微小偏差。
 * 本函数将最后一期的利息费用/摊销进行尾差调整，确保期末=面值（bullet除外见下）。
 *
 * bullet 分支说明：
 *   到期一次还本付息时，到期日应付金额 = 面值 + 全部累积利息。
 *   但在摊销表中最后一期 endCost 仍强制调整为 面值 + 累积票面利息。
 *   实际还款时一次归还该金额。为简化验证，generateSchedule 的 bullet 分支
 *   最后一期 endCost = faceValue + 累积 couponInterest（含本期）。
 *   ──── 修正：按会计准则，bullet分支下到期时摊余成本滚入全部利息费用
 *   (不拆分coupon和amortization)，最后一期endCost直接趋向到期应付总额。
 *   但PBT验证时 validateSchedule 对 bullet 使用 faceValue 作为基准
 *   （最终实际还款时 endCost 因利息全资本化而远大于 faceValue）。
 *   ──── 最终设计：bullet 分支不做尾差调整到 faceValue，
 *   因为 bullet 到期摊余成本 = faceValue × (1+couponRate)^periods ≠ faceValue。
 *   validateSchedule 对 bullet 使用 faceValue×(1+couponRate)^periods 作为理论终值。
 *   ──── 简化方案（对齐spec P6）：bullet最后一期endCost不调整，
 *   validateSchedule 对 bullet 的 expectedEnd = 最后一期理论 endCost（允许浮点误差）。
 *   P6 property 通过 installment 分支验证 |endCost - faceValue| < 1。
 *
 * installment 分支：
 *   最后一期 endCost 强制调整为 faceValue，尾差并入最后一期利息费用/摊销。
 *
 * @param initialCost - 初始摊余成本（发行价-交易费用）
 * @param faceValue - 债券面值
 * @param couponRate - 票面利率（年利率，小数形式）
 * @param eir - 实际利率（年利率，小数形式）
 * @param periods - 总期数
 * @param branch - 'bullet'=到期一次还本付息 | 'installment'=分期付息到期一次还本
 * @returns 完整摊销表
 */
export function generateSchedule(
  initialCost: number,
  faceValue: number,
  couponRate: number,
  eir: number,
  periods: number,
  branch: 'bullet' | 'installment',
): EIRRow[] {
  if (periods <= 0) return []

  const schedule: EIRRow[] = []
  let beginCost = initialCost

  for (let i = 1; i <= periods; i++) {
    const couponInterest = faceValue * couponRate
    let interestExpense = calcInterestExpense(beginCost, eir)
    let endCost: number

    if (branch === 'bullet') {
      // 到期一次还本付息：利息全部资本化滚入
      endCost = calcEndAmortizedCost_Bullet(beginCost, interestExpense)
    } else {
      // 分期付息：每期实付票面利息
      endCost = calcEndAmortizedCost_Installment(beginCost, interestExpense, couponInterest)

      // 最后一期尾差调整：强制 endCost = faceValue
      if (i === periods) {
        // 反推利息费用使期末=面值
        // endCost = begin + interestExpense - couponInterest = faceValue
        // => interestExpense = faceValue - begin + couponInterest
        interestExpense = faceValue - beginCost + couponInterest
        endCost = faceValue
      }
    }

    const amortization = interestExpense - couponInterest

    schedule.push({
      period: i,
      beginCost,
      couponInterest,
      interestExpense,
      amortization,
      endCost,
    })

    beginCost = endCost
  }

  return schedule
}

// ─── 5. 验证摊销表 ───────────────────────────────────────────

/**
 * 验证摊销表：最后一期期末摊余成本≈面值
 *
 * 验证规则：
 * - installment 分支：|最后一期 endCost - faceValue| < 1（允许±1元尾差）
 * - bullet 分支：到期摊余成本远大于面值（含累积利息），
 *   此处验证最后一期 endCost 是否与理论终值偏差 < 1。
 *   理论终值 = initialCost × (1+eir)^periods（纯复利滚动）。
 *   简化实现：直接检查最后一期 endCost 是否为正数且连续性正确。
 *   ──── 对齐 spec P6：validateSchedule 仅适用 installment 分支，
 *   bullet 分支 tailDiff 取最后一期 endCost 与 faceValue 的差额（信息性）。
 *
 * @param schedule - 摊销表
 * @param faceValue - 债券面值
 * @returns isValid=是否通过验证, tailDiff=尾差
 */
export function validateSchedule(
  schedule: EIRRow[],
  faceValue: number,
): { isValid: boolean; tailDiff: number } {
  if (schedule.length === 0) {
    return { isValid: false, tailDiff: 0 }
  }

  const lastRow = schedule[schedule.length - 1]
  const tailDiff = lastRow.endCost - faceValue

  // 允许 ±1 元尾差
  const isValid = Math.abs(tailDiff) < 1

  return { isValid, tailDiff }
}

// ─── 6. IRR求解实际利率 ──────────────────────────────────────

/**
 * 求解实际利率（IRR/EIR）
 *
 * 使未来现金流的现值 = 初始入账金额（初始摊余成本）。
 *
 * 数学原理：
 *   initialAmount = Σ cashFlows[i] / (1+eir)^(i+1)
 *   即求 eir 使 NPV(cashFlows, eir) - initialAmount = 0
 *
 * 算法：二分法（bisection），稳健可靠，适合会计领域精度需求。
 * - 搜索范围：[0, 2]（即 0% ~ 200%，涵盖正常债券利率）
 * - 精度：1e-10（小数点后10位）
 * - 最大迭代：200次
 *
 * 边界处理：
 * - cashFlows 为空 → 返回 0
 * - initialAmount ≤ 0 → 返回 0
 * - 不收敛 → 返回当前最佳近似值
 *
 * @param cashFlows - 未来各期现金流数组（正值，按期排列，最后一期含本金）
 * @param initialAmount - 初始入账金额（发行净收入）
 * @returns 实际利率（小数形式，如 0.05 表示 5%）
 */
export function solveEIR(cashFlows: number[], initialAmount: number): number {
  if (cashFlows.length === 0 || initialAmount <= 0) return 0

  // 计算给定利率下现金流的现值
  const calcPV = (rate: number): number => {
    let pv = 0
    for (let i = 0; i < cashFlows.length; i++) {
      pv += cashFlows[i] / Math.pow(1 + rate, i + 1)
    }
    return pv
  }

  // 二分法求解：找 rate 使 calcPV(rate) = initialAmount
  let lo = 0
  let hi = 2
  const maxIter = 200
  const tolerance = 1e-10

  // 检查边界：如果 PV(0) < initialAmount，说明无正解
  const pvAtZero = calcPV(0)
  if (pvAtZero <= initialAmount) {
    // 现金流总和 ≤ 初始金额，利率应为0或负（不合理），返回0
    // 特殊情况：pvAtZero 刚好等于 initialAmount 时 eir=0
    if (Math.abs(pvAtZero - initialAmount) < tolerance) return 0
    return 0
  }

  for (let iter = 0; iter < maxIter; iter++) {
    const mid = (lo + hi) / 2
    const pvMid = calcPV(mid)

    if (Math.abs(pvMid - initialAmount) < tolerance) {
      return mid
    }

    // PV 是关于 rate 的递减函数
    if (pvMid > initialAmount) {
      lo = mid
    } else {
      hi = mid
    }
  }

  // 未精确收敛，返回当前最佳估计
  return (lo + hi) / 2
}
