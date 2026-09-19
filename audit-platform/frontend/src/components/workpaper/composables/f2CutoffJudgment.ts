/**
 * F2-29~32 截止细判：同侧/跨期方向、证据缺口、金额勾稽
 *
 * 收敛（cutoff-test-architecture-convergence 第三模式）：跨期方向判定委托
 * cutoffCanonical.classifyCutoffBoundary（XOR 算术单一真源），F2 仅做 early_book/late_book
 * 等业务子类映射与证据/金额勾稽（F2 独有的更丰富语义）。
 */
import { classifyCutoffBoundary } from './cutoffCanonical'

export type CutoffTimingKind =
  | 'ok'
  | 'early_book'   // 记账在截止日前（或当日），单据在截止日后 → 提前入账
  | 'late_book'    // 单据在截止日前，记账在截止日后 → 推迟入账
  | 'cross_other'  // 其他分侧情形
  | 'incomplete'   // 日期不全，无法细判
  | 'invalid'

export type CutoffEvidenceGap =
  | ''
  | 'missing_doc'    // 有账无单
  | 'missing_book'   // 有单无账
  | 'amount_mismatch'

export interface CutoffFineJudge {
  timing: CutoffTimingKind
  evidenceGap: CutoffEvidenceGap
  isCrossPeriod: boolean
  isCorrect: boolean
  suggestion: string
}

function parseDay(s: string): number | null {
  if (!s) return null
  const t = new Date(s + 'T00:00:00').getTime()
  return Number.isNaN(t) ? null : t
}

/** 跨期方向细判（需单据日、记账日、截止日齐全）——委托 canonical 第三模式基座 */
export function classifyCutoffTiming(
  docDate: string,
  bookDate: string,
  periodEnd: string,
): CutoffTimingKind {
  // 跨期方向判定收敛到 cutoffCanonical.classifyCutoffBoundary（XOR 算术单一真源）
  const cls = classifyCutoffBoundary(bookDate, docDate, periodEnd)
  switch (cls) {
    case 'incomplete':
      return 'incomplete'
    case 'same':
      return 'ok'
    case 'book-before-doc-after':
      // 账在期内、单在期后 → 提前入账（多记当期）
      return 'early_book'
    case 'doc-before-book-after':
      // 单在期内、账在期后 → 推迟入账（漏记当期）
      return 'late_book'
    default:
      return 'cross_other'
  }
}

export function detectEvidenceGap(opts: {
  voucherNo: string
  bookDate: string
  docNo: string
  docDate: string
  amount: number
  docAmount?: number
}): CutoffEvidenceGap {
  const hasBook = !!(opts.voucherNo || opts.bookDate)
  const hasDoc = !!(opts.docNo || opts.docDate)
  if (hasBook && !hasDoc) return 'missing_doc'
  if (hasDoc && !hasBook) return 'missing_book'
  const da = opts.docAmount
  if (
    da != null
    && Number.isFinite(da)
    && da > 0
    && opts.amount > 0
    && Math.abs(da - opts.amount) > 0.01
  ) {
    return 'amount_mismatch'
  }
  return ''
}

const TIMING_LABEL: Record<CutoffTimingKind, string> = {
  ok: '',
  early_book: '提前入账：记账日落在截止日（含）前，单据日在截止日后',
  late_book: '推迟入账：单据日落在截止日（含）前，记账日在截止日后',
  cross_other: '单据日与记账日分落截止日两侧',
  incomplete: '请补全单据日与记账日以便判定',
  invalid: '日期无效',
}

const EVIDENCE_LABEL: Record<Exclude<CutoffEvidenceGap, ''>, string> = {
  missing_doc: '有账无单：请补全入库/出库单号与日期',
  missing_book: '有单无账：请补全记账凭证号与日期',
  amount_mismatch: '账金额与单据金额不一致，请核实',
}

export function assessCutoffRow(opts: {
  docDate: string
  bookDate: string
  periodEnd: string
  voucherNo: string
  docNo: string
  amount: number
  docAmount?: number
  overrideCorrect?: boolean | null
}): CutoffFineJudge {
  const timing = classifyCutoffTiming(opts.docDate, opts.bookDate, opts.periodEnd)
  const evidenceGap = detectEvidenceGap({
    voucherNo: opts.voucherNo,
    bookDate: opts.bookDate,
    docNo: opts.docNo,
    docDate: opts.docDate,
    amount: opts.amount,
    docAmount: opts.docAmount,
  })

  const hasBothDates = !!(opts.docDate && opts.bookDate && opts.periodEnd)
  const autoCross = hasBothDates && timing !== 'ok' && timing !== 'incomplete'
  const autoCorrect = hasBothDates
    ? timing === 'ok' && !evidenceGap
    : evidenceGap !== 'missing_doc' && evidenceGap !== 'missing_book'

  // 证据缺口时默认不正确（可覆盖）
  let isCorrect = autoCorrect
  if (evidenceGap === 'missing_doc' || evidenceGap === 'missing_book' || evidenceGap === 'amount_mismatch') {
    isCorrect = false
  }
  if (opts.overrideCorrect !== null && opts.overrideCorrect !== undefined) {
    isCorrect = opts.overrideCorrect
  }

  const parts: string[] = []
  if (TIMING_LABEL[timing]) parts.push(TIMING_LABEL[timing])
  if (evidenceGap) parts.push(EVIDENCE_LABEL[evidenceGap])

  return {
    timing,
    evidenceGap,
    isCrossPeriod: opts.overrideCorrect != null ? !opts.overrideCorrect : autoCross,
    isCorrect,
    suggestion: parts.join('；') || '',
  }
}

export function timingKindLabel(kind: CutoffTimingKind): string {
  switch (kind) {
    case 'early_book': return '提前入账'
    case 'late_book': return '推迟入账'
    case 'cross_other': return '跨期'
    case 'incomplete': return '待补日期'
    case 'invalid': return '无效'
    default: return '正常'
  }
}

/** 截止逐笔勾稽项（引导弹窗实时面板；与 assessCutoffRow 同源） */
export interface CutoffCheckResult {
  key: string
  label: string
  status: 'ok' | 'mismatch' | 'missing' | 'pending'
  detail: string
}

export function evaluateCutoffChecks(opts: {
  voucherNo: string
  bookDate: string
  docNo: string
  docDate: string
  amount: number
  docAmount?: number
  periodEnd: string
}): CutoffCheckResult[] {
  const judge = assessCutoffRow({
    docDate: opts.docDate,
    bookDate: opts.bookDate,
    periodEnd: opts.periodEnd,
    voucherNo: opts.voucherNo,
    docNo: opts.docNo,
    amount: opts.amount,
    docAmount: opts.docAmount,
  })
  const results: CutoffCheckResult[] = []

  const hasBook = !!(opts.voucherNo || opts.bookDate)
  const hasDoc = !!(opts.docNo || opts.docDate)

  if (hasBook && !hasDoc) {
    results.push({ key: 'doc', label: '原始单据', status: 'missing', detail: '有账无单' })
  } else if (hasDoc && !hasBook) {
    results.push({ key: 'book', label: '记账凭证', status: 'missing', detail: '有单无账' })
  } else if (hasBook && hasDoc) {
    results.push({ key: 'pair', label: '账证配对', status: 'ok', detail: '账、单均已填写' })
  } else {
    results.push({ key: 'pair', label: '账证配对', status: 'pending', detail: '待填写' })
  }

  if (!opts.docDate || !opts.bookDate || !opts.periodEnd) {
    results.push({ key: 'timing', label: '截止细判', status: 'pending', detail: '请补全单据日/记账日/截止日' })
  } else if (judge.timing === 'ok') {
    results.push({ key: 'timing', label: '截止细判', status: 'ok', detail: '同侧 · 期间归属正确' })
  } else {
    results.push({
      key: 'timing',
      label: '截止细判',
      status: 'mismatch',
      detail: timingKindLabel(judge.timing) + (TIMING_LABEL[judge.timing] ? `：${TIMING_LABEL[judge.timing]}` : ''),
    })
  }

  if (judge.evidenceGap === 'amount_mismatch') {
    results.push({
      key: 'amount',
      label: '金额勾稽',
      status: 'mismatch',
      detail: `账 ${opts.amount} vs 单 ${opts.docAmount}`,
    })
  } else if ((opts.docAmount ?? 0) > 0 && opts.amount > 0) {
    results.push({ key: 'amount', label: '金额勾稽', status: 'ok', detail: '一致' })
  } else {
    results.push({ key: 'amount', label: '金额勾稽', status: 'pending', detail: '单据金额可选填' })
  }

  return results
}
