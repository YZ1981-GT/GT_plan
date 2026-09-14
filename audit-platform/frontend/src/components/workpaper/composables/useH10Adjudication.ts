/**
 * useH10Adjudication — H10-1 审定表（损益类/AJE+RJE）
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  H10_ACCOUNT_CODE,
  H10_ADJUDICATION_ITEMS,
  H10_CHANGE_RATE_THRESHOLD,
} from './h10Constants'
import {
  parseH10AdjStore,
  patchH10AdjRow,
  type H10AdjustmentWriteback,
} from './h10AdjStorage'
import {
  parseNum,
  calcAuditedAmount,
  calcChangeAmount,
  calcChangeRate,
  isChangeRateExceeding,
  calcSubtotal,
} from './useH10FormulaEngine'
import { useH10Detail } from './useH10Detail'
import { applyH10DetailToAdjStore } from './h10FillFromDetail'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import { ElMessage } from 'element-plus'

export interface H10AdjudicationRow {
  rowKey: string
  label: string
  currentUnadjusted: number
  currentAje: number
  currentRje: number
  currentAudited: number
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  priorAudited: number
  changeAmount: number
  changeRate: number | null
  reasonAnalysis: string
  indexRef: string
  changeRateHighlight: boolean
  reasonRequired: boolean
}

const ITEM_ID_ROWS = 'H10-adj-rows'
const ITEM_ID_TB = 'H10-adj-tb'
const ITEM_ID_NOTE = 'H10-adj-note'
const ITEM_ID_CONCLUSION = 'H10-adj-conclusion'

type RowStore = ReturnType<typeof parseH10AdjStore>

export function useH10Adjudication(opts: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  writebackTB?: (auditedAmount: number) => Promise<void>
  writebackTrialBalance?: (auditedAmount: number) => Promise<void>
}) {
  const rowStore = ref<RowStore>(parseH10AdjStore(undefined))
  const trialBalanceAmount = ref(0)
  const auditNote = ref('')
  const auditConclusion = ref('')
  const aiLoading = ref(false)
  const collapsedGroups = ref<Record<string, boolean>>({})

  const writebackFn = () => opts.writebackTB ?? opts.writebackTrialBalance

  const detail = useH10Detail({
    allResponses: opts.allResponses,
    debouncedSave: opts.debouncedSave,
    isReadonly: opts.isReadonly,
  })

  watch(() => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark, (j) => {
    rowStore.value = parseH10AdjStore(j)
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

  function buildRow(def: (typeof H10_ADJUDICATION_ITEMS)[number]): H10AdjudicationRow {
    const raw = rowStore.value[def.rowKey] ?? {}
    const currentUnadjusted = parseNum(raw.currentUnadjusted)
    const currentAje = parseNum(raw.currentAje)
    const currentRje = parseNum(raw.currentRje)
    const priorUnadjusted = parseNum(raw.priorUnadjusted)
    const priorAje = parseNum(raw.priorAje)
    const priorRje = parseNum(raw.priorRje)
    const currentAudited = calcAuditedAmount(currentUnadjusted, currentAje, currentRje)
    const priorAudited = calcAuditedAmount(priorUnadjusted, priorAje, priorRje)
    const changeRate = calcChangeRate(priorAudited, currentAudited)
    const reasonRequired = isChangeRateExceeding(changeRate, H10_CHANGE_RATE_THRESHOLD)
    return {
      rowKey: def.rowKey,
      label: def.label,
      currentUnadjusted,
      currentAje,
      currentRje,
      currentAudited,
      priorUnadjusted,
      priorAje,
      priorRje,
      priorAudited,
      changeAmount: calcChangeAmount(currentAudited, priorAudited),
      changeRate,
      reasonAnalysis: raw.reasonAnalysis ?? '',
      indexRef: raw.indexRef ?? '',
      changeRateHighlight: reasonRequired,
      reasonRequired,
    }
  }

  const dataRows = computed(() => H10_ADJUDICATION_ITEMS.map(buildRow))

  const totalRow = computed(() => {
    const rows = dataRows.value
    const currentAudited = calcSubtotal(rows.map((r) => r.currentAudited))
    const priorAudited = calcSubtotal(rows.map((r) => r.priorAudited))
    const changeRate = calcChangeRate(priorAudited, currentAudited)
    return {
      rowKey: 'total',
      label: '合  计',
      currentUnadjusted: calcSubtotal(rows.map((r) => r.currentUnadjusted)),
      currentAje: calcSubtotal(rows.map((r) => r.currentAje)),
      currentRje: calcSubtotal(rows.map((r) => r.currentRje)),
      currentAudited,
      priorUnadjusted: calcSubtotal(rows.map((r) => r.priorUnadjusted)),
      priorAje: calcSubtotal(rows.map((r) => r.priorAje)),
      priorRje: calcSubtotal(rows.map((r) => r.priorRje)),
      priorAudited,
      changeAmount: calcChangeAmount(currentAudited, priorAudited),
      changeRate,
      reasonAnalysis: '',
      indexRef: '',
      changeRateHighlight: isChangeRateExceeding(changeRate, H10_CHANGE_RATE_THRESHOLD),
      reasonRequired: false,
    }
  })

  const groupedRows = computed(() => [{
    groupName: '资产处置损益审定项目',
    collapsed: collapsedGroups.value['资产处置损益审定项目'] ?? false,
    rows: dataRows.value,
    subtotal: {
      currentAudited: totalRow.value.currentAudited,
      priorAudited: totalRow.value.priorAudited,
    },
  }])

  const variance = computed(() => totalRow.value.currentAudited - trialBalanceAmount.value)
  const hasVarianceHighlight = computed(() => Math.abs(variance.value) > 0.01)

  const detailMismatch = computed(() =>
    Math.abs(detail.statsSummary.value.totalGainLoss - totalRow.value.currentAudited) > 0.01,
  )

  const hasDetailData = computed(() => detail.rows.value.length > 0)

  const detailCrossValidation = computed((): string | null => {
    if (!hasDetailData.value || !detailMismatch.value) return null
    const dTotal = detail.statsSummary.value.totalGainLoss
    const adjTotal = totalRow.value.currentAudited
    return `H10-1 审定合计 ${adjTotal.toFixed(2)} 与 H10-2 明细合计 ${dTotal.toFixed(2)} 不一致`
  })

  function persistRows(): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rowStore.value) })
  }

  function updateField(
    rowKey: string,
    field:
      | 'currentUnadjusted' | 'currentAje' | 'currentRje'
      | 'priorUnadjusted' | 'priorAje' | 'priorRje'
      | 'reasonAnalysis' | 'indexRef',
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
      void publishAdjudicated()
    }, 1500)
  }

  function applyAdjustmentWriteback(wb: H10AdjustmentWriteback): void {
    if (opts.isReadonly.value) return
    rowStore.value = patchH10AdjRow(rowStore.value, wb.rowKey, {
      currentAje: wb.currentAje,
      currentRje: wb.currentRje,
    })
    persistRows()
    publishAdjudicatedDebounced()
  }

  /** H10-2 明细按来源汇总 → 未审；试运行取披露明细净额 */
  function fillFromDetail(): { filled: number } {
    if (opts.isReadonly.value) return { filled: 0 }
    const detailRows = detail.rows.value
    let trialRows: Array<{ currentIncome: number; currentCost: number; priorIncome: number; priorCost: number }> = []
    const trialRaw = opts.allResponses.value.get('H10-disclosure-listed-trial')?.remark
    if (trialRaw) {
      try {
        const parsed = JSON.parse(trialRaw)
        if (Array.isArray(parsed)) trialRows = parsed
      } catch { /* ignore */ }
    }
    const result = applyH10DetailToAdjStore(rowStore.value, detailRows, trialRows)
    rowStore.value = result.nextStore
    persistRows()
    publishAdjudicatedDebounced()
    const n = result.filledKeys.length
    if (n > 0) {
      ElMessage.success(`已从 H10-2 带入 ${n} 个审定分项${result.trialCurrent || result.trialPrior ? '（含试运行）' : ''}`)
    } else {
      ElMessage.warning('H10-2 明细暂无可汇总金额（请先填来源底稿与处置损益）')
    }
    return { filled: n }
  }

  function toggleGroup(groupName: string): void {
    collapsedGroups.value = {
      ...collapsedGroups.value,
      [groupName]: !collapsedGroups.value[groupName],
    }
  }

  async function validateWithBackend(): Promise<boolean> {
    return validateFormulasRemote()
  }

  async function saveAdjudicationToBackend(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      await api.post(`/api/workpapers/${opts.wpId.value}/h10/save-adjudication`, {
        row_store: rowStore.value,
        adjudicated_amount: totalRow.value.currentAudited,
        audit_note: auditNote.value,
        audit_conclusion: auditConclusion.value,
      }, { _silent: true } as any)
    } catch { /* fallback to debounced save */ }
  }

  async function generateAiAnalysis(): Promise<void> {
    if (opts.isReadonly.value) return
    aiLoading.value = true
    try {
      const res = await api.post(`/api/workpapers/${opts.wpId.value}/h10/ai/adjudication-analysis`, {
        existingContent: auditNote.value,
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

  async function validateFormulasRemote(): Promise<boolean> {
    try {
      const res = await api.post(`/api/workpapers/${opts.wpId.value}/h10/validate-formulas`, {
        adjudication_rows: dataRows.value,
        detail_rows: detail.rows.value,
      }, { _silent: true } as any)
      const payload = res?.data ?? res
      return payload?.ok !== false
    } catch {
      return true
    }
  }

  async function publishAdjudicated(): Promise<void> {
    const amount = totalRow.value.currentAudited
    opts.debouncedSave('H10-1-adjudicated-amount', { conclusion: String(amount) })
    const wb = writebackFn()
    if (wb) await wb(amount)
    const payload = {
      accountCode: H10_ACCOUNT_CODE,
      adjudicatedAmount: amount,
      auditedAmount: amount,
      wpCode: 'H10',
      projectId: opts.projectId.value,
      timestamp: Date.now(),
    }
    // 只走 eventBus，crossWpEventBridge 自动桥接到 window（消除双投）
    try {
      eventBus.emit('substantive:adjudicated', payload as any)
    } catch { /* silent */ }
  }

  async function loadTrialBalanceFromApi(): Promise<void> {
    if (!opts.projectId.value) return
    try {
      const res = await api.get(`/api/projects/${opts.projectId.value}/trial-balance`, {
        params: { account_prefix: H10_ACCOUNT_CODE },
        _silent: true,
      } as any)
      const list = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])
      const hit = list.find((r: any) =>
        String(r.standard_account_code ?? r.account_code ?? '').startsWith(H10_ACCOUNT_CODE),
      )
      if (hit) {
        const credit = parseNum(hit.credit_amount ?? hit.period_credit)
        const debit = parseNum(hit.debit_amount ?? hit.period_debit)
        updateTrialBalance(credit - debit)
      }
    } catch { /* optional */ }
  }

  function onAdjustmentWriteback(e: Event): void {
    const detail = (e as CustomEvent).detail as H10AdjustmentWriteback | undefined
    if (detail?.rowKey) applyAdjustmentWriteback(detail)
  }

  onMounted(() => {
    void loadTrialBalanceFromApi()
    void publishAdjudicated()
    window.addEventListener('h10:adjustment-writeback', onAdjustmentWriteback)
  })
  onBeforeUnmount(() => {
    window.removeEventListener('h10:adjustment-writeback', onAdjustmentWriteback)
    if (publishTimer) clearTimeout(publishTimer)
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
    applyAdjustmentWriteback,
    fillFromDetail,
    validateFormulasRemote,
    validateWithBackend,
    saveAdjudicationToBackend,
    generateAiAnalysis,
    loadTrialBalanceFromApi,
  }
}
