/**
 * useD5Adjudication — D5-1 审定表核心逻辑 composable
 *
 * Spec: .kiro/specs/d5-receivables-financing/
 * Task: 6.1
 *
 * 职责：
 * - 固定行结构（ADJUDICATION_ROWS: 应收票据/应收账款/小计/减:OCI变动/FV合计/TB数/差异）
 * - rows computed（从allResponses加载 + crossSheet聚合填入 + 公式计算）
 * - trialBalanceAmount（从TB auto_data取数科目1124）+ trialBalanceDiff computed
 * - auditNotes 双向绑定（explanation/conclusion）
 * - updateCell（编辑 → 公式重算 → debouncedSave）
 * - publishAdjudicated（EventBus: substantive:adjudicated，payload含1124/auditedAmount）
 * - onAdjustmentCreated监听（AJE/RJE累加）
 * - 列：项目|期初(未审/AJE/RJE/审定)|期末(未审/AJE/RJE/审定)|变动额|变动率
 *
 * Requirements: 2.1-2.8, 3.1-3.7, 11.1, 11.2
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAuditedAmount,
  calcChangeAmount,
  calcChangeRate,
  calcSubtotal,
  calcFvTotal,
} from './useD5FormulaEngine'
import { eventBus } from '@/utils/eventBus'
import type { ChecklistResponse } from './useD5FormData'

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
  isFromCrossSheet: boolean
  isEditable: boolean
}

export interface AdjustmentPayload {
  wpCode: string
  entryType: 'AJE' | 'RJE'
  amount: number
  accountCode?: string
}

export interface UseD5AdjudicationOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: {
    categoryAggregation: ComputedRef<{
      notesReceivable: { prior: number; current: number }
      accountsReceivable: { prior: number; current: number }
    }>
    ociChange: ComputedRef<{ prior: number; current: number }>
    adjustmentTotals: ComputedRef<{ ajeTotal: number; rjeTotal: number }>
  }
  isReadonly: Ref<boolean>
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 固定行配置：审定表D5-1特殊OCI扣减结构 */
export const ADJUDICATION_ROWS = [
  { rowKey: 'notes-receivable', label: '应收票据', isComputed: false, isFromFV: false, isFromTB: false },
  { rowKey: 'accounts-receivable', label: '应收账款', isComputed: false, isFromFV: false, isFromTB: false },
  { rowKey: 'subtotal', label: '小计', isComputed: true, isFromFV: false, isFromTB: false },
  { rowKey: 'oci-change', label: '减：其他综合收益-公允价值变动', isComputed: false, isFromFV: true, isFromTB: false },
  { rowKey: 'fv-total', label: '应收款项融资公允价值合计', isComputed: true, isFromFV: false, isFromTB: false },
  { rowKey: 'trial-balance', label: '试算平衡表数', isComputed: false, isFromFV: false, isFromTB: true },
  { rowKey: 'difference', label: '差异数', isComputed: true, isFromFV: false, isFromTB: false },
] as const

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makeItemId(rowKey: string, field: string): string {
  return `D5-1-adj-${rowKey}-${field}`
}

function getResponseNum(allResponses: Map<string, ChecklistResponse>, itemId: string): number {
  return parseNum(allResponses.get(itemId)?.remark)
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD5Adjudication(options: UseD5AdjudicationOptions) {
  const { allResponses, saveImmediate, debouncedSave, crossSheet, isReadonly } = options

  // EventBus accumulated AJE/RJE (session-level, from adjustment:created events)
  const eventAjeAccum = ref(0)
  const eventRjeAccum = ref(0)

  // ─── Rows computed ───────────────────────────────────────────────────

  const rows: ComputedRef<AdjudicationRow[]> = computed(() => {
    const responses = allResponses.value
    const catAgg = crossSheet.categoryAggregation.value
    const ociData = crossSheet.ociChange.value
    const adjTotals = crossSheet.adjustmentTotals.value

    // D5-3 crossSheet AJE/RJE + session-level EventBus accumulated
    const totalAje = adjTotals.ajeTotal + eventAjeAccum.value
    const totalRje = adjTotals.rjeTotal + eventRjeAccum.value

    // ─── 应收票据行 ─────────────────────────────────────────────────
    const notesPriorUnadjusted = getResponseNum(responses, makeItemId('notes-receivable', 'priorUnadjusted'))
    const notesPriorAje = getResponseNum(responses, makeItemId('notes-receivable', 'priorAje'))
    const notesPriorRje = getResponseNum(responses, makeItemId('notes-receivable', 'priorRje'))
    // 期末未审数：优先使用crossSheet聚合值（D5-2→D5-1），无则取手动值
    const notesManualCurrent = getResponseNum(responses, makeItemId('notes-receivable', 'currentUnadjusted'))
    const notesCrossCurrent = catAgg.notesReceivable.current
    const notesCurrentUnadjusted = notesCrossCurrent !== 0 ? notesCrossCurrent : notesManualCurrent
    const notesCurrentAje = getResponseNum(responses, makeItemId('notes-receivable', 'currentAje')) + totalAje
    const notesCurrentRje = getResponseNum(responses, makeItemId('notes-receivable', 'currentRje')) + totalRje

    const notesPriorAudited = calcAuditedAmount(notesPriorUnadjusted, notesPriorAje, notesPriorRje)
    const notesCurrentAudited = calcAuditedAmount(notesCurrentUnadjusted, notesCurrentAje, notesCurrentRje)
    const notesChangeAmount = calcChangeAmount(notesPriorAudited, notesCurrentAudited)
    const notesChangeRate = calcChangeRate(notesPriorAudited, notesCurrentAudited)

    const notesRow: AdjudicationRow = {
      rowKey: 'notes-receivable',
      label: '应收票据',
      priorUnadjusted: notesPriorUnadjusted,
      priorAje: notesPriorAje,
      priorRje: notesPriorRje,
      priorAudited: notesPriorAudited,
      currentUnadjusted: notesCurrentUnadjusted,
      currentAje: notesCurrentAje,
      currentRje: notesCurrentRje,
      currentAudited: notesCurrentAudited,
      changeAmount: notesChangeAmount,
      changeRate: notesChangeRate,
      isFromCrossSheet: notesCrossCurrent !== 0,
      isEditable: true,
    }

    // ─── 应收账款行 ─────────────────────────────────────────────────
    const accPriorUnadjusted = getResponseNum(responses, makeItemId('accounts-receivable', 'priorUnadjusted'))
    const accPriorAje = getResponseNum(responses, makeItemId('accounts-receivable', 'priorAje'))
    const accPriorRje = getResponseNum(responses, makeItemId('accounts-receivable', 'priorRje'))
    const accManualCurrent = getResponseNum(responses, makeItemId('accounts-receivable', 'currentUnadjusted'))
    const accCrossCurrent = catAgg.accountsReceivable.current
    const accCurrentUnadjusted = accCrossCurrent !== 0 ? accCrossCurrent : accManualCurrent
    const accCurrentAje = getResponseNum(responses, makeItemId('accounts-receivable', 'currentAje')) + totalAje
    const accCurrentRje = getResponseNum(responses, makeItemId('accounts-receivable', 'currentRje')) + totalRje

    const accPriorAudited = calcAuditedAmount(accPriorUnadjusted, accPriorAje, accPriorRje)
    const accCurrentAudited = calcAuditedAmount(accCurrentUnadjusted, accCurrentAje, accCurrentRje)
    const accChangeAmount = calcChangeAmount(accPriorAudited, accCurrentAudited)
    const accChangeRate = calcChangeRate(accPriorAudited, accCurrentAudited)

    const accRow: AdjudicationRow = {
      rowKey: 'accounts-receivable',
      label: '应收账款',
      priorUnadjusted: accPriorUnadjusted,
      priorAje: accPriorAje,
      priorRje: accPriorRje,
      priorAudited: accPriorAudited,
      currentUnadjusted: accCurrentUnadjusted,
      currentAje: accCurrentAje,
      currentRje: accCurrentRje,
      currentAudited: accCurrentAudited,
      changeAmount: accChangeAmount,
      changeRate: accChangeRate,
      isFromCrossSheet: accCrossCurrent !== 0,
      isEditable: true,
    }

    // ─── 小计行 (= 应收票据 + 应收账款) ─────────────────────────────
    const subtotalPriorUnadjusted = calcSubtotal([notesPriorUnadjusted, accPriorUnadjusted])
    const subtotalPriorAje = calcSubtotal([notesPriorAje, accPriorAje])
    const subtotalPriorRje = calcSubtotal([notesPriorRje, accPriorRje])
    const subtotalCurrentUnadjusted = calcSubtotal([notesCurrentUnadjusted, accCurrentUnadjusted])
    const subtotalCurrentAje = calcSubtotal([notesCurrentAje, accCurrentAje])
    const subtotalCurrentRje = calcSubtotal([notesCurrentRje, accCurrentRje])
    const subtotalPriorAudited = calcAuditedAmount(subtotalPriorUnadjusted, subtotalPriorAje, subtotalPriorRje)
    const subtotalCurrentAudited = calcAuditedAmount(subtotalCurrentUnadjusted, subtotalCurrentAje, subtotalCurrentRje)
    const subtotalChangeAmount = calcChangeAmount(subtotalPriorAudited, subtotalCurrentAudited)
    const subtotalChangeRate = calcChangeRate(subtotalPriorAudited, subtotalCurrentAudited)

    const subtotalRow: AdjudicationRow = {
      rowKey: 'subtotal',
      label: '小计',
      priorUnadjusted: subtotalPriorUnadjusted,
      priorAje: subtotalPriorAje,
      priorRje: subtotalPriorRje,
      priorAudited: subtotalPriorAudited,
      currentUnadjusted: subtotalCurrentUnadjusted,
      currentAje: subtotalCurrentAje,
      currentRje: subtotalCurrentRje,
      currentAudited: subtotalCurrentAudited,
      changeAmount: subtotalChangeAmount,
      changeRate: subtotalChangeRate,
      isFromCrossSheet: false,
      isEditable: false,
    }

    // ─── 减：OCI公允价值变动行 (取自D5-4) ────────────────────────────
    const ociPriorUnadjusted = getResponseNum(responses, makeItemId('oci-change', 'priorUnadjusted'))
    const ociPriorAje = getResponseNum(responses, makeItemId('oci-change', 'priorAje'))
    const ociPriorRje = getResponseNum(responses, makeItemId('oci-change', 'priorRje'))
    // 期末：优先使用crossSheet计算的OCI变动值
    const ociManualCurrent = getResponseNum(responses, makeItemId('oci-change', 'currentUnadjusted'))
    const ociCrossCurrent = ociData.current
    const ociCurrentUnadjusted = ociCrossCurrent !== 0 ? ociCrossCurrent : ociManualCurrent
    const ociCurrentAje = getResponseNum(responses, makeItemId('oci-change', 'currentAje'))
    const ociCurrentRje = getResponseNum(responses, makeItemId('oci-change', 'currentRje'))

    const ociPriorAudited = calcAuditedAmount(ociPriorUnadjusted, ociPriorAje, ociPriorRje)
    const ociCurrentAudited = calcAuditedAmount(ociCurrentUnadjusted, ociCurrentAje, ociCurrentRje)
    const ociChangeAmount = calcChangeAmount(ociPriorAudited, ociCurrentAudited)
    const ociChangeRate = calcChangeRate(ociPriorAudited, ociCurrentAudited)

    const ociRow: AdjudicationRow = {
      rowKey: 'oci-change',
      label: '减：其他综合收益-公允价值变动',
      priorUnadjusted: ociPriorUnadjusted,
      priorAje: ociPriorAje,
      priorRje: ociPriorRje,
      priorAudited: ociPriorAudited,
      currentUnadjusted: ociCurrentUnadjusted,
      currentAje: ociCurrentAje,
      currentRje: ociCurrentRje,
      currentAudited: ociCurrentAudited,
      changeAmount: ociChangeAmount,
      changeRate: ociChangeRate,
      isFromCrossSheet: ociCrossCurrent !== 0,
      isEditable: true,
    }

    // ─── 公允价值合计行 (= 小计 - OCI变动) ──────────────────────────
    // 公式：公允价值合计 = 小计 - OCI变动（D5审定表特殊结构）
    const fvPriorAudited = calcFvTotal(subtotalPriorAudited, ociPriorAudited)
    const fvCurrentAudited = calcFvTotal(subtotalCurrentAudited, ociCurrentAudited)
    const fvPriorUnadjusted = calcFvTotal(subtotalPriorUnadjusted, ociPriorUnadjusted)
    const fvCurrentUnadjusted = calcFvTotal(subtotalCurrentUnadjusted, ociCurrentUnadjusted)
    const fvPriorAje = calcFvTotal(subtotalPriorAje, ociPriorAje)
    const fvCurrentAje = calcFvTotal(subtotalCurrentAje, ociCurrentAje)
    const fvPriorRje = calcFvTotal(subtotalPriorRje, ociPriorRje)
    const fvCurrentRje = calcFvTotal(subtotalCurrentRje, ociCurrentRje)
    const fvChangeAmount = calcChangeAmount(fvPriorAudited, fvCurrentAudited)
    const fvChangeRate = calcChangeRate(fvPriorAudited, fvCurrentAudited)

    const fvTotalRow: AdjudicationRow = {
      rowKey: 'fv-total',
      label: '应收款项融资公允价值合计',
      priorUnadjusted: fvPriorUnadjusted,
      priorAje: fvPriorAje,
      priorRje: fvPriorRje,
      priorAudited: fvPriorAudited,
      currentUnadjusted: fvCurrentUnadjusted,
      currentAje: fvCurrentAje,
      currentRje: fvCurrentRje,
      currentAudited: fvCurrentAudited,
      changeAmount: fvChangeAmount,
      changeRate: fvChangeRate,
      isFromCrossSheet: false,
      isEditable: false,
    }

    // ─── 试算平衡表数行 (从TB auto_data取数科目1124) ─────────────────
    const tbCurrentUnadjusted = trialBalanceAmount.value
    const tbPriorUnadjusted = getResponseNum(responses, makeItemId('trial-balance', 'priorUnadjusted'))

    const tbRow: AdjudicationRow = {
      rowKey: 'trial-balance',
      label: '试算平衡表数',
      priorUnadjusted: tbPriorUnadjusted,
      priorAje: 0,
      priorRje: 0,
      priorAudited: tbPriorUnadjusted,
      currentUnadjusted: tbCurrentUnadjusted,
      currentAje: 0,
      currentRje: 0,
      currentAudited: tbCurrentUnadjusted,
      changeAmount: calcChangeAmount(tbPriorUnadjusted, tbCurrentUnadjusted),
      changeRate: calcChangeRate(tbPriorUnadjusted, tbCurrentUnadjusted),
      isFromCrossSheet: false,
      isEditable: false,
    }

    // ─── 差异行 (= 公允价值合计 - 试算平衡表数) ─────────────────────
    const diffPriorAudited = fvPriorAudited - tbPriorUnadjusted
    const diffCurrentAudited = fvCurrentAudited - tbCurrentUnadjusted

    const differenceRow: AdjudicationRow = {
      rowKey: 'difference',
      label: '差异数',
      priorUnadjusted: 0,
      priorAje: 0,
      priorRje: 0,
      priorAudited: diffPriorAudited,
      currentUnadjusted: 0,
      currentAje: 0,
      currentRje: 0,
      currentAudited: diffCurrentAudited,
      changeAmount: calcChangeAmount(diffPriorAudited, diffCurrentAudited),
      changeRate: calcChangeRate(diffPriorAudited, diffCurrentAudited),
      isFromCrossSheet: false,
      isEditable: false,
    }

    return [notesRow, accRow, subtotalRow, ociRow, fvTotalRow, tbRow, differenceRow]
  })

  // ─── Trial Balance Amount ────────────────────────────────────────────

  const trialBalanceAmount: Ref<number> = ref(0)

  // Load from allResponses (auto_data from TB resolver for account 1124)
  watch(
    () => allResponses.value.get('D5-1-tb-amount')?.remark,
    (val) => { trialBalanceAmount.value = parseNum(val) },
    { immediate: true },
  )

  /** trialBalanceDiff = 公允价值合计审定数 - 试算平衡表数 */
  const trialBalanceDiff: ComputedRef<number> = computed(() => {
    const fvTotalRow = rows.value.find(r => r.rowKey === 'fv-total')
    if (!fvTotalRow) return 0
    return fvTotalRow.currentAudited - trialBalanceAmount.value
  })

  // ─── Audit Notes ─────────────────────────────────────────────────────

  const auditNotes = ref<{ explanation: string; conclusion: string }>({
    explanation: '',
    conclusion: '',
  })

  // Load from allResponses
  watch(
    () => [
      allResponses.value.get('D5-1-note-explanation')?.remark,
      allResponses.value.get('D5-1-note-conclusion')?.remark,
    ],
    ([explanation, conclusion]) => {
      auditNotes.value = {
        explanation: explanation || '',
        conclusion: conclusion || '',
      }
    },
    { immediate: true },
  )

  // Watch for changes and debounce save
  watch(
    () => auditNotes.value.explanation,
    (val) => {
      debouncedSave('D5-1-note-explanation', { remark: val })
    },
  )

  watch(
    () => auditNotes.value.conclusion,
    (val) => {
      debouncedSave('D5-1-note-conclusion', { remark: val })
    },
  )

  // ─── updateCell ──────────────────────────────────────────────────────

  function updateCell(rowKey: string, field: string, value: number | string): void {
    if (isReadonly.value) return

    const itemId = makeItemId(rowKey, field)
    const strValue = typeof value === 'number' ? String(value) : value

    // Update allResponses locally and trigger debounced save
    debouncedSave(itemId, { remark: strValue })
  }

  // ─── publishAdjudicated ──────────────────────────────────────────────

  function publishAdjudicated(): void {
    const fvTotalRow = rows.value.find(r => r.rowKey === 'fv-total')
    const auditedAmount = fvTotalRow?.currentAudited ?? 0

    const payload = {
      wpCode: 'D5',
      accountCode: '1124',
      auditedAmount,
      adjudicatedAmount: auditedAmount, // 别名兼容
      timestamp: Date.now(),
    }

    // Persist the adjudicated amount
    saveImmediate('D5-1-tb-amount', { remark: String(auditedAmount) })

    // 统一 eventBus (crossWpEventBridge 双向桥接 window)
    eventBus.emit('substantive:adjudicated', payload)
  }

  // ─── onAdjustmentCreated ─────────────────────────────────────────────

  function onAdjustmentCreated(payload: AdjustmentPayload): void {
    if (payload.wpCode !== 'D5') return
    if (payload.entryType === 'AJE') {
      eventAjeAccum.value += payload.amount
    } else if (payload.entryType === 'RJE') {
      eventRjeAccum.value += payload.amount
    }
  }

  // ─── EventBus Registration ───────────────────────────────────────────

  // 统一 eventBus
  eventBus.on('adjustment:created', (payload: any) => {
    if (payload) onAdjustmentCreated(payload)
  })

  onBeforeUnmount(() => {
    eventBus.off('adjustment:created')
  })

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    rows,
    trialBalanceAmount,
    trialBalanceDiff,
    auditNotes,
    updateCell,
    publishAdjudicated,
    onAdjustmentCreated,
    // Internal (for testing)
    _eventAjeAccum: eventAjeAccum,
    _eventRjeAccum: eventRjeAccum,
  }
}

export default useD5Adjudication
