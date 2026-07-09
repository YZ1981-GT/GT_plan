/**
 * useL3ReclassEngine — L3 长期借款一年内到期重分类引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 核心职责：判定一年内到期金额、生成重分类分录(RJE)。
 *
 * 业务背景：
 * 根据CAS30/企业会计准则，长期借款中将于报告期后一年内到期的部分
 * 应重分类至"一年内到期的非流动负债"（流动负债科目2801）。
 *
 * 重分类分录：
 *   借：长期借款（2501）  — currentPortion
 *   贷：一年内到期的非流动负债（2801）— currentPortion
 *
 * 公式来源：L3 长期借款.xlsx → Sheet "明细表L3-2" V/W列
 * 判定规则：到期日 ≤ 报告日 + 1年 → 全额重分类
 *
 * Requirements: 5.1-5.4, 10.3
 * Spec: .kiro/specs/l3-long-term-loans/
 * Task: 2.3
 */

// ─── 类型定义 ────────────────────────────────────────────────

/** 重分类调整分录 */
export interface ReclassEntry {
  description: string
  debit: { account: string; accountCode: string; amount: number }
  credit: { account: string; accountCode: string; amount: number }
}

// ─── 1. 一年内到期金额判定 ───────────────────────────────────

/**
 * 判定一年内到期金额
 *
 * 规则：如果借款到期日在报告日起一年内（含当天），则该笔借款全额重分类。
 * 如果到期日超过报告日一年以上，一年内到期金额=0。
 *
 * Source: L3-2 V/W列（手工判定/公式辅助），L3-1 F/L列SUMIF汇总
 *
 * 边界处理：
 * - dueDate 恰好等于 reportDate + 1年 → 需重分类（含边界）
 * - dueDate 已过报告日（已逾期）→ 需重分类（逾期仍在一年内）
 * - 无效日期 → 0
 * - amount ≤ 0 → 0
 *
 * @param dueDate    借款到期日 (ISO YYYY-MM-DD)
 * @param reportDate 报告期截止日 (ISO YYYY-MM-DD)
 * @param amount     借款本金余额
 * @returns 一年内到期金额（0 = 不需要重分类）
 */
export function calcCurrentPortion(dueDate: string, reportDate: string, amount: number): number {
  if (!dueDate || !reportDate) return 0
  if (amount <= 0) return 0

  const dueMs = parseUTCDate(dueDate)
  const reportMs = parseUTCDate(reportDate)

  if (isNaN(dueMs) || isNaN(reportMs)) return 0

  // 计算报告日 + 1年的边界日期
  const oneYearLaterMs = addOneYear(reportDate)
  if (isNaN(oneYearLaterMs)) return 0

  // 到期日 ≤ 报告日+1年 → 需重分类（含边界当天）
  if (dueMs <= oneYearLaterMs) {
    return amount
  }

  // 到期日 > 报告日+1年 → 不需要重分类
  return 0
}

// ─── 2. 生成重分类分录 ──────────────────────────────────────

/**
 * 生成重分类分录 (RJE)
 *
 * 重分类分录：
 *   借：长期借款（2501）  — currentPortion
 *   贷：一年内到期的非流动负债（2801）— currentPortion
 *
 * 边界处理：
 * - currentPortion = 0 → 仍返回结构，金额为0（调用方可据此判断是否提交）
 * - currentPortion < 0 → 按绝对值处理（防御性）
 *
 * @param currentPortion 一年内到期金额 (calcCurrentPortion 的输出)
 * @returns 重分类调整分录对象
 */
export function buildReclassEntry(currentPortion: number): ReclassEntry {
  const absAmount = Math.abs(currentPortion)

  return {
    description: '一年内到期的长期借款重分类',
    debit: {
      account: '长期借款',
      accountCode: '2501',
      amount: absAmount,
    },
    credit: {
      account: '一年内到期的非流动负债',
      accountCode: '2801',
      amount: absAmount,
    },
  }
}

// ─── 内部工具 ────────────────────────────────────────────────

/**
 * 将 ISO 日期字符串解析为 UTC 毫秒时间戳
 */
function parseUTCDate(dateStr: string): number {
  const parts = dateStr.split('-')
  if (parts.length !== 3) return NaN
  const y = parseInt(parts[0], 10)
  const m = parseInt(parts[1], 10)
  const d = parseInt(parts[2], 10)
  if (isNaN(y) || isNaN(m) || isNaN(d)) return NaN
  return Date.UTC(y, m - 1, d)
}

/**
 * 计算日期 + 1年 的 UTC 毫秒时间戳
 *
 * 使用日历年加法（非365天）：
 * - 2024-12-31 + 1年 = 2025-12-31
 * - 2024-02-29 + 1年 = 2025-02-28（闰年→非闰年自动修正）
 */
function addOneYear(dateStr: string): number {
  const parts = dateStr.split('-')
  if (parts.length !== 3) return NaN
  const y = parseInt(parts[0], 10)
  const m = parseInt(parts[1], 10)
  const d = parseInt(parts[2], 10)
  if (isNaN(y) || isNaN(m) || isNaN(d)) return NaN

  // 日历年+1
  // Date.UTC handles overflow (e.g. Feb 29 → Mar 1 in non-leap year)
  // But we want it to clamp to the last valid day, so use Date object
  const nextYear = y + 1
  // Get the last day of the target month in the next year
  const lastDayOfMonth = new Date(Date.UTC(nextYear, m - 1 + 1, 0)).getUTCDate()
  const clampedDay = Math.min(d, lastDayOfMonth)

  return Date.UTC(nextYear, m - 1, clampedDay)
}
