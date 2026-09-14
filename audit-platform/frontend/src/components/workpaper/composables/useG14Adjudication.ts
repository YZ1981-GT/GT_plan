import { useWorkpaperAuditYear } from './workpaperAuditYear'
/**
 * useG14Adjudication — G14-1 审定表（本期自 G14-2 同步，上期独立录入）
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import {
  G14_ACCOUNT_CODE,
  G14_CHANGE_AMOUNT_THRESHOLD,
  G14_CHANGE_RATE_THRESHOLD,
  G14_ECL_CROSS_REF,
  G14_LINE_ITEMS,
} from './g14Constants'
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
  const _auditYearRef = useWorkpaperAuditYear()

  const priorStore = ref<PriorStore>({})
  const trialBalanceAmount = ref(0)
  const auditNote = ref('')
  const auditConclusion = ref('')
  const aiLoading = ref(false)
  const tbLoading = ref(false)
  /** none | found | missing | error */
  const tbFetchStatus = ref<'none' | 'found' | 'missing' | 'error'>('none')

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
    const reasonRequired =
      isChangeRateExceeding(changeRate, G14_CHANGE_RATE_THRESHOLD)
      || Math.abs(changeAmount) >= G14_CHANGE_AMOUNT_THRESHOLD
      || (Math.abs(priorAudited) < 0.01 && Math.abs(currentAudited) >= 0.01)
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
      indexRef: prior.indexRef || G14_ECL_CROSS_REF[detailRow.rowKey] || '',
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
      changeRateHighlight: isChangeRateExceeding(changeRate, G14_CHANGE_RATE_THRESHOLD)
        || Math.abs(changeAmount) >= G14_CHANGE_AMOUNT_THRESHOLD,
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

  /** 总体变动率说明（对齐 xlsx 审计说明「本期较上期增减 %，负数为减少」） */
  const overallChangeRate = computed(() => totalRow.value.changeRate)
  const overallChangePctText = computed(() => {
    const r = overallChangeRate.value
    if (r === null) return '上期审定数为 0，无法计算变动率'
    const pct = (r * 100).toFixed(2)
    const dir = r >= 0 ? '增加' : '减少'
    return `${dir} ${pct}%`
  })
  const overallChangeExceedsThreshold = computed(() =>
    isChangeRateExceeding(overallChangeRate.value, G14_CHANGE_RATE_THRESHOLD)
    || Math.abs(totalRow.value.changeAmount) >= G14_CHANGE_AMOUNT_THRESHOLD,
  )

  const missingReasonCount = computed(() =>
    dataRows.value.filter((r) => r.reasonRequired && !String(r.reasonAnalysis ?? '').trim()).length,
  )
  const hasMissingReasons = computed(() => missingReasonCount.value > 0)

  /** 页面状态条：审定合计 / 变动 / 勾稽一览 */
  const statusSummary = computed(() => {
    const t = totalRow.value
    const tbOk = !hasVarianceHighlight.value
    const detailOk = !detailMismatch.value
    const reasonOk = !hasMissingReasons.value
    return {
      currentAudited: t.currentAudited,
      changeAmount: t.changeAmount,
      changeRate: t.changeRate,
      changePctText: overallChangePctText.value,
      changeWarn: overallChangeExceedsThreshold.value,
      tbOk,
      detailOk,
      reasonOk,
      allOk: tbOk && detailOk && reasonOk,
    }
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

  async function loadTrialBalanceFromApi(manual = false): Promise<boolean> {
    const _year = _auditYearRef.value
    if (_year == null || !options.projectId.value) {
      if (manual) ElMessage.warning('无法取数：缺少项目或审计年度')
      return false
    }
    tbLoading.value = true
    try {
      const res = await api.get(`/api/projects/${options.projectId.value}/trial-balance`, {
        params: { year: _year, account_prefix: G14_ACCOUNT_CODE },
        _silent: true,
      } as any)
      const rows = res?.data ?? res
      const list = Array.isArray(rows) ? rows : rows?.items ?? []
      const hit = list.find((r: any) =>
        String(r.standard_account_code ?? r.account_code ?? '').startsWith(G14_ACCOUNT_CODE),
      )
      if (hit) {
        const debit = parseNum(hit.debit_amount)
        const credit = parseNum(hit.credit_amount)
        // 损益类 6702：本期发生额 = 借方 − 贷方（与后端 _fetch_tb_pl_amount 一致）
        const amount = (hit.debit_amount != null || hit.credit_amount != null)
          ? (debit - credit)
          : parseNum(hit.unadjusted_amount ?? hit.current_amount ?? hit.debit_amount)
        updateTrialBalance(amount)
        tbFetchStatus.value = 'found'
        if (manual) ElMessage.success(`已从试算表取数 6702：${amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`)
        return true
      }
      tbFetchStatus.value = 'missing'
      if (manual) ElMessage.info('试算表未找到科目 6702，可手工录入试算平衡表数')
      return false
    } catch {
      tbFetchStatus.value = 'error'
      if (manual) ElMessage.error('试算表取数失败，请稍后重试或手工录入')
      return false
    } finally {
      tbLoading.value = false
    }
  }

  function publishAdjudicated(): void {
    if (hasMissingReasons.value) {
      ElMessage.warning(
        `有 ${missingReasonCount.value} 行变动超阈值未填原因分析，请先补充后再发布`,
      )
      return
    }
    if (detailMismatch.value) {
      ElMessage.warning('G14-1 与 G14-2 明细合计不一致，请先核对后再发布')
      return
    }
    if (hasVarianceHighlight.value) {
      ElMessage.warning('审定合计与试算平衡表 6702 存在差异，请先核对差异数后再发布')
      return
    }
    if (overallChangeExceedsThreshold.value && !String(auditNote.value ?? '').trim()) {
      ElMessage.warning('合计变动率超过 30%，请在审计说明中填写主要原因后再发布')
      return
    }
    const amount = totalRow.value.currentAudited
    options.debouncedSave('G14-1-adjudicated-amount', { conclusion: String(amount) })
    // substantive:adjudicated → 跨模块刷新；TB 回写走专用事件，避免父组件双次 writeback
    try {
      window.dispatchEvent(
        new CustomEvent('substantive:adjudicated', {
          detail: { accountCode: G14_ACCOUNT_CODE, adjudicatedAmount: amount },
        }),
      )
    } catch { /* silent */ }
    try {
      window.dispatchEvent(
        new CustomEvent('g14:writeback-trial-balance', {
          detail: { accountCode: G14_ACCOUNT_CODE, auditedAmount: amount },
        }),
      )
    } catch { /* silent */ }
    ElMessage.success(`已发布信用减值损失审定数 ${amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 元`)
  }

  async function generateAiAnalysis(): Promise<void> {
    if (options.isReadonly.value || !options.wpId.value) return
    aiLoading.value = true
    try {
      const res = await api.post(
        `/api/workpapers/${options.wpId.value}/g14/ai/adjudication-analysis`,
        {
          existingContent: auditNote.value,
          relatedContext: {
            totalAudited: totalRow.value.currentAudited,
            overallChangePctText: overallChangePctText.value,
            exceedsThreshold: overallChangeExceedsThreshold.value,
          },
        },
        { _silent: true } as any,
      )
      const content = res?.data?.content ?? res?.content ?? ''
      if (content) { auditNote.value = content; options.debouncedSave(ITEM_ID_NOTE, { conclusion: content }) }
    } catch {
      const draft = `本期信用减值损失审定数 ${totalRow.value.currentAudited.toLocaleString('zh-CN')} 元，较上期${overallChangePctText.value}。请结合各减值来源 ECL 变动说明主要原因。`
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
    overallChangeRate,
    overallChangePctText,
    overallChangeExceedsThreshold,
    missingReasonCount,
    hasMissingReasons,
    statusSummary,
    auditNote,
    auditConclusion,
    aiLoading,
    tbLoading,
    tbFetchStatus,
    detail,
    updatePriorField,
    updateTrialBalance,
    updateAuditNote,
    updateAuditConclusion,
    loadTrialBalanceFromApi,
    publishAdjudicated,
    generateAiAnalysis,
    G14_LINE_ITEMS,
  }
}
