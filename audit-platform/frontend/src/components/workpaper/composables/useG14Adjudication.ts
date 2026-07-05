/**
 * useG14Adjudication — G14-1 审定表（本期自 G14-2 同步，上期独立录入）
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { G14_ACCOUNT_CODE, G14_CHANGE_RATE_THRESHOLD, G14_LINE_ITEMS } from './g14Constants'
import {
  parseNum,
  calcAdjustedAmount,
  calcChangeAmount,
  calcChangeRate,
  isChangeRateExceeding,
  calcSubtotal,
} from './useG14FormulaEngine'
import { useG14Detail, type G14DetailRow } from './useG14Detail'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'

export interface G14AdjudicationRow {
  rowKey: string
  label: string
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

const ITEM_ID_PRIOR = 'G14-adj-prior'
const ITEM_ID_TB = 'G14-adj-tb'
const ITEM_ID_NOTE = 'G14-adj-note'
const ITEM_ID_CONCLUSION = 'G14-adj-conclusion'

interface PriorStore {
  [rowKey: string]: { priorUnadjusted?: number; priorAdjustment?: number; reasonAnalysis?: string; indexRef?: string }
}

function parsePrior(json: string | null | undefined): PriorStore {
  if (!json) return {}
  try {
    return JSON.parse(json) as PriorStore
  } catch {
    return {}
  }
}

export interface UseG14AdjudicationOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}

export function useG14Adjudication(options: UseG14AdjudicationOptions) {
  const priorStore = ref<PriorStore>({})
  const trialBalanceAmount = ref(0)
  const auditNote = ref('')
  const auditConclusion = ref('')
  const aiLoading = ref(false)

  const detail = useG14Detail({
    allResponses: options.allResponses,
    debouncedSave: options.debouncedSave,
    isReadonly: options.isReadonly,
  })

  watch(
    () => options.allResponses.value.get(ITEM_ID_PRIOR)?.remark,
    (json) => { priorStore.value = parsePrior(json) },
    { immediate: true },
  )
  watch(
    () => options.allResponses.value.get(ITEM_ID_TB)?.remark,
    (v) => { trialBalanceAmount.value = parseNum(v) },
    { immediate: true },
  )
  watch(
    () => options.allResponses.value.get(ITEM_ID_NOTE)?.conclusion,
    (v) => { auditNote.value = v ?? '' },
    { immediate: true },
  )
  watch(
    () => options.allResponses.value.get(ITEM_ID_CONCLUSION)?.conclusion,
    (v) => { auditConclusion.value = v ?? '' },
    { immediate: true },
  )

  function buildRow(detailRow: G14DetailRow): G14AdjudicationRow {
    const prior = priorStore.value[detailRow.rowKey] ?? {}
    const priorUnadjusted = parseNum(prior.priorUnadjusted)
    const priorAdjustment = parseNum(prior.priorAdjustment)
    const priorAudited = calcAdjustedAmount(priorUnadjusted, priorAdjustment)
    const currentAudited = detailRow.currentAudited
    const changeAmount = calcChangeAmount(currentAudited, priorAudited)
    const changeRate = calcChangeRate(priorAudited, currentAudited)
    const reasonRequired = isChangeRateExceeding(changeRate, G14_CHANGE_RATE_THRESHOLD)
    return {
      rowKey: detailRow.rowKey,
      label: detailRow.label,
      currentUnadjusted: detailRow.currentUnadjusted,
      currentAdjustment: detailRow.currentAdjustment,
      currentAudited,
      priorUnadjusted,
      priorAdjustment,
      priorAudited,
      changeAmount,
      changeRate,
      reasonAnalysis: prior.reasonAnalysis ?? '',
      indexRef: prior.indexRef ?? '',
      changeRateHighlight: reasonRequired,
      reasonRequired,
    }
  }

  const dataRows = computed(() => detail.rows.value.map(buildRow))

  const totalRow = computed(() => {
    const rows = dataRows.value
    const currentAudited = calcSubtotal(rows.map((r) => r.currentAudited))
    const priorAudited = calcSubtotal(rows.map((r) => r.priorAudited))
    const changeAmount = calcChangeAmount(currentAudited, priorAudited)
    const changeRate = calcChangeRate(priorAudited, currentAudited)
    return {
      rowKey: 'total',
      label: '合计',
      currentUnadjusted: calcSubtotal(rows.map((r) => r.currentUnadjusted)),
      currentAdjustment: calcSubtotal(rows.map((r) => r.currentAdjustment)),
      currentAudited,
      priorUnadjusted: calcSubtotal(rows.map((r) => r.priorUnadjusted)),
      priorAdjustment: calcSubtotal(rows.map((r) => r.priorAdjustment)),
      priorAudited,
      changeAmount,
      changeRate,
      reasonAnalysis: '',
      indexRef: '',
      changeRateHighlight: isChangeRateExceeding(changeRate, G14_CHANGE_RATE_THRESHOLD),
      reasonRequired: false,
    }
  })

  const variance = computed(() => totalRow.value.currentAudited - trialBalanceAmount.value)
  const hasVarianceHighlight = computed(() => Math.abs(variance.value) > 0.01)
  const detailMismatch = computed(() => {
    const dTotal = detail.totalRow.value.currentAudited
    return Math.abs(dTotal - totalRow.value.currentAudited) > 0.01
  })

  const hasDetailData = computed(() => {
    const raw = options.allResponses.value.get('G14-detail-rows')?.remark
    if (!raw) return false
    try {
      const arr = JSON.parse(raw)
      return Array.isArray(arr) && arr.length > 0
    } catch {
      return false
    }
  })

  const detailCrossValidation = computed((): string | null => {
    if (!detailMismatch.value) return null
    const detailTotal = detail.totalRow.value.currentAudited
    const adjTotal = totalRow.value.currentAudited
    const diff = Math.abs(detailTotal - adjTotal)
    return `G14-1 审定合计 ${adjTotal.toFixed(2)} 与 G14-2 明细合计 ${detailTotal.toFixed(2)} 不一致（差异 ${diff.toFixed(2)}）`
  })

  function persistPrior(): void {
    options.debouncedSave(ITEM_ID_PRIOR, { remark: JSON.stringify(priorStore.value) })
  }

  function updatePriorField(rowKey: string, field: 'priorUnadjusted' | 'priorAdjustment' | 'reasonAnalysis' | 'indexRef', value: unknown): void {
    if (options.isReadonly.value) return
    const entry = { ...(priorStore.value[rowKey] ?? {}) }
    if (field === 'reasonAnalysis' || field === 'indexRef') {
      entry[field] = String(value ?? '')
    } else {
      entry[field] = parseNum(value)
    }
    priorStore.value = { ...priorStore.value, [rowKey]: entry }
    persistPrior()
  }

  function updateTrialBalance(value: number): void {
    if (options.isReadonly.value) return
    trialBalanceAmount.value = value
    options.debouncedSave(ITEM_ID_TB, { remark: String(value) })
  }

  function updateAuditNote(value: string): void {
    if (options.isReadonly.value) return
    auditNote.value = value
    options.debouncedSave(ITEM_ID_NOTE, { conclusion: value })
  }

  function updateAuditConclusion(value: string): void {
    if (options.isReadonly.value) return
    auditConclusion.value = value
    options.debouncedSave(ITEM_ID_CONCLUSION, { conclusion: value })
  }

  async function loadTrialBalanceFromApi(): Promise<void> {
    if (!options.projectId.value) return
    try {
      const res = await api.get(`/api/projects/${options.projectId.value}/trial-balance`, {
        params: { account_prefix: G14_ACCOUNT_CODE },
        _silent: true,
      } as any)
      const rows = res?.data ?? res
      const list = Array.isArray(rows) ? rows : rows?.items ?? []
      const hit = list.find((r: any) => String(r.standard_account_code ?? r.account_code ?? '').startsWith(G14_ACCOUNT_CODE))
      if (hit) {
        const amount = parseNum(hit.unadjusted_amount ?? hit.current_amount ?? hit.debit_amount)
        updateTrialBalance(amount)
      }
    } catch {
      /* TB 可选 */
    }
  }

  function publishAdjudicated(): void {
    const amount = totalRow.value.currentAudited
    options.debouncedSave('G14-1-adjudicated-amount', { conclusion: String(amount) })
    window.dispatchEvent(
      new CustomEvent('substantive:adjudicated', {
        detail: { accountCode: G14_ACCOUNT_CODE, adjudicatedAmount: amount },
      }),
    )
  }

  async function generateAiAnalysis(): Promise<void> {
    if (options.isReadonly.value || !options.wpId.value) return
    aiLoading.value = true
    try {
      const res = await api.post(
        `/api/workpapers/${options.wpId.value}/g14/ai/adjudication-analysis`,
        { existingContent: auditNote.value, relatedContext: { totalAudited: totalRow.value.currentAudited } },
        { _silent: true } as any,
      )
      const content = res?.data?.content ?? res?.content ?? ''
      if (content) { auditNote.value = content; options.debouncedSave(ITEM_ID_NOTE, { conclusion: content }) }
    } catch {
      const draft = `本期信用减值损失审定数 ${totalRow.value.currentAudited.toLocaleString()} 元，请关注各减值来源变动。`
      auditNote.value = auditNote.value ? `${auditNote.value}\n${draft}` : draft
      options.debouncedSave(ITEM_ID_NOTE, { conclusion: auditNote.value })
    } finally { aiLoading.value = false }
  }

  function onDetailUpdated(): void {
    /* 触发 computed 刷新 */
  }

  onMounted(() => {
    void loadTrialBalanceFromApi()
    window.addEventListener('g14:detail-updated', onDetailUpdated)
  })
  onBeforeUnmount(() => {
    window.removeEventListener('g14:detail-updated', onDetailUpdated)
  })

  return {
    dataRows,
    totalRow,
    trialBalanceAmount,
    variance,
    hasVarianceHighlight,
    detailMismatch,
    hasDetailData,
    detailCrossValidation,
    auditNote,
    auditConclusion,
    aiLoading,
    detail,
    updatePriorField,
    updateTrialBalance,
    updateAuditNote,
    updateAuditConclusion,
    publishAdjudicated,
    generateAiAnalysis,
    G14_LINE_ITEMS,
  }
}
