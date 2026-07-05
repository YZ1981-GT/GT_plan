/**
 * useG9Adjudication — G9-1 审定表（借方/混合计量分组/AJE+RJE）
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  G9_ACCOUNT_CODE,
  G9_ADJUDICATION_ITEMS,
  G9_CHANGE_RATE_THRESHOLD,
  G9_GROUP_LABELS,
} from './g9Constants'
import type { G9MeasurementCategory } from './g9AdjudicationItems'
import { parseG9AdjStore, patchG9AdjRow, applyG9AdjustmentWriteback, type G9AdjustmentWriteback } from './g9AdjStorage'
import {
  parseNum,
  calcAdjustedAmount,
  calcChangeAmount,
  calcChangeRate,
  isChangeRateExceeding,
  calcSubtotal,
} from './useG9FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'

export interface G9AdjudicationRow {
  rowKey: string
  label: string
  category: G9MeasurementCategory
  openingUnadjusted: number
  openingAJE: number
  openingRJE: number
  openingAdjusted: number
  closingUnadjusted: number
  closingAJE: number
  closingRJE: number
  closingAdjusted: number
  changeAmount: number
  changeRate: number | null
  reasonAnalysis: string
  indexRef: string
  changeRateHighlight: boolean
  reasonRequired: boolean
}

const ITEM_ID_ROWS = 'G9-adj-rows'
const ITEM_ID_TB = 'G9-adj-tb'
const ITEM_ID_NOTE = 'G9-adj-note'
const ITEM_ID_CONCLUSION = 'G9-adj-conclusion'

type RowStore = ReturnType<typeof parseG9AdjStore>

export function useG9Adjudication(opts: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const rowStore = ref<RowStore>(parseG9AdjStore(undefined))
  const trialBalanceAmount = ref(0)
  const auditNote = ref('')
  const auditConclusion = ref('')
  const aiLoading = ref(false)
  const collapsedGroups = ref<Record<string, boolean>>({})

  watch(() => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark, (j) => {
    rowStore.value = parseG9AdjStore(j)
  }, { immediate: true })
  watch(() => opts.allResponses.value.get(ITEM_ID_TB)?.remark, (v) => {
    trialBalanceAmount.value = parseNum(v)
  }, { immediate: true })
  watch(() => opts.allResponses.value.get(ITEM_ID_NOTE)?.conclusion, (v) => {
    auditNote.value = v ?? ''
  }, { immediate: true })
  watch(() => opts.allResponses.value.get(ITEM_ID_CONCLUSION)?.conclusion, (v) => {
    auditConclusion.value = v ?? ''
  }, { immediate: true })

  function buildRow(def: (typeof G9_ADJUDICATION_ITEMS)[number]): G9AdjudicationRow {
    const raw = rowStore.value[def.rowKey] ?? {}
    const openingUnadjusted = parseNum(raw.openingUnadjusted)
    const openingAJE = parseNum(raw.openingAJE)
    const openingRJE = parseNum(raw.openingRJE)
    const openingAdjusted = calcAdjustedAmount(openingUnadjusted, openingAJE, openingRJE)
    const closingUnadjusted = parseNum(raw.closingUnadjusted)
    const closingAJE = parseNum(raw.closingAJE)
    const closingRJE = parseNum(raw.closingRJE)
    const closingAdjusted = calcAdjustedAmount(closingUnadjusted, closingAJE, closingRJE)
    const changeRate = calcChangeRate(openingAdjusted, closingAdjusted)
    return {
      rowKey: def.rowKey,
      label: def.label,
      category: def.category,
      openingUnadjusted,
      openingAJE,
      openingRJE,
      openingAdjusted,
      closingUnadjusted,
      closingAJE,
      closingRJE,
      closingAdjusted,
      changeAmount: calcChangeAmount(closingAdjusted, openingAdjusted),
      changeRate,
      reasonAnalysis: raw.reasonAnalysis ?? '',
      indexRef: raw.indexRef ?? '',
      changeRateHighlight: isChangeRateExceeding(changeRate, G9_CHANGE_RATE_THRESHOLD),
      reasonRequired: isChangeRateExceeding(changeRate, G9_CHANGE_RATE_THRESHOLD),
    }
  }

  const dataRows = computed(() => G9_ADJUDICATION_ITEMS.map(buildRow))

  const missingReasonCount = computed(() =>
    dataRows.value.filter((r) => r.reasonRequired && !r.reasonAnalysis?.trim()).length,
  )
  const hasMissingReasons = computed(() => missingReasonCount.value > 0)

  function subtotalForCategory(category: G9MeasurementCategory) {
    const rows = dataRows.value.filter((r) => r.category === category)
    const openingAdjusted = calcSubtotal(rows.map((r) => r.openingAdjusted))
    const closingAdjusted = calcSubtotal(rows.map((r) => r.closingAdjusted))
    const changeRate = calcChangeRate(openingAdjusted, closingAdjusted)
    return {
      rowKey: `${category}_subtotal`,
      label: '小计',
      category,
      openingUnadjusted: calcSubtotal(rows.map((r) => r.openingUnadjusted)),
      openingAJE: calcSubtotal(rows.map((r) => r.openingAJE)),
      openingRJE: calcSubtotal(rows.map((r) => r.openingRJE)),
      openingAdjusted,
      closingUnadjusted: calcSubtotal(rows.map((r) => r.closingUnadjusted)),
      closingAJE: calcSubtotal(rows.map((r) => r.closingAJE)),
      closingRJE: calcSubtotal(rows.map((r) => r.closingRJE)),
      closingAdjusted,
      changeAmount: calcChangeAmount(closingAdjusted, openingAdjusted),
      changeRate,
      reasonAnalysis: '',
      indexRef: '',
      changeRateHighlight: isChangeRateExceeding(changeRate, G9_CHANGE_RATE_THRESHOLD),
      reasonRequired: false,
    }
  }

  const groupedRows = computed(() => {
    const categories: G9MeasurementCategory[] = ['FVTPL', 'FVOCI', 'AmortizedCost']
    return categories.map((cat) => ({
      groupKey: cat,
      groupName: G9_GROUP_LABELS[cat],
      collapsed: !!collapsedGroups.value[cat],
      rows: dataRows.value.filter((r) => r.category === cat),
      subtotal: subtotalForCategory(cat),
    }))
  })

  const totalRow = computed(() => {
    const subs = groupedRows.value.map((g) => g.subtotal)
    const openingAdjusted = calcSubtotal(subs.map((r) => r.openingAdjusted))
    const closingAdjusted = calcSubtotal(subs.map((r) => r.closingAdjusted))
    const changeRate = calcChangeRate(openingAdjusted, closingAdjusted)
    return {
      rowKey: 'total',
      label: '合计',
      openingAdjusted,
      closingAdjusted,
      changeAmount: calcChangeAmount(closingAdjusted, openingAdjusted),
      changeRate,
      changeRateHighlight: isChangeRateExceeding(changeRate, G9_CHANGE_RATE_THRESHOLD),
    }
  })

  const groupTotals = computed(() => ({
    fvtpl: groupedRows.value.find((g) => g.groupKey === 'FVTPL')?.subtotal.closingAdjusted ?? 0,
    fvoci: groupedRows.value.find((g) => g.groupKey === 'FVOCI')?.subtotal.closingAdjusted ?? 0,
    amortizedCost: groupedRows.value.find((g) => g.groupKey === 'AmortizedCost')?.subtotal.closingAdjusted ?? 0,
  }))

  const variance = computed(() => totalRow.value.closingAdjusted - trialBalanceAmount.value)
  const hasVarianceHighlight = computed(() => Math.abs(variance.value) > 0.01)

  const detailTotalClosing = computed(() => {
    const json = opts.allResponses.value.get('G9-detail-rows')?.remark
    if (!json) return null
    try {
      const arr = JSON.parse(json)
      if (!Array.isArray(arr)) return null
      return calcSubtotal(arr.map((r: any) => parseNum(r.closingAdjusted ?? r.closingBalance)))
    } catch {
      return null
    }
  })

  const detailCrossVariance = computed(() => {
    if (detailTotalClosing.value == null) return null
    return totalRow.value.closingAdjusted - detailTotalClosing.value
  })

  const hasDetailCrossMismatch = computed(() =>
    detailCrossVariance.value != null && Math.abs(detailCrossVariance.value) > 0.01,
  )

  function persistRows(): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rowStore.value) })
  }

  function updateField(
    rowKey: string,
    field: keyof RowStore[string],
    value: unknown,
  ): void {
    if (opts.isReadonly.value) return
    const patch: Partial<RowStore[string]> = {}
    if (field === 'reasonAnalysis' || field === 'indexRef') {
      patch[field] = String(value ?? '')
    } else {
      patch[field] = parseNum(value) as never
    }
    rowStore.value = patchG9AdjRow(rowStore.value, rowKey, patch)
    persistRows()
    publishAdjudicatedDebounced()
  }

  function updateTrialBalance(v: number): void {
    if (opts.isReadonly.value) return
    trialBalanceAmount.value = v
    opts.debouncedSave(ITEM_ID_TB, { remark: String(v) })
  }

  function updateAuditNote(value: string): void {
    if (opts.isReadonly.value) return
    auditNote.value = value
    opts.debouncedSave(ITEM_ID_NOTE, { conclusion: value })
  }

  function toggleGroup(key: string): void {
    collapsedGroups.value = { ...collapsedGroups.value, [key]: !collapsedGroups.value[key] }
  }

  let _pubTimer: ReturnType<typeof setTimeout> | null = null
  function publishAdjudicatedDebounced(): void {
    if (_pubTimer) clearTimeout(_pubTimer)
    _pubTimer = setTimeout(() => {
      _pubTimer = null
      publishAdjudicated()
    }, 1500)
  }

  function publishAdjudicated(): void {
    const amount = totalRow.value.closingAdjusted
    const groups = groupTotals.value
    opts.debouncedSave('G9-1-adjudicated-amount', { conclusion: String(amount) })
    try {
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
        detail: { accountCode: G9_ACCOUNT_CODE, adjudicatedAmount: amount, groups },
      }))
    } catch { /* silent */ }
  }

  async function loadTrialBalanceFromApi(): Promise<void> {
    if (!opts.projectId.value) return
    try {
      const res = await api.get(`/api/projects/${opts.projectId.value}/trial-balance`, {
        params: { account_prefix: G9_ACCOUNT_CODE },
        _silent: true,
      } as any)
      const list = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])
      const hit = list.find((r: any) =>
        String(r.standard_account_code ?? r.account_code ?? '').startsWith(G9_ACCOUNT_CODE),
      )
      if (hit) {
        const debit = parseNum(hit.debit_amount ?? hit.period_debit)
        const credit = parseNum(hit.credit_amount ?? hit.period_credit)
        updateTrialBalance(debit - credit)
      }
    } catch { /* optional */ }
  }

  async function generateAiAnalysis(): Promise<void> {
    if (opts.isReadonly.value) return
    aiLoading.value = true
    try {
      const res = await api.post(
        `/api/workpapers/${opts.wpId.value}/g9/ai/adjudication-analysis`,
        { rows: dataRows.value.slice(0, 20), relatedContext: { total: totalRow.value } },
        { _silent: true } as any,
      )
      const content = res?.data?.content ?? res?.content ?? ''
      if (content) {
        auditConclusion.value = content
        opts.debouncedSave(ITEM_ID_CONCLUSION, { conclusion: content })
      }
    } catch { /* optional */ }
    finally { aiLoading.value = false }
  }

  async function validateFormulasRemote(): Promise<{ ok: boolean; errors: { field: string; message: string }[] }> {
    try {
      const adjJson = opts.allResponses.value.get('G9-adjustment-rows')?.remark
      let debits: number[] = []
      let credits: number[] = []
      if (adjJson) {
        try {
          const arr = JSON.parse(adjJson)
          if (Array.isArray(arr)) {
            debits = arr.map((r: any) => parseNum(r.debitAmount))
            credits = arr.map((r: any) => parseNum(r.creditAmount))
          }
        } catch { /* ignore */ }
      }
      const l3Json = opts.allResponses.value.get('G9-l3-rows')?.remark
      let l3Rows: unknown[] = []
      if (l3Json) {
        try {
          const arr = JSON.parse(l3Json)
          if (Array.isArray(arr)) l3Rows = arr
        } catch { /* ignore */ }
      }
      const res = await api.post(`/api/workpapers/${opts.wpId.value}/g9/validate-formulas`, {
        adjudication_rows: dataRows.value.map((r) => ({
          rowKey: r.rowKey,
          openingUnadjusted: r.openingUnadjusted,
          openingAJE: r.openingAJE,
          openingRJE: r.openingRJE,
          openingAdjusted: r.openingAdjusted,
          closingUnadjusted: r.closingUnadjusted,
          closingAJE: r.closingAJE,
          closingRJE: r.closingRJE,
          closingAdjusted: r.closingAdjusted,
        })),
        l3_rows: l3Rows,
        adjustment_debits: debits,
        adjustment_credits: credits,
      }, { _silent: true } as any)
      const data = res?.data ?? res
      return { ok: !!data.ok, errors: data.errors ?? [] }
    } catch {
      return { ok: true, errors: [] }
    }
  }

  function applyAdjustmentWriteback(aje: number, rje: number, rowKey = 'fvtpl_1'): void {
    if (opts.isReadonly.value) return
    rowStore.value = applyG9AdjustmentWriteback(rowStore.value, { rowKey, closingAje: aje, closingRje: rje })
    persistRows()
    publishAdjudicatedDebounced()
  }

  function onAdjustmentWriteback(ev: Event): void {
    const detail = (ev as CustomEvent<G9AdjustmentWriteback>).detail
    if (!detail) return
    applyAdjustmentWriteback(detail.closingAje, detail.closingRje, detail.rowKey)
  }

  function syncWritebackFromOverlay(): void {
    const json = opts.allResponses.value.get('G9-aje-adj-overlay')?.remark
    if (!json) return
    try {
      const wb = JSON.parse(json) as G9AdjustmentWriteback
      if (wb && typeof wb.closingAje === 'number') {
        rowStore.value = applyG9AdjustmentWriteback(rowStore.value, wb)
      }
    } catch { /* ignore */ }
  }

  onMounted(() => {
    if (!trialBalanceAmount.value) void loadTrialBalanceFromApi()
    syncWritebackFromOverlay()
    publishAdjudicated()
    window.addEventListener('g9:adjustment-writeback', onAdjustmentWriteback)
  })

  onBeforeUnmount(() => {
    window.removeEventListener('g9:adjustment-writeback', onAdjustmentWriteback)
  })

  return {
    groupedRows,
    totalRow,
    variance,
    hasVarianceHighlight,
    hasDetailCrossMismatch,
    detailTotalClosing,
    detailCrossVariance,
    trialBalanceAmount,
    auditNote,
    auditConclusion,
    aiLoading,
    updateField,
    updateTrialBalance,
    updateAuditNote,
    toggleGroup,
    loadTrialBalanceFromApi,
    generateAiAnalysis,
    publishAdjudicated,
    validateFormulasRemote,
    applyAdjustmentWriteback,
    dataRows,
    missingReasonCount,
    hasMissingReasons,
    accountCode: G9_ACCOUNT_CODE,
  }
}
