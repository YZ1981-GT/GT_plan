/**
 * useD7Adjudication — D7-1 审定表（双区块：按性质+按账龄，含扣减行）
 *
 * 双区块固定行结构：
 *   一、按性质分类：预收货款/开发项目预收款/预收工程款/其他/小计/减：计入其他非流动负债的合同负债/合同负债合计
 *   二、按账龄分类：1年以内/1~2年/2~3年/3年以上/合计/试算平衡表数/差异数
 *
 * 公式关系：
 *   - 审定数 = 未审 + AJE + RJE
 *   - 小计 = SUM(明细行)
 *   - 合同负债合计 = 小计 - 非流动负债扣减
 *   - 账龄合计 = SUM(4段)
 *   - 差异 = 账龄合计 - 试算平衡表数
 *   - 交叉验证：合同负债合计(性质) === 账龄合计(账龄)
 *
 * Spec: .kiro/specs/d7-contract-liabilities/
 * Task: 6.1
 * Requirements: 2.1-2.9, 3.1-3.7, 4.1-4.7, 17.1, 18.1, 23.1
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAuditedAmount,
  calcChangeAmount,
  calcChangeRate,
  calcSubtotal,
  calcContractLiabilityTotal,
  isChangeRateExceeding,
} from './useD7FormulaEngine'
import type { ChecklistResponse } from './useD7FormData'
import type useD7CrossSheet from './useD7CrossSheet'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AdjudicationRow {
  rowKey: string
  label: string
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  priorAudited: number
  currentUnadjusted: number
  currentAje: number
  currentRje: number
  currentAudited: number
  changeAmount: number
  changeRate: number | '' | 'N/A'
  reasonAnalysis: string
  isFromCrossSheet: boolean
  isEditable: boolean
  isDeductionRow: boolean
  rowType: 'detail' | 'subtotal' | 'deduction' | 'total' | 'tb' | 'diff'
}

export interface UseD7AdjudicationOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  crossSheet: ReturnType<typeof useD7CrossSheet>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId: Ref<string>
  projectId: Ref<string>
}

// ─── Block Configuration ─────────────────────────────────────────────────────

interface NatureBlockRowConfig {
  rowKey: string
  label: string
  isFromCrossSheet: boolean
  isEditable: boolean
  isDeductionRow: boolean
  rowType: AdjudicationRow['rowType']
}

const NATURE_BLOCK_CONFIG: NatureBlockRowConfig[] = [
  { rowKey: 'revenue', label: '预收货款', isFromCrossSheet: true, isEditable: true, isDeductionRow: false, rowType: 'detail' },
  { rowKey: 'development', label: '开发项目预收款', isFromCrossSheet: true, isEditable: true, isDeductionRow: false, rowType: 'detail' },
  { rowKey: 'engineering', label: '预收工程款', isFromCrossSheet: true, isEditable: true, isDeductionRow: false, rowType: 'detail' },
  { rowKey: 'other', label: '其他', isFromCrossSheet: true, isEditable: true, isDeductionRow: false, rowType: 'detail' },
  { rowKey: 'nature-subtotal', label: '小计', isFromCrossSheet: false, isEditable: false, isDeductionRow: false, rowType: 'subtotal' },
  { rowKey: 'non-current-deduction', label: '减：计入其他非流动负债的合同负债', isFromCrossSheet: false, isEditable: true, isDeductionRow: true, rowType: 'deduction' },
  { rowKey: 'contract-liability-total', label: '合同负债合计', isFromCrossSheet: false, isEditable: false, isDeductionRow: false, rowType: 'total' },
]

interface AgingBlockRowConfig {
  rowKey: string
  label: string
  isFromCrossSheet: boolean
  isEditable: boolean
  rowType: AdjudicationRow['rowType']
}

const AGING_BLOCK_CONFIG: AgingBlockRowConfig[] = [
  { rowKey: 'within-1-year', label: '1年以内(含1年)', isFromCrossSheet: true, isEditable: true, rowType: 'detail' },
  { rowKey: '1-to-2-years', label: '1至2年(含2年)', isFromCrossSheet: true, isEditable: true, rowType: 'detail' },
  { rowKey: '2-to-3-years', label: '2至3年(含3年)', isFromCrossSheet: true, isEditable: true, rowType: 'detail' },
  { rowKey: 'over-3-years', label: '3年以上', isFromCrossSheet: true, isEditable: true, rowType: 'detail' },
  { rowKey: 'aging-total', label: '合计', isFromCrossSheet: false, isEditable: false, rowType: 'subtotal' },
  { rowKey: 'trial-balance', label: '试算平衡表数', isFromCrossSheet: false, isEditable: false, rowType: 'tb' },
  { rowKey: 'difference', label: '差异数', isFromCrossSheet: false, isEditable: false, rowType: 'diff' },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getNumFromResponse(map: Map<string, ChecklistResponse>, itemId: string): number {
  return parseNum(map.get(itemId)?.remark)
}

function buildRow(params: {
  rowKey: string; label: string
  priorUnadjusted: number; priorAje: number; priorRje: number
  currentUnadjusted: number; currentAje: number; currentRje: number
  reasonAnalysis: string; isFromCrossSheet: boolean; isEditable: boolean
  isDeductionRow: boolean; rowType: AdjudicationRow['rowType']
}): AdjudicationRow {
  const priorAudited = calcAuditedAmount(params.priorUnadjusted, params.priorAje, params.priorRje)
  const currentAudited = calcAuditedAmount(params.currentUnadjusted, params.currentAje, params.currentRje)
  return {
    ...params,
    priorAudited,
    currentAudited,
    changeAmount: calcChangeAmount(priorAudited, currentAudited),
    changeRate: calcChangeRate(priorAudited, currentAudited),
  }
}

// ─── Cross Sheet → Row Key Mapping ──────────────────────────────────────────

const NATURE_KEY_MAP: Record<string, string> = {
  revenue: 'revenue',
  development: 'development',
  engineering: 'engineering',
  other: 'other',
}

const AGING_KEY_MAP: Record<string, string> = {
  within1Year: 'within-1-year',
  year1to2: '1-to-2-years',
  year2to3: '2-to-3-years',
  over3Years: 'over-3-years',
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD7Adjudication(options: UseD7AdjudicationOptions) {
  const { allResponses, crossSheet, saveImmediate, debouncedSave } = options

  // ─── Trial Balance ─────────────────────────────────────────────────────

  const trialBalanceAmount = computed<number>(() => {
    return getNumFromResponse(allResponses.value, 'D7-1-adj-aging-trial-balance-currentAudited')
  })

  // ─── Nature Rows ───────────────────────────────────────────────────────

  const natureRows: ComputedRef<AdjudicationRow[]> = computed(() => {
    const map = allResponses.value
    const natAgg = crossSheet.natureAggregation.value
    const adjTotals = crossSheet.adjustmentTotals.value

    const detailRows: AdjudicationRow[] = NATURE_BLOCK_CONFIG.filter(c => c.rowType === 'detail')
      .map(config => {
        const prefix = `D7-1-adj-nature-${config.rowKey}`
        const aggKey = Object.entries(NATURE_KEY_MAP).find(([, v]) => v === config.rowKey)?.[0] || ''
        const agg = (natAgg as any)[aggKey]

        return buildRow({
          rowKey: config.rowKey,
          label: config.label,
          priorUnadjusted: agg ? agg.prior : getNumFromResponse(map, `${prefix}-priorUnadjusted`),
          priorAje: getNumFromResponse(map, `${prefix}-priorAje`),
          priorRje: getNumFromResponse(map, `${prefix}-priorRje`),
          currentUnadjusted: agg ? agg.current : getNumFromResponse(map, `${prefix}-currentUnadjusted`),
          currentAje: getNumFromResponse(map, `${prefix}-currentAje`),
          currentRje: getNumFromResponse(map, `${prefix}-currentRje`),
          reasonAnalysis: map.get(`${prefix}-reasonAnalysis`)?.remark || '',
          isFromCrossSheet: config.isFromCrossSheet,
          isEditable: config.isEditable,
          isDeductionRow: config.isDeductionRow,
          rowType: config.rowType,
        })
      })

    // 小计 = SUM(detail rows)
    const subtotalRow = buildRow({
      rowKey: 'nature-subtotal',
      label: '小计',
      priorUnadjusted: calcSubtotal(detailRows.map(r => r.priorUnadjusted)),
      priorAje: calcSubtotal(detailRows.map(r => r.priorAje)),
      priorRje: calcSubtotal(detailRows.map(r => r.priorRje)),
      currentUnadjusted: calcSubtotal(detailRows.map(r => r.currentUnadjusted)),
      currentAje: calcSubtotal(detailRows.map(r => r.currentAje)),
      currentRje: calcSubtotal(detailRows.map(r => r.currentRje)),
      reasonAnalysis: '',
      isFromCrossSheet: false,
      isEditable: false,
      isDeductionRow: false,
      rowType: 'subtotal',
    })

    // 减：非流动负债扣减
    const dedPrefix = 'D7-1-adj-nature-non-current-deduction'
    const deductionRow = buildRow({
      rowKey: 'non-current-deduction',
      label: '减：计入其他非流动负债的合同负债',
      priorUnadjusted: getNumFromResponse(map, `${dedPrefix}-priorUnadjusted`),
      priorAje: getNumFromResponse(map, `${dedPrefix}-priorAje`),
      priorRje: getNumFromResponse(map, `${dedPrefix}-priorRje`),
      currentUnadjusted: getNumFromResponse(map, `${dedPrefix}-currentUnadjusted`),
      currentAje: getNumFromResponse(map, `${dedPrefix}-currentAje`),
      currentRje: getNumFromResponse(map, `${dedPrefix}-currentRje`),
      reasonAnalysis: map.get(`${dedPrefix}-reasonAnalysis`)?.remark || '',
      isFromCrossSheet: false,
      isEditable: true,
      isDeductionRow: true,
      rowType: 'deduction',
    })

    // 合同负债合计 = 小计 - 扣减
    const totalRow = buildRow({
      rowKey: 'contract-liability-total',
      label: '合同负债合计',
      priorUnadjusted: calcContractLiabilityTotal(subtotalRow.priorUnadjusted, deductionRow.priorUnadjusted),
      priorAje: calcContractLiabilityTotal(subtotalRow.priorAje, deductionRow.priorAje),
      priorRje: calcContractLiabilityTotal(subtotalRow.priorRje, deductionRow.priorRje),
      currentUnadjusted: calcContractLiabilityTotal(subtotalRow.currentUnadjusted, deductionRow.currentUnadjusted),
      currentAje: calcContractLiabilityTotal(subtotalRow.currentAje, deductionRow.currentAje),
      currentRje: calcContractLiabilityTotal(subtotalRow.currentRje, deductionRow.currentRje),
      reasonAnalysis: '',
      isFromCrossSheet: false,
      isEditable: false,
      isDeductionRow: false,
      rowType: 'total',
    })

    return [...detailRows, subtotalRow, deductionRow, totalRow]
  })

  // ─── Aging Rows ────────────────────────────────────────────────────────

  const agingRows: ComputedRef<AdjudicationRow[]> = computed(() => {
    const map = allResponses.value
    const agingAgg = crossSheet.agingAggregation.value

    const detailRows: AdjudicationRow[] = AGING_BLOCK_CONFIG.filter(c => c.rowType === 'detail')
      .map(config => {
        const prefix = `D7-1-adj-aging-${config.rowKey}`
        const aggKey = Object.entries(AGING_KEY_MAP).find(([, v]) => v === config.rowKey)?.[0] || ''
        const agg = (agingAgg as any)[aggKey]

        return buildRow({
          rowKey: config.rowKey,
          label: config.label,
          priorUnadjusted: agg ? agg.prior : getNumFromResponse(map, `${prefix}-priorUnadjusted`),
          priorAje: getNumFromResponse(map, `${prefix}-priorAje`),
          priorRje: getNumFromResponse(map, `${prefix}-priorRje`),
          currentUnadjusted: agg ? agg.current : getNumFromResponse(map, `${prefix}-currentUnadjusted`),
          currentAje: getNumFromResponse(map, `${prefix}-currentAje`),
          currentRje: getNumFromResponse(map, `${prefix}-currentRje`),
          reasonAnalysis: map.get(`${prefix}-reasonAnalysis`)?.remark || '',
          isFromCrossSheet: config.isFromCrossSheet,
          isEditable: config.isEditable,
          isDeductionRow: false,
          rowType: config.rowType,
        })
      })

    // 合计 = SUM(4段)
    const agingTotalRow = buildRow({
      rowKey: 'aging-total',
      label: '合计',
      priorUnadjusted: calcSubtotal(detailRows.map(r => r.priorUnadjusted)),
      priorAje: calcSubtotal(detailRows.map(r => r.priorAje)),
      priorRje: calcSubtotal(detailRows.map(r => r.priorRje)),
      currentUnadjusted: calcSubtotal(detailRows.map(r => r.currentUnadjusted)),
      currentAje: calcSubtotal(detailRows.map(r => r.currentAje)),
      currentRje: calcSubtotal(detailRows.map(r => r.currentRje)),
      reasonAnalysis: '',
      isFromCrossSheet: false,
      isEditable: false,
      isDeductionRow: false,
      rowType: 'subtotal',
    })

    // 试算平衡表数
    const tbRow: AdjudicationRow = {
      rowKey: 'trial-balance',
      label: '试算平衡表数',
      priorUnadjusted: 0, priorAje: 0, priorRje: 0,
      priorAudited: getNumFromResponse(map, 'D7-1-adj-aging-trial-balance-priorAudited'),
      currentUnadjusted: 0, currentAje: 0, currentRje: 0,
      currentAudited: getNumFromResponse(map, 'D7-1-adj-aging-trial-balance-currentAudited'),
      changeAmount: 0, changeRate: '', reasonAnalysis: '',
      isFromCrossSheet: false, isEditable: false, isDeductionRow: false, rowType: 'tb',
    }

    // 差异 = 合计 - 试算平衡表数
    const diffRow: AdjudicationRow = {
      rowKey: 'difference',
      label: '差异数',
      priorUnadjusted: 0, priorAje: 0, priorRje: 0,
      priorAudited: agingTotalRow.priorAudited - tbRow.priorAudited,
      currentUnadjusted: 0, currentAje: 0, currentRje: 0,
      currentAudited: agingTotalRow.currentAudited - tbRow.currentAudited,
      changeAmount: 0, changeRate: '', reasonAnalysis: '',
      isFromCrossSheet: false, isEditable: false, isDeductionRow: false, rowType: 'diff',
    }

    return [...detailRows, agingTotalRow, tbRow, diffRow]
  })

  // ─── Trial Balance Diff ────────────────────────────────────────────────

  const trialBalanceDiff: ComputedRef<number> = computed(() => {
    const agingTotalRow = agingRows.value.find(r => r.rowKey === 'aging-total')
    return (agingTotalRow?.currentAudited ?? 0) - trialBalanceAmount.value
  })

  // ─── Cross Validation Warning ──────────────────────────────────────────

  const crossValidationWarning: ComputedRef<string | null> = computed(() => {
    const cv = crossSheet.crossValidation.value
    if (cv.isConsistent) return null
    return `按性质分类合计与按账龄分类合计不一致，差额：${cv.diff.toFixed(2)}元`
  })

  // ─── Audit Notes ───────────────────────────────────────────────────────

  const auditNotes = ref<{ explanation: string; conclusion: string; agingExplanation: string }>({
    explanation: '',
    conclusion: '',
    agingExplanation: '',
  })

  watch(allResponses, (map) => {
    auditNotes.value.explanation = map.get('D7-1-note-explanation')?.remark || ''
    auditNotes.value.conclusion = map.get('D7-1-note-conclusion')?.remark || ''
    auditNotes.value.agingExplanation = map.get('D7-1-note-aging-explanation')?.remark || ''
  }, { immediate: true })

  watch(() => auditNotes.value.explanation, (v) => debouncedSave('D7-1-note-explanation', { remark: v }))
  watch(() => auditNotes.value.conclusion, (v) => debouncedSave('D7-1-note-conclusion', { remark: v }))
  watch(() => auditNotes.value.agingExplanation, (v) => debouncedSave('D7-1-note-aging-explanation', { remark: v }))

  // ─── updateCell ────────────────────────────────────────────────────────

  function updateCell(rowKey: string, field: string, value: number | string): void {
    // Determine block (nature vs aging)
    const isNature = NATURE_BLOCK_CONFIG.some(c => c.rowKey === rowKey)
    const block = isNature ? 'nature' : 'aging'
    const itemId = `D7-1-adj-${block}-${rowKey}-${field}`
    const remarkValue = typeof value === 'number' ? String(value) : value

    const map = allResponses.value
    map.set(itemId, { item_id: itemId, conclusion: null, remark: remarkValue })
    allResponses.value = new Map(map)

    debouncedSave(itemId, { remark: remarkValue })
  }

  // ─── publishAdjudicated ────────────────────────────────────────────────

  function publishAdjudicated(): void {
    const totalRow = natureRows.value.find(r => r.rowKey === 'contract-liability-total')
    if (!totalRow) return
    try {
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
        detail: { wpCode: 'D7', accountCode: '2205', auditedAmount: totalRow.currentAudited },
      }))
    } catch { /* EventBus failure non-blocking */ }
  }

  // ─── onAdjustmentCreated ───────────────────────────────────────────────

  function onAdjustmentCreated(payload: any): void {
    if (!payload || payload.wpCode !== 'D7') return
    const { entryType, amount } = payload
    if (!entryType || !amount) return

    // Apply to nature block subtotal level AJE/RJE
    const field = entryType === 'AJE' ? 'currentAje' : 'currentRje'
    // Accumulate to the 'other' row for simplicity (user can redistribute)
    const itemId = `D7-1-adj-nature-other-${field}`
    const map = allResponses.value
    const currentVal = getNumFromResponse(map, itemId)
    const newVal = currentVal + parseNum(amount)
    updateCell('other', field, newVal)
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    natureRows,
    agingRows,
    trialBalanceAmount,
    trialBalanceDiff,
    crossValidationWarning,
    auditNotes,
    updateCell,
    publishAdjudicated,
    onAdjustmentCreated,
  }
}

export default useD7Adjudication
