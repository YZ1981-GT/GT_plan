import { useWorkpaperAuditYear } from './workpaperAuditYear'
/**
 * useG12Adjudication �?G12-1 ??�?
 */
import { ref, computed, watch, onMounted, type Ref, type ComputedRef } from 'vue'
import { G12_ACCOUNT_CODE, G12_CHANGE_RATE_THRESHOLD, G12_ADJUDICATION_ITEMS } from './g12Constants'
import { parseNum, calcAdjustedAmount, calcChangeAmount, calcChangeRate, isChangeRateExceeding, calcSubtotal } from './useG12FormulaEngine'
import { useG12HedgeDetail } from './useG12HedgeDetail'
import { G12_AJE_ADJ_OVERLAY_ID } from './useG12Adjustment'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'

const ITEM_PRIOR = 'G12-adj-prior'
const ITEM_TB = 'G12-adj-tb'
const ITEM_NOTE = 'G12-adj-note'
const ITEM_CONCLUSION = 'G12-adj-conclusion'

interface PriorStore { [k: string]: { priorUnadjusted?: number; priorAdjustment?: number; reasonAnalysis?: string; indexRef?: string } }

export function useG12Adjudication(opts: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const _auditYearRef = useWorkpaperAuditYear()
  const priorStore = ref<PriorStore>({})
  const ajeOverlay = ref<Record<string, number>>({})
  const trialBalanceAmount = ref(0)
  const auditNote = ref('')
  const auditConclusion = ref('')
  const aiLoading = ref(false)
  const hedge = useG12HedgeDetail({ allResponses: opts.allResponses, debouncedSave: opts.debouncedSave, isReadonly: opts.isReadonly })

  watch(() => opts.allResponses.value.get(ITEM_PRIOR)?.remark, (j) => {
    try { priorStore.value = j ? JSON.parse(j) : {} } catch { priorStore.value = {} }
  }, { immediate: true })
  watch(() => opts.allResponses.value.get(G12_AJE_ADJ_OVERLAY_ID)?.remark, (j) => {
    try { ajeOverlay.value = j ? JSON.parse(j) : {} } catch { ajeOverlay.value = {} }
  }, { immediate: true })
  watch(() => opts.allResponses.value.get(ITEM_TB)?.remark, (v) => { trialBalanceAmount.value = parseNum(v) }, { immediate: true })
  watch(() => opts.allResponses.value.get(ITEM_NOTE)?.conclusion, (v) => { auditNote.value = v ?? '' }, { immediate: true })
  watch(() => opts.allResponses.value.get(ITEM_CONCLUSION)?.conclusion, (v) => { auditConclusion.value = v ?? '' }, { immediate: true })

  const agg = computed(() => hedge.aggregateForAdjudication())

  function buildRow(def: (typeof G12_ADJUDICATION_ITEMS)[number]) {
    const a = agg.value[def.rowKey] ?? { unadjusted: 0, adjustment: 0, audited: 0 }
    const overlayAdj = parseNum(ajeOverlay.value[def.rowKey])
    const currentAdjustment = a.adjustment + overlayAdj
    const currentUnadjusted = a.unadjusted
    const currentAudited = calcAdjustedAmount(currentUnadjusted, currentAdjustment)
    const prior = priorStore.value[def.rowKey] ?? {}
    const priorUnadjusted = parseNum(prior.priorUnadjusted)
    const priorAdjustment = parseNum(prior.priorAdjustment)
    const priorAudited = calcAdjustedAmount(priorUnadjusted, priorAdjustment)
    const changeRate = calcChangeRate(priorAudited, currentAudited)
    return {
      rowKey: def.rowKey,
      label: def.label,
      currentUnadjusted,
      currentAdjustment,
      currentAudited,
      priorUnadjusted,
      priorAdjustment,
      priorAudited,
      changeAmount: calcChangeAmount(currentAudited, priorAudited),
      changeRate,
      reasonAnalysis: prior.reasonAnalysis ?? '',
      indexRef: prior.indexRef ?? '',
      changeRateHighlight: isChangeRateExceeding(changeRate, G12_CHANGE_RATE_THRESHOLD),
      reasonRequired: isChangeRateExceeding(changeRate, G12_CHANGE_RATE_THRESHOLD),
    }
  }

  const dataRows = computed(() => G12_ADJUDICATION_ITEMS.map(buildRow))
  const totalRow = computed(() => {
    const rows = dataRows.value
    const currentAudited = calcSubtotal(rows.map((r) => r.currentAudited))
    const priorAudited = calcSubtotal(rows.map((r) => r.priorAudited))
    const changeRate = calcChangeRate(priorAudited, currentAudited)
    return {
      rowKey: 'total', label: '??',
      currentUnadjusted: calcSubtotal(rows.map((r) => r.currentUnadjusted)),
      currentAdjustment: calcSubtotal(rows.map((r) => r.currentAdjustment)),
      currentAudited, priorUnadjusted: calcSubtotal(rows.map((r) => r.priorUnadjusted)),
      priorAdjustment: calcSubtotal(rows.map((r) => r.priorAdjustment)), priorAudited,
      changeAmount: calcChangeAmount(currentAudited, priorAudited), changeRate,
      reasonAnalysis: '', indexRef: '',
      changeRateHighlight: isChangeRateExceeding(changeRate, G12_CHANGE_RATE_THRESHOLD),
      reasonRequired: false,
    }
  })

  const variance = computed(() => totalRow.value.currentAudited - trialBalanceAmount.value)
  const hasVarianceHighlight = computed(() => Math.abs(variance.value) > 0.01)

  function updatePriorField(rowKey: string, field: 'priorUnadjusted' | 'priorAdjustment' | 'reasonAnalysis' | 'indexRef', value: unknown) {
    if (opts.isReadonly.value) return
    const entry = { ...(priorStore.value[rowKey] ?? {}) }
    if (field === 'reasonAnalysis' || field === 'indexRef') entry[field] = String(value ?? '')
    else entry[field] = parseNum(value)
    priorStore.value = { ...priorStore.value, [rowKey]: entry }
    opts.debouncedSave(ITEM_PRIOR, { remark: JSON.stringify(priorStore.value) })
  }

  function updateTrialBalance(v: number) { if (!opts.isReadonly.value) { trialBalanceAmount.value = v; opts.debouncedSave(ITEM_TB, { remark: String(v) }) } }
  function updateAuditNote(v: string) { if (!opts.isReadonly.value) { auditNote.value = v; opts.debouncedSave(ITEM_NOTE, { conclusion: v }) } }
  function updateAuditConclusion(v: string) { if (!opts.isReadonly.value) { auditConclusion.value = v; opts.debouncedSave(ITEM_CONCLUSION, { conclusion: v }) } }

  async function loadTrialBalanceFromApi() {
    const _year = _auditYearRef.value
    if (_year == null) return
    if (!opts.projectId.value) return
    try {
      const res = await api.get(`/api/projects/${opts.projectId.value}/trial-balance`, { params: { year: _year, account_prefix: G12_ACCOUNT_CODE  }, _silent: true } as any)
      const list = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])
      const hit = list.find((r: any) => String(r.standard_account_code ?? r.account_code ?? '').startsWith(G12_ACCOUNT_CODE))
      if (hit) updateTrialBalance(parseNum(hit.credit_amount ?? 0) - parseNum(hit.debit_amount ?? 0))
    } catch { /* optional */ }
  }

  function publishAdjudicated() {
    const amount = totalRow.value.currentAudited
    opts.debouncedSave('G12-1-adjudicated-amount', { conclusion: String(amount) })
    try {
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
        detail: { accountCode: G12_ACCOUNT_CODE, adjudicatedAmount: amount },
      }))
    } catch { /* silent */ }
    try {
      window.dispatchEvent(new CustomEvent('g12:writeback-trial-balance', {
        detail: { accountCode: G12_ACCOUNT_CODE, auditedAmount: amount },
      }))
    } catch { /* silent */ }
  }

  async function generateAiAnalysis(): Promise<void> {
    if (opts.isReadonly.value || !opts.wpId.value) return
    aiLoading.value = true
    try {
      const res = await api.post(
        `/api/workpapers/${opts.wpId.value}/g12/ai/adjudication-analysis`,
        { existingContent: auditNote.value, relatedContext: { totalAudited: totalRow.value.currentAudited } },
        { _silent: true } as any,
      )
      const content = res?.data?.data?.content ?? res?.data?.content ?? res?.content ?? ''
      if (content) { auditNote.value = content; opts.debouncedSave(ITEM_NOTE, { conclusion: content }) }
    } catch {
      const draft = `???????????�?${totalRow.value.currentAudited.toLocaleString()} ??????????? G12-2/G12-4 ?????`
      auditNote.value = auditNote.value ? `${auditNote.value}\n${draft}` : draft
      opts.debouncedSave(ITEM_NOTE, { conclusion: auditNote.value })
    } finally { aiLoading.value = false }
  }

  onMounted(() => { void loadTrialBalanceFromApi(); window.addEventListener('g12:hedge-detail-updated', () => {}) })

  return { dataRows, totalRow, trialBalanceAmount, variance, hasVarianceHighlight, auditNote, auditConclusion, aiLoading, hedge, updatePriorField, updateTrialBalance, updateAuditNote, updateAuditConclusion, publishAdjudicated, generateAiAnalysis }
}
