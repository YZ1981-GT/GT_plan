/**
 * useE1InterestCalc — E1-15/E1-20 利息计算 composable (variant复用)
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 12.1
 *
 * 职责：
 * - variant='monthly' (E1-15): 12月×存款类型矩阵, 每月测算利息=月均余额×月利率, 差异=测算-账面
 * - variant='accrued' (E1-20): 按账户明细行, 应计利息=本金×日利率×天数, 含外币折算(×汇率→人民币)
 * - 序列化/反序列化 → checklist_responses
 *   - monthly: 'E1-interest-monthly-rows'
 *   - accrued: 'E1-accrued-interest-rows'
 * - Debounce 2s 自动保存
 *
 * Requirements: 9.4-9.6, 10.3-10.4
 */
import { ref, computed, watch, onBeforeUnmount, type ComputedRef } from 'vue'
import type { UseE1BaseOptions, ChecklistItem } from './useE1Adjudication'
import { parseNum, calcAccruedInterest, calcFxConvert, sumField } from './useE1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type InterestCalcVariant = 'monthly' | 'accrued'

/** E1-15 月度利息分析 — 每行=一个月 */
export interface MonthlyInterestRow {
  id: string
  month: number              // 1-12
  monthlyAvgBalance: number  // 月均余额
  monthlyRate: number        // 月利率
  calculatedInterest: number // readonly: balance × rate
}

/** E1-15 汇总数据 */
export interface MonthlySummary {
  totalCalculated: number    // 测算利息合计
  bookInterest: number       // 账面利息收入
  diff: number               // 差异 = calculated - book
}

/** E1-20 应计利息测算 — 每行=一个银行账户 */
export interface AccruedInterestRow {
  id: string
  bank: string               // 开户银行
  accountNo: string          // 银行账号
  usage: string              // 用途
  currency: string           // 币种
  fcAmount: number           // 原币金额
  settleDate: string         // 结息日
  cutoffDate: string         // 截止日
  days: number               // readonly: cutoff - settle (天数)
  dailyRate: number          // 日利率
  accruedFc: number          // readonly: fcAmount × days × dailyRate
  fxRate: number             // 汇率
  accruedRmb: number         // readonly: accruedFc × fxRate
  note: string               // 备注
}

// ─── Constants ───────────────────────────────────────────────────────────────

function getStorageKey(variant: InterestCalcVariant): string {
  return variant === 'monthly' ? 'E1-interest-monthly-rows' : 'E1-accrued-interest-rows'
}

const MONTHLY_USER_FIELDS = ['id', 'month', 'monthlyAvgBalance', 'monthlyRate']
const ACCRUED_USER_FIELDS = ['id', 'bank', 'accountNo', 'usage', 'currency', 'fcAmount', 'settleDate', 'cutoffDate', 'dailyRate', 'fxRate', 'note']

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(prefix: string): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `${prefix}-${crypto.randomUUID()}`
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

/** 计算两个日期之间的天数 */
function calcDaysBetween(settleDate: string, cutoffDate: string): number {
  if (!settleDate || !cutoffDate) return 0
  const d1 = new Date(settleDate)
  const d2 = new Date(cutoffDate)
  if (isNaN(d1.getTime()) || isNaN(d2.getTime())) return 0
  const diffMs = d2.getTime() - d1.getTime()
  return Math.max(0, Math.round(diffMs / (1000 * 60 * 60 * 24)))
}

function recalcMonthlyRow(row: MonthlyInterestRow): MonthlyInterestRow {
  return { ...row, calculatedInterest: row.monthlyAvgBalance * row.monthlyRate }
}

function recalcAccruedRow(row: AccruedInterestRow): AccruedInterestRow {
  const days = calcDaysBetween(row.settleDate, row.cutoffDate)
  const accruedFc = calcAccruedInterest(row.fcAmount, days, row.dailyRate)
  const accruedRmb = calcFxConvert(accruedFc, row.fxRate)
  return { ...row, days, accruedFc, accruedRmb }
}

function createDefaultMonthlyRows(): MonthlyInterestRow[] {
  return Array.from({ length: 12 }, (_, i) =>
    recalcMonthlyRow({
      id: `monthly-${i + 1}`,
      month: i + 1,
      monthlyAvgBalance: 0,
      monthlyRate: 0,
      calculatedInterest: 0,
    }),
  )
}

function createEmptyAccruedRow(): AccruedInterestRow {
  return recalcAccruedRow({
    id: generateRowId('accrued'),
    bank: '',
    accountNo: '',
    usage: '',
    currency: '人民币',
    fcAmount: 0,
    settleDate: '',
    cutoffDate: '',
    days: 0,
    dailyRate: 0,
    accruedFc: 0,
    fxRate: 1,
    accruedRmb: 0,
    note: '',
  })
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useE1InterestCalc(options: UseE1BaseOptions & { variant: InterestCalcVariant }) {
  const { allResponses, saveImmediate, isReadonly, variant } = options
  const storageKey = getStorageKey(variant)

  // ─── State ─────────────────────────────────────────────────────────────

  const rows = ref<Array<MonthlyInterestRow | AccruedInterestRow>>([])
  const isLoading = ref(false)

  // Monthly summary (E1-15 only)
  const monthlySummary = ref<MonthlySummary>({ totalCalculated: 0, bookInterest: 0, diff: 0 })

  // ─── Deserialization ───────────────────────────────────────────────────

  function loadFromResponses(): void {
    const response = allResponses.value.get(storageKey)
    const raw = response?.remark
    if (!raw) {
      rows.value = variant === 'monthly' ? createDefaultMonthlyRows() : [createEmptyAccruedRow()]
      loadMonthlySummary()
      return
    }
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed) || parsed.length === 0) {
        rows.value = variant === 'monthly' ? createDefaultMonthlyRows() : [createEmptyAccruedRow()]
        loadMonthlySummary()
        return
      }
      if (variant === 'monthly') {
        rows.value = parsed.map((r: Record<string, unknown>) =>
          recalcMonthlyRow({
            id: String(r.id || generateRowId('monthly')),
            month: parseNum(r.month),
            monthlyAvgBalance: parseNum(r.monthlyAvgBalance),
            monthlyRate: parseNum(r.monthlyRate),
            calculatedInterest: 0,
          }),
        )
      } else {
        rows.value = parsed.map((r: Record<string, unknown>) =>
          recalcAccruedRow({
            id: String(r.id || generateRowId('accrued')),
            bank: String(r.bank || ''),
            accountNo: String(r.accountNo || ''),
            usage: String(r.usage || ''),
            currency: String(r.currency || '人民币'),
            fcAmount: parseNum(r.fcAmount),
            settleDate: String(r.settleDate || ''),
            cutoffDate: String(r.cutoffDate || ''),
            days: 0,
            dailyRate: parseNum(r.dailyRate),
            accruedFc: 0,
            fxRate: parseNum(r.fxRate) || 1,
            accruedRmb: 0,
            note: String(r.note || ''),
          }),
        )
      }
      loadMonthlySummary()
    } catch {
      console.warn(`[useE1InterestCalc:${variant}] JSON parse failed, fallback to default`)
      rows.value = variant === 'monthly' ? createDefaultMonthlyRows() : [createEmptyAccruedRow()]
    }
  }

  function loadMonthlySummary(): void {
    if (variant !== 'monthly') return
    const summaryResp = allResponses.value.get(`${storageKey}-summary`)
    if (summaryResp?.remark) {
      try {
        const s = JSON.parse(summaryResp.remark)
        monthlySummary.value = {
          totalCalculated: parseNum(s.totalCalculated),
          bookInterest: parseNum(s.bookInterest),
          diff: parseNum(s.totalCalculated) - parseNum(s.bookInterest),
        }
      } catch { /* use defaults */ }
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

  // ─── Computed ──────────────────────────────────────────────────────────

  /** Monthly: 测算利息合计 */
  const totalCalculated = computed(() => {
    if (variant !== 'monthly') return 0
    return sumField(rows.value as unknown as Array<Record<string, unknown>>, 'calculatedInterest')
  })

  // Auto-sync summary
  if (variant === 'monthly') {
    watch(totalCalculated, (newTotal) => {
      monthlySummary.value.totalCalculated = newTotal
      monthlySummary.value.diff = newTotal - monthlySummary.value.bookInterest
    })
  }

  // ─── Serialization ─────────────────────────────────────────────────────

  function serializeRows(): string {
    const fields = variant === 'monthly' ? MONTHLY_USER_FIELDS : ACCRUED_USER_FIELDS
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

    // Persist monthly summary
    if (variant === 'monthly') {
      const summaryKey = `${storageKey}-summary`
      const summaryJson = JSON.stringify(monthlySummary.value)
      allResponses.value.set(summaryKey, { item_id: summaryKey, conclusion: null, remark: summaryJson })
      items.push({ item_id: summaryKey, conclusion: null, remark: summaryJson })
    }

    saveImmediate(items).catch(() => { /* silent */ })
  }

  // ─── Row CRUD ──────────────────────────────────────────────────────────

  function addRow(): void {
    if (isReadonly.value) return
    if (variant === 'monthly') return // Monthly has fixed 12 rows
    rows.value = [...rows.value, createEmptyAccruedRow()]
    scheduleSave()
  }

  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    if (variant === 'monthly') return // Monthly has fixed 12 rows
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
    const numericFields = ['monthlyAvgBalance', 'monthlyRate', 'fcAmount', 'dailyRate', 'fxRate']
    if (numericFields.includes(field)) {
      row[field] = parseNum(value)
    } else {
      row[field] = String(value)
    }

    let recalculated: MonthlyInterestRow | AccruedInterestRow
    if (variant === 'monthly') {
      recalculated = recalcMonthlyRow(row as unknown as MonthlyInterestRow)
    } else {
      recalculated = recalcAccruedRow(row as unknown as AccruedInterestRow)
    }

    const newRows = [...rows.value]
    newRows[idx] = recalculated
    rows.value = newRows
    scheduleSave()
  }

  /** Update monthly summary bookInterest */
  function updateSummary(field: keyof MonthlySummary, value: number): void {
    if (isReadonly.value) return
    if (variant !== 'monthly') return
    if (field === 'bookInterest') {
      monthlySummary.value.bookInterest = parseNum(value)
      monthlySummary.value.diff = monthlySummary.value.totalCalculated - monthlySummary.value.bookInterest
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
    monthlySummary,
    totalCalculated,
    isLoading,
    addRow,
    removeRow,
    updateCell,
    updateSummary,
    hydrate,
  }
}
