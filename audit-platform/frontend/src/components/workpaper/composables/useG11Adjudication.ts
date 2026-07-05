/**
 * useG11Adjudication — G11-1 审定表（损益类/本期-上期）
 */
import { ref, computed, watch, onMounted, type Ref, type ComputedRef } from 'vue'
import {
  G11_ACCOUNT_CODE,
  G11_ADJUDICATION_ITEMS,
  G11_CHANGE_RATE_THRESHOLD,
} from './g11Constants'
import {
  parseG11AdjStore,
  patchG11AdjRow,
} from './g11AdjStorage'
import {
  parseNum,
  calcAdjustedAmount,
  calcChangeAmount,
  calcChangeRate,
  isChangeRateExceeding,
  calcSubtotal,
} from './useG11FormulaEngine'
import { useG11DetailAnalysis } from './useG11DetailAnalysis'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'

export interface G11AdjudicationRow {
  rowKey: string
  label: string
  group?: string
  currentUnadjusted: number
  currentAdjustment: number
  currentAudited: number
  priorUnadjusted: number
  priorAdjustment: number
  priorAudited: number
  changeAmount: number
  changeRate: number | null
  reasonAnalysis: string
  indexRef: string
  changeRateHighlight: boolean
  reasonRequired: boolean
}

const ITEM_ID_ROWS = 'G11-adj-rows'
const ITEM_ID_TB = 'G11-adj-tb'
const ITEM_ID_NOTE = 'G11-adj-note'
const ITEM_ID_CONCLUSION = 'G11-adj-conclusion'

interface RowStore {
  [rowKey: string]: {
    currentUnadjusted?: number
    currentAdjustment?: number
    priorUnadjusted?: number
    priorAdjustment?: number
    reasonAnalysis?: string
    indexRef?: string
  }
}

function parseStore(json: string | null | undefined): RowStore {
  return parseG11AdjStore(json) as RowStore
}

export function useG11Adjudication(opts: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const rowStore = ref<RowStore>(parseG11AdjStore(undefined) as RowStore)
  const trialBalanceAmount = ref(0)
  const auditNote = ref('')
  const auditConclusion = ref('')
  const aiLoading = ref(false)
  const collapsedGroups = ref<Record<string, boolean>>({})

  const detail = useG11DetailAnalysis({
    allResponses: opts.allResponses,
    debouncedSave: opts.debouncedSave,
    isReadonly: opts.isReadonly,
  })

  watch(() => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark, (j) => {
    rowStore.value = parseStore(j)
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

  function buildRow(def: (typeof G11_ADJUDICATION_ITEMS)[number]): G11AdjudicationRow {
    const raw = rowStore.value[def.rowKey] ?? {}
    const currentUnadjusted = parseNum(raw.currentUnadjusted)
    const currentAdjustment = parseNum(raw.currentAdjustment)
    const priorUnadjusted = parseNum(raw.priorUnadjusted)
    const priorAdjustment = parseNum(raw.priorAdjustment)
    const currentAudited = calcAdjustedAmount(currentUnadjusted, currentAdjustment)
    const priorAudited = calcAdjustedAmount(priorUnadjusted, priorAdjustment)
    const changeRate = calcChangeRate(priorAudited, currentAudited)
    const reasonRequired = isChangeRateExceeding(changeRate, G11_CHANGE_RATE_THRESHOLD)
    return {
      rowKey: def.rowKey,
      label: def.label,
      group: def.group,
      currentUnadjusted,
      currentAdjustment,
      currentAudited,
      priorUnadjusted,
      priorAdjustment,
      priorAudited,
      changeAmount: calcChangeAmount(currentAudited, priorAudited),
      changeRate,
      reasonAnalysis: raw.reasonAnalysis ?? '',
      indexRef: raw.indexRef ?? '',
      changeRateHighlight: reasonRequired,
      reasonRequired,
    }
  }

  const dataRows = computed(() => G11_ADJUDICATION_ITEMS.map(buildRow))

  const totalRow = computed(() => {
    const rows = dataRows.value
    const currentAudited = calcSubtotal(rows.map((r) => r.currentAudited))
    const priorAudited = calcSubtotal(rows.map((r) => r.priorAudited))
    const changeRate = calcChangeRate(priorAudited, currentAudited)
    return {
      rowKey: 'total',
      label: '合  计',
      currentUnadjusted: calcSubtotal(rows.map((r) => r.currentUnadjusted)),
      currentAdjustment: calcSubtotal(rows.map((r) => r.currentAdjustment)),
      currentAudited,
      priorUnadjusted: calcSubtotal(rows.map((r) => r.priorUnadjusted)),
      priorAdjustment: calcSubtotal(rows.map((r) => r.priorAdjustment)),
      priorAudited,
      changeAmount: calcChangeAmount(currentAudited, priorAudited),
      changeRate,
      reasonAnalysis: '',
      indexRef: '',
      changeRateHighlight: isChangeRateExceeding(changeRate, G11_CHANGE_RATE_THRESHOLD),
      reasonRequired: false,
    }
  })

  const groupedRows = computed(() => {
    const groups = new Map<string, G11AdjudicationRow[]>()
    for (const row of dataRows.value) {
      const g = row.group ?? '其他'
      if (!groups.has(g)) groups.set(g, [])
      groups.get(g)!.push(row)
    }
    return [...groups.entries()].map(([groupName, rows]) => ({
      groupName,
      collapsed: collapsedGroups.value[groupName] ?? false,
      rows,
      subtotal: {
        currentAudited: calcSubtotal(rows.map((r) => r.currentAudited)),
        priorAudited: calcSubtotal(rows.map((r) => r.priorAudited)),
      },
    }))
  })

  const variance = computed(() => totalRow.value.currentAudited - trialBalanceAmount.value)
  const hasVarianceHighlight = computed(() => Math.abs(variance.value) > 0.01)

  const detailMismatch = computed(() =>
    Math.abs(detail.totalRow.value.currentAudited - totalRow.value.currentAudited) > 0.01,
  )

  const hasDetailData = computed(() => detail.rows.value.length > 0)

  const detailCrossValidation = computed((): string | null => {
    if (!hasDetailData.value || !detailMismatch.value) return null
    const dTotal = detail.totalRow.value.currentAudited
    const adjTotal = totalRow.value.currentAudited
    return `G11-1 审定合计 ${adjTotal.toFixed(2)} 与 G11-2 明细合计 ${dTotal.toFixed(2)} 不一致`
  })

  function persistRows(): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rowStore.value) })
  }

  function updateField(
    rowKey: string,
    field: 'currentUnadjusted' | 'currentAdjustment' | 'priorUnadjusted' | 'priorAdjustment' | 'reasonAnalysis' | 'indexRef',
    value: unknown,
  ): void {
    if (opts.isReadonly.value || rowKey === 'total') return
    const entry = { ...(rowStore.value[rowKey] ?? {}) }
    if (field === 'reasonAnalysis' || field === 'indexRef') entry[field] = String(value ?? '')
    else entry[field] = parseNum(value)
    rowStore.value = { ...rowStore.value, [rowKey]: entry }
    persistRows()
    publishAdjudicatedDebounced()
  }

  function toggleGroup(groupName: string): void {
    collapsedGroups.value = {
      ...collapsedGroups.value,
      [groupName]: !collapsedGroups.value[groupName],
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
    rowStore.value = patchG11AdjRow(rowStore.value, 'other', { currentAdjustment: net })
    persistRows()
    publishAdjudicatedDebounced()
  }

  async function validateWithBackend(): Promise<boolean> {
    try {
      const res = await api.post(`/api/workpapers/${opts.wpId.value}/g11/validate-formulas`, {
        adjudication_rows: dataRows.value,
        detail_rows: detail.rows.value,
      }, { _silent: true } as any)
      const payload = res?.data ?? res
      return payload?.ok !== false
    } catch {
      return true
    }
  }

  async function saveAdjudicationToBackend(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      await api.post(`/api/workpapers/${opts.wpId.value}/g11/save-adjudication`, {
        row_store: rowStore.value,
        adjudicated_amount: totalRow.value.currentAudited,
        audit_note: auditNote.value,
        audit_conclusion: auditConclusion.value,
      }, { _silent: true } as any)
    } catch { /* fallback to debounced save */ }
  }

  function publishAdjudicated(): void {
    const amount = totalRow.value.currentAudited
    opts.debouncedSave('G11-1-adjudicated-amount', { conclusion: String(amount) })
    try {
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
        detail: { accountCode: G11_ACCOUNT_CODE, adjudicatedAmount: amount },
      }))
    } catch { /* silent */ }
  }

  async function loadTrialBalanceFromApi(): Promise<void> {
    if (!opts.projectId.value) return
    try {
      const res = await api.get(`/api/projects/${opts.projectId.value}/trial-balance`, {
        params: { account_prefix: G11_ACCOUNT_CODE },
        _silent: true,
      } as any)
      const list = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])
      const hit = list.find((r: any) =>
        String(r.standard_account_code ?? r.account_code ?? '').startsWith(G11_ACCOUNT_CODE),
      )
      if (hit) {
        const credit = parseNum(hit.credit_amount ?? hit.period_credit)
        const debit = parseNum(hit.debit_amount ?? hit.period_debit)
        updateTrialBalance(credit - debit)
      }
    } catch { /* optional */ }
  }

  async function generateAiAnalysis(): Promise<void> {
    if (opts.isReadonly.value) return
    aiLoading.value = true
    try {
      const res = await api.post(`/api/workpapers/${opts.wpId.value}/g11/ai/adjudication-analysis`, {
        rows: dataRows.value.map((r) => ({
          label: r.label,
          currentAudited: r.currentAudited,
          priorAudited: r.priorAudited,
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
    auditNote,
    auditConclusion,
    aiLoading,
    detailCrossValidation,
    hasDetailData,
    detailMismatch,
    updateField,
    updateTrialBalance,
    updateAuditNote,
    updateAuditConclusion,
    toggleGroup,
    publishAdjudicated,
    applyNetAdjustment,
    validateWithBackend,
    saveAdjudicationToBackend,
    generateAiAnalysis,
    loadTrialBalanceFromApi,
  }
}
