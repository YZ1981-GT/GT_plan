/**
 * useF1Adjudication — F1-1 审定表核心逻辑 composable
 *
 * Spec: .kiro/specs/f1-prepayment/
 * Task: 6.1
 *
 * 职责：
 * - 双区块：按性质分类（货款/工程款/设备款/服务费/其他）+ 按账龄分类（项目 aging 配置驱动）
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
import { useAgingConfig, PRESET_SEGMENTS } from '@/composables/useAgingConfig'
import {
  AGING_ROWS_3YEAR,
  resolveAdjudicationAgingRows,
  type AgingRowDef,
} from './agingPresets'
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

/** 区块一：按性质分类（对齐 Excel F1-1 / F4 往来款性质枚举） */
export const NATURE_ROWS = [
  { rowKey: 'goods', label: '货款' },
  { rowKey: 'construction', label: '工程款' },
  { rowKey: 'equipment', label: '设备款' },
  { rowKey: 'service', label: '服务费' },
  { rowKey: 'other', label: '其他' },
] as const

/** 明细表款项性质下拉（与 NATURE_ROWS.label 一致） */
export const F1_PAYMENT_NATURE_OPTIONS = NATURE_ROWS.map(r => r.label)

/** 区块二默认账龄行（THREE_YEAR；运行时由 useAgingConfig 覆盖） */
export const AGING_ROWS: AgingRowDef[] = AGING_ROWS_3YEAR

/** 性质标签→rowKey映射 */
const NATURE_LABEL_TO_KEY: Record<string, string> = Object.fromEntries(
  NATURE_ROWS.map(r => [r.label, r.rowKey]),
)

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
  const manualPrior = getResponseNum(allResponses, makeItemId(section, rowKey, 'priorUnadjusted'))
  const priorUnadjusted = crossSheetPrior !== 0 ? crossSheetPrior : manualPrior
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

  // 项目级账龄配置（F1 默认 THREE_YEAR；可切换 FIVE_YEAR / CUSTOM）
  const { segments } = useAgingConfig(projectId, 'F1')

  const agingRowDefs: ComputedRef<AgingRowDef[]> = computed(() => {
    const segs = segments.value.length ? segments.value : PRESET_SEGMENTS.THREE_YEAR
    return resolveAdjudicationAgingRows(segs)
  })

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

    // === 区块二：按账龄分类（动态段） ===
    const agingRows: AdjudicationRow[] = agingRowDefs.value.map(({ rowKey, label }) => {
      const crossCurrent = parseNum(agingAgg[rowKey])
      const crossPrior = parseNum(agingAgg[`prior_${rowKey}`])
      return buildRow(
        'aging',
        rowKey,
        label,
        responses,
        crossCurrent,
        crossPrior,
        eventAjeAccum.value,
        eventRjeAccum.value,
      )
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

    const isNature = NATURE_ROWS.some(r => r.rowKey === rowKey)
    const section = isNature ? 'nature' : 'aging'
    const itemId = makeItemId(section, rowKey, field)

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

    if (projectId.value) {
      try {
        window.dispatchEvent(new CustomEvent('f1:writeback-trial-balance', {
          detail: { projectId: projectId.value, accountCode: '1123', auditedAmount },
        }))
      } catch { /* silent */ }
    }
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
    agingRowDefs,
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
    _NATURE_LABEL_TO_KEY: NATURE_LABEL_TO_KEY,
  }
}

export default useF1Adjudication
