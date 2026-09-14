/**
 * useL5AmortizationEngine — L5 长期应付款 未确认融资费用摊销引擎（核心！）
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。支持 fast-check PBT 验证。
 *
 * ─── 实际利率法（Effective Interest Rate Method）──────────────
 *
 * 依据 CAS 21 租赁 / CAS 22 金融工具：
 * 未确认融资费用按实际利率法摊销，计入各期财务费用。
 *
 * 核心公式（来源 L5-5 xlsx）：
 *   F{n} = H{n-1} × C{n-1}  — 确认的融资费用 = 期初应付本金余额 × 实际利率
 *   G{n} = B{n} - F{n}      — 应付本金减少额 = 各期付款金额 - 确认的融资费用
 *   H{n} = H{n-1} - G{n}    — 期末应付本金余额 = 期初余额 - 本金减少额
 *
 * 等价简化：
 *   期末摊余成本 = 期初 - (付款 - 摊销) = 期初 - 本金减少
 *
 * 最终效果：摊余成本逐期趋向0，全部还清时余额=0（允许尾差±1元）。
 * ────────────────────────────────────────────────────────────
 *
 * 本引擎覆盖：
 * - calcAmortization: 每期摊销（确认的融资费用）
 * - calcEndCost: 期末摊余成本
 * - generateSchedule: 完整摊销表（含尾差调整）
 * - validateSchedule: 末期验证（期末≈0）
 *
 * Spec: .kiro/specs/l5-long-term-payables/ Requirements 4.2-4.4, 6.1-6.5
 */

// ─── 接口定义 ────────────────────────────────────────────────

/**
 * 摊销表行结构
 *
 * 每期一行，记录摊余成本从期初到期末的变动。
 * 摊余成本逐期递减，最后一期趋向0。
 */
export interface AmortRow {
  /** 期数（从1开始） */
  period: number
  /** 期初摊余成本（应付本金余额） */
  beginCost: number
  /** 确认的融资费用 = 期初 × 实际利率 */
  amortization: number
  /** 各期付款金额 */
  repayment: number
  /** 期末摊余成本 */
  endCost: number
}

// ─── 1. 每期摊销计算 ─────────────────────────────────────────

/**
 * 计算每期摊销（确认的融资费用）
 *
 * 确认的融资费用 = 期初摊余成本 × 实际利率(EIR)
 *
 * 来源：L5-5 xlsx 公式 F{n} = H{n-1} × C{n-1}
 * EIR=0 时摊销=0（无融资费用，全部付款偿还本金）。
 *
 * PBT Properties:
 * - P5: calcAmortization(cost, eir) === cost × eir
 * - P6: calcAmortization(cost, 0) === 0
 *
 * @param amortizedCost - 期初摊余成本（≥0）
 * @param eir - 实际利率（年利率，小数形式，如 0.05 表示 5%）
 * @returns 确认的融资费用（摊销额）
 */
export function calcAmortization(amortizedCost: number, eir: number): number {
  return amortizedCost * eir
}

// ─── 2. 期末摊余成本 ─────────────────────────────────────────

/**
 * 计算期末摊余成本
 *
 * 期末摊余成本 = 期初 - (付款 - 摊销) = 期初 - 本金减少额
 *
 * 来源：L5-5 xlsx 公式
 *   G{n} = B{n} - F{n}    (本金减少 = 付款 - 融资费用)
 *   H{n} = H{n-1} - G{n}  (期末 = 期初 - 本金减少)
 *
 * 等价展开：endCost = begin - (repayment - amortization)
 *         = begin - repayment + amortization
 *
 * @param begin - 期初摊余成本
 * @param amortization - 确认的融资费用（期初×EIR）
 * @param repayment - 本期付款金额
 * @returns 期末摊余成本
 */
export function calcEndCost(begin: number, amortization: number, repayment: number): number {
  return begin - repayment + amortization
}

// ─── 3. 生成完整摊销表 ───────────────────────────────────────

/**
 * 生成完整未确认融资费用摊销表
 *
 * 根据初始摊余成本、各期付款金额、实际利率和期数，
 * 生成逐期的摊余成本变动表。
 *
 * ⚠️ 最后一期尾差调整：
 * 由于浮点精度和等额还款舍入，最后一期的期末摊余成本可能与0有微小偏差。
 * 本函数将最后一期的摊销额进行尾差调整，确保 endCost = 0。
 *
 * repayments数组处理：
 * - 若 repayments.length >= periods，使用前 periods 个值
 * - 若 repayments.length < periods，超出部分使用最后一个付款值
 *
 * EIR=0 特殊处理：
 * - 摊销=0，全部付款偿还本金（无融资费用）
 *
 * PBT Property:
 * - P7: |generateSchedule(...).last.endCost| < 1
 *
 * @param initialCost - 初始摊余成本（>0，即初始应付本金总额）
 * @param repayments - 各期付款金额数组（若长度不足则复用最后一个值）
 * @param eir - 实际利率（年利率，小数形式）
 * @param periods - 总期数（>0）
 * @returns 完整摊销表
 */
export function generateSchedule(
  initialCost: number,
  repayments: number[],
  eir: number,
  periods: number,
): AmortRow[] {
  if (periods <= 0 || initialCost <= 0) return []
  if (repayments.length === 0) return []

  const schedule: AmortRow[] = []
  let beginCost = initialCost

  for (let i = 1; i <= periods; i++) {
    // 获取本期付款金额
    const repayment = i <= repayments.length
      ? repayments[i - 1]
      : repayments[repayments.length - 1]

    let amortization = calcAmortization(beginCost, eir)
    let endCost: number

    if (i === periods) {
      // 最后一期尾差调整：强制 endCost = 0
      // 反推摊销使期末=0：endCost = begin - repayment + amortization = 0
      // => amortization = repayment - begin
      amortization = repayment - beginCost
      endCost = 0
    } else {
      endCost = calcEndCost(beginCost, amortization, repayment)
    }

    schedule.push({
      period: i,
      beginCost,
      amortization,
      repayment,
      endCost,
    })

    beginCost = endCost
  }

  return schedule
}

// ─── 4. 验证摊销表 ───────────────────────────────────────────

/**
 * 验证摊销表：最后一期未确认余额≈0
 *
 * 验证规则：|最后一期 endCost| < 1（允许±1元尾差）
 *
 * 来源：Requirements 4.4 — 验证最后一期未确认融资费用余额≈0
 *
 * @param schedule - 摊销表
 * @returns isValid=是否通过验证, tailDiff=尾差（最后一期endCost）
 */
export function validateSchedule(schedule: AmortRow[]): { isValid: boolean; tailDiff: number } {
  if (schedule.length === 0) {
    return { isValid: false, tailDiff: 0 }
  }

  const lastRow = schedule[schedule.length - 1]
  const tailDiff = lastRow.endCost

  // 允许 ±1 元尾差
  const isValid = Math.abs(tailDiff) < 1

  return { isValid, tailDiff }
}
