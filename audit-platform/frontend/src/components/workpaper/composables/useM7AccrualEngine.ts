/**
 * useM7AccrualEngine — M7 安全生产费计提引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：4201 专项储备（**贷方/权益类！**）
 *
 * ─── 安全生产费计提业务规则 ───
 * 高危行业（煤矿、非煤矿山、危险品、烟花爆竹、建筑施工等）
 * 按国家规定提取安全生产费，属于专项储备（贷方增加）。
 *
 * 计提基础分三类：
 * 1. 矿山企业：按开采原矿产量分档计提 → calcAccrualByOutput
 * 2. 危险品企业：按营业收入超额累退分档计提 → calcAccrualByOutput（多档）
 * 3. 建筑施工/其他：按营业收入×单一比例计提 → calcAccrualByRevenue
 *
 * 计提差异方向（设计决策 — m7_conflict_resolution.md #2）：
 * - xlsx: H=B-G（差异=账面计提-应计金额，正差=多计提）
 * - 设计: calcAccrualDiff(est, booked)=est-booked（正差=应补提=审计风险点）
 * - 最终: 保持设计方向 est-booked，正差=少提=需关注
 * ────────────────────────────────────────
 *
 * 本引擎覆盖：
 * - P3: 按产量分档计提 Σ(output×rate)
 * - P4: 按营业收入计提 revenue×rate
 * - P5: 计提差异 estimated-booked
 *
 * 对应xlsx公式（M7-4计提测试表 37×19, 29公式）：
 * - G12=E12*F12 → 应计金额=基数×比例（单档）
 * - G21=SUM(G12:G20) → 合计=各档应计之和
 * - H12=B12-G12 → xlsx差异=账面-应计（设计取反：est-booked）
 *
 * Spec: .kiro/specs/m7-special-reserve/ Task 2.2
 * Requirements: 4.2-4.4, 7.1-7.3
 */

// ─── helpers ────────────────────────────────────────────────

/** 将 NaN / undefined / null 视为 0 */
function safe(v: unknown): number {
  if (v === null || v === undefined) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── P3: 按产量分档计提 ────────────────────────────────────

/**
 * 按产量（或超额累退）分档计提安全生产费（Property P3）
 *
 * 应计金额 = Σ(各档产量 × 档位标准)
 *
 * 适用场景：
 * - 矿山企业：按开采原矿产量分档（如：≤100万吨部分 5元/吨，>100万吨部分 4元/吨）
 * - 危险品企业：按营业收入超额累退分档
 *
 * 来源：M7-4 计提测试表
 * 对应xlsx公式：
 *   G12 = E12 * F12（第1档：基数×比例）
 *   G13 = E13 * F13（第2档：基数×比例）
 *   ...
 *   G21 = SUM(G12:G20)（各档合计）
 *
 * @param tiers - 各档 { output: 产量/基数, rate: 档位标准/比例 }
 * @returns 应计金额合计
 */
export function calcAccrualByOutput(tiers: { output: number; rate: number }[]): number {
  if (!Array.isArray(tiers)) return 0
  let total = 0
  for (const tier of tiers) {
    total += safe(tier.output) * safe(tier.rate)
  }
  return total
}

// ─── P4: 按营业收入计提 ────────────────────────────────────

/**
 * 按营业收入×单一比例计提安全生产费（Property P4）
 *
 * 应计金额 = 营业收入 × 计提比例
 *
 * 适用场景：
 * - 建筑施工企业：以建筑安装工程造价为基数×比例
 * - 其他企业：以营业收入为基数×单一比例
 *
 * 来源：M7-4 计提测试表
 * 对应xlsx公式：G = E × F（单行，基数×比例）
 *
 * @param revenue - 营业收入/建安造价（基数）
 * @param rate - 计提比例（如 0.015 = 1.5%）
 * @returns 应计金额
 */
export function calcAccrualByRevenue(revenue: number, rate: number): number {
  return safe(revenue) * safe(rate)
}

// ─── P5: 计提差异 ──────────────────────────────────────────

/**
 * 计算计提差异（Property P5）
 *
 * 差异 = 应计提金额 - 账面计提金额
 * - 正差 → 应补提（少计提=审计风险点）
 * - 负差 → 多计提（需要冲回）
 * - 零 → 计提准确
 *
 * ⚠️ 方向说明（m7_conflict_resolution.md 冲突#2 解决方案）：
 * xlsx公式为 H=B-G（账面-应计，正差=多计提），与本函数方向相反。
 * 设计采用 est-booked（正差=少提=风险），因为审计关注"是否少提"更直观。
 * UI展示时标注"正差表示少计提"。
 *
 * 来源：M7-4 计提测试表
 * 对应xlsx公式：H = B - G（方向相反！设计取 est-booked）
 *
 * @param estimated - 应计提金额（按标准计算的应提数）
 * @param booked - 账面计提金额（企业实际计提数）
 * @returns 计提差异（正=应补提，负=多计提）
 */
export function calcAccrualDiff(estimated: number, booked: number): number {
  return safe(estimated) - safe(booked)
}
