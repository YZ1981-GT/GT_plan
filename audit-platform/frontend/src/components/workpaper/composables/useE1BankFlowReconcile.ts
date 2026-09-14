/**
 * useE1BankFlowReconcile — E1-31 银行流水双向核对
 *
 * - （一）月度：对账单 vs 日记账 + 差额/差异率
 * - （二）日记账 → 流水抽样核对
 * - （三）流水 → 日记账抽样核对
 * - OCR 流水明细 + 金额/日期自动匹配
 * - 覆盖率 + 红旗提示 + 说明/结论
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { UseE1BaseOptions, ChecklistItem } from './useE1Adjudication'
import { parseNum } from './useE1FormulaEngine'

export const E1_BANK_FLOW_PACK_KEY = 'E1-bank-flow-pack'
export const E1_BANK_FLOW_NOTE_KEY = 'E1-bank-flow-audit-note'
export const E1_BANK_FLOW_CONCLUSION_KEY = 'E1-bank-flow-audit-conclusion'
export const E1_IPO_APPLICABLE_KEY = 'E1-ipo-applicable'
const LEGACY_ROWS_KEY = 'E1-ipo-E1-31-rows'

export type YesNo = '是' | '否' | ''
export type CheckReason = '大额' | '关联交易' | '双向交易' | '其他' | ''
export type FlowDirection = '收入' | '支出' | ''

export interface StatementLine {
  id: string
  date: string
  summary: string
  counterparty: string
  amount: number
  direction: FlowDirection
  source: string
}

export interface JournalLine {
  id: string
  date: string
  voucherNo: string
  businessContent: string
  counterAccount: string
  counterparty: string
  debit: number
  credit: number
  source: string
}

export interface MonthlyRow {
  month: number
  stmtIncome: number
  stmtExpense: number
  stmtBalance: number
  journalDebit: number
  journalCredit: number
  journalBalance: number
}

export interface BidirectCheckRow {
  id: string
  checkReason: CheckReason
  vDate: string
  voucherNo: string
  businessContent: string
  counterAccount: string
  counterparty: string
  debit: number
  credit: number
  sDate: string
  summary: string
  payerPayee: string
  stmtAmount: number
  infoConsistent: YesNo
  thirdParty: YesNo
  inconsistencyReason: string
  supportDocs: string
  conclusion: string
}

export interface TipFlag {
  key: string
  label: string
  checked: boolean
  note: string
}

export interface OcrJobMeta {
  id: string
  fileName: string
  attachmentId?: string
  at: string
  lineCount: number
  skippedCount: number
  confidence: number
  bank?: string
  accountNo?: string
}

export interface BankFlowPack {
  bank: string
  accountNo: string
  largeThresholdBookToBank: number
  largeThresholdBankToBook: number
  statementLines: StatementLine[]
  journalLines: JournalLine[]
  monthly: MonthlyRow[]
  bookToBank: BidirectCheckRow[]
  bankToBook: BidirectCheckRow[]
  coverageLowReason: string
  tips: TipFlag[]
  /** OCR 回填审计轨迹 */
  ocrJobs?: OcrJobMeta[]
}

export const TIP_DEFS: Array<{ key: string; label: string }> = [
  { key: 'icWeak', label: '资金管理内部控制存在较大缺陷' },
  { key: 'unrecordedAcct', label: '存在账外账户或账户发生额未完整反映' },
  { key: 'scaleMismatch', label: '大额资金流动与经营活动/筹资投资不匹配' },
  { key: 'rpLarge', label: '与股东/实控人/董监高存在异常大额资金往来' },
  { key: 'cashWithdraw', label: '频繁或大额取现且无合理理由' },
  { key: 'intangiblePay', label: '大额购无形资产/咨询等付款商业实质存疑' },
  { key: 'controllerPersonal', label: '实控人个人账户资金进出频繁/大额' },
  { key: 'dividendTransfer', label: '大额分红、股权转让款或款项用途异常' },
  { key: 'rpCustomerVendor', label: '与关联客户/供应商异常大额往来' },
  { key: 'thirdParty', label: '存在第三方代收代付安排' },
]

function uid(prefix: string): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `${prefix}-${crypto.randomUUID()}`
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

function emptyMonthly(): MonthlyRow[] {
  return Array.from({ length: 12 }, (_, i) => ({
    month: i + 1,
    stmtIncome: 0,
    stmtExpense: 0,
    stmtBalance: 0,
    journalDebit: 0,
    journalCredit: 0,
    journalBalance: 0,
  }))
}

function emptyTips(): TipFlag[] {
  return TIP_DEFS.map(t => ({ key: t.key, label: t.label, checked: false, note: '' }))
}

export function createEmptyStatementLine(): StatementLine {
  return {
    id: uid('st'),
    date: '',
    summary: '',
    counterparty: '',
    amount: 0,
    direction: '',
    source: 'manual',
  }
}

export function createEmptyJournalLine(): JournalLine {
  return {
    id: uid('jl'),
    date: '',
    voucherNo: '',
    businessContent: '',
    counterAccount: '',
    counterparty: '',
    debit: 0,
    credit: 0,
    source: 'manual',
  }
}

export function createEmptyCheckRow(): BidirectCheckRow {
  return {
    id: uid('ck'),
    checkReason: '',
    vDate: '',
    voucherNo: '',
    businessContent: '',
    counterAccount: '',
    counterparty: '',
    debit: 0,
    credit: 0,
    sDate: '',
    summary: '',
    payerPayee: '',
    stmtAmount: 0,
    infoConsistent: '',
    thirdParty: '',
    inconsistencyReason: '',
    supportDocs: '',
    conclusion: '',
  }
}

function emptyPack(): BankFlowPack {
  return {
    bank: '',
    accountNo: '',
    largeThresholdBookToBank: 0,
    largeThresholdBankToBook: 0,
    statementLines: [],
    journalLines: [],
    monthly: emptyMonthly(),
    bookToBank: [],
    bankToBook: [],
    coverageLowReason: '',
    tips: emptyTips(),
    ocrJobs: [],
  }
}

function yn(v: unknown): YesNo {
  return v === '是' || v === '否' ? v : ''
}

function parseDirection(v: unknown, amount?: number): FlowDirection {
  const s = String(v || '')
  if (s.includes('收') || s === '收入' || s === '贷' || s.toLowerCase() === 'credit' || s === 'C') return '收入'
  if (s.includes('支') || s === '支出' || s === '借' || s.toLowerCase() === 'debit' || s === 'D') return '支出'
  if (typeof amount === 'number' && amount < 0) return '支出'
  return ''
}

function normalizeStatement(raw: Record<string, unknown>): StatementLine {
  const amount = Math.abs(parseNum(raw.amount ?? raw.stmtAmount))
  return {
    id: String(raw.id || uid('st')),
    date: String(raw.date || raw.sDate || ''),
    summary: String(raw.summary || ''),
    counterparty: String(raw.counterparty || raw.payerPayee || ''),
    amount,
    direction: parseDirection(raw.direction || raw.transaction_type, parseNum(raw.amount)),
    source: String(raw.source || 'manual'),
  }
}

function normalizeJournal(raw: Record<string, unknown>): JournalLine {
  return {
    id: String(raw.id || uid('jl')),
    date: String(raw.date || raw.vDate || ''),
    voucherNo: String(raw.voucherNo || ''),
    businessContent: String(raw.businessContent || ''),
    counterAccount: String(raw.counterAccount || ''),
    counterparty: String(raw.counterparty || ''),
    debit: parseNum(raw.debit),
    credit: parseNum(raw.credit),
    source: String(raw.source || 'manual'),
  }
}

function normalizeCheck(raw: Record<string, unknown>): BidirectCheckRow {
  const reason = String(raw.checkReason || '') as CheckReason
  const okReason: CheckReason = ['大额', '关联交易', '双向交易', '其他'].includes(reason)
    ? reason
    : ''
  return {
    id: String(raw.id || uid('ck')),
    checkReason: okReason,
    vDate: String(raw.vDate || raw.date || ''),
    voucherNo: String(raw.voucherNo || ''),
    businessContent: String(raw.businessContent || ''),
    counterAccount: String(raw.counterAccount || ''),
    counterparty: String(raw.counterparty || ''),
    debit: parseNum(raw.debit),
    credit: parseNum(raw.credit),
    sDate: String(raw.sDate || ''),
    summary: String(raw.summary || ''),
    payerPayee: String(raw.payerPayee || ''),
    stmtAmount: parseNum(raw.stmtAmount ?? raw.amount),
    infoConsistent: yn(raw.infoConsistent),
    thirdParty: yn(raw.thirdParty),
    inconsistencyReason: String(raw.inconsistencyReason || ''),
    supportDocs: String(raw.supportDocs || ''),
    conclusion: String(raw.conclusion || ''),
  }
}

function monthOf(date: string): number {
  if (!date || date.length < 7) return 0
  const m = parseInt(date.slice(5, 7), 10)
  return m >= 1 && m <= 12 ? m : 0
}

function dayDiff(a: string, b: string): number {
  if (!a || !b || a.length < 10 || b.length < 10) return 999
  const da = Date.parse(a.slice(0, 10))
  const db = Date.parse(b.slice(0, 10))
  if (!Number.isFinite(da) || !Number.isFinite(db)) return 999
  return Math.abs(Math.round((da - db) / 86400000))
}

function approxEq(a: number, b: number, tol = 0.01): boolean {
  return Math.abs(a - b) <= tol
}

function journalAmount(j: JournalLine): number {
  return Math.max(parseNum(j.debit), parseNum(j.credit))
}

export function diffPair(stmt: number, journal: number): { amount: number; rate: number | null } {
  const amount = parseNum(stmt) - parseNum(journal)
  if (parseNum(stmt) === 0) return { amount, rate: parseNum(journal) === 0 ? 0 : null }
  return { amount, rate: amount / parseNum(stmt) }
}

/** 日记账列表合并（纯函数）：append | replace | merge(凭证号+日期+借贷) */
export function mergeJournalLineLists(
  existing: JournalLine[],
  incoming: JournalLine[],
  fillMode: 'append' | 'replace' | 'merge',
): JournalLine[] {
  if (!incoming.length) return existing
  if (fillMode === 'replace') return [...incoming]
  if (fillMode === 'merge') {
    const keyOf = (j: JournalLine) =>
      `${j.voucherNo}|${j.date}|${j.debit}|${j.credit}`
    const map = new Map(existing.map(j => [keyOf(j), j]))
    for (const j of incoming) map.set(keyOf(j), j)
    return Array.from(map.values())
  }
  return [...existing, ...incoming]
}

export type AutoMatchMode = 'replace' | 'merge'

export interface AutoMatchResult {
  bookToBank: number
  bankToBook: number
  matchedBook: number
  unmatchedBook: number
  matchedBank: number
  unmatchedBank: number
  preserved: number
  mode: AutoMatchMode
}

export function useE1BankFlowReconcile(options: UseE1BaseOptions) {
  const { allResponses, saveImmediate, isReadonly } = options

  const pack = ref<BankFlowPack>(emptyPack())
  const auditNote = ref('')
  const auditConclusion = ref('')
  const isLoading = ref(false)

  const isApplicable = computed(() => {
    const v = allResponses.value.get(E1_IPO_APPLICABLE_KEY)?.conclusion
    return v !== 'N'
  })

  const monthlyTotals = computed(() => {
    const init = {
      stmtIncome: 0,
      stmtExpense: 0,
      journalDebit: 0,
      journalCredit: 0,
    }
    return pack.value.monthly.reduce(
      (acc, r) => ({
        stmtIncome: acc.stmtIncome + parseNum(r.stmtIncome),
        stmtExpense: acc.stmtExpense + parseNum(r.stmtExpense),
        journalDebit: acc.journalDebit + parseNum(r.journalDebit),
        journalCredit: acc.journalCredit + parseNum(r.journalCredit),
      }),
      init,
    )
  })

  const coverage = computed(() => {
    const bookDr = monthlyTotals.value.journalDebit
    const bookCr = monthlyTotals.value.journalCredit
    const b2bDr = pack.value.bookToBank.reduce((s, r) => s + parseNum(r.debit), 0)
    const b2bCr = pack.value.bookToBank.reduce((s, r) => s + parseNum(r.credit), 0)
    const s2bDr = pack.value.bankToBook.reduce((s, r) => s + parseNum(r.debit), 0)
    const s2bCr = pack.value.bankToBook.reduce((s, r) => s + parseNum(r.credit), 0)
    // 从流水侧核查：金额用 stmtAmount 拆分按借贷方向较难，按行记到借或贷同 E1 模板：
    // 模板用 K80(借侧流水已核) / L80(贷侧) — 用 debit/credit 字段在 bankToBook 中填写
    const ratio = (num: number, den: number) => (den === 0 ? null : num / den)
    return {
      bookDr,
      bookCr,
      bookToBankDr: b2bDr,
      bookToBankCr: b2bCr,
      bankToBookDr: s2bDr,
      bankToBookCr: s2bCr,
      ratio1Dr: ratio(b2bDr, bookDr),
      ratio1Cr: ratio(b2bCr, bookCr),
      ratio2Dr: ratio(s2bDr, bookDr),
      ratio2Cr: ratio(s2bCr, bookCr),
    }
  })

  const mismatchMonthlyCount = computed(() =>
    pack.value.monthly.filter(r => {
      const d1 = diffPair(r.stmtIncome, r.journalDebit)
      const d2 = diffPair(r.stmtExpense, r.journalCredit)
      const d3 = diffPair(r.stmtBalance, r.journalBalance)
      return Math.abs(d1.amount) > 0.01 || Math.abs(d2.amount) > 0.01 || Math.abs(d3.amount) > 0.01
    }).length,
  )

  function load(): void {
    isLoading.value = true
    try {
      const raw = allResponses.value.get(E1_BANK_FLOW_PACK_KEY)?.remark
      if (raw) {
        try {
          const parsed = JSON.parse(raw)
          if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
            const tipMap = new Map(
              (Array.isArray(parsed.tips) ? parsed.tips : []).map((t: any) => [String(t.key), t]),
            )
            pack.value = {
              bank: String(parsed.bank || ''),
              accountNo: String(parsed.accountNo || ''),
              largeThresholdBookToBank: parseNum(parsed.largeThresholdBookToBank),
              largeThresholdBankToBook: parseNum(parsed.largeThresholdBankToBook),
              statementLines: Array.isArray(parsed.statementLines)
                ? parsed.statementLines.map((r: any) => normalizeStatement(r))
                : [],
              journalLines: Array.isArray(parsed.journalLines)
                ? parsed.journalLines.map((r: any) => normalizeJournal(r))
                : [],
              monthly: Array.isArray(parsed.monthly) && parsed.monthly.length === 12
                ? parsed.monthly.map((r: any, i: number) => ({
                    month: parseNum(r.month) || i + 1,
                    stmtIncome: parseNum(r.stmtIncome),
                    stmtExpense: parseNum(r.stmtExpense),
                    stmtBalance: parseNum(r.stmtBalance),
                    journalDebit: parseNum(r.journalDebit),
                    journalCredit: parseNum(r.journalCredit),
                    journalBalance: parseNum(r.journalBalance),
                  }))
                : emptyMonthly(),
              bookToBank: Array.isArray(parsed.bookToBank)
                ? parsed.bookToBank.map((r: any) => normalizeCheck(r))
                : [],
              bankToBook: Array.isArray(parsed.bankToBook)
                ? parsed.bankToBook.map((r: any) => normalizeCheck(r))
                : [],
              coverageLowReason: String(parsed.coverageLowReason || ''),
              tips: TIP_DEFS.map(d => {
                const t = tipMap.get(d.key) as any
                return {
                  key: d.key,
                  label: d.label,
                  checked: !!(t && t.checked),
                  note: String(t?.note || ''),
                }
              }),
              ocrJobs: Array.isArray(parsed.ocrJobs)
                ? parsed.ocrJobs.slice(-20).map((j: any) => ({
                    id: String(j.id || uid('ocr')),
                    fileName: String(j.fileName || ''),
                    attachmentId: j.attachmentId ? String(j.attachmentId) : undefined,
                    at: String(j.at || ''),
                    lineCount: parseNum(j.lineCount),
                    skippedCount: parseNum(j.skippedCount),
                    confidence: parseNum(j.confidence),
                    bank: j.bank ? String(j.bank) : undefined,
                    accountNo: j.accountNo ? String(j.accountNo) : undefined,
                  }))
                : [],
            }
          }
        } catch {
          pack.value = emptyPack()
        }
      } else {
        // 旧月度扁平行迁移
        const legacy = allResponses.value.get(LEGACY_ROWS_KEY)?.remark
        if (legacy) {
          try {
            const list = JSON.parse(legacy)
            if (Array.isArray(list) && list.length) {
              const monthly = emptyMonthly()
              for (const r of list) {
                const m = parseNum(r.month)
                if (m >= 1 && m <= 12) {
                  monthly[m - 1] = {
                    month: m,
                    stmtIncome: parseNum(r.stmtIncome),
                    stmtExpense: parseNum(r.stmtExpense),
                    stmtBalance: parseNum(r.stmtBalance),
                    journalDebit: parseNum(r.journalDebit),
                    journalCredit: parseNum(r.journalCredit),
                    journalBalance: parseNum(r.journalBalance),
                  }
                }
              }
              pack.value = { ...emptyPack(), monthly }
            } else {
              pack.value = emptyPack()
            }
          } catch {
            pack.value = emptyPack()
          }
        } else {
          pack.value = emptyPack()
        }
      }
      auditNote.value = allResponses.value.get(E1_BANK_FLOW_NOTE_KEY)?.remark
        || allResponses.value.get('E1-ipo-audit-note-E1-31')?.remark
        || ''
      auditConclusion.value = allResponses.value.get(E1_BANK_FLOW_CONCLUSION_KEY)?.remark
        || allResponses.value.get('E1-ipo-audit-conclusion-E1-31')?.remark
        || ''
    } finally {
      isLoading.value = false
    }
  }

  load()

  watch(
    () => allResponses.value.get(E1_BANK_FLOW_PACK_KEY)?.remark,
    (n, o) => { if (n !== o) load() },
  )

  let saveTimer: ReturnType<typeof setTimeout> | null = null
  function scheduleSave(): void {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      persist()
    }, 2000)
  }

  function persist(): void {
    const item: ChecklistItem = {
      item_id: E1_BANK_FLOW_PACK_KEY,
      conclusion: null,
      remark: JSON.stringify(pack.value),
    }
    allResponses.value.set(E1_BANK_FLOW_PACK_KEY, item)
    saveImmediate([item]).catch(() => {})
  }

  function setApplicable(val: boolean): void {
    if (isReadonly.value) return
    const item = {
      item_id: E1_IPO_APPLICABLE_KEY,
      conclusion: val ? 'Y' : 'N',
      remark: null,
    }
    allResponses.value.set(E1_IPO_APPLICABLE_KEY, item)
    saveImmediate([item]).catch(() => {})
  }

  function patchPack(partial: Partial<BankFlowPack>): void {
    if (isReadonly.value) return
    pack.value = { ...pack.value, ...partial }
    scheduleSave()
  }

  function updateMeta(field: 'bank' | 'accountNo', value: string): void {
    patchPack({ [field]: value })
  }

  function setThreshold(side: 'bookToBank' | 'bankToBook', value: number): void {
    if (side === 'bookToBank') patchPack({ largeThresholdBookToBank: parseNum(value) })
    else patchPack({ largeThresholdBankToBook: parseNum(value) })
  }

  function updateMonthly(month: number, field: keyof Omit<MonthlyRow, 'month'>, value: number): void {
    if (isReadonly.value) return
    pack.value = {
      ...pack.value,
      monthly: pack.value.monthly.map(r =>
        r.month === month ? { ...r, [field]: parseNum(value) } : r,
      ),
    }
    scheduleSave()
  }

  /** 用流水/日记账明细回填月度发生额（不覆盖余额，由人工填期末） */
  function recalcMonthlyFromLines(): void {
    if (isReadonly.value) return
    const next = emptyMonthly()
    for (const s of pack.value.statementLines) {
      const m = monthOf(s.date)
      if (!m) continue
      if (s.direction === '支出') next[m - 1].stmtExpense += parseNum(s.amount)
      else next[m - 1].stmtIncome += parseNum(s.amount)
    }
    for (const j of pack.value.journalLines) {
      const m = monthOf(j.date)
      if (!m) continue
      next[m - 1].journalDebit += parseNum(j.debit)
      next[m - 1].journalCredit += parseNum(j.credit)
    }
    // 保留原有余额
    pack.value = {
      ...pack.value,
      monthly: next.map((r, i) => ({
        ...r,
        stmtBalance: pack.value.monthly[i]?.stmtBalance || 0,
        journalBalance: pack.value.monthly[i]?.journalBalance || 0,
      })),
    }
    scheduleSave()
  }

  function addStatementLine(partial?: Partial<StatementLine>): void {
    if (isReadonly.value) return
    pack.value = {
      ...pack.value,
      statementLines: [...pack.value.statementLines, { ...createEmptyStatementLine(), ...partial }],
    }
    scheduleSave()
  }

  function removeStatementLine(id: string): void {
    if (isReadonly.value) return
    pack.value = {
      ...pack.value,
      statementLines: pack.value.statementLines.filter(r => r.id !== id),
    }
    scheduleSave()
  }

  function updateStatementLine(id: string, field: keyof StatementLine, value: unknown): void {
    if (isReadonly.value) return
    pack.value = {
      ...pack.value,
      statementLines: pack.value.statementLines.map(r =>
        r.id === id ? { ...r, [field]: value } : r,
      ),
    }
    scheduleSave()
  }

  function mergeOcrStatementLines(
    lines: Array<Partial<StatementLine>>,
    meta?: {
      bank?: string
      accountNo?: string
      ocrJob?: Omit<OcrJobMeta, 'id' | 'at'> & { id?: string; at?: string }
    },
  ): number {
    if (isReadonly.value) return 0
    const mapped = lines
      .map(r => normalizeStatement({ ...r, source: r.source || 'ocr' }))
      .filter(r => r.date || r.amount || r.counterparty)
    if (!mapped.length) return 0
    const next: Partial<BankFlowPack> = {
      statementLines: [...pack.value.statementLines, ...mapped],
    }
    if (meta?.bank && !pack.value.bank) next.bank = meta.bank
    if (meta?.accountNo && !pack.value.accountNo) next.accountNo = meta.accountNo
    pack.value = { ...pack.value, ...next }
    if (meta?.ocrJob) {
      recordOcrJob({
        ...meta.ocrJob,
        lineCount: meta.ocrJob.lineCount ?? mapped.length,
        bank: meta.ocrJob.bank || meta.bank,
        accountNo: meta.ocrJob.accountNo || meta.accountNo,
      })
    } else {
      scheduleSave()
    }
    return mapped.length
  }

  function recordOcrJob(partial: Omit<OcrJobMeta, 'id' | 'at'> & { id?: string; at?: string }): void {
    if (isReadonly.value) return
    const job: OcrJobMeta = {
      id: partial.id || uid('ocr'),
      fileName: partial.fileName || '',
      attachmentId: partial.attachmentId,
      at: partial.at || new Date().toISOString(),
      lineCount: partial.lineCount || 0,
      skippedCount: partial.skippedCount || 0,
      confidence: partial.confidence || 0,
      bank: partial.bank,
      accountNo: partial.accountNo,
    }
    const prev = Array.isArray(pack.value.ocrJobs) ? pack.value.ocrJobs : []
    pack.value = { ...pack.value, ocrJobs: [...prev, job].slice(-20) }
    scheduleSave()
  }

  function addJournalLine(partial?: Partial<JournalLine>): void {
    if (isReadonly.value) return
    pack.value = {
      ...pack.value,
      journalLines: [...pack.value.journalLines, { ...createEmptyJournalLine(), ...partial }],
    }
    scheduleSave()
  }

  /** 抽凭/导入日记账：append 追加；replace 整表替换；merge 按凭证号+日期去重合并 */
  function mergeJournalLines(
    rows: Array<Partial<JournalLine>>,
    fillMode: 'append' | 'replace' | 'merge' = 'append',
  ): number {
    if (isReadonly.value) return 0
    const mapped = rows
      .map(r => normalizeJournal({ ...r, source: r.source || '抽凭' }))
      .filter(r => r.date || r.voucherNo || r.debit || r.credit)
    if (!mapped.length) return 0

    pack.value = {
      ...pack.value,
      journalLines: mergeJournalLineLists(pack.value.journalLines, mapped, fillMode),
    }
    scheduleSave()
    return mapped.length
  }

  function removeJournalLine(id: string): void {
    if (isReadonly.value) return
    pack.value = {
      ...pack.value,
      journalLines: pack.value.journalLines.filter(r => r.id !== id),
    }
    scheduleSave()
  }

  function updateJournalLine(id: string, field: keyof JournalLine, value: unknown): void {
    if (isReadonly.value) return
    pack.value = {
      ...pack.value,
      journalLines: pack.value.journalLines.map(r =>
        r.id === id ? { ...r, [field]: value } : r,
      ),
    }
    scheduleSave()
  }

  function updateCheckRow(
    side: 'bookToBank' | 'bankToBook',
    id: string,
    field: keyof BidirectCheckRow,
    value: unknown,
  ): void {
    if (isReadonly.value) return
    pack.value = {
      ...pack.value,
      [side]: pack.value[side].map(r => (r.id === id ? { ...r, [field]: value } : r)),
    }
    scheduleSave()
  }

  function addCheckRow(side: 'bookToBank' | 'bankToBook', partial?: Partial<BidirectCheckRow>): void {
    if (isReadonly.value) return
    pack.value = {
      ...pack.value,
      [side]: [...pack.value[side], { ...createEmptyCheckRow(), ...partial }],
    }
    scheduleSave()
  }

  function removeCheckRow(side: 'bookToBank' | 'bankToBook', id: string): void {
    if (isReadonly.value) return
    pack.value = {
      ...pack.value,
      [side]: pack.value[side].filter(r => r.id !== id),
    }
    scheduleSave()
  }

  function checkKeyBook(r: BidirectCheckRow): string {
    return `b|${r.voucherNo}|${r.vDate}|${r.debit}|${r.credit}`
  }

  function checkKeyBank(r: BidirectCheckRow): string {
    return `s|${r.sDate}|${r.stmtAmount}|${r.payerPayee}|${r.summary}`
  }

  function isManuallyTouched(r: BidirectCheckRow): boolean {
    return !!(
      r.thirdParty
      || r.inconsistencyReason
      || r.supportDocs
      || r.conclusion
      || (r.infoConsistent && r.infoConsistent !== '是')
    )
  }

  function buildMatchCandidates(): {
    bookToBank: BidirectCheckRow[]
    bankToBook: BidirectCheckRow[]
    matchedBook: number
    unmatchedBook: number
    matchedBank: number
    unmatchedBank: number
  } {
    const thrB = parseNum(pack.value.largeThresholdBookToBank)
    const thrS = parseNum(pack.value.largeThresholdBankToBook)
    const usedStmt = new Set<string>()
    const usedJrnl = new Set<string>()

    const bookToBank: BidirectCheckRow[] = []
    let matchedBook = 0
    let unmatchedBook = 0

    for (const j of pack.value.journalLines) {
      const amt = journalAmount(j)
      if (thrB > 0 && amt < thrB) continue
      if (!amt) continue
      const hit = pack.value.statementLines.find(s => {
        if (usedStmt.has(s.id)) return false
        if (!approxEq(parseNum(s.amount), amt)) return false
        return dayDiff(j.date, s.date) <= 1
      })
      if (hit) {
        usedStmt.add(hit.id)
        usedJrnl.add(j.id)
        matchedBook += 1
        bookToBank.push({
          ...createEmptyCheckRow(),
          checkReason: thrB > 0 && amt >= thrB ? '大额' : '其他',
          vDate: j.date,
          voucherNo: j.voucherNo,
          businessContent: j.businessContent,
          counterAccount: j.counterAccount,
          counterparty: j.counterparty,
          debit: j.debit,
          credit: j.credit,
          sDate: hit.date,
          summary: hit.summary,
          payerPayee: hit.counterparty,
          stmtAmount: hit.amount,
          infoConsistent: '是',
        })
      } else {
        unmatchedBook += 1
        bookToBank.push({
          ...createEmptyCheckRow(),
          checkReason: '大额',
          vDate: j.date,
          voucherNo: j.voucherNo,
          businessContent: j.businessContent,
          counterAccount: j.counterAccount,
          counterparty: j.counterparty,
          debit: j.debit,
          credit: j.credit,
          infoConsistent: '',
        })
      }
    }

    const bankToBook: BidirectCheckRow[] = []
    let matchedBank = 0
    let unmatchedBank = 0

    for (const s of pack.value.statementLines) {
      if (usedStmt.has(s.id)) continue
      const amt = parseNum(s.amount)
      if (thrS > 0 && amt < thrS) continue
      if (!amt) continue
      const hit = pack.value.journalLines.find(j => {
        if (usedJrnl.has(j.id)) return false
        if (!approxEq(journalAmount(j), amt)) return false
        return dayDiff(j.date, s.date) <= 1
      })
      if (hit) {
        usedJrnl.add(hit.id)
        usedStmt.add(s.id)
        matchedBank += 1
        bankToBook.push({
          ...createEmptyCheckRow(),
          checkReason: thrS > 0 && amt >= thrS ? '大额' : '其他',
          vDate: hit.date,
          voucherNo: hit.voucherNo,
          businessContent: hit.businessContent,
          counterAccount: hit.counterAccount,
          counterparty: hit.counterparty,
          debit: hit.debit,
          credit: hit.credit,
          sDate: s.date,
          summary: s.summary,
          payerPayee: s.counterparty,
          stmtAmount: s.amount,
          infoConsistent: '是',
        })
      } else {
        unmatchedBank += 1
        bankToBook.push({
          ...createEmptyCheckRow(),
          checkReason: thrS > 0 && amt >= thrS ? '大额' : '其他',
          sDate: s.date,
          summary: s.summary,
          payerPayee: s.counterparty,
          stmtAmount: s.amount,
          debit: s.direction === '支出' ? 0 : amt,
          credit: s.direction === '支出' ? amt : 0,
          infoConsistent: '',
        })
      }
    }

    return { bookToBank, bankToBook, matchedBook, unmatchedBook, matchedBank, unmatchedBank }
  }

  function previewMatch(): Omit<AutoMatchResult, 'preserved' | 'mode'> {
    const c = buildMatchCandidates()
    return {
      bookToBank: c.bookToBank.length,
      bankToBook: c.bankToBook.length,
      matchedBook: c.matchedBook,
      unmatchedBook: c.unmatchedBook,
      matchedBank: c.matchedBank,
      unmatchedBank: c.unmatchedBank,
    }
  }

  /**
   * 自动双向匹配。
   * - replace：用本次候选覆盖抽样表（默认）
   * - merge：按键合并；已有人工填写的行优先保留
   */
  function autoMatchBoth(mode: AutoMatchMode = 'replace'): AutoMatchResult {
    if (isReadonly.value) {
      return {
        bookToBank: 0, bankToBook: 0, matchedBook: 0, unmatchedBook: 0,
        matchedBank: 0, unmatchedBank: 0, preserved: 0, mode,
      }
    }
    const c = buildMatchCandidates()
    let preserved = 0

    if (mode === 'merge') {
      const bMap = new Map(pack.value.bookToBank.map(r => [checkKeyBook(r), r]))
      const sMap = new Map(pack.value.bankToBook.map(r => [checkKeyBank(r), r]))
      for (const r of c.bookToBank) {
        const k = checkKeyBook(r)
        const prev = bMap.get(k)
        if (prev && isManuallyTouched(prev)) {
          preserved += 1
          continue
        }
        bMap.set(k, prev ? { ...r, id: prev.id, thirdParty: prev.thirdParty, inconsistencyReason: prev.inconsistencyReason, supportDocs: prev.supportDocs, conclusion: prev.conclusion || r.conclusion, infoConsistent: prev.infoConsistent || r.infoConsistent } : r)
      }
      for (const r of c.bankToBook) {
        const k = checkKeyBank(r)
        const prev = sMap.get(k)
        if (prev && isManuallyTouched(prev)) {
          preserved += 1
          continue
        }
        sMap.set(k, prev ? { ...r, id: prev.id, thirdParty: prev.thirdParty, inconsistencyReason: prev.inconsistencyReason, supportDocs: prev.supportDocs, conclusion: prev.conclusion || r.conclusion, infoConsistent: prev.infoConsistent || r.infoConsistent } : r)
      }
      pack.value = {
        ...pack.value,
        bookToBank: Array.from(bMap.values()),
        bankToBook: Array.from(sMap.values()),
      }
    } else {
      pack.value = {
        ...pack.value,
        bookToBank: c.bookToBank,
        bankToBook: c.bankToBook,
      }
    }
    scheduleSave()
    return {
      bookToBank: pack.value.bookToBank.length,
      bankToBook: pack.value.bankToBook.length,
      matchedBook: c.matchedBook,
      unmatchedBook: c.unmatchedBook,
      matchedBank: c.matchedBank,
      unmatchedBank: c.unmatchedBank,
      preserved,
      mode,
    }
  }

  function updateTip(key: string, field: 'checked' | 'note', value: boolean | string): void {
    if (isReadonly.value) return
    pack.value = {
      ...pack.value,
      tips: pack.value.tips.map(t => (t.key === key ? { ...t, [field]: value } : t)),
    }
    scheduleSave()
  }

  function setCoverageLowReason(val: string): void {
    patchPack({ coverageLowReason: val })
  }

  function saveNote(val: string): void {
    if (isReadonly.value) return
    auditNote.value = val
    const item = { item_id: E1_BANK_FLOW_NOTE_KEY, conclusion: null, remark: val }
    allResponses.value.set(E1_BANK_FLOW_NOTE_KEY, item)
    saveImmediate([item]).catch(() => {})
  }

  function saveConclusion(val: string): void {
    if (isReadonly.value) return
    auditConclusion.value = val
    const item = { item_id: E1_BANK_FLOW_CONCLUSION_KEY, conclusion: null, remark: val }
    allResponses.value.set(E1_BANK_FLOW_CONCLUSION_KEY, item)
    saveImmediate([item]).catch(() => {})
  }

  function hydrate(): void {
    load()
  }

  onBeforeUnmount(() => {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
      persist()
    }
  })

  return {
    pack,
    auditNote,
    auditConclusion,
    isLoading,
    isApplicable,
    monthlyTotals,
    coverage,
    mismatchMonthlyCount,
    setApplicable,
    updateMeta,
    setThreshold,
    updateMonthly,
    recalcMonthlyFromLines,
    addStatementLine,
    removeStatementLine,
    updateStatementLine,
    mergeOcrStatementLines,
    recordOcrJob,
    addJournalLine,
    removeJournalLine,
    updateJournalLine,
    updateCheckRow,
    addCheckRow,
    removeCheckRow,
    mergeJournalLines,
    previewMatch,
    autoMatchBoth,
    updateTip,
    setCoverageLowReason,
    saveNote,
    saveConclusion,
    hydrate,
    scheduleSave,
  }
}
