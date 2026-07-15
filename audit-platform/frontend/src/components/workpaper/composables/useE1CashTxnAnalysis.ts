/**
 * useE1CashTxnAnalysis — E1-26 现金交易分析（IPO/舞弊应对）
 *
 * 分段：月度总体 → 合理性分析 → 金额分布/分层 → 客户供应商概要 → 说明/结论
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { UseE1BaseOptions, ChecklistItem } from './useE1Adjudication'

export const E1_CASH_TXN_PACK_KEY = 'E1-cash-txn-analysis-pack'
export const E1_CASH_TXN_NOTE_KEY = 'E1-cash-txn-audit-note'
export const E1_CASH_TXN_CONCLUSION_KEY = 'E1-cash-txn-audit-conclusion'
export const E1_IPO_APPLICABLE_KEY = 'E1-ipo-applicable'

export interface MonthAmountRow {
  month: number
  current: number
  prior: number
  prior2: number // 上上期，用于算「上期变动」
}

export interface SideSummary {
  taxInclusiveBase: number // 当期含税收入/支出
  remark: string
}

export interface StratumRow {
  id: string
  label: string
  current: number
  prior: number
}

export interface DistSide {
  totalAmount: number
  txnCount: number
  strata: StratumRow[]
  remark: string
}

export interface ProfileMetric {
  key: string
  label: string
  value: number | string
  remark: string
  isRatio?: boolean
}

export interface CashTxnPack {
  salesMonths: MonthAmountRow[]
  purchaseMonths: MonthAmountRow[]
  salesOverall: SideSummary
  purchaseOverall: SideSummary
  reasonablenessNote: string
  salesDist: DistSide
  purchaseDist: DistSide
  salesProfile: ProfileMetric[]
  purchaseProfile: ProfileMetric[]
  overallRemark: string
}

function uid(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function changeRate(current: number, prior: number): number | null {
  if (prior === 0) return current === 0 ? 0 : null
  return (current - prior) / prior
}

function emptyMonths(): MonthAmountRow[] {
  return Array.from({ length: 12 }, (_, i) => ({
    month: i + 1,
    current: 0,
    prior: 0,
    prior2: 0,
  }))
}

function defaultStrata(): StratumRow[] {
  return [
    { id: uid('st'), label: '0~~A万元', current: 0, prior: 0 },
    { id: uid('st'), label: 'A~B万元', current: 0, prior: 0 },
  ]
}

export function defaultSalesProfile(): ProfileMetric[] {
  return [
    { key: 'totalCustomers', label: '当期总客户数', value: 0, remark: '' },
    { key: 'cashCustomers', label: '涉现收款客户数', value: 0, remark: '' },
    { key: 'cashCustomerRatio', label: '涉现收款客户占比', value: '', remark: '', isRatio: true },
    { key: 'avgCashPerCustomer', label: '涉现客户平均现金收款金额', value: 0, remark: '' },
    { key: 'top50CashRatio', label: '前50名现金收款客户占总收入比', value: '', remark: '', isRatio: true },
    { key: 'cashOnlyCustomers', label: '仅现收款客户数', value: 0, remark: '' },
    { key: 'cashOnlyCustomerRatio', label: '仅现收款客户数占总客户数之比', value: '', remark: '', isRatio: true },
    { key: 'cashOnlyAmount', label: '仅现收款客户收款总额', value: 0, remark: '' },
    { key: 'cashOnlyRevenueRatio', label: '仅现收款客户占总收入之比', value: '', remark: '', isRatio: true },
  ]
}

export function defaultPurchaseProfile(): ProfileMetric[] {
  return [
    { key: 'totalSuppliers', label: '当期总供应商数', value: 0, remark: '' },
    { key: 'cashSuppliers', label: '涉现付款供应商数', value: 0, remark: '' },
    { key: 'cashSupplierRatio', label: '涉现付款供应商占比', value: '', remark: '', isRatio: true },
    { key: 'avgCashPerSupplier', label: '涉现供应商平均现金付款金额', value: 0, remark: '' },
    { key: 'top50CashRatio', label: '前50名现金付款供应商占总采购比', value: '', remark: '', isRatio: true },
    { key: 'cashOnlySuppliers', label: '仅现付款供应商数', value: 0, remark: '' },
    { key: 'cashOnlySupplierRatio', label: '仅现付款供应商占总供应商数之比', value: '', remark: '', isRatio: true },
    { key: 'cashOnlyAmount', label: '仅现付款供应商付款总额', value: 0, remark: '' },
    { key: 'cashOnlyPurchaseRatio', label: '仅现付款供应商占总采购金额之比', value: '', remark: '', isRatio: true },
  ]
}

function emptyDist(): DistSide {
  return { totalAmount: 0, txnCount: 0, strata: defaultStrata(), remark: '' }
}

export function createEmptyPack(): CashTxnPack {
  return {
    salesMonths: emptyMonths(),
    purchaseMonths: emptyMonths(),
    salesOverall: { taxInclusiveBase: 0, remark: '' },
    purchaseOverall: { taxInclusiveBase: 0, remark: '' },
    reasonablenessNote: '',
    salesDist: emptyDist(),
    purchaseDist: emptyDist(),
    salesProfile: defaultSalesProfile(),
    purchaseProfile: defaultPurchaseProfile(),
    overallRemark: '',
  }
}

function normalizeMonths(raw: unknown): MonthAmountRow[] {
  const base = emptyMonths()
  if (!Array.isArray(raw)) return base
  return base.map((row, i) => {
    const src = raw.find((r: any) => Number(r?.month) === i + 1) || raw[i] || {}
    return {
      month: i + 1,
      current: num(src.current ?? src.cashSalesCurrent),
      prior: num(src.prior ?? src.cashSalesPrior),
      prior2: num(src.prior2),
    }
  })
}

function normalizeProfile(raw: unknown, fallback: () => ProfileMetric[]): ProfileMetric[] {
  const defaults = fallback()
  if (!Array.isArray(raw) || !raw.length) return defaults
  return defaults.map(d => {
    const hit = raw.find((r: any) => r?.key === d.key) || {}
    return {
      ...d,
      value: hit.value !== undefined && hit.value !== null ? hit.value : d.value,
      remark: String(hit.remark || ''),
    }
  })
}

function normalizeDist(raw: unknown): DistSide {
  const empty = emptyDist()
  if (!raw || typeof raw !== 'object') return empty
  const obj = raw as Record<string, unknown>
  const strata = Array.isArray(obj.strata) && obj.strata.length
    ? obj.strata.map((s: any) => ({
        id: String(s.id || uid('st')),
        label: String(s.label || ''),
        current: num(s.current),
        prior: num(s.prior),
      }))
    : defaultStrata()
  return {
    totalAmount: num(obj.totalAmount),
    txnCount: num(obj.txnCount),
    strata,
    remark: String(obj.remark || ''),
  }
}

function monthSideView(rows: MonthAmountRow[]) {
  const withRates = rows.map(r => ({
    ...r,
    change: changeRate(r.current, r.prior),
    priorChange: changeRate(r.prior, r.prior2),
  }))
  const totalCurrent = rows.reduce((s, r) => s + r.current, 0)
  const totalPrior = rows.reduce((s, r) => s + r.prior, 0)
  const totalPrior2 = rows.reduce((s, r) => s + r.prior2, 0)
  return {
    rows: withRates,
    totalCurrent,
    totalPrior,
    totalChange: changeRate(totalCurrent, totalPrior),
    totalPriorChange: changeRate(totalPrior, totalPrior2),
    monthlyAvg: totalCurrent / 12,
  }
}

export function formatPct(rate: number | null): string {
  if (rate == null) return currentIsInf()
  return `${(rate * 100).toFixed(2)}%`
}

function currentIsInf(): string {
  return '—'
}

export function useE1CashTxnAnalysis(options: UseE1BaseOptions) {
  const { allResponses, saveImmediate, isReadonly } = options

  const pack = ref<CashTxnPack>(createEmptyPack())
  const auditNote = ref('')
  const auditConclusion = ref('')
  const isLoading = ref(false)

  const isApplicable = computed(() => {
    const v = allResponses.value.get(E1_IPO_APPLICABLE_KEY)?.conclusion
    return v !== 'N'
  })

  function load(): void {
    isLoading.value = true
    try {
      const raw = allResponses.value.get(E1_CASH_TXN_PACK_KEY)?.remark
      if (raw) {
        try {
          const parsed = JSON.parse(raw)
          if (parsed && typeof parsed === 'object') {
            pack.value = {
              ...createEmptyPack(),
              ...parsed,
              salesMonths: normalizeMonths(parsed.salesMonths),
              purchaseMonths: normalizeMonths(parsed.purchaseMonths),
              salesOverall: {
                taxInclusiveBase: num(parsed.salesOverall?.taxInclusiveBase),
                remark: String(parsed.salesOverall?.remark || ''),
              },
              purchaseOverall: {
                taxInclusiveBase: num(parsed.purchaseOverall?.taxInclusiveBase),
                remark: String(parsed.purchaseOverall?.remark || ''),
              },
              reasonablenessNote: String(parsed.reasonablenessNote || ''),
              salesDist: normalizeDist(parsed.salesDist),
              purchaseDist: normalizeDist(parsed.purchaseDist),
              salesProfile: normalizeProfile(parsed.salesProfile, defaultSalesProfile),
              purchaseProfile: normalizeProfile(parsed.purchaseProfile, defaultPurchaseProfile),
              overallRemark: String(parsed.overallRemark || ''),
            }
          }
        } catch {
          pack.value = createEmptyPack()
        }
      } else {
        // 兼容旧 IPO 薄表：仅月份现金销售/采购
        const legacy = allResponses.value.get('E1-ipo-E1-26-rows')?.remark
        if (legacy) {
          try {
            const rows = JSON.parse(legacy)
            if (Array.isArray(rows) && rows.length) {
              const next = createEmptyPack()
              next.salesMonths = next.salesMonths.map((m, i) => {
                const src = rows.find((r: any) => Number(r.month) === i + 1) || rows[i] || {}
                return {
                  month: i + 1,
                  current: num(src.cashSalesCurrent),
                  prior: num(src.cashSalesPrior),
                  prior2: 0,
                }
              })
              next.purchaseMonths = next.purchaseMonths.map((m, i) => {
                const src = rows.find((r: any) => Number(r.month) === i + 1) || rows[i] || {}
                return {
                  month: i + 1,
                  current: num(src.cashPurchaseCurrent),
                  prior: num(src.cashPurchasePrior),
                  prior2: 0,
                }
              })
              pack.value = next
            }
          } catch { /* ignore */ }
        }
      }
      auditNote.value =
        allResponses.value.get(E1_CASH_TXN_NOTE_KEY)?.remark
        || allResponses.value.get('E1-ipo-audit-note-E1-26')?.remark
        || ''
      auditConclusion.value =
        allResponses.value.get(E1_CASH_TXN_CONCLUSION_KEY)?.remark
        || allResponses.value.get('E1-ipo-audit-conclusion-E1-26')?.remark
        || ''
    } finally {
      isLoading.value = false
    }
  }

  load()

  watch(
    () => allResponses.value.get(E1_CASH_TXN_PACK_KEY)?.remark,
    (n, o) => {
      if (n !== o) load()
    },
  )

  let saveTimer: ReturnType<typeof setTimeout> | null = null

  function scheduleSave(): void {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      persistPack()
    }, 2000)
  }

  function persistPack(): void {
    const remark = JSON.stringify(pack.value)
    const items: ChecklistItem[] = [
      { item_id: E1_CASH_TXN_PACK_KEY, conclusion: null, remark },
    ]
    allResponses.value.set(E1_CASH_TXN_PACK_KEY, { item_id: E1_CASH_TXN_PACK_KEY, conclusion: null, remark })
    void saveImmediate(items)
  }

  function patchPack(mutator: (p: CashTxnPack) => void): void {
    if (isReadonly.value) return
    const next = JSON.parse(JSON.stringify(pack.value)) as CashTxnPack
    mutator(next)
    pack.value = next
    scheduleSave()
  }

  function setApplicable(val: boolean): void {
    if (isReadonly.value) return
    const conclusion = val ? 'Y' : 'N'
    const item = { item_id: E1_IPO_APPLICABLE_KEY, conclusion, remark: null }
    allResponses.value.set(E1_IPO_APPLICABLE_KEY, item)
    void saveImmediate([item])
  }

  function saveNote(val: string): void {
    if (isReadonly.value) return
    auditNote.value = val
    const item = { item_id: E1_CASH_TXN_NOTE_KEY, conclusion: null, remark: val }
    allResponses.value.set(E1_CASH_TXN_NOTE_KEY, item)
    void saveImmediate([item])
  }

  function saveConclusion(val: string): void {
    if (isReadonly.value) return
    auditConclusion.value = val
    const item = { item_id: E1_CASH_TXN_CONCLUSION_KEY, conclusion: null, remark: val }
    allResponses.value.set(E1_CASH_TXN_CONCLUSION_KEY, item)
    void saveImmediate([item])
  }

  const salesView = computed(() => monthSideView(pack.value.salesMonths))
  const purchaseView = computed(() => monthSideView(pack.value.purchaseMonths))

  const salesShare = computed(() => {
    const base = pack.value.salesOverall.taxInclusiveBase
    if (!base) return null
    return salesView.value.totalCurrent / base
  })
  const purchaseShare = computed(() => {
    const base = pack.value.purchaseOverall.taxInclusiveBase
    if (!base) return null
    return purchaseView.value.totalCurrent / base
  })

  const salesAvgPerTxn = computed(() => {
    const c = pack.value.salesDist.txnCount
    return c ? pack.value.salesDist.totalAmount / c : 0
  })
  const purchaseAvgPerTxn = computed(() => {
    const c = pack.value.purchaseDist.txnCount
    return c ? pack.value.purchaseDist.totalAmount / c : 0
  })

  const highCashShare = computed(() =>
    (salesShare.value != null && salesShare.value >= 0.3)
    || (purchaseShare.value != null && purchaseShare.value >= 0.3),
  )

  function replacePack(next: CashTxnPack): void {
    if (isReadonly.value) return
    pack.value = {
      ...createEmptyPack(),
      ...next,
      salesMonths: normalizeMonths(next.salesMonths),
      purchaseMonths: normalizeMonths(next.purchaseMonths),
      salesDist: normalizeDist(next.salesDist),
      purchaseDist: normalizeDist(next.purchaseDist),
      salesProfile: normalizeProfile(next.salesProfile, defaultSalesProfile),
      purchaseProfile: normalizeProfile(next.purchaseProfile, defaultPurchaseProfile),
    }
    persistPack()
  }

  onBeforeUnmount(() => {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
      persistPack()
    }
  })

  return {
    pack,
    auditNote,
    auditConclusion,
    isLoading,
    isApplicable,
    salesView,
    purchaseView,
    salesShare,
    purchaseShare,
    salesAvgPerTxn,
    purchaseAvgPerTxn,
    highCashShare,
    load,
    patchPack,
    setApplicable,
    saveNote,
    saveConclusion,
    replacePack,
    formatPct,
    changeRate,
  }
}
