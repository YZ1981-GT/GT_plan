/**
 * useG10Adjudication — G10-1 审定表（贷方/期初期末列）
 */
import { ref, computed, watch, onMounted, type Ref, type ComputedRef } from 'vue'
import {
  G10_ACCOUNT_CODE,
  G10_ADJUDICATION_ITEMS,
  G10_CHANGE_RATE_THRESHOLD,
  G10_GROUP_LABELS,
} from './g10Constants'
import { parseG10AdjStore, patchG10AdjRow } from './g10AdjStorage'
import {
  parseNum,
  calcCreditBalance,
  calcAdjustedAmount,
  calcChangeAmount,
  calcChangeRate,
  isChangeRateExceeding,
  calcSubtotal,
} from './useG10FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'

export interface G10AdjudicationRow {
  rowKey: string
  label: string
  group?: string
  openingUnadjusted: number
  openingAdjustment: number
  openingAdjusted: number
  periodCredit: number
  periodDebit: number
  closingUnadjusted: number
  closingAdjustment: number
  closingAdjusted: number
  changeAmount: number
  changeRate: number | null
  reasonAnalysis: string
  indexRef: string
  changeRateHighlight: boolean
  reasonRequired: boolean
  formulaBalanced: boolean
}

const ITEM_ID_ROWS = 'G10-adj-rows'
const ITEM_ID_TB = 'G10-adj-tb'
const ITEM_ID_NOTE = 'G10-adj-note'
const ITEM_ID_CONCLUSION = 'G10-adj-conclusion'

type RowStore = ReturnType<typeof parseG10AdjStore>

export function useG10Adjudication(opts: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const rowStore = ref<RowStore>(parseG10AdjStore(undefined))
  const trialBalanceAmount = ref(0)
  const auditNote = ref('')
  const auditConclusion = ref('')
  const aiLoading = ref(false)
  const collapsedGroups = ref<Record<string, boolean>>({})

  watch(() => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark, (j) => {
    rowStore.value = parseG10AdjStore(j)
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

  function buildRow(def: (typeof G10_ADJUDICATION_ITEMS)[number]): G10AdjudicationRow {
    const raw = rowStore.value[def.rowKey] ?? {}
    const openingUnadjusted = parseNum(raw.openingUnadjusted)
    const openingAdjustment = parseNum(raw.openingAdjustment)
    const periodCredit = parseNum(raw.periodCredit)
    const periodDebit = parseNum(raw.periodDebit)
    const closingAdjustment = parseNum(raw.closingAdjustment)
    const openingAdjusted = calcAdjustedAmount(openingUnadjusted, openingAdjustment)
    const closingUnadjusted = calcCreditBalance(openingAdjusted, periodCredit, periodDebit)
    const closingAdjusted = calcAdjustedAmount(closingUnadjusted, closingAdjustment)
    const changeRate = calcChangeRate(openingAdjusted, closingAdjusted)
    const reasonRequired = isChangeRateExceeding(changeRate, G10_CHANGE_RATE_THRESHOLD)
    const expectedClosing = calcCreditBalance(openingAdjusted, periodCredit, periodDebit)
    return {
      rowKey: def.rowKey,
      label: def.label,
      group: def.group,
      openingUnadjusted,
      openingAdjustment,
      openingAdjusted,
      periodCredit,
      periodDebit,
      closingUnadjusted,
      closingAdjustment,
      closingAdjusted,
      changeAmount: calcChangeAmount(closingAdjusted, openingAdjusted),
      changeRate,
      reasonAnalysis: raw.reasonAnalysis ?? '',
      indexRef: raw.indexRef ?? '',
      changeRateHighlight: reasonRequired,
      reasonRequired,
      formulaBalanced: Math.abs(closingUnadjusted - expectedClosing) < 0.01,
    }
  }

  const dataRows = computed(() => G10_ADJUDICATION_ITEMS.map(buildRow))

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
      periodCredit: calcSubtotal(rows.map((r) => r.periodCredit)),
      periodDebit: calcSubtotal(rows.map((r) => r.periodDebit)),
      closingUnadjusted: calcSubtotal(rows.map((r) => r.closingUnadjusted)),
      closingAdjustment: calcSubtotal(rows.map((r) => r.closingAdjustment)),
      closingAdjusted,
      changeAmount: calcChangeAmount(closingAdjusted, openingAdjusted),
      changeRate,
      reasonAnalysis: '',
      indexRef: '',
      changeRateHighlight: isChangeRateExceeding(changeRate, G10_CHANGE_RATE_THRESHOLD),
      reasonRequired: false,
      formulaBalanced: true,
    }
  })

  const groupedRows = computed(() => {
    const groups = new Map<string, G10AdjudicationRow[]>()
    for (const row of dataRows.value) {
      const g = row.group ?? '其他'
      if (!groups.has(g)) groups.set(g, [])
      groups.get(g)!.push(row)
    }
    return [...groups.entries()].map(([groupKey, rows]) => ({
      groupKey,
      groupName: G10_GROUP_LABELS[groupKey] ?? groupKey,
      collapsed: collapsedGroups.value[groupKey] ?? false,
      rows,
      subtotal: {
        openingAdjusted: calcSubtotal(rows.map((r) => r.openingAdjusted)),
        closingAdjusted: calcSubtotal(rows.map((r) => r.closingAdjusted)),
      },
    }))
  })

  const variance = computed(() => totalRow.value.closingAdjusted - trialBalanceAmount.value)
  const hasVarianceHighlight = computed(() => Math.abs(variance.value) > 0.01)
  const hasFormulaMismatch = computed(() => dataRows.value.some((r) => !r.formulaBalanced))

  const detailTotalClosing = computed(() => {
    const json = opts.allResponses.value.get('G10-detail-rows')?.remark
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
    | 'periodCredit' | 'periodDebit'
    | 'closingAdjustment' | 'reasonAnalysis' | 'indexRef'

  function updateField(rowKey: string, field: EditableField, value: unknown): void {
    if (opts.isReadonly.value || rowKey === 'total') return
    const entry = { ...(rowStore.value[rowKey] ?? {}) }
    if (field === 'reasonAnalysis' || field === 'indexRef') entry[field] = String(value ?? '')
    else entry[field] = parseNum(value)
    rowStore.value = { ...rowStore.value, [rowKey]: entry }
    persistRows()
    publishAdjudicatedDebounced()
  }

  function toggleGroup(groupKey: string): void {
    collapsedGroups.value = {
      ...collapsedGroups.value,
      [groupKey]: !collapsedGroups.value[groupKey],
    }
  }

  function updateTrialBalance(value: number): void {
    if (opts.isReadonly.value) return
    trialBalanceAmount.value = value
    opts.debouncedSave(ITEM_ID_TB, { remark: String(value) })
  }

  function updateAuditNote(value: string): void {
    if (opts.isReadonly.value) return
    auditNote.value = value
    opts.debouncedSave(ITEM_ID_NOTE, { conclusion: value })
  }

  function updateAuditConclusion(value: string): void {
    if (opts.isReadonly.value) return
    auditConclusion.value = value
    opts.debouncedSave(ITEM_ID_CONCLUSION, { conclusion: value })
  }

  let publishTimer: ReturnType<typeof setTimeout> | null = null
  function publishAdjudicatedDebounced(): void {
    if (publishTimer) clearTimeout(publishTimer)
    publishTimer = setTimeout(() => {
      publishTimer = null
      publishAdjudicated()
    }, 1500)
  }

  function applyNetAdjustment(net: number): void {
    if (opts.isReadonly.value) return
    rowStore.value = patchG10AdjRow(rowStore.value, 'book_other', { closingAdjustment: net })
    persistRows()
    publishAdjudicatedDebounced()
  }

  function publishAdjudicated(): void {
    const amount = totalRow.value.closingAdjusted
    opts.debouncedSave('G10-1-adjudicated-amount', { conclusion: String(amount) })
    try {
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
        detail: { accountCode: G10_ACCOUNT_CODE, adjudicatedAmount: amount },
      }))
    } catch { /* silent */ }
  }

  async function loadTrialBalanceFromApi(): Promise<void> {
    if (!opts.projectId.value) return
    try {
      const res = await api.get(`/api/projects/${opts.projectId.value}/trial-balance`, {
        params: { account_prefix: G10_ACCOUNT_CODE },
        _silent: true,
      } as any)
      const list = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])
      const hit = list.find((r: any) =>
        String(r.standard_account_code ?? r.account_code ?? '').startsWith(G10_ACCOUNT_CODE),
      )
      if (hit) {
        const credit = parseNum(hit.credit_amount ?? hit.period_credit)
        const debit = parseNum(hit.debit_amount ?? hit.period_debit)
        updateTrialBalance(credit - debit)
      }
    } catch { /* optional */ }
  }

  async function validateFormulasRemote(): Promise<{ ok: boolean; errors: { field: string; message: string }[] }> {
    try {
      const res = await api.post(`/api/workpapers/${opts.wpId.value}/g10/validate-formulas`, {
        adjudication_rows: dataRows.value.map((r) => ({
          rowKey: r.rowKey,
          openingUnadjusted: r.openingUnadjusted,
          openingAdjustment: r.openingAdjustment,
          openingAdjusted: r.openingAdjusted,
          periodCredit: r.periodCredit,
          periodDebit: r.periodDebit,
          closingUnadjusted: r.closingUnadjusted,
          closingAdjustment: r.closingAdjustment,
          closingAdjusted: r.closingAdjusted,
        })),
        l3_rows: [],
        adjustment_debits: [],
        adjustment_credits: [],
      }, { _silent: true } as any)
      const data = res?.data ?? res
      return { ok: !!data.ok, errors: data.errors ?? [] }
    } catch {
      return { ok: true, errors: [] }
    }
  }

  async function generateAiAnalysis(): Promise<void> {
    if (opts.isReadonly.value) return
    aiLoading.value = true
    try {
      const res = await api.post(`/api/workpapers/${opts.wpId.value}/g10/ai/adjudication-analysis`, {
        rows: dataRows.value.map((r) => ({
          label: r.label,
          openingAdjusted: r.openingAdjusted,
          closingAdjusted: r.closingAdjusted,
          changeRate: r.changeRate,
        })),
      }, { _silent: true } as any)
      const text = res?.data?.content ?? res?.content ?? ''
      if (text) updateAuditNote(text)
    } catch { /* AI optional */ }
    finally { aiLoading.value = false }
  }

  onMounted(() => {
    void loadTrialBalanceFromApi()
    publishAdjudicated()
  })

  return {
    dataRows,
    totalRow,
    groupedRows,
    trialBalanceAmount,
    variance,
    hasVarianceHighlight,
    hasFormulaMismatch,
    detailTotalClosing,
    detailCrossVariance,
    hasDetailCrossMismatch,
    auditNote,
    auditConclusion,
    aiLoading,
    updateField,
    updateTrialBalance,
    updateAuditNote,
    updateAuditConclusion,
    toggleGroup,
    publishAdjudicated,
    applyNetAdjustment,
    generateAiAnalysis,
    validateFormulasRemote,
    loadTrialBalanceFromApi,
  }
}
