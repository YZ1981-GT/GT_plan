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
import { ref, computed, watch, onBeforeUnmount, type ComputedRef } from 'vue'
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
  certType: string       // 存单类型
  depositDate: string    // 存入日期
  maturityDate: string   // 到期日期
  amount: number         // 金额
  interestRate: number   // 利率
  result: '已见' | '未见' | ''  // 盘点结果
}

export type CashCountRow = RmbCountRow | FxCountRow | CertCountRow

/** RMB variant 汇总 */
export interface RmbSummary {
  totalActual: number    // 实盘合计
  bookBalance: number    // 账面余额
  countDiff: number      // 盘点差异 = actual - book
  diffReason: string     // 差异原因
}

// ─── Constants ───────────────────────────────────────────────────────────────

function getStorageKey(variant: CashCountVariant): string {
  return `E1-cash-count-${variant}-rows`
}

const RMB_USER_FIELDS = ['id', 'denomination', 'quantity']
const FX_USER_FIELDS = ['id', 'currency', 'denomination', 'quantity', 'fcAmount', 'fxRate']
const CERT_USER_FIELDS = ['id', 'certNo', 'bank', 'certType', 'depositDate', 'maturityDate', 'amount', 'interestRate', 'result']

const TOLERANCE = 0.005

// ─── Helpers ─────────────────────────────────────────────────────────────────

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
  return { id: generateRowId('cert'), certNo: '', bank: '', certType: '', depositDate: '', maturityDate: '', amount: 0, interestRate: 0, result: '' }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useE1CashCount(options: UseE1BaseOptions & { variant: CashCountVariant }) {
  const { allResponses, saveImmediate, isReadonly, variant } = options
  const storageKey = getStorageKey(variant)

  // ─── State ─────────────────────────────────────────────────────────────

  const rows = ref<CashCountRow[]>([])
  const isLoading = ref(false)

  // RMB-specific summary (separate item for summary data)
  const rmbSummary = ref<RmbSummary>({ totalActual: 0, bookBalance: 0, countDiff: 0, diffReason: '' })

  // ─── Deserialization ───────────────────────────────────────────────────

  function loadFromResponses(): void {
    const response = allResponses.value.get(storageKey)
    const raw = response?.remark
    if (!raw) {
      rows.value = [createDefaultRow()]
      loadRmbSummary()
      return
    }
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed) || parsed.length === 0) {
        rows.value = [createDefaultRow()]
        loadRmbSummary()
        return
      }
      rows.value = parsed.map((r: Record<string, unknown>) => deserializeRow(r))
      loadRmbSummary()
    } catch {
      console.warn(`[useE1CashCount:${variant}] JSON parse failed, fallback to empty`)
      rows.value = [createDefaultRow()]
    }
  }

  function loadRmbSummary(): void {
    if (variant !== 'rmb') return
    const summaryResp = allResponses.value.get(`${storageKey}-summary`)
    if (summaryResp?.remark) {
      try {
        const s = JSON.parse(summaryResp.remark)
        rmbSummary.value = {
          totalActual: parseNum(s.totalActual),
          bookBalance: parseNum(s.bookBalance),
          countDiff: calcCountDiff(parseNum(s.totalActual), parseNum(s.bookBalance)),
          diffReason: String(s.diffReason || ''),
        }
      } catch { /* use defaults */ }
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
          certType: String(r.certType || ''),
          depositDate: String(r.depositDate || ''),
          maturityDate: String(r.maturityDate || ''),
          amount: parseNum(r.amount),
          interestRate: parseNum(r.interestRate),
          result: (['已见', '未见'].includes(String(r.result)) ? String(r.result) : '') as CertCountRow['result'],
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

    // Persist RMB summary separately
    if (variant === 'rmb') {
      const summaryKey = `${storageKey}-summary`
      const summaryJson = JSON.stringify(rmbSummary.value)
      allResponses.value.set(summaryKey, { item_id: summaryKey, conclusion: null, remark: summaryJson })
      items.push({ item_id: summaryKey, conclusion: null, remark: summaryJson })
    }

    saveImmediate(items).catch(() => { /* silent */ })
  }

  // ─── Computed ──────────────────────────────────────────────────────────

  /** RMB: 实盘合计 = SUM(subtotal) */
  const rmbTotal = computed(() => {
    if (variant !== 'rmb') return 0
    return sumField(rows.value as unknown as Array<Record<string, unknown>>, 'subtotal')
  })

  // Auto-sync rmbSummary.totalActual from computed total
  if (variant === 'rmb') {
    watch(rmbTotal, (newTotal) => {
      rmbSummary.value.totalActual = newTotal
      rmbSummary.value.countDiff = calcCountDiff(newTotal, rmbSummary.value.bookBalance)
    })
  }

  // ─── Validation Helpers ────────────────────────────────────────────────

  function hasDiff(): boolean {
    if (variant !== 'rmb') return false
    return Math.abs(rmbSummary.value.countDiff) > TOLERANCE
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

  /** Update RMB summary fields (bookBalance, diffReason) */
  function updateSummary(field: keyof RmbSummary, value: number | string): void {
    if (isReadonly.value) return
    if (variant !== 'rmb') return
    if (field === 'bookBalance') {
      rmbSummary.value.bookBalance = parseNum(value)
      rmbSummary.value.countDiff = calcCountDiff(rmbSummary.value.totalActual, rmbSummary.value.bookBalance)
    } else if (field === 'diffReason') {
      rmbSummary.value.diffReason = String(value)
    }
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
