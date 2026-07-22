import { useWorkpaperAuditYear } from './workpaperAuditYear'
/**
 * useG13Adjudication — G13-1 审定表（与 xlsx 分层行一致；本期主行自 G13-2 汇总，「其中」手工）
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  G13_ACCOUNT_CODE,
  G13_CHANGE_RATE_THRESHOLD,
  G13_ADJUDICATION_ITEMS,
  G13_LEGACY_ADJ_KEY_MAP,
  isG13AdjRowInTotal,
  type G13AdjudicationDef,
} from './g13Constants'
import {
  parseNum,
  calcAdjustedAmount,
  calcChangeAmount,
  calcChangeRate,
  isChangeRateExceeding,
  calcSubtotal,
} from './useG13FormulaEngine'
import { useG13Detail } from './useG13Detail'
import { G13_AJE_ADJ_OVERLAY_ID } from './g13AdjStorage'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'

export interface G13AdjudicationRow {
  rowKey: string
  label: string
  kind: G13AdjudicationDef['kind']
  indent: number
  emphasize: boolean
  /** 主行/衍生：来自明细汇总；「其中」：可手工编辑本期 */
  autoCurrent: boolean
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

const ITEM_ID_PRIOR = 'G13-adj-prior'
const ITEM_ID_TB = 'G13-adj-tb'
const ITEM_ID_NOTE = 'G13-adj-note'
const ITEM_ID_CONCLUSION = 'G13-adj-conclusion'

interface PriorEntry {
  priorUnadjusted?: number
  priorAdjustment?: number
  /** 「其中」行本期手工数 */
  currentUnadjusted?: number
  currentAdjustment?: number
  reasonAnalysis?: string
  indexRef?: string
}

interface PriorStore {
  [rowKey: string]: PriorEntry
}

function migratePriorStore(raw: PriorStore): PriorStore {
  const next: PriorStore = { ...raw }
  for (const [legacy, target] of Object.entries(G13_LEGACY_ADJ_KEY_MAP)) {
    if (next[legacy] && !next[target]) {
      next[target] = next[legacy]
    }
    if (next[legacy]) delete next[legacy]
  }
  return next
}

function parsePrior(json: string | null | undefined): PriorStore {
  if (!json) return {}
  try {
    return migratePriorStore(JSON.parse(json) as PriorStore)
  } catch {
    return {}
  }
}

export interface UseG13AdjudicationOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}

export function useG13Adjudication(options: UseG13AdjudicationOptions) {
  const _auditYearRef = useWorkpaperAuditYear()

  const priorStore = ref<PriorStore>({})
  const ajeOverlay = ref<Record<string, number>>({})
  const hasAjeOverlay = ref(false)
  const trialBalanceAmount = ref(0)
  const auditNote = ref('')
  const auditConclusion = ref('')
  const aiLoading = ref(false)

  const detail = useG13Detail({
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
    () => options.allResponses.value.get(G13_AJE_ADJ_OVERLAY_ID)?.remark,
    (json) => {
      if (!json) {
        ajeOverlay.value = {}
        hasAjeOverlay.value = false
        return
      }
      try {
        const parsed = JSON.parse(json) as Record<string, number>
        ajeOverlay.value = parsed && typeof parsed === 'object' ? parsed : {}
        hasAjeOverlay.value = true
      } catch {
        ajeOverlay.value = {}
        hasAjeOverlay.value = false
      }
    },
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

  const detailAgg = computed(() => detail.aggregateByAdjRowKey())

  function buildRow(def: G13AdjudicationDef): G13AdjudicationRow {
    const prior = priorStore.value[def.rowKey] ?? {}
    const autoCurrent = def.kind !== 'ofWhich'
    let currentUnadjusted: number
    let currentAdjustment: number
    let currentAudited: number

    if (autoCurrent) {
      const agg = detailAgg.value[def.rowKey] ?? { unadjusted: 0, adjustment: 0, audited: 0 }
      currentUnadjusted = agg.unadjusted
      // G13-3 确认后优先取分项 overlay，避免无明细行时调整数丢失；未发布前仍用明细调整
      currentAdjustment = hasAjeOverlay.value
        ? parseNum(ajeOverlay.value[def.rowKey])
        : agg.adjustment
      currentAudited = calcAdjustedAmount(currentUnadjusted, currentAdjustment)
    } else {
      currentUnadjusted = parseNum(prior.currentUnadjusted)
      currentAdjustment = parseNum(prior.currentAdjustment)
      currentAudited = calcAdjustedAmount(currentUnadjusted, currentAdjustment)
    }

    const priorUnadjusted = parseNum(prior.priorUnadjusted)
    const priorAdjustment = parseNum(prior.priorAdjustment)
    const priorAudited = calcAdjustedAmount(priorUnadjusted, priorAdjustment)
    const changeAmount = calcChangeAmount(currentAudited, priorAudited)
    const changeRate = calcChangeRate(priorAudited, currentAudited)
    const reasonRequired = isChangeRateExceeding(changeRate, G13_CHANGE_RATE_THRESHOLD)

    return {
      rowKey: def.rowKey,
      label: def.label,
      kind: def.kind,
      indent: def.indent,
      emphasize: !!def.emphasize,
      autoCurrent,
      currentUnadjusted,
      currentAdjustment,
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

  const dataRows = computed(() => G13_ADJUDICATION_ITEMS.map(buildRow))

  const totalEligibleRows = computed(() =>
    dataRows.value.filter((r) => isG13AdjRowInTotal(r.kind)),
  )

  const totalRow = computed(() => {
    const rows = totalEligibleRows.value
    const currentAudited = calcSubtotal(rows.map((r) => r.currentAudited))
    const priorAudited = calcSubtotal(rows.map((r) => r.priorAudited))
    const changeAmount = calcChangeAmount(currentAudited, priorAudited)
    const changeRate = calcChangeRate(priorAudited, currentAudited)
    return {
      rowKey: 'total',
      label: '合计',
      kind: 'main' as const,
      indent: 0,
      emphasize: false,
      autoCurrent: true,
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
      changeRateHighlight: isChangeRateExceeding(changeRate, G13_CHANGE_RATE_THRESHOLD),
      reasonRequired: false,
    }
  })

  const variance = computed(() => totalRow.value.currentAudited - trialBalanceAmount.value)
  const hasVarianceHighlight = computed(() => Math.abs(variance.value) > 0.01)

  const hasDetailData = computed(() => detail.rows.value.length > 0)

  const detailCrossValidation = computed((): string | null => {
    if (!hasDetailData.value) return null
    const detailTotal = detail.grandTotalAudited.value
    const adjTotal = totalRow.value.currentAudited
    const diff = Math.abs(detailTotal - adjTotal)
    if (diff > 0.01) {
      return `G13-1 审定合计 ${adjTotal.toFixed(2)} 与 G13-2 明细合计 ${detailTotal.toFixed(2)} 不一致（差异 ${diff.toFixed(2)}；「其中」行不计入审定合计）`
    }
    return null
  })

  /** 总体变动率说明（xlsx 审计说明第 1 项） */
  const overallChangeRate = computed(() => totalRow.value.changeRate)
  const overallChangePctText = computed(() => {
    const r = overallChangeRate.value
    if (r === null) return '上期为 0，无法计算变动率'
    const pct = (r * 100).toFixed(2)
    const dir = r >= 0 ? '增加' : '减少'
    return `较上期审定数${dir} ${pct}%`
  })

  function persistPrior(): void {
    options.debouncedSave(ITEM_ID_PRIOR, { remark: JSON.stringify(priorStore.value) })
  }

  function updatePriorField(
    rowKey: string,
    field: keyof PriorEntry,
    value: unknown,
  ): void {
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
    const _year = _auditYearRef.value
    if (_year == null) return
    if (!options.projectId.value) return
    try {
      const res = await api.get(`/api/projects/${options.projectId.value}/trial-balance`, {
        params: { year: _year, account_prefix: G13_ACCOUNT_CODE },
        _silent: true,
      } as any)
      const rows = res?.data ?? res
      const list = Array.isArray(rows) ? rows : rows?.items ?? []
      const hit = list.find((r: any) =>
        String(r.standard_account_code ?? r.account_code ?? '').startsWith(G13_ACCOUNT_CODE),
      )
      if (hit) {
        const debit = parseNum(hit.debit_amount ?? hit.period_debit)
        const credit = parseNum(hit.credit_amount ?? hit.period_credit)
        updateTrialBalance(credit - debit)
      }
    } catch { /* TB 可选 */ }
  }

  function broadcastAdjudicated(): void {
    const amount = totalRow.value.currentAudited
    options.debouncedSave('G13-1-adjudicated-amount', { conclusion: String(amount) })
    try {
      window.dispatchEvent(
        new CustomEvent('substantive:adjudicated', {
          detail: { accountCode: G13_ACCOUNT_CODE, adjudicatedAmount: amount },
        }),
      )
    } catch { /* silent */ }
  }

  /** 显式发布：跨模块刷新 + TB 回写（自动 watch 仅 broadcast，避免频繁写 TB） */
  function publishAdjudicated(): void {
    const amount = totalRow.value.currentAudited
    broadcastAdjudicated()
    try {
      window.dispatchEvent(
        new CustomEvent('g13:writeback-trial-balance', {
          detail: { accountCode: G13_ACCOUNT_CODE, auditedAmount: amount },
        }),
      )
    } catch { /* silent */ }
  }

  let _pubTimer: ReturnType<typeof setTimeout> | null = null
  function publishAdjudicatedDebounced(): void {
    if (_pubTimer) clearTimeout(_pubTimer)
    _pubTimer = setTimeout(() => {
      _pubTimer = null
      broadcastAdjudicated()
    }, 800)
  }

  // 合计变动自动广播，避免未点「发布」导致附注过期
  watch(() => totalRow.value.currentAudited, () => { publishAdjudicatedDebounced() })

  async function generateAiAnalysis(): Promise<void> {
    if (options.isReadonly.value || !options.wpId.value) return
    aiLoading.value = true
    try {
      const res = await api.post(
        `/api/workpapers/${options.wpId.value}/g13/ai/adjudication-analysis`,
        { existingContent: auditNote.value, relatedContext: { totalAudited: totalRow.value.currentAudited } },
        { _silent: true } as any,
      )
      const content = res?.data?.content ?? res?.content ?? ''
      if (content) { auditNote.value = content; options.debouncedSave(ITEM_ID_NOTE, { conclusion: content }) }
    } catch {
      const draft = `本期公允价值变动收益审定数 ${totalRow.value.currentAudited.toLocaleString()} 元，${overallChangePctText.value}。`
      auditNote.value = auditNote.value ? `${auditNote.value}\n${draft}` : draft
      options.debouncedSave(ITEM_ID_NOTE, { conclusion: auditNote.value })
    } finally { aiLoading.value = false }
  }

  function onDetailUpdated(): void {
    /* allResponses watch 已驱动 computed；保留事件名兼容 */
  }

  onMounted(() => {
    void loadTrialBalanceFromApi()
    publishAdjudicatedDebounced()
    window.addEventListener('g13:detail-updated', onDetailUpdated)
  })
  onBeforeUnmount(() => {
    window.removeEventListener('g13:detail-updated', onDetailUpdated)
    if (_pubTimer) clearTimeout(_pubTimer)
  })

  return {
    dataRows,
    totalRow,
    trialBalanceAmount,
    variance,
    hasVarianceHighlight,
    hasDetailData,
    detailCrossValidation,
    overallChangeRate,
    overallChangePctText,
    hasAjeOverlay,
    ajeOverlay,
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
  }
}
