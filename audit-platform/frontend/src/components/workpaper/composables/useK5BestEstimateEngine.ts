/**
 * K5 预计负债 — 最佳估计数引擎（纯函数）
 *
 * CAS13 最佳估计数计量方法：
 *   单一事项：最佳估计数 = 最可能发生金额（由调用方直接取值）
 *   连续区间：最佳估计数 = (上限 + 下限) / 2
 *   多情形：  最佳估计数 = Σ(各情形金额 × 概率)  期望值加权
 *   时间价值重大：按现值折现
 *
 * 设计原则：纯函数，无Vue响应式，无副作用，可PBT验证
 * 所有函数对 NaN / undefined 输入视为 0 处理
 *
 * Spec: .kiro/specs/k5-provisions/ Requirements 5.1-5.4, 6.2, 7.2-7.3, 10.4-10.7
 */

// ─── Helpers ────────────────────────────────────────────────────────────────

/** 将 NaN / undefined / null 转为 0 */
function safeNum(v: unknown): number {
  if (v === null || v === undefined) return 0
  const n = Number(v)
  return Number.isNaN(n) ? 0 : n
}

// ─── 计量函数 ───────────────────────────────────────────────────────────────

/**
 * 区间中值 = (上限 + 下限) / 2
 *
 * 当最佳估计数在一个连续范围内各种可能结果
 * 发生概率相同时，取中间值作为最佳估计数
 *
 * @param upper 区间上限
 * @param lower 区间下限
 * @returns 区间中值
 *
 * Requirements 5.2, 10.4
 */
export function calcRangeMidpoint(upper: number, lower: number): number {
  return (safeNum(upper) + safeNum(lower)) / 2
}

/**
 * 期望值 = Σ(各情形金额 × 概率)
 *
 * 当涉及多个项目或多种可能结果时，
 * 按各种可能结果及相关概率加权计算确定最佳估计数
 *
 * 错误处理：
 * - amounts 和 probs 长度不一致 → 返回 0
 * - 空数组 → 返回 0
 *
 * @param amounts 各情形金额数组
 * @param probs 各情形概率数组（小数形式，如 0.3 表示 30%）
 * @returns 期望值
 *
 * Requirements 5.3, 10.5
 */
export function calcExpectedValue(amounts: number[], probs: number[]): number {
  if (!amounts || !probs || amounts.length === 0 || probs.length === 0) return 0
  if (amounts.length !== probs.length) return 0
  let sum = 0
  for (let i = 0; i < amounts.length; i++) {
    sum += safeNum(amounts[i]) * safeNum(probs[i])
  }
  return sum
}

/**
 * 保修支出 = 销售收入 × 历史保修率
 *
 * 产品质量保修测算：根据销售收入和历史保修率计算预计保修支出
 *
 * @param revenue 销售收入
 * @param rate 历史保修率（小数形式，如 0.02 表示 2%）
 * @returns 预计保修支出
 *
 * Requirements 6.2, 10.6
 */
export function calcWarrantyProvision(revenue: number, rate: number): number {
  return safeNum(revenue) * safeNum(rate)
}

/**
 * 现值 = future / (1 + rate) ^ years
 *
 * 弃置费用等涉及时间价值重大的预计负债，按现值折现
 *
 * 错误处理（兜底）：
 * - rate <= 0 → 返回 future（不折现）
 * - years <= 0 → 返回 future（不折现）
 *
 * @param future 未来金额（预计弃置支出）
 * @param rate 折现率（小数形式，如 0.05 表示 5%）
 * @param years 折现年数
 * @returns 现值
 *
 * Requirements 7.2, 7.3, 10.7
 */
export function calcPresentValue(future: number, rate: number, years: number): number {
  const f = safeNum(future)
  const r = safeNum(rate)
  const y = safeNum(years)
  if (r <= 0 || y <= 0) return f
  return f / Math.pow(1 + r, y)
}
