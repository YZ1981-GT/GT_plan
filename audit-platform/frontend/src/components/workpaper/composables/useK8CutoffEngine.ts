/**
 * K8 销售费用 — 截止测试引擎（纯函数，无副作用）
 * 科目：6601销售费用（损益类/借方科目）
 *
 * 职责：
 * - 跨期判断 isCrossPeriod：判断两个日期是否分属不同会计期间
 * - 自动抽样 autoSampleCutoff：从序时账提取期末±N天凭证作为截止测试样本
 *
 * 截止测试双向：
 * - K8-6 记账凭证 → 原始凭证（真实性认定）
 * - K8-7 原始凭证 → 记账凭证（完整性认定）
 *
 * 所有函数为纯函数，便于PBT验证。
 * 与平台 useCutoffAutoSampling 配合（该composable负责API调用，本引擎负责纯计算）。
 *
 * Spec: .kiro/specs/k8-selling-expenses/
 * Validates: Requirements 5.3-5.4, 9.7
 *
 * 收敛（cutoff-test-architecture-convergence Wave1）：isCrossPeriod 委托 cutoffCanonical
 * 单一真源（natural-month 模式），行为等价（P8 已锁定）。
 */
import { crossesByNaturalMonth } from './cutoffCanonical'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 序时账分录条目（从 tb_ledger 或 ledger API 取得） */
export interface LedgerEntry {
  /** 凭证号 */
  voucherNo: string
  /** 凭证日期 YYYY-MM-DD */
  voucherDate: string
  /** 摘要 */
  summary: string | null
  /** 借方金额 */
  debitAmount: number | null
  /** 贷方金额 */
  creditAmount: number | null
  /** 科目编码 */
  accountCode: string
  /** 科目名称 */
  accountName: string | null
  /** 原始凭证日期 YYYY-MM-DD（可能为空） */
  sourceDate?: string | null
}

/** 截止测试样本条目 */
export interface CutoffSample {
  /** 凭证号 */
  voucherNo: string
  /** 记账日期 YYYY-MM-DD */
  bookDate: string
  /** 原始凭证日期 YYYY-MM-DD（可能为空） */
  sourceDate: string | null
  /** 摘要 */
  summary: string | null
  /** 借方金额 */
  debitAmount: number | null
  /** 贷方金额 */
  creditAmount: number | null
  /** 科目编码 */
  accountCode: string
  /** 科目名称 */
  accountName: string | null
  /** 是否跨期（自动计算） */
  isCrossPeriod: boolean
}

// ─── Helper: 安全解析日期 ────────────────────────────────────────────────────

/**
 * 安全解析日期字符串为 Date 对象
 * 支持 YYYY-MM-DD 格式，返回 null 如果无效
 */
function safeParseDate(dateStr: string | null | undefined): Date | null {
  if (!dateStr || typeof dateStr !== 'string') return null
  const trimmed = dateStr.trim()
  if (!trimmed) return null
  // 严格匹配 YYYY-MM-DD 格式
  const match = trimmed.match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (!match) return null
  const year = parseInt(match[1], 10)
  const month = parseInt(match[2], 10)
  const day = parseInt(match[3], 10)
  // 基本范围校验
  if (month < 1 || month > 12 || day < 1 || day > 31) return null
  const d = new Date(year, month - 1, day)
  // 验证构造出的日期与输入一致（防止溢出，如2月30日→3月2日）
  if (d.getFullYear() !== year || d.getMonth() !== month - 1 || d.getDate() !== day) return null
  return d
}

// ─── Core Functions ──────────────────────────────────────────────────────────

/**
 * 跨期判断：判断原始凭证日期(sourceDate)与记账日期(bookDate)是否分属不同会计期间。
 *
 * 薄封装：委托 cutoffCanonical.crossesByNaturalMonth（natural-month 模式单一真源，
 * 年+月不同即跨期，与截止日相对位置无关；任一日期非法 → false）。行为等价（P8 已锁定）。
 *
 * Validates: Requirements 5.4, 9.7
 *
 * @param sourceDate 原始凭证日期 YYYY-MM-DD
 * @param bookDate 记账日期 YYYY-MM-DD
 * @param _periodEnd 会计期间截止日 YYYY-MM-DD（预留，natural-month 语义下不参与判定）
 */
export function isCrossPeriod(sourceDate: string, bookDate: string, _periodEnd: string): boolean {
  return crossesByNaturalMonth(sourceDate, bookDate)
}

/**
 * 自动从序时账提取期末±days天凭证作为截止测试样本
 *
 * 逻辑：
 * - 解析 periodEnd 为截止基准日
 * - 计算日期窗口 [periodEnd - days, periodEnd + days]
 * - 筛选 ledger 中 voucherDate 在窗口内的条目
 * - 自动计算每条样本的 isCrossPeriod 标记
 *
 * Validates: Requirements 5.3, 9.7
 *
 * @param ledger 序时账分录数组
 * @param periodEnd 会计期间截止日 YYYY-MM-DD（如 "2025-12-31"）
 * @param days 期末前后天数（默认5天，即±5天窗口共10天）
 * @returns 截止测试样本数组（已标记跨期）
 */
export function autoSampleCutoff(
  ledger: LedgerEntry[],
  periodEnd: string,
  days: number = 5,
): CutoffSample[] {
  if (!Array.isArray(ledger) || ledger.length === 0) return []

  const endDate = safeParseDate(periodEnd)
  if (!endDate) return []

  // 计算日期窗口
  const windowStart = new Date(endDate.getTime() - days * 24 * 60 * 60 * 1000)
  const windowEnd = new Date(endDate.getTime() + days * 24 * 60 * 60 * 1000)

  const samples: CutoffSample[] = []

  for (const entry of ledger) {
    const entryDate = safeParseDate(entry.voucherDate)
    if (!entryDate) continue

    // 判断凭证日期是否在窗口内（含边界）
    if (entryDate >= windowStart && entryDate <= windowEnd) {
      const sourceDate = entry.sourceDate ?? null
      const crossPeriod = sourceDate
        ? isCrossPeriod(sourceDate, entry.voucherDate, periodEnd)
        : false

      samples.push({
        voucherNo: entry.voucherNo,
        bookDate: entry.voucherDate,
        sourceDate: sourceDate,
        summary: entry.summary,
        debitAmount: entry.debitAmount,
        creditAmount: entry.creditAmount,
        accountCode: entry.accountCode,
        accountName: entry.accountName,
        isCrossPeriod: crossPeriod,
      })
    }
  }

  return samples
}
