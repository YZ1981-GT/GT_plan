/**
 * useL1InterestEngine — L1 短期借款利息测算引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 核心职责：利息计算、计息天数、起止裁剪、逾期天数、逾期利息。
 * 联动：L1-5 利息测算 → L2 应付利息 / L8 财务费用
 *
 * 公式来源：L1 短期借款.xlsx → Sheet "利息测算表L1-5" + "逾期贷款检查表L1-7"
 * 天数基准：**365天制**（致同2025修订版模板实际公式，非360天！）
 *
 * xlsx公式引用：
 * - M11: =J11*I11/365*L11  (利息=本金×利率/365×天数)
 * - G11: =IF(D11<=$D$9,$D$9,D11)  (起算时点)
 * - H11: =IF(E11<=$E$9,E11,$E$9)  (截止时点)
 * - L11: =IF(G11=0,0,IF((H11-G11)=365,H11-G11,H11-G11+1))  (计息天数)
 * - J11(L1-7): =IF(I11=0,0,$I$9-I11)  (逾期天数)
 * - L11(L1-7): =E11*G11*K11  (逾期利息=本金×逾期利率日×天数)
 */

// ─── 常量 ────────────────────────────────────────────────────

/** 年天数基准：365天制（致同2025修订版） */
const YEAR_DAYS = 365

// ─── 1. 利息计算（核心公式） ─────────────────────────────────

/**
 * 利息 = 本金 × 年利率 × 计息天数 / 365
 *
 * xlsx对应: M11: =J11*I11/365*L11
 *
 * 边界处理：
 * - principal=0 → 0
 * - annualRate=0 → 0
 * - days=0 → 0
 * - days<0 → 视为0（无效区间不产生利息）
 *
 * @param principal  借款本金（≥0）
 * @param annualRate 年利率（如0.05表示5%）
 * @param days       计息天数（≥0）
 * @returns 测算利息金额
 */
export function calcInterest(principal: number, annualRate: number, days: number): number {
  if (principal === 0 || annualRate === 0 || days <= 0) return 0
  return principal * annualRate * days / YEAR_DAYS
}

// ─── 2. 计息天数计算 ────────────────────────────────────────

/**
 * 计息天数（从 xlsx L1-5 公式 L11 提取）
 *
 * xlsx对应: L11: =IF(G11=0,0,IF((H11-G11)=365,H11-G11,H11-G11+1))
 *
 * 逻辑：
 * - 起算日期为null → 0
 * - 截止日期为null → 0
 * - (截止-起算) == 365天 → 365（整年取365天，避免闰年366天问题）
 * - 否则 → (截止-起算) + 1（非整年"算头算尾"+1天）
 *
 * @param startDate 起算时点（已裁剪后）
 * @param endDate   截止时点（已裁剪后）
 * @returns 计息天数
 */
export function calcInterestDays(startDate: Date | null, endDate: Date | null): number {
  if (!startDate || !endDate) return 0

  // 使用 UTC 日期避免时区干扰，只比较日期部分
  const startMs = Date.UTC(startDate.getFullYear(), startDate.getMonth(), startDate.getDate())
  const endMs = Date.UTC(endDate.getFullYear(), endDate.getMonth(), endDate.getDate())

  const diffDays = Math.round((endMs - startMs) / (1000 * 60 * 60 * 24))

  if (diffDays <= 0) return 0

  // 整年取365天（IF (H-G)==365 THEN 365）
  if (diffDays === YEAR_DAYS) return YEAR_DAYS

  // 非整年：算头算尾 +1
  return diffDays + 1
}

// ─── 3. 起算时点裁剪 ────────────────────────────────────────

/**
 * 起算时点 = max(报告期起始日, 借款起始日)
 *
 * xlsx对应: G11: =IF(D11<=$D$9,$D$9,D11)
 * 含义：如果借款开始日期 ≤ 报告期起始日，则用报告期起始日（借款在报告期之前开始）
 *        否则用借款起始日（借款在报告期内开始）
 *
 * @param loanStart   借款起始日期（D11）
 * @param reportStart 报告期起始日期（$D$9）
 * @returns 裁剪后的起算时点
 */
export function calcStartDate(loanStart: Date, reportStart: Date): Date {
  const loanMs = loanStart.getTime()
  const reportMs = reportStart.getTime()

  // max(报告期起始日, 借款起始日)
  return loanMs <= reportMs ? reportStart : loanStart
}

// ─── 4. 截止时点裁剪 ────────────────────────────────────────

/**
 * 截止时点 = min(借款讫止日, 报告期截止日)
 *
 * xlsx对应: H11: =IF(E11<=$E$9,E11,$E$9)
 * 含义：如果借款到期日 ≤ 报告期截止日，则用借款到期日（借款在报告期内到期）
 *        否则用报告期截止日（借款跨过报告期末）
 *
 * @param loanEnd   借款讫止日期（E11）
 * @param reportEnd 报告期截止日期（$E$9）
 * @returns 裁剪后的截止时点
 */
export function calcEndDate(loanEnd: Date, reportEnd: Date): Date {
  const loanMs = loanEnd.getTime()
  const reportMs = reportEnd.getTime()

  // min(借款讫止日, 报告期截止日)
  return loanMs <= reportMs ? loanEnd : reportEnd
}

// ─── 5. 利息差异 ────────────────────────────────────────────

/**
 * 差异 = 测算利息 - 账面已计利息
 *
 * xlsx对应: N11（利息测算表差异列）
 * 正值=少计利息，负值=多计利息
 *
 * @param calculated 测算利息（calcInterest计算结果）
 * @param booked     账面已计利息（账载数）
 * @returns 差异金额
 */
export function calcInterestDiff(calculated: number, booked: number): number {
  return calculated - booked
}

// ─── 6. 逾期天数 ────────────────────────────────────────────

/**
 * 逾期天数 = 报告期截止日 - 借款到期日
 *
 * xlsx对应: J11(L1-7): =IF(I11=0,0,$I$9-I11)
 * 含义：如果借款到期日为空（无到期日）→ 0天
 *        否则逾期天数 = 报告日 - 到期日
 *        正值=已逾期，负值=尚未到期
 *
 * @param dueDate    借款到期日（I11），null表示无到期日
 * @param reportDate 报告期截止日（$I$9）
 * @returns 逾期天数（正值逾期，负值未到期）
 */
export function calcOverdueDays(dueDate: Date | null, reportDate: Date): number {
  if (!dueDate) return 0

  const dueMs = Date.UTC(dueDate.getFullYear(), dueDate.getMonth(), dueDate.getDate())
  const reportMs = Date.UTC(reportDate.getFullYear(), reportDate.getMonth(), reportDate.getDate())

  return Math.round((reportMs - dueMs) / (1000 * 60 * 60 * 24))
}

// ─── 7. 逾期利息计算 ────────────────────────────────────────

/**
 * 逾期利息 = 借款金额 × 逾期利率(日) × 计息天数
 *
 * xlsx对应: L11(L1-7): =E11*G11*K11
 * - E11 = 借款金额（本金）
 * - G11 = 逾期利率（日利率）
 * - K11 = 计息天数
 *
 * 边界处理：
 * - principal=0 → 0
 * - dailyRate=0 → 0
 * - days≤0 → 0
 *
 * @param principal 借款金额
 * @param dailyRate 逾期利率（日），如年化18%罚息→日利率=0.18/365
 * @param days      逾期计息天数
 * @returns 逾期利息金额
 */
export function calcOverdueInterest(principal: number, dailyRate: number, days: number): number {
  if (principal === 0 || dailyRate === 0 || days <= 0) return 0
  return principal * dailyRate * days
}
