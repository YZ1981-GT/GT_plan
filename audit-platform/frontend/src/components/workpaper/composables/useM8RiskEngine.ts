/**
 * useM8RiskEngine — M8 一般风险准备风险资产计提引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：4104 一般风险准备（贷方/权益类）
 *
 * ─── 风险资产计提测试 ───
 * 金融企业按风险资产期末余额的1.5%计提一般风险准备（最低标准）。
 * 来源：《金融企业准备金计提管理办法》（财金〔2012〕20号）第五条
 *
 * M8-4 测试表核心公式：
 *   G = E × F （应计提金额 = 风险资产期末余额 × 计提比例）
 *   H = B - G （差异 = 本期计提(账面) - 应计提金额）
 *
 * 差异含义：
 *   差异为正 = 实际计提 > 应计提 = 超额计提（安全）
 *   差异为负 = 实际计提 < 应计提 = 计提不足（风险！）
 *
 * ⚠️ 注意：calcProvisionDiff 的签名是 estimated - booked
 *   结果为正 = 应计提 > 账面 = 计提不足
 *   结果为负 = 应计提 < 账面 = 超额计提
 * ─────────────────────────────────────
 *
 * 本引擎覆盖：
 * - P3: 风险资产计提（calcRiskProvision = riskAssets × rate）
 * - P4: 计提差异（calcProvisionDiff = estimated - booked）
 *
 * Spec: .kiro/specs/m8-general-risk-reserve/ Task 2.2
 * Requirements: 3.4-3.5, 6.1-6.2
 */

// ─── helpers ────────────────────────────────────────────────

/** 将 NaN / undefined / null 视为 0 */
function safe(v: unknown): number {
  if (v === null || v === undefined) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── P3: 风险资产计提 ───────────────────────────────────────

/**
 * 计算应计提余额（Property P3）
 *
 * 应计提余额 = 风险资产期末余额 × 计提比例
 *
 * 来源：《金融企业准备金计提管理办法》（财金〔2012〕20号）第五条
 * 金融企业应当于每年年度终了根据承担风险和损失的资产余额，
 * 计提一般准备，一般准备余额原则上不得低于风险资产期末余额的1.5%。
 *
 * 对应xlsx公式：G = E × F
 *   E = 风险资产期末余额
 *   F = 计提比例（默认1.5% = 0.015）
 *   G = 应计提金额
 *
 * @param riskAssets - 风险资产期末余额（E列）
 * @param rate - 计提比例（F列，如0.015表示1.5%）
 * @returns 应计提余额（G列）
 */
export function calcRiskProvision(riskAssets: number, rate: number): number {
  return safe(riskAssets) * safe(rate)
}

// ─── P4: 计提差异 ───────────────────────────────────────────

/**
 * 计算计提差异（Property P4）
 *
 * 计提差异 = 应计提金额 - 实际账面余额
 *
 * 差异为正 = 应计提 > 账面 = 计提不足（审计风险！需关注）
 * 差异为负 = 应计提 < 账面 = 超额计提（安全，但可能虚增权益）
 *
 * 对应xlsx公式：H = G - B（H = 应计提 - 账面）
 *   注意：设计文档定义 H = B - G（差异=本期计提-应计提）方向相反，
 *   本函数按spec接口 estimated - booked 实现。
 *
 * @param estimated - 应计提金额（由 calcRiskProvision 计算得出）
 * @param booked - 实际账面余额（当前一般风险准备账面余额）
 * @returns 计提差异（正=计提不足，负=超额计提）
 */
export function calcProvisionDiff(estimated: number, booked: number): number {
  return safe(estimated) - safe(booked)
}
