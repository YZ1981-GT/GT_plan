/**
 * F2-29~32 截止细判：同侧/跨期方向、证据缺口、金额勾稽
 */
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

/** 跨期方向细判（需单据日、记账日、截止日齐全） */
export function classifyCutoffTiming(
  docDate: string,
  bookDate: string,
  periodEnd: string,
): CutoffTimingKind {
  const doc = parseDay(docDate)
  const book = parseDay(bookDate)
  const end = parseDay(periodEnd)
  if (doc == null || book == null || end == null) return 'incomplete'
  const docOnOrBefore = doc <= end
  const bookOnOrBefore = book <= end
  if (docOnOrBefore === bookOnOrBefore) return 'ok'
  // 账在期内、单在期后 → 提前入账（多记当期）
  if (bookOnOrBefore && !docOnOrBefore) return 'early_book'
  // 单在期内、账在期后 → 推迟入账（漏记当期）
  if (docOnOrBefore && !bookOnOrBefore) return 'late_book'
  return 'cross_other'
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
