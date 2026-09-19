/**
 * useE1CashCount — E1-7/8/9 盘点通用 composable
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 9.1
 *
 * 职责：
 * - variant 配置：'rmb'(面值×张数)、'fx'(外币+汇率)、'cert'(存单)
 * - RMB: denomination(面值) × quantity(张数) = subtotal, totalActual实盘, bookBalance账面, countDiff=actual-book
 * - FX: currency, denomination, quantity, fcAmount(原币), fxRate, rmbAmount(原币×汇率)
 * - Cert: certNo, bank, certType, depositDate, maturityDate, amount, interestRate, result(已见/未见)
 * - 差异≠0时强制填写差异原因
 * - 序列化/反序列化 → checklist_responses (item_id: 'E1-cash-count-{variant}-rows')
 * - Debounce 2s 自动保存
 *
 * Requirements: 7.1-7.5
 */
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import type { UseE1BaseOptions, ChecklistItem } from './useE1Adjudication'
import { parseNum, calcCountDiff, calcFxConvert, sumField } from './useE1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type CashCountVariant = 'rmb' | 'fx' | 'cert'

export interface RmbCountRow {
  id: string
  denomination: number   // 面值
  quantity: number       // 张数
  subtotal: number       // readonly: denomination × quantity
}

export interface FxCountRow {
  id: string
  currency: string       // 币种
  denomination: number   // 面值
  quantity: number       // 张数
  fcAmount: number       // 原币金额
  fxRate: number         // 汇率
  rmbAmount: number      // readonly: fcAmount × fxRate
}

export interface CertCountRow {
  id: string
  certNo: string         // 存单编号
  bank: string           // 开户银行
  depositor: string      // 存款人/户名
  account: string        // 账号
  certType: string       // 存单类型（定期存款/大额存单/开户证实书等）
  currency: string       // 币种
  depositDate: string    // 存入日期
  maturityDate: string   // 到期日期
  amount: number         // 金额
  interestRate: number   // 利率
  bookConsistent: '是' | '否' | '' // 是否与账面一致
  inconsistencyReason: string       // 不一致原因
  pledged: '是' | '否' | ''        // 是否质押/受限
  pledgeMatter: string              // 质押/受限事项描述
  result: '已见' | '未见' | ''     // 盘点结果
  certificateIndex: string          // 存单/开户证实书索引
  openingProofIndex: string         // 开户证明索引
  custodyProofIndex: string         // 保管/质押证明索引
  note: string                      // 备注
}

export type CashCountRow = RmbCountRow | FxCountRow | CertCountRow

/** E1-7/8 完整倒轧链汇总；末尾三个旧字段仅用于旧 JSON 兼容。 */
export interface CashRollForwardSummary {
  reportDateBookBalance: number
  cumulativeIncome: number
  cumulativeExpense: number
  priorDayBookBalance: number
  receiptVoucherUnposted: number
  paymentVoucherUnposted: number
  unvoucheredIncome: number
  unvoucheredExpense: number
  expectedCountAmount: number
  actualCountAmount: number
  overShort: number
  diffReason: string
  closingFxRate: number
  reportDateForeignBookBalance: number
  expectedFunctionalCurrency: number
  exchangeDifference: number
  /** @deprecated 旧版字段，序列化时继续保留。 */
  totalActual: number
  /** @deprecated 旧版字段，等同 reportDateBookBalance。 */
  bookBalance: number
  /** @deprecated 旧版字段，等同 overShort。 */
  countDiff: number
}

export type RmbSummary = CashRollForwardSummary

// ─── Constants ───────────────────────────────────────────────────────────────

function getStorageKey(variant: CashCountVariant): string {
  return `E1-cash-count-${variant}-rows`
}

const RMB_USER_FIELDS = ['id', 'denomination', 'quantity']
const FX_USER_FIELDS = ['id', 'currency', 'denomination', 'quantity', 'fcAmount', 'fxRate']
const CERT_USER_FIELDS = [
  'id', 'certNo', 'bank', 'depositor', 'account', 'certType', 'currency',
  'depositDate', 'maturityDate', 'amount', 'interestRate', 'bookConsistent',
  'inconsistencyReason', 'pledged', 'pledgeMatter', 'result', 'certificateIndex',
  'openingProofIndex', 'custodyProofIndex', 'note',
]

const TOLERANCE = 0.005

// ─── Helpers ─────────────────────────────────────────────────────────────────

function createEmptySummary(): CashRollForwardSummary {
  return {
    reportDateBookBalance: 0,
    cumulativeIncome: 0,
    cumulativeExpense: 0,
    priorDayBookBalance: 0,
    receiptVoucherUnposted: 0,
    paymentVoucherUnposted: 0,
    unvoucheredIncome: 0,
    unvoucheredExpense: 0,
    expectedCountAmount: 0,
    actualCountAmount: 0,
    overShort: 0,
    diffReason: '',
    closingFxRate: 0,
    reportDateForeignBookBalance: 0,
    expectedFunctionalCurrency: 0,
    exchangeDifference: 0,
    totalActual: 0,
    bookBalance: 0,
    countDiff: 0,
  }
}

function recalculateSummary(summary: CashRollForwardSummary, actual: number): CashRollForwardSummary {
  const priorDayBookBalance = summary.reportDateBookBalance + summary.cumulativeIncome - summary.cumulativeExpense
  const expectedCountAmount = priorDayBookBalance
    + summary.receiptVoucherUnposted
    - summary.paymentVoucherUnposted
    + summary.unvoucheredIncome
    - summary.unvoucheredExpense
  const expectedFunctionalCurrency = summary.reportDateForeignBookBalance * summary.closingFxRate
  const overShort = calcCountDiff(actual, expectedCountAmount)
  return {
    ...summary,
    priorDayBookBalance,
    expectedCountAmount,
    actualCountAmount: actual,
    overShort,
    expectedFunctionalCurrency,
    exchangeDifference: expectedFunctionalCurrency - summary.reportDateBookBalance,
    totalActual: actual,
    bookBalance: summary.reportDateBookBalance,
    countDiff: overShort,
  }
}

function generateRowId(prefix: string): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `${prefix}-${crypto.randomUUID()}`
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function recalcRmbRow(row: RmbCountRow): RmbCountRow {
  return { ...row, subtotal: row.denomination * row.quantity }
}

function recalcFxRow(row: FxCountRow): FxCountRow {
  return { ...row, rmbAmount: calcFxConvert(row.fcAmount, row.fxRate) }
}

function createEmptyRmbRow(): RmbCountRow {
  return recalcRmbRow({ id: generateRowId('rmb'), denomination: 0, quantity: 0, subtotal: 0 })
}

function createEmptyFxRow(): FxCountRow {
  return recalcFxRow({ id: generateRowId('fx'), currency: '', denomination: 0, quantity: 0, fcAmount: 0, fxRate: 0, rmbAmount: 0 })
}

function createEmptyCertRow(): CertCountRow {
  return {
    id: generateRowId('cert'),
    certNo: '',
    bank: '',
    depositor: '',
    account: '',
    certType: '',
    currency: '人民币',
    depositDate: '',
    maturityDate: '',
    amount: 0,
    interestRate: 0,
    bookConsistent: '',
    inconsistencyReason: '',
    pledged: '',
    pledgeMatter: '',
    result: '',
    certificateIndex: '',
    openingProofIndex: '',
    custodyProofIndex: '',
    note: '',
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useE1CashCount(options: UseE1BaseOptions & { variant: CashCountVariant }) {
  const { allResponses, saveImmediate, isReadonly, variant } = options
  const storageKey = getStorageKey(variant)

  // ─── State ─────────────────────────────────────────────────────────────

  const rows = ref<CashCountRow[]>([])
  const isLoading = ref(false)

  // E1-7/8 shared roll-forward summary; rmbSummary name is retained for caller compatibility.
  const rmbSummary = ref<CashRollForwardSummary>(createEmptySummary())

  function currentActualTotal(): number {
    if (variant === 'rmb') {
      return sumField(rows.value as unknown as Array<Record<string, unknown>>, 'subtotal')
    }
    if (variant === 'fx') {
      return sumField(rows.value as unknown as Array<Record<string, unknown>>, 'rmbAmount')
    }
    return 0
  }

  // ─── Deserialization ───────────────────────────────────────────────────

  function loadFromResponses(): void {
    const response = allResponses.value.get(storageKey)
    const raw = response?.remark
    if (!raw) {
      rows.value = [createDefaultRow()]
      loadSummary()
      return
    }
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed) || parsed.length === 0) {
        rows.value = [createDefaultRow()]
        loadSummary()
        return
      }
      rows.value = parsed.map((r: Record<string, unknown>) => deserializeRow(r))
      loadSummary()
    } catch {
      console.warn(`[useE1CashCount:${variant}] JSON parse failed, fallback to empty`)
      rows.value = [createDefaultRow()]
      loadSummary()
    }
  }

  /**
   * New E1-7/8 summary uses `${storageKey}-summary`.
   * E1-8 previously stored `{bookBalance,diffReason}` under a component-local key;
   * read it as a fallback so historical workpapers remain usable.
   */
  function loadSummary(): void {
    if (variant === 'cert') return
    const summaryResp = allResponses.value.get(`${storageKey}-summary`)
      || (variant === 'fx' ? allResponses.value.get('E1-cashcount-fx-summary-fx') : undefined)
    if (!summaryResp?.remark) {
      rmbSummary.value = recalculateSummary(createEmptySummary(), currentActualTotal())
      return
    }
    try {
      const s = JSON.parse(summaryResp.remark)
      const normalized: CashRollForwardSummary = {
        ...createEmptySummary(),
        reportDateBookBalance: parseNum(s.reportDateBookBalance ?? s.bookBalance),
        cumulativeIncome: parseNum(s.cumulativeIncome),
        cumulativeExpense: parseNum(s.cumulativeExpense),
        receiptVoucherUnposted: parseNum(s.receiptVoucherUnposted),
        paymentVoucherUnposted: parseNum(s.paymentVoucherUnposted),
        unvoucheredIncome: parseNum(s.unvoucheredIncome),
        unvoucheredExpense: parseNum(s.unvoucheredExpense),
        diffReason: String(s.diffReason || ''),
        closingFxRate: parseNum(s.closingFxRate),
        reportDateForeignBookBalance: parseNum(s.reportDateForeignBookBalance),
      }
      rmbSummary.value = recalculateSummary(normalized, currentActualTotal())
    } catch {
      rmbSummary.value = recalculateSummary(createEmptySummary(), currentActualTotal())
    }
  }

  function createDefaultRow(): CashCountRow {
    switch (variant) {
      case 'rmb': return createEmptyRmbRow()
      case 'fx': return createEmptyFxRow()
      case 'cert': return createEmptyCertRow()
    }
  }

  function deserializeRow(r: Record<string, unknown>): CashCountRow {
    switch (variant) {
      case 'rmb':
        return recalcRmbRow({
          id: String(r.id || generateRowId('rmb')),
          denomination: parseNum(r.denomination),
          quantity: parseNum(r.quantity),
          subtotal: 0,
        })
      case 'fx':
        return recalcFxRow({
          id: String(r.id || generateRowId('fx')),
          currency: String(r.currency || ''),
          denomination: parseNum(r.denomination),
          quantity: parseNum(r.quantity),
          fcAmount: parseNum(r.fcAmount),
          fxRate: parseNum(r.fxRate),
          rmbAmount: 0,
        })
      case 'cert':
        return {
          id: String(r.id || generateRowId('cert')),
          certNo: String(r.certNo || ''),
          bank: String(r.bank || ''),
          depositor: String(r.depositor || ''),
          account: String(r.account || ''),
          certType: String(r.certType || ''),
          currency: String(r.currency || '人民币'),
          depositDate: String(r.depositDate || ''),
          maturityDate: String(r.maturityDate || ''),
          amount: parseNum(r.amount),
          interestRate: parseNum(r.interestRate),
          bookConsistent: (['是', '否'].includes(String(r.bookConsistent)) ? String(r.bookConsistent) : '') as CertCountRow['bookConsistent'],
          inconsistencyReason: String(r.inconsistencyReason || ''),
          pledged: (['是', '否'].includes(String(r.pledged)) ? String(r.pledged) : '') as CertCountRow['pledged'],
          pledgeMatter: String(r.pledgeMatter || ''),
          result: (['已见', '未见'].includes(String(r.result)) ? String(r.result) : '') as CertCountRow['result'],
          certificateIndex: String(r.certificateIndex || ''),
          openingProofIndex: String(r.openingProofIndex || ''),
          custodyProofIndex: String(r.custodyProofIndex || ''),
          note: String(r.note || ''),
        }
    }
  }

  loadFromResponses()

  watch(
    () => allResponses.value.get(storageKey)?.remark,
    (newRemark, oldRemark) => {
      if (newRemark !== oldRemark && newRemark !== serializeRows()) {
        loadFromResponses()
      }
    },
  )

  // ─── Serialization ─────────────────────────────────────────────────────

  function getUserFields(): string[] {
    switch (variant) {
      case 'rmb': return RMB_USER_FIELDS
      case 'fx': return FX_USER_FIELDS
      case 'cert': return CERT_USER_FIELDS
    }
  }

  function serializeRows(): string {
    const fields = getUserFields()
    const data = rows.value.map(row => {
      const obj: Record<string, unknown> = {}
      for (const field of fields) {
        obj[field] = (row as Record<string, unknown>)[field]
      }
      return obj
    })
    return JSON.stringify(data)
  }

  // ─── Debounce Save ─────────────────────────────────────────────────────

  let saveTimer: ReturnType<typeof setTimeout> | null = null

  function scheduleSave(): void {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      persistToResponses()
    }, 2000)
  }

  function persistToResponses(): void {
    const serialized = serializeRows()
    const items: ChecklistItem[] = [
      { item_id: storageKey, conclusion: null, remark: serialized },
    ]
    allResponses.value.set(storageKey, { item_id: storageKey, conclusion: null, remark: serialized })

    // Persist E1-7/8 roll-forward summary separately.  The JSON still carries
    // totalActual/bookBalance/countDiff aliases for older readers.
    if (variant !== 'cert') {
      const summaryKey = `${storageKey}-summary`
      rmbSummary.value = recalculateSummary(rmbSummary.value, currentActualTotal())
      const summaryJson = JSON.stringify(rmbSummary.value)
      allResponses.value.set(summaryKey, { item_id: summaryKey, conclusion: null, remark: summaryJson })
      items.push({ item_id: summaryKey, conclusion: null, remark: summaryJson })
    }

    saveImmediate(items).catch(() => { /* silent */ })
  }

  // ─── Computed ──────────────────────────────────────────────────────────

  /** E1-7/8: 实盘本位币合计。 */
  const actualTotal = computed(() => currentActualTotal())
  /** RMB alias retained for the existing template/API. */
  const rmbTotal = computed(() => (variant === 'rmb' ? actualTotal.value : 0))

  if (variant !== 'cert') {
    watch(actualTotal, (newTotal) => {
      rmbSummary.value = recalculateSummary(rmbSummary.value, newTotal)
    }, { immediate: true })
  }

  // ─── Validation Helpers ────────────────────────────────────────────────

  function hasDiff(): boolean {
    if (variant === 'cert') return false
    return Math.abs(rmbSummary.value.overShort) > TOLERANCE
  }

  function isMissingReason(): boolean {
    return hasDiff() && !rmbSummary.value.diffReason.trim()
  }

  // ─── Row CRUD ──────────────────────────────────────────────────────────

  function addRow(): void {
    if (isReadonly.value) return
    rows.value = [...rows.value, createDefaultRow()]
    scheduleSave()
  }

  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex(r => r.id === rowId)
    if (idx === -1) return
    rows.value = rows.value.filter(r => r.id !== rowId)
    scheduleSave()
  }

  function updateCell(rowId: string, field: string, value: number | string): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex(r => r.id === rowId)
    if (idx === -1) return

    const row = { ...(rows.value[idx] as Record<string, unknown>) }
    const numericFields = ['denomination', 'quantity', 'fcAmount', 'fxRate', 'amount', 'interestRate']
    if (numericFields.includes(field)) {
      row[field] = parseNum(value)
    } else {
      row[field] = String(value)
    }

    let recalculated: CashCountRow
    switch (variant) {
      case 'rmb':
        recalculated = recalcRmbRow(row as unknown as RmbCountRow)
        break
      case 'fx':
        recalculated = recalcFxRow(row as unknown as FxCountRow)
        break
      default:
        recalculated = row as unknown as CertCountRow
    }

    const newRows = [...rows.value]
    newRows[idx] = recalculated
    rows.value = newRows
    scheduleSave()
  }

  /** Update E1-7/8 user-entered roll-forward fields, then refresh all formulas. */
  function updateSummary(field: keyof CashRollForwardSummary, value: number | string): void {
    if (isReadonly.value || variant === 'cert') return
    const next = { ...rmbSummary.value }
    if (field === 'diffReason') {
      next.diffReason = String(value ?? '')
    } else {
      Object.assign(next, { [field]: parseNum(value) })
    }
    rmbSummary.value = recalculateSummary(next, currentActualTotal())
    scheduleSave()
  }

  // ─── Hydration ─────────────────────────────────────────────────────────

  function hydrate(): void {
    isLoading.value = true
    try {
      loadFromResponses()
    } finally {
      isLoading.value = false
    }
  }

  // ─── Cleanup ───────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
      persistToResponses()
    }
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    rows,
    rmbSummary,
    rmbTotal,
    actualTotal,
    isLoading,
    hasDiff,
    isMissingReason,
    addRow,
    removeRow,
    updateCell,
    updateSummary,
    hydrate,
  }
}

