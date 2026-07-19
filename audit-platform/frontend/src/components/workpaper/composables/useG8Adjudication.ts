import { useWorkpaperAuditYear } from './workpaperAuditYear'
/**
 * useG8Adjudication — G8-1 审定表（借方/单分组公允价值/账项调整）
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  G8_ACCOUNT_CODE,
  G8_ADJUDICATION_ITEMS,
  G8_CHANGE_RATE_THRESHOLD,
  G8_GROUP_LABEL,
} from './g8Constants'
import { parseG8AdjStore, patchG8AdjRow, applyG8AdjustmentWriteback, type G8AdjustmentWriteback } from './g8AdjStorage'
import {
  parseNum,
  calcAdjustedAmount,
  calcChangeAmount,
  calcChangeRate,
  isChangeRateExceeding,
  calcSubtotal,
} from './useG8FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'

export interface G8AdjudicationRow {
  rowKey: string
  label: string
  openingUnadjusted: number
  openingAdjustment: number
  openingAdjusted: number
  closingUnadjusted: number
  closingAdjustment: number
  closingAdjusted: number
  changeAmount: number
  changeRate: number | null
  reasonAnalysis: string
  indexRef: string
  changeRateHighlight: boolean
  reasonRequired: boolean
}

const ITEM_ID_ROWS = 'G8-adj-rows'
const ITEM_ID_TB = 'G8-adj-tb'
const ITEM_ID_NOTE = 'G8-adj-note'
const ITEM_ID_CONCLUSION = 'G8-adj-conclusion'

type RowStore = ReturnType<typeof parseG8AdjStore>

export function useG8Adjudication(opts: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const _auditYearRef = useWorkpaperAuditYear()
  const rowStore = ref<RowStore>(parseG8AdjStore(undefined))
  const trialBalanceAmount = ref(0)
  const auditNote = ref('')
  const auditConclusion = ref('')
  const aiLoading = ref(false)
  const collapsed = ref(false)

  watch(() => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark, (j) => {
    rowStore.value = parseG8AdjStore(j)
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

  function buildRow(def: (typeof G8_ADJUDICATION_ITEMS)[number]): G8AdjudicationRow {
    const raw = rowStore.value[def.rowKey] ?? {}
    const openingUnadjusted = parseNum(raw.openingUnadjusted)
    const openingAdjustment = parseNum(raw.openingAdjustment)
    const openingAdjusted = calcAdjustedAmount(openingUnadjusted, openingAdjustment)
    const closingUnadjusted = parseNum(raw.closingUnadjusted)
    const closingAdjustment = parseNum(raw.closingAdjustment)
    const closingAdjusted = calcAdjustedAmount(closingUnadjusted, closingAdjustment)
    const changeRate = calcChangeRate(openingAdjusted, closingAdjusted)
    const reasonRequired = isChangeRateExceeding(changeRate, G8_CHANGE_RATE_THRESHOLD)
    return {
      rowKey: def.rowKey,
      label: def.label,
      openingUnadjusted,
      openingAdjustment,
      openingAdjusted,
      closingUnadjusted,
      closingAdjustment,
      closingAdjusted,
      changeAmount: calcChangeAmount(closingAdjusted, openingAdjusted),
      changeRate,
      reasonAnalysis: raw.reasonAnalysis ?? '',
      indexRef: raw.indexRef ?? '',
      changeRateHighlight: reasonRequired,
      reasonRequired,
    }
  }

  const dataRows = computed(() => G8_ADJUDICATION_ITEMS.map(buildRow))

  const missingReasonCount = computed(() =>
    dataRows.value.filter((r) => r.reasonRequired && !r.reasonAnalysis?.trim()).length,
  )
  const hasMissingReasons = computed(() => missingReasonCount.value > 0)

  const groupedRows = computed(() => {
    const rows = dataRows.value
    const openingAdjusted = calcSubtotal(rows.map((r) => r.openingAdjusted))
    const closingAdjusted = calcSubtotal(rows.map((r) => r.closingAdjusted))
    const changeRate = calcChangeRate(openingAdjusted, closingAdjusted)
    return [{
      groupKey: 'fair_value',
      groupName: G8_GROUP_LABEL,
      collapsed: collapsed.value,
      rows,
      subtotal: {
        openingAdjusted,
        closingAdjusted,
        changeRate,
        changeRateHighlight: isChangeRateExceeding(changeRate, G8_CHANGE_RATE_THRESHOLD),
      },
    }]
  })

  const totalRow = computed(() => {
    const rows = dataRows.value
    const openingAdjusted = calcSubtotal(rows.map((r) => r.openingAdjusted))
    const closingAdjusted = calcSubtotal(rows.map((r) => r.closingAdjusted))
    const changeRate = calcChangeRate(openingAdjusted, closingAdjusted)
    return {
      rowKey: 'total',
      label: '合  计',
      openingUnadjusted: calcSubtotal(rows.map((r) => r.openingUnadjusted)),
      openingAdjustment: calcSubtotal(rows.map((r) => r.openingAdjustment)),
      openingAdjusted,
      closingUnadjusted: calcSubtotal(rows.map((r) => r.closingUnadjusted)),
      closingAdjustment: calcSubtotal(rows.map((r) => r.closingAdjustment)),
      closingAdjusted,
      changeAmount: calcChangeAmount(closingAdjusted, openingAdjusted),
      changeRate,
      reasonAnalysis: '',
      indexRef: '',
      changeRateHighlight: isChangeRateExceeding(changeRate, G8_CHANGE_RATE_THRESHOLD),
      reasonRequired: false,
    }
  })

  const variance = computed(() => totalRow.value.closingAdjusted - trialBalanceAmount.value)
  const hasVarianceHighlight = computed(() => Math.abs(variance.value) > 0.01)

  const detailTotalClosing = computed(() => {
    const json = opts.allResponses.value.get('G8-detail-rows')?.remark
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

  type EditableField =
    | 'openingUnadjusted' | 'openingAdjustment'
    | 'closingUnadjusted' | 'closingAdjustment'
    | 'reasonAnalysis' | 'indexRef'

  function updateField(rowKey: string, field: EditableField, value: unknown): void {
    if (opts.isReadonly.value) return
    const patch: Partial<RowStore[string]> = {}
    if (field === 'reasonAnalysis' || field === 'indexRef') {
      patch[field] = String(value ?? '')
    } else {
      patch[field] = parseNum(value) as never
    }
    rowStore.value = patchG8AdjRow(rowStore.value, rowKey, patch)
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

  function toggleGroup(): void {
    collapsed.value = !collapsed.value
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
    opts.debouncedSave('G8-1-adjudicated-amount', { conclusion: String(amount) })
    try {
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
        detail: { accountCode: G8_ACCOUNT_CODE, adjudicatedAmount: amount },
      }))
    } catch { /* silent */ }
  }

  async function loadTrialBalanceFromApi(): Promise<void> {
    const _year = _auditYearRef.value
    if (_year == null) return
    if (!opts.projectId.value) return
    try {
      const res = await api.get(`/api/projects/${opts.projectId.value}/trial-balance`, {
        params: { year: _year, account_prefix: G8_ACCOUNT_CODE  },
        _silent: true,
      } as any)
      const list = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])
      const hit = list.find((r: any) =>
        String(r.standard_account_code ?? r.account_code ?? '').startsWith(G8_ACCOUNT_CODE),
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
        `/api/workpapers/${opts.wpId.value}/g8/ai/adjudication-analysis`,
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
      const adjJson = opts.allResponses.value.get('G8-adjustment-rows')?.remark
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
      const res = await api.post(`/api/workpapers/${opts.wpId.value}/g8/validate-formulas`, {
        adjudication_rows: dataRows.value.map((r) => ({
          rowKey: r.rowKey,
          openingUnadjusted: r.openingUnadjusted,
          openingAdjustment: r.openingAdjustment,
          openingAdjusted: r.openingAdjusted,
          closingUnadjusted: r.closingUnadjusted,
          closingAdjustment: r.closingAdjustment,
          closingAdjusted: r.closingAdjusted,
        })),
        detail_rows: [],
        fair_value_rows: [],
        adjustment_debits: debits,
        adjustment_credits: credits,
      }, { _silent: true } as any)
      const data = res?.data ?? res
      return { ok: !!data.ok, errors: data.errors ?? [] }
    } catch {
      return { ok: true, errors: [] }
    }
  }

  function applyAdjustmentWriteback(closingAdjustment: number, rowKey = 'fv_1'): void {
    if (opts.isReadonly.value) return
    rowStore.value = applyG8AdjustmentWriteback(rowStore.value, { rowKey, closingAdjustment })
    persistRows()
    publishAdjudicatedDebounced()
  }

  function onAdjustmentWriteback(ev: Event): void {
    const detail = (ev as CustomEvent<G8AdjustmentWriteback>).detail
    if (!detail) return
    applyAdjustmentWriteback(detail.closingAdjustment, detail.rowKey)
  }

  function syncWritebackFromOverlay(): void {
    const json = opts.allResponses.value.get('G8-adj-overlay')?.remark
    if (!json) return
    try {
      const wb = JSON.parse(json) as G8AdjustmentWriteback
      if (wb && typeof wb.closingAdjustment === 'number') {
        rowStore.value = applyG8AdjustmentWriteback(rowStore.value, wb)
      }
    } catch { /* ignore */ }
  }

  onMounted(() => {
    if (!trialBalanceAmount.value) void loadTrialBalanceFromApi()
    syncWritebackFromOverlay()
    publishAdjudicated()
    window.addEventListener('g8:adjustment-writeback', onAdjustmentWriteback)
  })

  onBeforeUnmount(() => {
    window.removeEventListener('g8:adjustment-writeback', onAdjustmentWriteback)
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
    accountCode: G8_ACCOUNT_CODE,
  }
}
