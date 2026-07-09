/**
 * useL8CutoffEngine — L8 截止测试引擎（纯函数）
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 *
 * ─── 截止测试核心逻辑 ───
 * 财务费用作为损益类科目，截止测试（期末前后归属期间正确性）是关键程序。
 * 集成 useCutoffAutoSampling 自动提取报告日±N天序时账，识别跨期费用。
 *
 * 默认窗口：±5天（参照 useCutoffAutoSampling 标准）
 * ─────────────────────────
 *
 * 本引擎覆盖：
 * - 跨期判定（应归属期间 ≠ 实际入账期间）
 * - 提取报告日±N天窗口内的序时账明细
 *
 * Spec: .kiro/specs/l8-financial-expenses/ Task 2.3
 * Requirements: 6.2-6.4, 8.7
 */

import { parseNum } from './useL8FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/**
 * 序时账分录条目
 *
 * 来源：tb_ledger（科目6603财务费用）
 * 用于截止测试窗口提取 + 跨期判定
 */
export interface LedgerEntry {
  /** 凭证号 */
  voucherNo: string
  /** 凭证日期（YYYY-MM-DD） */
  date: string
  /** 摘要 */
  summary: string
  /** 金额（正数） */
  amount: number
  /** 应归属期间（YYYY-MM，如 "2024-12"） */
  attributionPeriod: string
  /** 实际入账期间（YYYY-MM，如 "2025-01"） */
  bookingPeriod: string
  /** 对方科目 */
  counterAccount: string
}

// ─── 1. 跨期判定 ────────────────────────────────────────────────────────────

/**
 * 判断是否跨期（Requirements 6.4, 8.7）
 *
 * 跨期定义：应归属期间 ≠ 实际入账期间
 * 即费用在A期间发生，但在B期间才入账（归属与记账不一致）。
 *
 * 典型场景：
 * - 12月发生的费用1月才入账 → 跨期（应在上期确认）
 * - 1月发生的费用12月提前入账 → 跨期（应在下期确认）
 *
 * @param attributionPeriod - 应归属期间（YYYY-MM格式，如 "2024-12"）
 * @param bookingPeriod - 实际入账期间（YYYY-MM格式，如 "2025-01"）
 * @returns true表示跨期（红色高亮），false表示正常
 */
export function isCrossPeriod(attributionPeriod: string, bookingPeriod: string): boolean {
  // 标准化比较：trim后严格不等即为跨期
  const attr = (attributionPeriod ?? '').trim()
  const book = (bookingPeriod ?? '').trim()
  // 两者均为空视为无法判定，不标记跨期
  if (!attr || !book) return false
  return attr !== book
}

// ─── 2. 提取报告日±N天窗口序时账 ───────────────────────────────────────────

/**
 * 提取报告日±N天窗口内的序时账明细（Requirements 6.2-6.3）
 *
 * 从完整序时账中筛选出凭证日期在 [reportDate - N天, reportDate + N天] 范围内的条目。
 * 用于截止测试：识别报告期前后可能跨期入账的财务费用。
 *
 * 默认窗口 N=5（参照 l8_conflict_resolution.md + useCutoffAutoSampling 标准）
 *
 * @param ledger - 完整序时账明细数组
 * @param reportDate - 报告日/截止日（YYYY-MM-DD格式，如 "2024-12-31"）
 * @param days - 窗口天数（±N天，默认5）
 * @returns 窗口内的序时账条目子集
 */
export function extractCutoffWindow(
  ledger: LedgerEntry[],
  reportDate: string,
  days: number = 5,
): LedgerEntry[] {
  if (!Array.isArray(ledger) || !reportDate) return []

  const d = parseNum(days)
  if (d < 0) return []

  // 解析报告日为毫秒时间戳（UTC 0点，避免时区偏移）
  const reportMs = parseDateToMs(reportDate)
  if (reportMs === null) return []

  // 计算窗口边界（含边界日）
  const msPerDay = 86_400_000
  const windowStart = reportMs - d * msPerDay
  const windowEnd = reportMs + d * msPerDay

  return ledger.filter(entry => {
    if (!entry || !entry.date) return false
    const entryMs = parseDateToMs(entry.date)
    if (entryMs === null) return false
    return entryMs >= windowStart && entryMs <= windowEnd
  })
}

// ─── 3. 窗口内跨期条目提取 ──────────────────────────────────────────────────

/**
 * 从窗口内序时账中提取所有跨期条目
 *
 * 先调用 extractCutoffWindow 获取窗口内条目，
 * 再从中筛选 isCrossPeriod === true 的条目。
 *
 * @param ledger - 完整序时账明细数组
 * @param reportDate - 报告日（YYYY-MM-DD）
 * @param days - 窗口天数（±N天，默认5）
 * @returns 窗口内且跨期的条目
 */
export function extractCrossPeriodEntries(
  ledger: LedgerEntry[],
  reportDate: string,
  days: number = 5,
): LedgerEntry[] {
  const windowEntries = extractCutoffWindow(ledger, reportDate, days)
  return windowEntries.filter(entry =>
    isCrossPeriod(entry.attributionPeriod, entry.bookingPeriod),
  )
}

// ─── 4. 跨期金额合计 ────────────────────────────────────────────────────────

/**
 * 计算跨期条目金额合计
 *
 * @param entries - 跨期条目数组（extractCrossPeriodEntries 结果）
 * @returns 跨期金额合计
 */
export function calcCrossPeriodTotal(entries: LedgerEntry[]): number {
  if (!Array.isArray(entries)) return 0
  let total = 0
  for (const entry of entries) {
    total += parseNum(entry.amount)
  }
  return total
}

// ─── 5. 跨期率 ──────────────────────────────────────────────────────────────

/**
 * 计算窗口内跨期率
 *
 * 跨期率 = 跨期笔数 / 窗口内总笔数 × 100
 * 总笔数为0时返回0（无数据时无跨期率）
 *
 * @param crossCount - 跨期条目数
 * @param totalCount - 窗口内总条目数
 * @returns 跨期率（百分比）
 */
export function calcCrossPeriodRate(crossCount: number, totalCount: number): number {
  const total = parseNum(totalCount)
  if (total === 0) return 0
  return (parseNum(crossCount) / total) * 100
}

// ─── helpers ────────────────────────────────────────────────────────────────

/**
 * 将 YYYY-MM-DD 日期字符串解析为 UTC 0点毫秒时间戳
 * 无效日期返回 null
 */
function parseDateToMs(dateStr: string): number | null {
  if (!dateStr || typeof dateStr !== 'string') return null
  // 严格匹配 YYYY-MM-DD 格式
  const match = dateStr.match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (!match) return null
  const y = parseInt(match[1], 10)
  const m = parseInt(match[2], 10) - 1 // 0-indexed
  const d = parseInt(match[3], 10)
  // 使用 Date.UTC 避免时区问题
  const ms = Date.UTC(y, m, d)
  // 验证日期有效性（如 2月30日无效）
  const check = new Date(ms)
  if (check.getUTCFullYear() !== y || check.getUTCMonth() !== m || check.getUTCDate() !== d) {
    return null
  }
  return ms
}
