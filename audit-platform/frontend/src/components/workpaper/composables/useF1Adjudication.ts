/**
 * useF1Adjudication — F1-1 审定表核心逻辑 composable
 *
 * Spec: .kiro/specs/f1-prepayment/
 * Task: 6.1
 *
 * 职责：
 * - 双区块固定行（按性质分类 NATURE_ROWS + 按账龄分类 AGING_ROWS）
 * - sections computed（从allResponses加载 + crossSheet聚合填入）
 * - trialBalanceAmount（从TB auto_data取数）+ trialBalanceDiff computed
 * - crossValidationDiff + crossValidationWarning computed
 * - auditNotes 双向绑定（agingReason/changeAnalysis/conclusion）
 * - updateCell（编辑 → 公式重算 → debouncedSave）
 * - publishAdjudicated（EventBus发布，payload含1123/auditedAmount）
 * - onAdjustmentCreated监听（AJE/RJE累加）
 *
 * Requirements: 1.1-1.8, 2.1-2.8, 3.1-3.7, 18.1
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAuditedAmount,
  calcChangeAmount,
  calcChangeRate,
  calcSubtotal,
} from './useF1FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import type { useF1CrossSheet } from './useF1CrossSheet'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AdjudicationRow {
  rowKey: string
  label: string
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  priorAudited: number      // = 未审 + AJE + RJE
  currentUnadjusted: number
  currentAje: number
  currentRje: number
  currentAudited: number    // = 未审 + AJE + RJE
  changeAmount: number      // = 期末审定 - 期初审定
  changeRate: number | '' | 'N/A'
  reasonAnalysis: string
  isFromCrossSheet: boolean
  isEditable: boolean
}

export interface AdjudicationSection {
  sectionKey: 'by-nature' | 'by-aging'
  sectionLabel: string
  rows: AdjudicationRow[]
  subtotalRow: AdjudicationRow
}

export interface AdjustmentPayload {
  wpCode: string
  entryType: 'AJE' | 'RJE'
  amount: number
  accountCode?: string
}

export interface UseF1AdjudicationOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: ReturnType<typeof useF1CrossSheet>
  isReadonly: Ref<boolean>
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 区块一：按性质分类固定行 */
export const NATURE_ROWS = [
  { rowKey: 'fixed-asset-sales', label: '预收销售固定资产款' },
  { rowKey: 'land-use-right', label: '预收销售土地使用权款' },
  { rowKey: 'contract-invalid', label: '合同不成立时已收取的对价' },
  { rowKey: 'other', label: '其他' },
] as const

/** 区块二：按账龄分类固定行 */
export const AGING_ROWS = [
  { rowKey: 'within-1-year', label: '1年以内' },
  { rowKey: '1-to-2-years', label: '1至2年' },
  { rowKey: '2-to-3-years', label: '2至3年' },
  { rowKey: 'over-3-years', label: '3年以上' },
] as const

/** 性质标签→rowKey映射 */
const NATURE_LABEL_TO_KEY: Record<string, string> = {
  '预收销售固定资产款': 'fixed-asset-sales',
  '预收销售土地使用权款': 'land-use-right',
  '合同不成立时已收取的对价': 'contract-invalid',
  '其他': 'other',
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makeItemId(section: string, rowKey: string, field: string): string {
  return `F1-adj-${section}-${rowKey}-${field}`
}

function getResponseNum(allResponses: Map<string, ChecklistResponse>, itemId: string): number {
  return parseNum(allResponses.get(itemId)?.remark)
}

function getResponseStr(allResponses: Map<string, ChecklistResponse>, itemId: string): string {
  return allResponses.get(itemId)?.remark || ''
}

function buildRow(
  section: string,
  rowKey: string,
  label: string,
  allResponses: Map<string, ChecklistResponse>,
  crossSheetCurrent: number,
  crossSheetPrior: number,
  eventAje: number,
  eventRje: number,
): AdjudicationRow {
  // Manual fields (editable)
  const priorUnadjusted = getResponseNum(allResponses, makeItemId(section, rowKey, 'priorUnadjusted'))
  const priorAje = getResponseNum(allResponses, makeItemId(section, rowKey, 'priorAje'))
  const priorRje = getResponseNum(allResponses, makeItemId(section, rowKey, 'priorRje'))

  // Current: crossSheet fills currentUnadjusted (from F1-2), or manual edit
  const manualCurrent = getResponseNum(allResponses, makeItemId(section, rowKey, 'currentUnadjusted'))
  const currentUnadjusted = crossSheetCurrent !== 0 ? crossSheetCurrent : manualCurrent
  const currentAje = getResponseNum(allResponses, makeItemId(section, rowKey, 'currentAje')) + eventAje
  const currentRje = getResponseNum(allResponses, makeItemId(section, rowKey, 'currentRje')) + eventRje

  const priorAudited = calcAuditedAmount(priorUnadjusted, priorAje, priorRje)
  const currentAudited = calcAuditedAmount(currentUnadjusted, currentAje, currentRje)
  const changeAmount = calcChangeAmount(currentAudited, priorAudited)
  const changeRate = calcChangeRate(priorAudited, currentAudited)
  const reasonAnalysis = getResponseStr(allResponses, makeItemId(section, rowKey, 'reasonAnalysis'))

  const isFromCrossSheet = crossSheetCurrent !== 0 || crossSheetPrior !== 0

  return {
    rowKey,
    label,
    priorUnadjusted,
    priorAje,
    priorRje,
    priorAudited,
    currentUnadjusted,
    currentAje,
    currentRje,
    currentAudited,
    changeAmount,
    changeRate,
    reasonAnalysis,
    isFromCrossSheet,
    isEditable: true,
  }
}

function buildSubtotalRow(rows: AdjudicationRow[], label: string): AdjudicationRow {
  const priorUnadjusted = calcSubtotal(rows.map(r => r.priorUnadjusted))
  const priorAje = calcSubtotal(rows.map(r => r.priorAje))
  const priorRje = calcSubtotal(rows.map(r => r.priorRje))
  const currentUnadjusted = calcSubtotal(rows.map(r => r.currentUnadjusted))
  const currentAje = calcSubtotal(rows.map(r => r.currentAje))
  const currentRje = calcSubtotal(rows.map(r => r.currentRje))
  const priorAudited = calcAuditedAmount(priorUnadjusted, priorAje, priorRje)
  const currentAudited = calcAuditedAmount(currentUnadjusted, currentAje, currentRje)
  const changeAmount = calcChangeAmount(currentAudited, priorAudited)
  const changeRate = calcChangeRate(priorAudited, currentAudited)

  return {
    rowKey: 'subtotal',
    label,
    priorUnadjusted,
    priorAje,
    priorRje,
    priorAudited,
    currentUnadjusted,
    currentAje,
    currentRje,
    currentAudited,
    changeAmount,
    changeRate,
    reasonAnalysis: '',
    isFromCrossSheet: false,
    isEditable: false,
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useF1Adjudication(options: UseF1AdjudicationOptions) {
  const { allResponses, wpId, projectId, saveImmediate, debouncedSave, crossSheet, isReadonly } = options

  let _debounceTimer: ReturnType<typeof setTimeout> | null = null
  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []

  // EventBus accumulated AJE/RJE (session-level, from adjustment:created events)
  const eventAjeAccum = ref(0)
  const eventRjeAccum = ref(0)

  // ─── Sections computed ───────────────────────────────────────────────

  const sections: ComputedRef<AdjudicationSection[]> = computed(() => {
    const responses = allResponses.value
    const natureAgg = crossSheet.natureAggregation.value
    const agingAgg = crossSheet.agingAggregation.value

    // === 区块一：按性质分类 ===
    const natureRows: AdjudicationRow[] = NATURE_ROWS.map(({ rowKey, label }) => {
      const aggData = natureAgg[label] || { current: 0, prior: 0 }
      return buildRow('nature', rowKey, label, responses, aggData.current, aggData.prior, 0, 0)
    })

    const natureSubtotal = buildSubtotalRow(natureRows, '合计')

    // === 区块二：按账龄分类 ===
    const agingRows: AdjudicationRow[] = AGING_ROWS.map(({ rowKey, label }) => {
      let crossCurrent = 0
      let crossPrior = 0
      switch (rowKey) {
        case 'within-1-year':
          crossCurrent = agingAgg.within1
          crossPrior = agingAgg.prior_within1
          break
        case '1-to-2-years':
          crossCurrent = agingAgg.y1to2
          crossPrior = agingAgg.prior_y1to2
          break
        case '2-to-3-years':
          crossCurrent = agingAgg.y2to3
          crossPrior = agingAgg.prior_y2to3
          break
        case 'over-3-years':
          crossCurrent = agingAgg.over3
          crossPrior = agingAgg.prior_over3
          break
      }
      return buildRow('aging', rowKey, label, responses, crossCurrent, crossPrior, eventAjeAccum.value, eventRjeAccum.value)
    })

    const agingSubtotal = buildSubtotalRow(agingRows, '合计')

    return [
      {
        sectionKey: 'by-nature' as const,
        sectionLabel: '一、按性质分类',
        rows: natureRows,
        subtotalRow: natureSubtotal,
      },
      {
        sectionKey: 'by-aging' as const,
        sectionLabel: '二、按账龄分类',
        rows: agingRows,
        subtotalRow: agingSubtotal,
      },
    ]
  })

  // ─── Trial Balance Amount ────────────────────────────────────────────

  const trialBalanceAmount: Ref<number> = ref(0)

  // Load from allResponses or auto_data
  watch(
    () => allResponses.value.get('F1-adj-trial-balance-amount')?.remark,
    (val) => { trialBalanceAmount.value = parseNum(val) },
    { immediate: true },
  )

  /** trialBalanceDiff = 账龄合计 currentAudited - trialBalanceAmount */
  const trialBalanceDiff: ComputedRef<number> = computed(() => {
    const agingSubtotal = sections.value[1]?.subtotalRow
    if (!agingSubtotal) return 0
    return agingSubtotal.currentAudited - trialBalanceAmount.value
  })

  // ─── Cross Validation ────────────────────────────────────────────────

  /** crossValidationDiff = 性质合计 currentAudited - 账龄合计 currentAudited */
  const crossValidationDiff: ComputedRef<number> = computed(() => {
    const natureSubtotal = sections.value[0]?.subtotalRow
    const agingSubtotal = sections.value[1]?.subtotalRow
    if (!natureSubtotal || !agingSubtotal) return 0
    return natureSubtotal.currentAudited - agingSubtotal.currentAudited
  })

  /** crossValidationWarning: non-null when diff !== 0 */
  const crossValidationWarning: ComputedRef<string | null> = computed(() => {
    const diff = crossValidationDiff.value
    if (diff === 0) return null
    const sign = diff > 0 ? '+' : ''
    return `性质分类合计≠账龄分类合计，差额：${sign}${diff}元`
  })

  // ─── Audit Notes ─────────────────────────────────────────────────────

  const auditNotes = ref<{ agingReason: string; changeAnalysis: string; conclusion: string }>({
    agingReason: '',
    changeAnalysis: '',
    conclusion: '',
  })

  // Load from allResponses
  watch(
    () => [
      allResponses.value.get('F1-adj-note-aging-reason')?.remark,
      allResponses.value.get('F1-adj-note-change-analysis')?.remark,
      allResponses.value.get('F1-adj-note-conclusion')?.remark,
    ],
    ([aging, change, concl]) => {
      auditNotes.value = {
        agingReason: aging || '',
        changeAnalysis: change || '',
        conclusion: concl || '',
      }
    },
    { immediate: true },
  )

  // Watch for changes and debounce save
  watch(
    () => auditNotes.value.agingReason,
    (val) => {
      debouncedSave('F1-adj-note-aging-reason', { remark: val })
    },
  )

  watch(
    () => auditNotes.value.changeAnalysis,
    (val) => {
      debouncedSave('F1-adj-note-change-analysis', { remark: val })
    },
  )

  watch(
    () => auditNotes.value.conclusion,
    (val) => {
      debouncedSave('F1-adj-note-conclusion', { remark: val })
    },
  )

  // ─── updateCell ──────────────────────────────────────────────────────

  function updateCell(rowKey: string, field: string, value: number | string): void {
    if (isReadonly.value) return

    // Determine section from rowKey
    const isNature = NATURE_ROWS.some(r => r.rowKey === rowKey)
    const section = isNature ? 'nature' : 'aging'
    const itemId = makeItemId(section, rowKey, field)

    // Update allResponses and trigger save
    const strValue = typeof value === 'number' ? String(value) : value
    debouncedSave(itemId, { remark: strValue })
  }

  // ─── publishAdjudicated ──────────────────────────────────────────────

  function publishAdjudicated(): void {
    const agingSubtotal = sections.value[1]?.subtotalRow
    const auditedAmount = agingSubtotal?.currentAudited ?? 0

    const payload = {
      wpCode: 'F1',
      accountCode: '1123',
      auditedAmount,
    }

    try {
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', { detail: payload }))
    } catch { /* silent */ }
  }

  // ─── onAdjustmentCreated ─────────────────────────────────────────────

  function onAdjustmentCreated(payload: AdjustmentPayload): void {
    if (payload.wpCode !== 'F1') return
    if (payload.entryType === 'AJE') {
      eventAjeAccum.value += payload.amount
    } else if (payload.entryType === 'RJE') {
      eventRjeAccum.value += payload.amount
    }
  }

  // ─── EventBus Registration ───────────────────────────────────────────

  const adjustmentHandler = (e: Event) => {
    const detail = (e as CustomEvent).detail
    if (detail) onAdjustmentCreated(detail)
  }
  window.addEventListener('adjustment:created', adjustmentHandler)
  eventListeners.push({ event: 'adjustment:created', handler: adjustmentHandler })

  onBeforeUnmount(() => {
    if (_debounceTimer) {
      clearTimeout(_debounceTimer)
      _debounceTimer = null
    }
    for (const { event, handler } of eventListeners) {
      window.removeEventListener(event, handler)
    }
  })

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    // 双区块
    sections,
    // 试算平衡表数 + 差异
    trialBalanceAmount,
    trialBalanceDiff,
    // 交叉验证
    crossValidationDiff,
    crossValidationWarning,
    // 审计说明
    auditNotes,
    // 操作
    updateCell,
    publishAdjudicated,
    // EventBus
    onAdjustmentCreated,
    // Internal (for testing)
    _eventAjeAccum: eventAjeAccum,
    _eventRjeAccum: eventRjeAccum,
  }
}

export default useF1Adjudication
