/**
 * useL3InterestEngine — L3 长期借款利息测算引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 核心职责：利息计算、计息天数裁剪、逾期天数、利息差异。
 * 联动：L3-5 利息测算 → L2 应付利息 / L8 财务费用
 *
 * 公式来源：L3 长期借款.xlsx → Sheet "利息测算表L3-5" + "逾期贷款检查表L3-7"
 * 天数基准：**365天制**（致同2025修订版模板实际公式确认：M11=J11*I11/365*L11）
 *
 * 🔴 CRITICAL: 使用 365 天制！（非360天）
 * 源模板公式引用：
 * - L3-5 M11: =J11*I11/365*L11  (利息=本金×利率/365×天数)
 * - L3-5 G11: =IF(D11<=$D$9,$D$9,D11)  (起算时点)
 * - L3-5 H11: =IF(E11<=$E$9,E11,$E$9)  (截止时点)
 * - L3-5 L11: =IF(G11=0,0,IF((H11-G11)=365,H11-G11,H11-G11+1))  (计息天数)
 * - L3-5 N11: =M11-K11  (差异=测算利息-账载利息)
 * - L3-7 J11: =$I$9-I11  (逾期天数=报告日-到期日)
 */

// ─── 常量 ────────────────────────────────────────────────────

/** 年天数基准：365天制（致同2025修订版） */
const YEAR_DAYS = 365

// ─── 1. 利息计算（核心公式） ─────────────────────────────────

/**
 * 利息 = 本金 × 年利率 × 计息天数 / 365
 *
 * xlsx对应: L3-5 M11: =J11*I11/365*L11
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

// ─── 2. 逾期天数 ────────────────────────────────────────────

/**
 * 逾期天数 = 报告日 - 到期日
 *
 * xlsx对应: L3-7 J11: =$I$9-I11
 * 含义：正值=已逾期，负值=尚未到期，0=当天到期
 *
 * 接收 ISO 日期字符串（YYYY-MM-DD），内部解析为 UTC 日期比较。
 * 无效日期字符串返回 0。
 *
 * @param dueDate    借款到期日（ISO字符串 YYYY-MM-DD）
 * @param reportDate 报告期截止日（ISO字符串 YYYY-MM-DD）
 * @returns 逾期天数（正值逾期，负值未到期）
 */
export function calcOverdueDays(dueDate: string, reportDate: string): number {
  if (!dueDate || !reportDate) return 0

  const dueParts = dueDate.split('-')
  const reportParts = reportDate.split('-')

  if (dueParts.length !== 3 || reportParts.length !== 3) return 0

  const dueMs = Date.UTC(
    parseInt(dueParts[0], 10),
    parseInt(dueParts[1], 10) - 1,
    parseInt(dueParts[2], 10),
  )
  const reportMs = Date.UTC(
    parseInt(reportParts[0], 10),
    parseInt(reportParts[1], 10) - 1,
    parseInt(reportParts[2], 10),
  )

  if (isNaN(dueMs) || isNaN(reportMs)) return 0

  return Math.round((reportMs - dueMs) / (1000 * 60 * 60 * 24))
}

// ─── 3. 利息差异 ────────────────────────────────────────────

/**
 * 利息差异 = 测算利息 - 账载利息
 *
 * xlsx对应: L3-5 N11: =M11-K11
 * 正值=少计利息（账载偏低），负值=多计利息（账载偏高）
 *
 * @param estimated 测算利息（calcInterest计算结果）
 * @param booked    账载利息（账面已计利息金额）
 * @returns 差异金额
 */
export function calcInterestDiff(estimated: number, booked: number): number {
  return estimated - booked
}

// ─── 4. 计息天数计算（报告期区间裁剪） ──────────────────────

/**
 * 计息天数（从 xlsx L3-5 公式 L11 提取）
 *
 * xlsx对应: L3-5 L11: =IF(G11=0,0,IF((H11-G11)=365,H11-G11,H11-G11+1))
 *
 * 逻辑：
 * 1. 起算日 = max(报告期起始日, 借款起始日) → G11
 * 2. 截止日 = min(借款到期日, 报告期截止日) → H11
 * 3. 如果起算日无效（null/空） → 0天
 * 4. (截止-起算) == 365天 → 365（整年取365天）
 * 5. 否则 → (截止-起算) + 1（非整年"算头算尾"+1天）
 *
 * 接收 ISO 日期字符串。
 *
 * @param loanStart   借款起始日期 (YYYY-MM-DD)
 * @param loanEnd     借款到期日期 (YYYY-MM-DD)
 * @param reportStart 报告期起始日期 (YYYY-MM-DD)
 * @param reportEnd   报告期截止日期 (YYYY-MM-DD)
 * @returns 计息天数
 */
export function calcInterestDays(
  loanStart: string,
  loanEnd: string,
  reportStart: string,
  reportEnd: string,
): number {
  if (!loanStart || !loanEnd || !reportStart || !reportEnd) return 0

  const loanStartMs = parseUTCDate(loanStart)
  const loanEndMs = parseUTCDate(loanEnd)
  const reportStartMs = parseUTCDate(reportStart)
  const reportEndMs = parseUTCDate(reportEnd)

  if (isNaN(loanStartMs) || isNaN(loanEndMs) || isNaN(reportStartMs) || isNaN(reportEndMs)) {
    return 0
  }

  // 起算时点 = max(reportStart, loanStart)
  const startMs = Math.max(reportStartMs, loanStartMs)
  // 截止时点 = min(loanEnd, reportEnd)
  const endMs = Math.min(loanEndMs, reportEndMs)

  const diffDays = Math.round((endMs - startMs) / (1000 * 60 * 60 * 24))

  if (diffDays <= 0) return 0

  // 整年取365天
  if (diffDays === YEAR_DAYS) return YEAR_DAYS

  // 非整年：算头算尾 +1
  return diffDays + 1
}

// ─── 内部工具 ────────────────────────────────────────────────

/**
 * 将 ISO 日期字符串解析为 UTC 毫秒时间戳
 */
function parseUTCDate(dateStr: string): number {
  const parts = dateStr.split('-')
  if (parts.length !== 3) return NaN
  return Date.UTC(
    parseInt(parts[0], 10),
    parseInt(parts[1], 10) - 1,
    parseInt(parts[2], 10),
  )
}
