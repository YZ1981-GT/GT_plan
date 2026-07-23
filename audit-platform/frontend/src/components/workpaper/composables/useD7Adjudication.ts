/**
 * useD7Adjudication — D7-1 审定表（双区块：按性质+按账龄，含扣减行）
 *
 * 双区块结构：
 *   一、按性质分类（固定 4 行）：预收货款/开发项目预收款/预收工程款/其他/小计/减：非流动负债/合同负债合计
 *   二、按账龄分类（按项目账龄配置段动态生成）：各段明细行/合计/试算平衡表数/差异数
 *
 * 公式关系：
 *   - 审定数 = 未审 + AJE + RJE（AJE/RJE 纯 computed 从 crossSheet.adjustmentTotals 双分组派生）
 *   - 小计 = SUM(明细行)；合同负债合计 = 小计 - 非流动负债扣减
 *   - 账龄合计 = SUM(各段)；差异 = 账龄合计 - 试算平衡表数
 *   - 交叉验证：性质区块调整合计 === 账龄区块调整合计；两区块合计不相加计入总额
 *
 * Spec: .kiro/specs/d7-contract-liabilities-enhancement/
 * Task: 6
 * Requirements: 3.1-3.5, 10.3, 10.4, 10.5, 10.6, 11.1, 11.2
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAuditedAmount,
  calcChangeAmount,
  calcChangeRate,
  calcSubtotal,
  calcContractLiabilityTotal,
} from './useD7FormulaEngine'
import { eventBus } from '@/utils/eventBus'
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
  /** TB 预填种子（科目2205期末审定数，来自后端 project_context.tb_amount）；仅在用户未手工保存试算平衡表数时回退使用 */
  tbSeedAmount?: Ref<number>
  isReadonly?: Ref<boolean>
}

// ─── Block Configuration ─────────────────────────────────────────────────────

interface NatureBlockRowConfig {
  rowKey: string
  label: string
  natureKey: 'revenue' | 'development' | 'engineering' | 'other' | ''
  isFromCrossSheet: boolean
  isEditable: boolean
  isDeductionRow: boolean
  rowType: AdjudicationRow['rowType']
}

const NATURE_BLOCK_CONFIG: NatureBlockRowConfig[] = [
  { rowKey: 'revenue', label: '预收货款', natureKey: 'revenue', isFromCrossSheet: true, isEditable: true, isDeductionRow: false, rowType: 'detail' },
  { rowKey: 'development', label: '开发项目预收款', natureKey: 'development', isFromCrossSheet: true, isEditable: true, isDeductionRow: false, rowType: 'detail' },
  { rowKey: 'engineering', label: '预收工程款', natureKey: 'engineering', isFromCrossSheet: true, isEditable: true, isDeductionRow: false, rowType: 'detail' },
  { rowKey: 'other', label: '其他', natureKey: 'other', isFromCrossSheet: true, isEditable: true, isDeductionRow: false, rowType: 'detail' },
]

/**
 * 默认 THREE_YEAR 账龄段 key → 旧 rowKey 映射。
 *
 * 账龄区块改为按项目账龄配置段动态生成后，对默认 THREE_YEAR 段沿用旧 rowKey，
 * 以保留既有项目已保存的手工数据（item_id `D7-1-adj-aging-{rowKey}-{field}`）不被孤立；
 * 自定义段则直接用段 key。
 */
const LEGACY_AGING_ROWKEY: Record<string, string> = {
  within1: 'within-1-year',
  y1to2: '1-to-2-years',
  y2to3: '2-to-3-years',
  over3: 'over-3-years',
}

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

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD7Adjudication(options: UseD7AdjudicationOptions) {
  const { allResponses, crossSheet, debouncedSave, tbSeedAmount } = options
  const isReadonly = options.isReadonly ?? ref(false)

  // ─── Trial Balance ─────────────────────────────────────────────────────

  function resolveTbCurrentAudited(): number {
    const saved = allResponses.value.get('D7-1-adj-aging-trial-balance-currentAudited')?.remark
    if (saved != null && String(saved).trim() !== '') return parseNum(saved)
    return tbSeedAmount?.value ?? 0
  }

  const trialBalanceAmount = computed<number>(() => resolveTbCurrentAudited())

  // ─── Nature Rows ───────────────────────────────────────────────────────

  const natureRows: ComputedRef<AdjudicationRow[]> = computed(() => {
    const map = allResponses.value
    const natAgg = crossSheet.natureAggregation.value
    const adjByNature = crossSheet.adjustmentTotals.value.byNature

    const detailRows: AdjudicationRow[] = NATURE_BLOCK_CONFIG
      .map(config => {
        const prefix = `D7-1-adj-nature-${config.rowKey}`
        const agg = config.natureKey ? (natAgg as any)[config.natureKey] : null
        // 调整数（AJE/RJE）纯 computed 从按性质分组的 adjustmentTotals 派生（Req 10.3, 11.2）
        const adj = config.natureKey ? adjByNature[config.natureKey] : { aje: 0, rje: 0 }

        return buildRow({
          rowKey: config.rowKey,
          label: config.label,
          priorUnadjusted: agg ? agg.prior : getNumFromResponse(map, `${prefix}-priorUnadjusted`),
          priorAje: getNumFromResponse(map, `${prefix}-priorAje`),
          priorRje: getNumFromResponse(map, `${prefix}-priorRje`),
          currentUnadjusted: agg ? agg.current : getNumFromResponse(map, `${prefix}-currentUnadjusted`),
          currentAje: adj.aje,
          currentRje: adj.rje,
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

  // ─── Aging Rows（按项目账龄配置段动态生成） ────────────────────────────

  const agingRows: ComputedRef<AdjudicationRow[]> = computed(() => {
    const map = allResponses.value
    const agingByKey = crossSheet.agingByKey.value
    const adjByAging = crossSheet.adjustmentTotals.value.byAging
    const agingSegs = crossSheet.agingSegments.value

    const detailRows: AdjudicationRow[] = agingSegs.map(seg => {
      const rowKey = LEGACY_AGING_ROWKEY[seg.key] ?? seg.key
      const prefix = `D7-1-adj-aging-${rowKey}`
      const crossCurrent = agingByKey.current[seg.key] ?? 0
      const crossPrior = agingByKey.prior[seg.key] ?? 0
      // 调整数纯 computed 从按账龄分组的 adjustmentTotals 派生（Req 10.4, 11.2）
      const adj = adjByAging[seg.key] ?? { aje: 0, rje: 0 }
      const isFromCrossSheet = crossCurrent !== 0 || crossPrior !== 0

      return buildRow({
        rowKey,
        label: seg.label,
        priorUnadjusted: isFromCrossSheet ? crossPrior : getNumFromResponse(map, `${prefix}-priorUnadjusted`),
        priorAje: getNumFromResponse(map, `${prefix}-priorAje`),
        priorRje: getNumFromResponse(map, `${prefix}-priorRje`),
        currentUnadjusted: isFromCrossSheet ? crossCurrent : getNumFromResponse(map, `${prefix}-currentUnadjusted`),
        currentAje: adj.aje,
        currentRje: adj.rje,
        reasonAnalysis: map.get(`${prefix}-reasonAnalysis`)?.remark || '',
        isFromCrossSheet: true,
        isEditable: true,
        isDeductionRow: false,
        rowType: 'detail',
      })
    })

    // 合计 = SUM(各段)
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

    // 试算平衡表数（期末回退到 project_context.tb_amount 种子）
    const tbRow: AdjudicationRow = {
      rowKey: 'trial-balance',
      label: '试算平衡表数',
      priorUnadjusted: 0, priorAje: 0, priorRje: 0,
      priorAudited: getNumFromResponse(map, 'D7-1-adj-aging-trial-balance-priorAudited'),
      currentUnadjusted: 0, currentAje: 0, currentRje: 0,
      currentAudited: resolveTbCurrentAudited(),
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
    if (isReadonly.value) return
    // Determine block (nature vs aging): nature rowKeys 为固定 4 类 + 扣减
    const isNature = NATURE_BLOCK_CONFIG.some(c => c.rowKey === rowKey)
      || rowKey === 'non-current-deduction'
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
      eventBus.emit('substantive:adjudicated', {
        wpCode: 'D7',
        accountCode: '2205',
        auditedAmount: totalRow.currentAudited,
        adjudicatedAmount: totalRow.currentAudited,
        timestamp: Date.now(),
      })
    } catch { /* EventBus failure non-blocking */ }
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
  }
}

export default useD7Adjudication
