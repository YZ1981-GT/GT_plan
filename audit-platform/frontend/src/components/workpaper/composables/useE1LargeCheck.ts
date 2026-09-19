/**
 * useE1LargeCheck — E1-23 / E1-28 货币资金（库存现金）收支检查
 *
 * - mode: monetary(E1-23) | cashIpo(E1-28)
 * - 样本选取元数据 + 借方明细 + 贷方明细
 * - cashIpo：锁定 1001，证据列为收据/合同/验收（借）与审批/采购合同/入库（贷）
 * - 检查比例：检查金额合计 / 账面发生额
 * - 抽凭回填 mergeDebit/Credit；行级 OCR patch
 */
import { ref, computed, watch, onBeforeUnmount, unref, type Ref } from 'vue'
import type { UseE1BaseOptions, ChecklistItem } from './useE1Adjudication'
import { parseNum } from './useE1FormulaEngine'

export type LargeCheckMode = 'monetary' | 'cashIpo'
export type AccountCategory = 'cash' | 'bank' | 'other'
export type SamplingMethodKey = 'random' | 'systematic' | 'mus' | 'haphazard' | ''

export const ACCOUNT_CATEGORY_OPTIONS: Array<{ value: AccountCategory; label: string }> = [
  { value: 'cash', label: '现金' },
  { value: 'bank', label: '银行存款' },
  { value: 'other', label: '其他货币资金' },
]

export function accountCategoryLabel(cat: AccountCategory): string {
  return ACCOUNT_CATEGORY_OPTIONS.find(o => o.value === cat)?.label || cat
}

/** 由科目编码推断所属科目分区 */
export function inferAccountCategory(accountCode: string): AccountCategory {
  const code = String(accountCode || '').trim()
  if (code.startsWith('1001')) return 'cash'
  if (code.startsWith('1012')) return 'other'
  return 'bank'
}

export interface LargeCheckSamplingMeta {
  populationDebitCount: number
  populationDebitAmount: number
  populationCreditCount: number
  populationCreditAmount: number
  specificSampleNote: string
  samplingPopulationCount: number
  samplingPopulationAmount: number
  sampleSize: number
  samplingMethod: SamplingMethodKey
  samplingProcessNote: string
  largeAmountThreshold: number
}

export interface LargeCheckDebitRow {
  id: string
  accountCategory: AccountCategory
  date: string
  voucherNo: string
  businessContent: string
  counterAccount: string
  counterDetail: string
  debitAmount: number
  /** 收据/收款单（E1-28）或银行回单（E1-23）日期 */
  receiptDate: string
  receiptPayer: string
  receiptAmount: number
  /** E1-28：销售合同 */
  contractDate: string
  contractParty: string
  contractAmount: number
  settlementMethod: string
  /** E1-28：签收/验收单 */
  acceptanceDateNo: string
  acceptor: string
  otherSupportDocs: string
  indexNo: string
  isAbnormal: '' | '是' | '否'
  note: string
  source: string
}

export interface LargeCheckCreditRow {
  id: string
  accountCategory: AccountCategory
  date: string
  voucherNo: string
  businessContent: string
  counterAccount: string
  counterDetail: string
  creditAmount: number
  receiptDate: string
  receiptPayee: string
  receiptAmount: number
  approvalDateNo: string
  /** E1-28：支付方式 */
  paymentMethod: string
  isProperlyApproved: '' | '是' | '否'
  /** E1-28：采购合同 */
  contractDate: string
  contractParty: string
  contractAmount: number
  settlementMethod: string
  /** E1-28：入库单/验收单 */
  acceptanceDateNo: string
  acceptor: string
  otherSupportDocs: string
  indexNo: string
  isAbnormal: '' | '是' | '否'
  note: string
  source: string
}

export interface LargeCheckCoverage {
  bookDebitAmount: number
  bookCreditAmount: number
}

export interface LargeCheckPack {
  sampling: LargeCheckSamplingMeta
  debitRows: LargeCheckDebitRow[]
  creditRows: LargeCheckCreditRow[]
  coverage: LargeCheckCoverage
}

const STORAGE_KEY_BY_MODE: Record<LargeCheckMode, string> = {
  monetary: 'E1-largecheck-pack',
  cashIpo: 'E1-cashcheck-pack',
}

const LEGACY_IPO_ROWS_KEY = 'E1-ipo-E1-28-rows'

function generateId(prefix: string): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `${prefix}-${crypto.randomUUID()}`
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function emptySampling(): LargeCheckSamplingMeta {
  return {
    populationDebitCount: 0,
    populationDebitAmount: 0,
    populationCreditCount: 0,
    populationCreditAmount: 0,
    specificSampleNote: '',
    samplingPopulationCount: 0,
    samplingPopulationAmount: 0,
    sampleSize: 0,
    samplingMethod: '',
    samplingProcessNote: '',
    largeAmountThreshold: 0,
  }
}

function emptyCoverage(): LargeCheckCoverage {
  return { bookDebitAmount: 0, bookCreditAmount: 0 }
}

export function createEmptyDebitRow(partial?: Partial<LargeCheckDebitRow>): LargeCheckDebitRow {
  return {
    id: generateId('lc-d'),
    accountCategory: 'bank',
    date: '',
    voucherNo: '',
    businessContent: '',
    counterAccount: '',
    counterDetail: '',
    debitAmount: 0,
    receiptDate: '',
    receiptPayer: '',
    receiptAmount: 0,
    contractDate: '',
    contractParty: '',
    contractAmount: 0,
    settlementMethod: '',
    acceptanceDateNo: '',
    acceptor: '',
    otherSupportDocs: '',
    indexNo: '',
    isAbnormal: '',
    note: '',
    source: '',
    ...partial,
  }
}

export function createEmptyCreditRow(partial?: Partial<LargeCheckCreditRow>): LargeCheckCreditRow {
  return {
    id: generateId('lc-c'),
    accountCategory: 'bank',
    date: '',
    voucherNo: '',
    businessContent: '',
    counterAccount: '',
    counterDetail: '',
    creditAmount: 0,
    receiptDate: '',
    receiptPayee: '',
    receiptAmount: 0,
    approvalDateNo: '',
    paymentMethod: '',
    isProperlyApproved: '',
    contractDate: '',
    contractParty: '',
    contractAmount: 0,
    settlementMethod: '',
    acceptanceDateNo: '',
    acceptor: '',
    otherSupportDocs: '',
    indexNo: '',
    isAbnormal: '',
    note: '',
    source: '',
    ...partial,
  }
}

function normalizeDebit(raw: Record<string, unknown>, forceCash = false): LargeCheckDebitRow {
  const cat = String(raw.accountCategory || (forceCash ? 'cash' : 'bank')) as AccountCategory
  const abnormal = String(raw.isAbnormal || '')
  return createEmptyDebitRow({
    id: String(raw.id || generateId('lc-d')),
    accountCategory: forceCash
      ? 'cash'
      : (['cash', 'bank', 'other'].includes(cat) ? cat : 'bank'),
    date: String(raw.date || ''),
    voucherNo: String(raw.voucherNo || ''),
    businessContent: String(raw.businessContent || raw.content || raw.summary || ''),
    counterAccount: String(raw.counterAccount || ''),
    counterDetail: String(raw.counterDetail || ''),
    debitAmount: parseNum(raw.debitAmount ?? raw.amount),
    receiptDate: String(raw.receiptDate || ''),
    receiptPayer: String(raw.receiptPayer || raw.payer || raw.receipt || ''),
    receiptAmount: parseNum(raw.receiptAmount),
    contractDate: String(raw.contractDate || ''),
    contractParty: String(raw.contractParty || raw.customerName || raw.contract || ''),
    contractAmount: parseNum(raw.contractAmount),
    settlementMethod: String(raw.settlementMethod || ''),
    acceptanceDateNo: String(raw.acceptanceDateNo || ''),
    acceptor: String(raw.acceptor || raw.acceptance || ''),
    otherSupportDocs: String(raw.otherSupportDocs || ''),
    indexNo: String(raw.indexNo || ''),
    isAbnormal: abnormal === '是' || abnormal === '否' ? abnormal : '',
    note: String(raw.note || ''),
    source: String(raw.source || ''),
  })
}

function normalizeCredit(raw: Record<string, unknown>, forceCash = false): LargeCheckCreditRow {
  const cat = String(raw.accountCategory || (forceCash ? 'cash' : 'bank')) as AccountCategory
  const abnormal = String(raw.isAbnormal || '')
  const approved = String(raw.isProperlyApproved || '')
  return createEmptyCreditRow({
    id: String(raw.id || generateId('lc-c')),
    accountCategory: forceCash
      ? 'cash'
      : (['cash', 'bank', 'other'].includes(cat) ? cat : 'bank'),
    date: String(raw.date || ''),
    voucherNo: String(raw.voucherNo || ''),
    businessContent: String(raw.businessContent || raw.content || raw.summary || ''),
    counterAccount: String(raw.counterAccount || ''),
    counterDetail: String(raw.counterDetail || ''),
    creditAmount: parseNum(raw.creditAmount ?? raw.amount),
    receiptDate: String(raw.receiptDate || ''),
    receiptPayee: String(raw.receiptPayee || raw.payee || ''),
    receiptAmount: parseNum(raw.receiptAmount),
    approvalDateNo: String(raw.approvalDateNo || ''),
    paymentMethod: String(raw.paymentMethod || ''),
    isProperlyApproved: approved === '是' || approved === '否' ? approved : '',
    contractDate: String(raw.contractDate || ''),
    contractParty: String(raw.contractParty || raw.supplierName || raw.contract || ''),
    contractAmount: parseNum(raw.contractAmount),
    settlementMethod: String(raw.settlementMethod || ''),
    acceptanceDateNo: String(raw.acceptanceDateNo || ''),
    acceptor: String(raw.acceptor || raw.acceptance || ''),
    otherSupportDocs: String(raw.otherSupportDocs || ''),
    indexNo: String(raw.indexNo || ''),
    isAbnormal: abnormal === '是' || abnormal === '否' ? abnormal : '',
    note: String(raw.note || ''),
    source: String(raw.source || ''),
  })
}

function amountMismatch(book: number, receipt: number): boolean {
  if (!receipt || !book) return false
  return Math.abs(book - receipt) > 0.01
}

/** 账证金额不符时建议标异常（不强制覆盖人工「否」） */
export function suggestAbnormal(
  bookAmount: number,
  receiptAmount: number,
  current: '' | '是' | '否',
): '' | '是' | '否' {
  if (current === '是' || current === '否') return current
  return amountMismatch(bookAmount, receiptAmount) ? '是' : current
}

function applyFillMode<T extends { voucherNo: string }>(
  existing: T[],
  incoming: T[],
  mode: 'append' | 'replace' | 'merge',
): T[] {
  if (mode === 'replace') return [...incoming]
  if (mode === 'merge') {
    const nos = new Set(existing.map(r => r.voucherNo).filter(Boolean))
    const extras = incoming.filter(r => !r.voucherNo || !nos.has(r.voucherNo))
    return [...existing, ...extras]
  }
  return [...existing, ...incoming]
}

export function useE1LargeCheck(
  options: UseE1BaseOptions & { mode?: LargeCheckMode | Ref<LargeCheckMode> },
) {
  const { allResponses, saveImmediate, isReadonly } = options
  const modeRef = computed<LargeCheckMode>(() => unref(options.mode) || 'monetary')
  const isCashIpo = computed(() => modeRef.value === 'cashIpo')
  const storageKey = computed(() => STORAGE_KEY_BY_MODE[modeRef.value])
  const defaultCat = computed<AccountCategory>(() => 'cash')

  const sampling = ref<LargeCheckSamplingMeta>(emptySampling())
  const debitRows = ref<LargeCheckDebitRow[]>([createEmptyDebitRow({ accountCategory: 'cash' })])
  const creditRows = ref<LargeCheckCreditRow[]>([createEmptyCreditRow({ accountCategory: 'cash' })])
  const coverage = ref<LargeCheckCoverage>(emptyCoverage())
  const isLoading = ref(false)

  const debitCheckedAmount = computed(() =>
    debitRows.value.reduce((s, r) => s + parseNum(r.debitAmount), 0),
  )
  const creditCheckedAmount = computed(() =>
    creditRows.value.reduce((s, r) => s + parseNum(r.creditAmount), 0),
  )
  const debitCoverageRatio = computed(() => {
    const book = parseNum(coverage.value.bookDebitAmount)
    if (!book) return 0
    return debitCheckedAmount.value / book
  })
  const creditCoverageRatio = computed(() => {
    const book = parseNum(coverage.value.bookCreditAmount)
    if (!book) return 0
    return creditCheckedAmount.value / book
  })
  const debitAbnormalCount = computed(() => debitRows.value.filter(r => r.isAbnormal === '是').length)
  const creditAbnormalCount = computed(() => creditRows.value.filter(r => r.isAbnormal === '是').length)

  function serializePack(): string {
    const pack: LargeCheckPack = {
      sampling: { ...sampling.value },
      debitRows: debitRows.value.map(r => ({ ...r })),
      creditRows: creditRows.value.map(r => ({ ...r })),
      coverage: { ...coverage.value },
    }
    return JSON.stringify(pack)
  }

  function loadFromResponses(): void {
    let raw = allResponses.value.get(storageKey.value)?.remark
    if (!raw && isCashIpo.value) {
      raw = allResponses.value.get(LEGACY_IPO_ROWS_KEY)?.remark
    }
    const forceCash = isCashIpo.value
    if (!raw) {
      sampling.value = emptySampling()
      debitRows.value = [createEmptyDebitRow({ accountCategory: defaultCat.value })]
      creditRows.value = [createEmptyCreditRow({ accountCategory: defaultCat.value })]
      coverage.value = emptyCoverage()
      return
    }
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) {
        // 旧版 IPO 扁平行 → 塞入借方作兼容
        debitRows.value = parsed.length
          ? parsed.map((r: Record<string, unknown>) => normalizeDebit(r, forceCash))
          : [createEmptyDebitRow({ accountCategory: defaultCat.value })]
        creditRows.value = [createEmptyCreditRow({ accountCategory: defaultCat.value })]
        sampling.value = emptySampling()
        coverage.value = emptyCoverage()
        return
      }
      if (!parsed || typeof parsed !== 'object') return
      sampling.value = { ...emptySampling(), ...(parsed.sampling || {}) }
      coverage.value = { ...emptyCoverage(), ...(parsed.coverage || {}) }
      const d = Array.isArray(parsed.debitRows) ? parsed.debitRows : []
      const c = Array.isArray(parsed.creditRows) ? parsed.creditRows : []
      debitRows.value = d.length
        ? d.map((r: Record<string, unknown>) => normalizeDebit(r, forceCash))
        : [createEmptyDebitRow({ accountCategory: defaultCat.value })]
      creditRows.value = c.length
        ? c.map((r: Record<string, unknown>) => normalizeCredit(r, forceCash))
        : [createEmptyCreditRow({ accountCategory: defaultCat.value })]
    } catch {
      sampling.value = emptySampling()
      debitRows.value = [createEmptyDebitRow({ accountCategory: defaultCat.value })]
      creditRows.value = [createEmptyCreditRow({ accountCategory: defaultCat.value })]
      coverage.value = emptyCoverage()
    }
  }

  loadFromResponses()

  watch(storageKey, () => { loadFromResponses() })
  watch(
    () => allResponses.value.get(storageKey.value)?.remark,
    (next, prev) => {
      if (next !== prev && next !== serializePack()) loadFromResponses()
    },
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
    const remark = serializePack()
    const key = storageKey.value
    const item: ChecklistItem = { item_id: key, conclusion: null, remark }
    allResponses.value.set(key, item)
    saveImmediate([item]).catch(() => {})
  }

  function updateSampling<K extends keyof LargeCheckSamplingMeta>(
    key: K,
    value: LargeCheckSamplingMeta[K],
  ): void {
    if (isReadonly.value) return
    sampling.value = { ...sampling.value, [key]: value }
    scheduleSave()
  }

  function updateCoverage(field: keyof LargeCheckCoverage, value: number): void {
    if (isReadonly.value) return
    coverage.value = { ...coverage.value, [field]: parseNum(value) }
    scheduleSave()
  }

  function addDebitRow(cat: AccountCategory = 'bank'): void {
    if (isReadonly.value) return
    const useCat = isCashIpo.value ? 'cash' : cat
    debitRows.value = [...debitRows.value, createEmptyDebitRow({ accountCategory: useCat })]
    scheduleSave()
  }

  function addCreditRow(cat: AccountCategory = 'bank'): void {
    if (isReadonly.value) return
    const useCat = isCashIpo.value ? 'cash' : cat
    creditRows.value = [...creditRows.value, createEmptyCreditRow({ accountCategory: useCat })]
    scheduleSave()
  }

  function removeDebitRow(id: string): void {
    if (isReadonly.value) return
    debitRows.value = debitRows.value.filter(r => r.id !== id)
    if (!debitRows.value.length) {
      debitRows.value = [createEmptyDebitRow({ accountCategory: defaultCat.value })]
    }
    scheduleSave()
  }

  function removeCreditRow(id: string): void {
    if (isReadonly.value) return
    creditRows.value = creditRows.value.filter(r => r.id !== id)
    if (!creditRows.value.length) {
      creditRows.value = [createEmptyCreditRow({ accountCategory: defaultCat.value })]
    }
    scheduleSave()
  }

  function updateDebitCell(id: string, field: string, value: unknown): void {
    if (isReadonly.value) return
    const idx = debitRows.value.findIndex(r => r.id === id)
    if (idx === -1) return
    const row = { ...debitRows.value[idx] }
    if (['debitAmount', 'receiptAmount', 'contractAmount'].includes(field)) {
      ;(row as any)[field] = parseNum(value)
    } else if (field === 'accountCategory' && isCashIpo.value) {
      row.accountCategory = 'cash'
    } else {
      ;(row as any)[field] = value
    }
    if (field === 'debitAmount' || field === 'receiptAmount') {
      row.isAbnormal = suggestAbnormal(row.debitAmount, row.receiptAmount, row.isAbnormal)
    }
    const next = [...debitRows.value]
    next[idx] = row
    debitRows.value = next
    scheduleSave()
  }

  function updateCreditCell(id: string, field: string, value: unknown): void {
    if (isReadonly.value) return
    const idx = creditRows.value.findIndex(r => r.id === id)
    if (idx === -1) return
    const row = { ...creditRows.value[idx] }
    if (['creditAmount', 'receiptAmount', 'contractAmount'].includes(field)) {
      ;(row as any)[field] = parseNum(value)
    } else if (field === 'accountCategory' && isCashIpo.value) {
      row.accountCategory = 'cash'
    } else {
      ;(row as any)[field] = value
    }
    if (field === 'creditAmount' || field === 'receiptAmount') {
      row.isAbnormal = suggestAbnormal(row.creditAmount, row.receiptAmount, row.isAbnormal)
    }
    const next = [...creditRows.value]
    next[idx] = row
    creditRows.value = next
    scheduleSave()
  }

  function patchDebitRow(id: string, patch: Partial<LargeCheckDebitRow>): void {
    if (isReadonly.value) return
    const idx = debitRows.value.findIndex(r => r.id === id)
    if (idx === -1) return
    const merged = normalizeDebit({ ...debitRows.value[idx], ...patch, id }, isCashIpo.value)
    merged.isAbnormal = suggestAbnormal(merged.debitAmount, merged.receiptAmount, merged.isAbnormal)
    const next = [...debitRows.value]
    next[idx] = merged
    debitRows.value = next
    scheduleSave()
  }

  function patchCreditRow(id: string, patch: Partial<LargeCheckCreditRow>): void {
    if (isReadonly.value) return
    const idx = creditRows.value.findIndex(r => r.id === id)
    if (idx === -1) return
    const merged = normalizeCredit({ ...creditRows.value[idx], ...patch, id }, isCashIpo.value)
    merged.isAbnormal = suggestAbnormal(merged.creditAmount, merged.receiptAmount, merged.isAbnormal)
    const next = [...creditRows.value]
    next[idx] = merged
    creditRows.value = next
    scheduleSave()
  }

  function mergeDebitRows(
    incoming: Array<Partial<LargeCheckDebitRow>>,
    mode: 'append' | 'replace' | 'merge' = 'append',
  ): void {
    if (isReadonly.value) return
    const mapped = incoming.map(r => normalizeDebit(
      { ...r, source: r.source || '抽凭', accountCategory: isCashIpo.value ? 'cash' : r.accountCategory },
      isCashIpo.value,
    ))
    debitRows.value = applyFillMode(
      debitRows.value.filter(r => r.voucherNo || r.date || r.debitAmount),
      mapped,
      mode,
    )
    if (!debitRows.value.length) {
      debitRows.value = [createEmptyDebitRow({ accountCategory: defaultCat.value })]
    }
    scheduleSave()
  }

  function mergeCreditRows(
    incoming: Array<Partial<LargeCheckCreditRow>>,
    mode: 'append' | 'replace' | 'merge' = 'append',
  ): void {
    if (isReadonly.value) return
    const mapped = incoming.map(r => normalizeCredit(
      { ...r, source: r.source || '抽凭', accountCategory: isCashIpo.value ? 'cash' : r.accountCategory },
      isCashIpo.value,
    ))
    creditRows.value = applyFillMode(
      creditRows.value.filter(r => r.voucherNo || r.date || r.creditAmount),
      mapped,
      mode,
    )
    if (!creditRows.value.length) {
      creditRows.value = [createEmptyCreditRow({ accountCategory: defaultCat.value })]
    }
    scheduleSave()
  }

  function hydrate(): void {
    isLoading.value = true
    try { loadFromResponses() } finally { isLoading.value = false }
  }

  onBeforeUnmount(() => {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
      persist()
    }
  })

  return {
    mode: modeRef,
    isCashIpo,
    sampling,
    debitRows,
    creditRows,
    coverage,
    isLoading,
    debitCheckedAmount,
    creditCheckedAmount,
    debitCoverageRatio,
    creditCoverageRatio,
    debitAbnormalCount,
    creditAbnormalCount,
    updateSampling,
    updateCoverage,
    addDebitRow,
    addCreditRow,
    removeDebitRow,
    removeCreditRow,
    updateDebitCell,
    updateCreditCell,
    patchDebitRow,
    patchCreditRow,
    mergeDebitRows,
    mergeCreditRows,
    hydrate,
  }
}
