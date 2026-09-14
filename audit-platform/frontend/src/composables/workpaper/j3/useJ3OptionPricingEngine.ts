/**
 * useJ3OptionPricingEngine — J3 股份支付 Black-Scholes 期权定价纯函数引擎
 *
 * 核心公式（Black-Scholes-Merton 1973）：
 *   C = S₀·N(d₁) - K·e^(-rT)·N(d₂)
 *   d₁ = [ln(S/K) + (r + σ²/2)·T] / (σ·√T)
 *   d₂ = d₁ - σ·√T
 *
 * 其中：
 *   S = 标的股票价格（当前市价）
 *   K = 行权价格（执行价格）
 *   T = 到期时间（年）
 *   r = 无风险利率（连续复利）
 *   σ = 波动率（年化标准差）
 *   N(x) = 标准正态分布累积分布函数
 *
 * 所有函数为纯函数，无副作用，便于 PBT 验证数学正确性。
 *
 * Spec: .kiro/specs/j3-share-based-payment/
 * Requirements: 3.1-3.6
 */

// ─── 类型定义 ─────────────────────────────────────────────────────────────────

export interface BSParams {
  S: number      // 标的价格 > 0
  K: number      // 行权价 > 0
  T: number      // 到期时间(年) > 0
  r: number      // 无风险利率 (如 0.05 表示 5%)
  sigma: number  // 波动率 (如 0.3 表示 30%)
}

export interface BSValidation {
  isValid: boolean
  warnings: string[]
}

// ─── 标准正态分布累积分布函数 ──────────────────────────────────────────────────

/**
 * 标准正态分布累积分布函数 N(x)
 *
 * 使用 Abramowitz & Stegun 近似公式（误差 < 7.5e-8）。
 * 适用于 Black-Scholes 模型精度要求。
 *
 * @param x 标准正态分布变量值
 * @returns P(Z ≤ x)，范围 [0, 1]
 */
export function normalCDF(x: number): number {
  // 常量（Abramowitz & Stegun 26.2.17）
  const a1 = 0.254829592
  const a2 = -0.284496736
  const a3 = 1.421413741
  const a4 = -1.453152027
  const a5 = 1.061405429
  const p = 0.3275911

  // 利用对称性处理负数
  const sign = x < 0 ? -1 : 1
  const absX = Math.abs(x)

  const t = 1.0 / (1.0 + p * absX)
  const y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-absX * absX / 2)

  return 0.5 * (1.0 + sign * y)
}

// ─── d1 计算 ─────────────────────────────────────────────────────────────────

/**
 * 计算 d₁ = [ln(S/K) + (r + σ²/2)·T] / (σ·√T)
 *
 * @param S 标的价格
 * @param K 行权价格
 * @param T 到期时间（年）
 * @param r 无风险利率
 * @param sigma 波动率
 * @returns d₁ 值
 */
export function calcD1(S: number, K: number, T: number, r: number, sigma: number): number {
  const numerator = Math.log(S / K) + (r + (sigma * sigma) / 2) * T
  const denominator = sigma * Math.sqrt(T)
  return numerator / denominator
}

// ─── d2 计算 ─────────────────────────────────────────────────────────────────

/**
 * 计算 d₂ = d₁ - σ·√T
 *
 * @param d1 已计算的 d₁ 值
 * @param sigma 波动率
 * @param T 到期时间（年）
 * @returns d₂ 值
 */
export function calcD2(d1: number, sigma: number, T: number): number {
  return d1 - sigma * Math.sqrt(T)
}

// ─── Black-Scholes 看涨期权定价 ──────────────────────────────────────────────

/**
 * Black-Scholes 看涨期权价格
 *   C = S·N(d₁) - K·e^(-rT)·N(d₂)
 *
 * @param S 标的价格 (> 0)
 * @param K 行权价格 (> 0)
 * @param T 到期时间（年）(> 0)
 * @param r 无风险利率
 * @param sigma 波动率 (> 0)
 * @returns 期权理论价格
 */
export function calcBlackScholes(S: number, K: number, T: number, r: number, sigma: number): number {
  const d1 = calcD1(S, K, T, r, sigma)
  const d2 = calcD2(d1, sigma, T)
  return S * normalCDF(d1) - K * Math.exp(-r * T) * normalCDF(d2)
}

// ─── 参数合理性校验 ──────────────────────────────────────────────────────────

/**
 * BS模型参数合理性校验
 *
 * 审计实务中需要关注参数是否在合理区间：
 * - 波动率 σ ∈ [10%, 100%]
 * - 无风险利率 r ∈ [1%, 10%]
 * - 到期时间 T > 0
 * - 标的价格/行权价 > 0
 *
 * @param params BS参数
 * @returns 校验结果（isValid + warnings数组）
 */
export function validateBSParams(params: BSParams): BSValidation {
  const warnings: string[] = []
  let isValid = true

  // 硬性约束（无法计算）
  if (params.S <= 0) {
    warnings.push('标的价格必须大于0')
    isValid = false
  }
  if (params.K <= 0) {
    warnings.push('行权价格必须大于0')
    isValid = false
  }
  if (params.T <= 0) {
    warnings.push('到期时间必须大于0')
    isValid = false
  }
  if (params.sigma <= 0) {
    warnings.push('波动率必须大于0')
    isValid = false
  }

  // 软性约束（审计关注）
  if (params.sigma > 0 && params.sigma < 0.10) {
    warnings.push('波动率低于10%，偏低（审计关注）')
  }
  if (params.sigma > 1.0) {
    warnings.push('波动率超过100%，偏高（审计关注）')
  }
  if (params.r < 0.01) {
    warnings.push('无风险利率低于1%（审计关注）')
  }
  if (params.r > 0.10) {
    warnings.push('无风险利率超过10%（审计关注）')
  }

  return { isValid, warnings }
}
