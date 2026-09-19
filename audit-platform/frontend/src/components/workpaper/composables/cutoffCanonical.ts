/**
 * cutoffCanonical — 截止性测试判定/窗口/结论的单一真源（纯函数，无 Vue 依赖）
 *
 * Spec: .kiro/specs/cutoff-test-architecture-convergence/
 * Wave 0 Task 2 — 先并存不接线，后续各调用方逐步委托本模块。
 *
 * 收敛目标（Req3/Req4）：
 * - computeWindow / inWindow      ← 替代 computeDateRange / filterByCutoffWindow 的窗口计算
 * - crossesByCutoffBoundary       ← 等价 useI2FormulaEngine.isCutoffPeriodCrossing（I2/I6）
 * - crossesByNaturalMonth         ← 等价 useK8/useK9CutoffEngine.isCrossPeriod（K8/K9）
 * - judgeCrossPeriod(sample,cd,mode) ← 统一入口 + 单日期降级（等价 markCutoffCrossPeriod）
 * - deriveConclusion              ← 统一 6 态结论状态机（缺侧证据→证据不完整）
 * - mapLegacyConclusion           ← 旧中文结论字面量 → 统一状态映射
 *
 * 🔴 Req3.5：cutoff-boundary（截止日两侧 XOR）与 natural-month（不同自然会计月）两套语义
 * 不等价，canonical 保留两种模式，各调用方沿用既有模式，禁止强行统一（会改结论=回归）。
 */

// ─── Types ───────────────────────────────────────────────────────────────────

/** 跨期判定模式：I2/I6 用 cutoff-boundary；K8/K9 用 natural-month */
export type CutoffMode = 'cutoff-boundary' | 'natural-month'

/** 双侧证据（记账侧 bookDate / 原始单据侧 documentDate），缺失为空串 */
export interface CutoffDatePair {
  bookDate: string
  documentDate: string
}

/** judgeCrossPeriod 原子结果 */
export type CrossPeriodVerdict = 'none' | 'suspect' | 'crossing' | 'same'

/** 统一结论状态机（6 态，互斥完备） */
export type CutoffConclusion =
  | '待追查'
  | '证据不完整'
  | '正常'
  | '跨期'
  | '需调整'
  | '已调整'

export const CUTOFF_CONCLUSIONS: readonly CutoffConclusion[] = [
  '待追查',
  '证据不完整',
  '正常',
  '跨期',
  '需调整',
  '已调整',
] as const

// ─── 日期解析（本地 0 点，避免时区偏移；非法返回 null） ──────────────────────

function parseDate(dateStr: string | null | undefined): Date | null {
  if (!dateStr) return null
  const d = new Date(String(dateStr).slice(0, 10) + 'T00:00:00')
  return Number.isNaN(d.getTime()) ? null : d
}

function formatDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** 自然会计月序号 = year*12 + (month-1)，用于 natural-month 模式比较 */
function monthOrdinal(d: Date): number {
  return d.getFullYear() * 12 + d.getMonth()
}

// ─── 窗口（等价 cutoffJudgment.computeDateRange / filterByCutoffWindow） ───────

/**
 * 计算截止窗口闭区间 [cutoffDate − daysBefore, cutoffDate + daysAfter]。
 * cutoffDate 非法时原样返回（与既有 computeDateRange 一致）。
 */
export function computeWindow(
  cutoffDate: string,
  daysBefore: number,
  daysAfter: number,
): { start: string; end: string } {
  const base = parseDate(cutoffDate)
  if (!base) return { start: cutoffDate, end: cutoffDate }
  const start = new Date(base)
  start.setDate(start.getDate() - daysBefore)
  const end = new Date(base)
  end.setDate(end.getDate() + daysAfter)
  return { start: formatDate(start), end: formatDate(end) }
}

/**
 * 判断某日期是否落在窗口闭区间内（等价 filterByCutoffWindow 的逐元素判定）。
 * 日期非法或窗口非法 → false。
 */
export function inWindow(
  date: string,
  cutoffDate: string,
  daysBefore: number,
  daysAfter: number,
): boolean {
  const d = parseDate(date)
  if (!d) return false
  const { start, end } = computeWindow(cutoffDate, daysBefore, daysAfter)
  const s = parseDate(start)
  const e = parseDate(end)
  if (!s || !e) return false
  const t = d.getTime()
  return t >= s.getTime() && t <= e.getTime()
}

// ─── 跨期判定（两套语义，Req3.5 保留差异） ────────────────────────────────────

/**
 * cutoff-boundary 的方向子类（第三模式基座，供 F2 存货截止 early_book/late_book 细判复用）：
 * - 'same'                     两侧同处截止日一侧（不跨期）
 * - 'book-before-doc-after'    记账日≤截止日 且 单据日>截止日（提前入账/多记当期）
 * - 'doc-before-book-after'    单据日≤截止日 且 记账日>截止日（推迟入账/漏记当期）
 * - 'incomplete'               任一日期非法/缺失
 * XOR 跨期算术的【唯一真源】——crossesByCutoffBoundary 亦由本函数派生。
 */
export type CutoffBoundaryClass =
  | 'same'
  | 'book-before-doc-after'
  | 'doc-before-book-after'
  | 'incomplete'

export function classifyCutoffBoundary(
  bookDate: string,
  documentDate: string,
  cutoffDate: string,
): CutoffBoundaryClass {
  const b = parseDate(bookDate)
  const d = parseDate(documentDate)
  const c = parseDate(cutoffDate)
  if (!b || !d || !c) return 'incomplete'
  const cutoff = c.getTime()
  const bookOnOrBefore = b.getTime() <= cutoff
  const docOnOrBefore = d.getTime() <= cutoff
  if (bookOnOrBefore === docOnOrBefore) return 'same'
  return bookOnOrBefore ? 'book-before-doc-after' : 'doc-before-book-after'
}

/**
 * cutoff-boundary 模式（I2/I6）：记账日与单据日分处截止日两侧（XOR）即跨期。
 * 等价 useI2FormulaEngine.isCutoffPeriodCrossing。任一日期非法 → false。
 * 由 classifyCutoffBoundary 派生（XOR 算术单一真源）。
 */
export function crossesByCutoffBoundary(
  bookDate: string,
  documentDate: string,
  cutoffDate: string,
): boolean {
  const cls = classifyCutoffBoundary(bookDate, documentDate, cutoffDate)
  return cls === 'book-before-doc-after' || cls === 'doc-before-book-after'
}

/**
 * natural-month 模式（K8/K9）：两侧日期分属不同自然会计月（year+month 不同）即跨期。
 * 等价 useK8/useK9CutoffEngine.isCrossPeriod（与截止日相对位置无关）。任一日期非法 → false。
 */
export function crossesByNaturalMonth(dateA: string, dateB: string): boolean {
  const a = parseDate(dateA)
  const b = parseDate(dateB)
  if (!a || !b) return false
  return monthOrdinal(a) !== monthOrdinal(b)
}

/**
 * 统一跨期判定入口。
 * - 双侧证据齐全 → 按 mode 判 crossing/same
 * - 仅单侧日期 → 'suspect'（单日期降级：唯一有的日期 > 截止日视为跨期疑点，
 *   等价 useCutoffAutoSampling.markCutoffCrossPeriod 的单日期降级）
 * - 无任何日期 → 'none'
 */
export function judgeCrossPeriod(
  pair: CutoffDatePair,
  cutoffDate: string,
  mode: CutoffMode,
): CrossPeriodVerdict {
  // 用【解析有效性】判在场，而非 !!string：非空但非法的日期视为缺失，
  // 精确匹配 legacy markCutoffCrossPeriod 的降级行为，且使非法日期正确落"证据不完整"。
  const bookD = parseDate(pair.bookDate)
  const docD = parseDate(pair.documentDate)
  const bookHas = !!bookD
  const docHas = !!docD
  if (!bookHas && !docHas) return 'none'

  if (bookHas !== docHas) {
    // 单日期降级：唯一有效的日期落在截止日之后 → 跨期疑点
    const only = (bookHas ? bookD : docD) as Date
    const c = parseDate(cutoffDate)?.getTime()
    if (!Number.isFinite(c)) return 'none'
    return only.getTime() > (c as number) ? 'suspect' : 'same'
  }

  // 双侧齐全
  const crossing =
    mode === 'natural-month'
      ? crossesByNaturalMonth(pair.bookDate, pair.documentDate)
      : crossesByCutoffBoundary(pair.bookDate, pair.documentDate, cutoffDate)
  return crossing ? 'crossing' : 'same'
}

// ─── 结论状态机（Req4） ───────────────────────────────────────────────────────

/**
 * 旧中文结论字面量 → 统一 6 态（Req4.4，映射保语义不改归类）。
 * 未识别的字面量按"待追查"兜底（不静默判正常）。
 */
export function mapLegacyConclusion(literal: string | null | undefined): CutoffConclusion {
  const s = String(literal ?? '').trim()
  switch (s) {
    case '正常':
      return '正常'
    case '跨期':
    case '可能跨期':
    case '跨期多记':
    case '跨期漏记':
      return '跨期'
    case '证据不完整':
      return '证据不完整'
    case '需调整':
      return '需调整'
    case '已调整':
      return '已调整'
    case '待检查':
    case '待追查':
    case '':
      return '待追查'
    default:
      return '待追查'
  }
}

/**
 * 由样本双侧证据派生默认结论（Req2.2/Req4）。手工结论优先由调用方处理，
 * 本函数仅作缺省回退。
 * - 无证据 / 缺任一侧日期 → '证据不完整'（绝不判'正常'）
 * - 双侧齐全跨期 → '跨期'
 * - 双侧齐全同期 → '正常'
 */
export function deriveConclusion(
  pair: CutoffDatePair,
  cutoffDate: string,
  mode: CutoffMode,
): CutoffConclusion {
  const verdict = judgeCrossPeriod(pair, cutoffDate, mode)
  // 双侧证据齐全 = 两侧日期均可解析（与 judgeCrossPeriod 在场判定一致）
  const bothValid = !!parseDate(pair.bookDate) && !!parseDate(pair.documentDate)
  switch (verdict) {
    case 'crossing':
      return '跨期'
    case 'same':
      // 双侧齐全同期 → 正常；单侧/非法（缺独立证据）→ 证据不完整
      return bothValid ? '正常' : '证据不完整'
    case 'suspect':
      // 单侧且晚于截止日 → 缺另一侧证据的跨期疑点 → 证据不完整（需补录后再判）
      return '证据不完整'
    case 'none':
    default:
      return '证据不完整'
  }
}
