/**
 * useD6Adjudication — D6 合同资产审定表D6-1（三区块177公式）
 *
 * 三区块固定结构：
 *   一、合同资产原值（dynamic rows from D6-2 aggregation + subtotal + deduction + 原值小计）
 *   二、合同资产坏账准备（dynamic rows from D6-3 aggregation + subtotal + deduction + 坏账小计）
 *   三、合同资产净值（net value = block1 - block2, row-by-row + TB number + difference）
 *
 * 公式关系：
 *   - 审定数 = 未审 + AJE + RJE
 *   - 小计 = SUM(动态行)
 *   - XX小计 = 小计 - 非流动扣减
 *   - 区块三净值行 = 区块一对应行 - 区块二对应行（跨区块联动 via rowKey）
 *   - 变动额 = 期末审定 - 期初审定
 *   - 变动率: prior=0&&current=0→''; prior=0→'N/A'; else→(current-prior)/prior
 *   - 差异 = 净值合计 - 试算平衡表数
 *
 * Spec: .kiro/specs/d6-contract-assets/
 * Task: 6.1
 * Requirements: 2.1-2.10, 3.1-3.8, 4.1-4.7, 26.1-26.6
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import {
  parseNum,
  calcAuditedAmount,
  calcSubtotal,
  calcBlockTotal,
  calcNetValue,
  calcChangeAmount,
  calcChangeRate,
} from './useD6FormulaEngine'
import type { ChecklistResponse } from './useD6FormData'
import type useD6CrossSheet from './useD6CrossSheet'

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
  isDeduction: boolean
  rowType: 'dynamic' | 'subtotal' | 'deduction' | 'block_total' | 'tb' | 'diff'
}

export interface AdjudicationBlock {
  blockKey: 'block1' | 'block2' | 'block3'
  blockTitle: string
  rows: AdjudicationRow[]
  subtotalRow: AdjudicationRow
  deductionRow: AdjudicationRow
  blockTotalRow: AdjudicationRow
}

export interface UseD6AdjudicationOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  crossSheet: ReturnType<typeof useD6CrossSheet>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId: Ref<string>
  projectId: Ref<string>
}

// ─── Block Configuration ─────────────────────────────────────────────────────

interface BlockConfig {
  blockKey: 'block1' | 'block2' | 'block3'
  blockTitle: string
  subtotalLabel: string
  deductionLabel: string
  totalLabel: string
}

const BLOCK_CONFIGS: BlockConfig[] = [
  {
    blockKey: 'block1',
    blockTitle: '一、合同资产原值',
    subtotalLabel: '小计',
    deductionLabel: '减：列示于其他非流动资产的合同资产',
    totalLabel: '合同资产原值小计',
  },
  {
    blockKey: 'block2',
    blockTitle: '二、合同资产坏账准备',
    subtotalLabel: '小计',
    deductionLabel: '减：列示于其他非流动资产的合同资产坏账准备',
    totalLabel: '合同资产坏账准备小计',
  },
  {
    blockKey: 'block3',
    blockTitle: '三、合同资产净值',
    subtotalLabel: '小计',
    deductionLabel: '减：列示于其他非流动资产的合同资产净值',
    totalLabel: '合同资产净值合计',
  },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 生成简易唯一ID */
function generateRowId(): string {
  return `adj-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

/** 从 allResponses 读取指定 item_id 的 remark 数值 */
function getNumFromResponse(map: Map<string, ChecklistResponse>, itemId: string): number {
  return parseNum(map.get(itemId)?.remark)
}

/** 从 allResponses 读取指定 item_id 的 remark 字符串 */
function getStrFromResponse(map: Map<string, ChecklistResponse>, itemId: string): string {
  return map.get(itemId)?.remark ?? ''
}

/** 构建完整行对象（含公式计算） */
function buildRow(params: {
  rowKey: string
  label: string
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  currentUnadjusted: number
  currentAje: number
  currentRje: number
  reasonAnalysis: string
  isFromCrossSheet: boolean
  isEditable: boolean
  isDeduction: boolean
  rowType: AdjudicationRow['rowType']
}): AdjudicationRow {
  const priorAudited = calcAuditedAmount(params.priorUnadjusted, params.priorAje, params.priorRje)
  const currentAudited = calcAuditedAmount(params.currentUnadjusted, params.currentAje, params.currentRje)
  const changeAmount = calcChangeAmount(priorAudited, currentAudited)
  const changeRate = calcChangeRate(priorAudited, currentAudited)

  return {
    rowKey: params.rowKey,
    label: params.label,
    priorUnadjusted: params.priorUnadjusted,
    priorAje: params.priorAje,
    priorRje: params.priorRje,
    priorAudited,
    currentUnadjusted: params.currentUnadjusted,
    currentAje: params.currentAje,
    currentRje: params.currentRje,
    currentAudited,
    changeAmount,
    changeRate,
    reasonAnalysis: params.reasonAnalysis,
    isFromCrossSheet: params.isFromCrossSheet,
    isEditable: params.isEditable,
    isDeduction: params.isDeduction,
    rowType: params.rowType,
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD6Adjudication(options: UseD6AdjudicationOptions) {
  const { allResponses, crossSheet, saveImmediate, debouncedSave, wpId, projectId } = options

  // ─── Audit Notes ───────────────────────────────────────────────────────────

  const auditNotes = ref<{
    explanation: string
    impairmentEval: string
    longTermReason: string
    conclusion: string
  }>({
    explanation: '',
    impairmentEval: '',
    longTermReason: '',
    conclusion: '',
  })

  // Load audit notes from allResponses
  function _loadAuditNotes(): void {
    const map = allResponses.value
    auditNotes.value = {
      explanation: getStrFromResponse(map, 'D6-1-note-explanation'),
      impairmentEval: getStrFromResponse(map, 'D6-1-note-impairmentEval'),
      longTermReason: getStrFromResponse(map, 'D6-1-note-longTermReason'),
      conclusion: getStrFromResponse(map, 'D6-1-note-conclusion'),
    }
  }

  // Watch allResponses to reload notes
  watch(allResponses, _loadAuditNotes, { immediate: true })

  // Watch auditNotes for changes → debouncedSave
  watch(auditNotes, (notes) => {
    debouncedSave('D6-1-note-explanation', { remark: notes.explanation })
    debouncedSave('D6-1-note-impairmentEval', { remark: notes.impairmentEval })
    debouncedSave('D6-1-note-longTermReason', { remark: notes.longTermReason })
    debouncedSave('D6-1-note-conclusion', { remark: notes.conclusion })
  }, { deep: true })

  // ─── Trial Balance ─────────────────────────────────────────────────────────

  const trialBalanceAmount = ref<number>(0)

  // Load TB amount from allResponses (auto_data or manual)
  watch(allResponses, (map) => {
    trialBalanceAmount.value = getNumFromResponse(map, 'D6-1-tb-amount')
  }, { immediate: true })

  // ─── Dynamic Row Keys Tracking ─────────────────────────────────────────────

  /**
   * Track dynamic row keys per block (block1/block2 only; block3 is derived).
   * Loaded from allResponses, persisted via D6-1-adj-{blockKey}-rowKeys.
   */
  const block1RowKeys = ref<string[]>([])
  const block2RowKeys = ref<string[]>([])

  function _loadRowKeys(): void {
    const map = allResponses.value
    const b1Keys = getStrFromResponse(map, 'D6-1-adj-block1-rowKeys')
    const b2Keys = getStrFromResponse(map, 'D6-1-adj-block2-rowKeys')
    block1RowKeys.value = b1Keys ? safeParseArray(b1Keys) : []
    block2RowKeys.value = b2Keys ? safeParseArray(b2Keys) : []
  }

  function safeParseArray(str: string): string[] {
    try {
      const parsed = JSON.parse(str)
      return Array.isArray(parsed) ? parsed : []
    } catch { return [] }
  }

  watch(allResponses, _loadRowKeys, { immediate: true })

  // ─── Block Building Logic ──────────────────────────────────────────────────

  /** Build a dynamic row from stored responses */
  function _buildDynamicRow(
    blockKey: string,
    rowKey: string,
    label: string,
    isFromCrossSheet: boolean,
  ): AdjudicationRow {
    const map = allResponses.value
    const prefix = `D6-1-adj-${blockKey}-${rowKey}`

    return buildRow({
      rowKey,
      label,
      priorUnadjusted: getNumFromResponse(map, `${prefix}-priorUnadjusted`),
      priorAje: getNumFromResponse(map, `${prefix}-priorAje`),
      priorRje: getNumFromResponse(map, `${prefix}-priorRje`),
      currentUnadjusted: getNumFromResponse(map, `${prefix}-currentUnadjusted`),
      currentAje: getNumFromResponse(map, `${prefix}-currentAje`),
      currentRje: getNumFromResponse(map, `${prefix}-currentRje`),
      reasonAnalysis: getStrFromResponse(map, `${prefix}-reasonAnalysis`),
      isFromCrossSheet,
      isEditable: true,
      isDeduction: false,
      rowType: 'dynamic',
    })
  }

  /** Build deduction row */
  function _buildDeductionRow(blockKey: string, label: string): AdjudicationRow {
    const map = allResponses.value
    const prefix = `D6-1-adj-${blockKey}-deduction`

    return buildRow({
      rowKey: 'deduction',
      label,
      priorUnadjusted: getNumFromResponse(map, `${prefix}-priorUnadjusted`),
      priorAje: getNumFromResponse(map, `${prefix}-priorAje`),
      priorRje: getNumFromResponse(map, `${prefix}-priorRje`),
      currentUnadjusted: getNumFromResponse(map, `${prefix}-currentUnadjusted`),
      currentAje: getNumFromResponse(map, `${prefix}-currentAje`),
      currentRje: getNumFromResponse(map, `${prefix}-currentRje`),
      reasonAnalysis: getStrFromResponse(map, `${prefix}-reasonAnalysis`),
      isFromCrossSheet: false,
      isEditable: true,
      isDeduction: true,
      rowType: 'deduction',
    })
  }

  /** Build subtotal row from dynamic rows */
  function _buildSubtotalRow(dynamicRows: AdjudicationRow[], label: string): AdjudicationRow {
    const priorUnadjusted = calcSubtotal(dynamicRows.map(r => r.priorUnadjusted))
    const priorAje = calcSubtotal(dynamicRows.map(r => r.priorAje))
    const priorRje = calcSubtotal(dynamicRows.map(r => r.priorRje))
    const currentUnadjusted = calcSubtotal(dynamicRows.map(r => r.currentUnadjusted))
    const currentAje = calcSubtotal(dynamicRows.map(r => r.currentAje))
    const currentRje = calcSubtotal(dynamicRows.map(r => r.currentRje))

    return buildRow({
      rowKey: 'subtotal',
      label,
      priorUnadjusted, priorAje, priorRje,
      currentUnadjusted, currentAje, currentRje,
      reasonAnalysis: '',
      isFromCrossSheet: false,
      isEditable: false,
      isDeduction: false,
      rowType: 'subtotal',
    })
  }

  /** Build block total row = subtotal - deduction */
  function _buildBlockTotalRow(
    subtotalRow: AdjudicationRow,
    deductionRow: AdjudicationRow,
    label: string,
  ): AdjudicationRow {
    return buildRow({
      rowKey: 'blockTotal',
      label,
      priorUnadjusted: calcBlockTotal(subtotalRow.priorUnadjusted, deductionRow.priorUnadjusted),
      priorAje: calcBlockTotal(subtotalRow.priorAje, deductionRow.priorAje),
      priorRje: calcBlockTotal(subtotalRow.priorRje, deductionRow.priorRje),
      currentUnadjusted: calcBlockTotal(subtotalRow.currentUnadjusted, deductionRow.currentUnadjusted),
      currentAje: calcBlockTotal(subtotalRow.currentAje, deductionRow.currentAje),
      currentRje: calcBlockTotal(subtotalRow.currentRje, deductionRow.currentRje),
      reasonAnalysis: '',
      isFromCrossSheet: false,
      isEditable: false,
      isDeduction: false,
      rowType: 'block_total',
    })
  }

  // ─── Block1: 合同资产原值 ──────────────────────────────────────────────────

  function _buildBlock1(): AdjudicationBlock {
    const config = BLOCK_CONFIGS[0]
    const origAgg = crossSheet.originalValueAggregation.value

    // Dynamic rows: from crossSheet aggregation + stored row keys
    const dynamicRowKeys = block1RowKeys.value.length > 0
      ? block1RowKeys.value
      : Object.keys(origAgg)

    // Sync row keys if crossSheet has new categories
    const allCategories = new Set([...dynamicRowKeys, ...Object.keys(origAgg)])
    const mergedKeys = Array.from(allCategories)

    const dynamicRows: AdjudicationRow[] = mergedKeys.map(key => {
      const row = _buildDynamicRow('block1', key, key, !!origAgg[key])
      // Override with crossSheet aggregation values if available (期初审定/期末审定)
      if (origAgg[key]) {
        const map = allResponses.value
        const prefix = `D6-1-adj-block1-${key}`
        // Only override currentUnadjusted from crossSheet if no manual override
        const hasManualCurrent = map.has(`${prefix}-currentUnadjusted`)
        if (!hasManualCurrent) {
          return buildRow({
            ...row,
            priorUnadjusted: origAgg[key].prior,
            currentUnadjusted: origAgg[key].current,
            priorAje: row.priorAje,
            priorRje: row.priorRje,
            currentAje: row.currentAje,
            currentRje: row.currentRje,
            reasonAnalysis: row.reasonAnalysis,
            isFromCrossSheet: true,
            isEditable: true,
            isDeduction: false,
            rowType: 'dynamic',
          })
        }
      }
      return row
    })

    const subtotalRow = _buildSubtotalRow(dynamicRows, config.subtotalLabel)
    const deductionRow = _buildDeductionRow('block1', config.deductionLabel)
    const blockTotalRow = _buildBlockTotalRow(subtotalRow, deductionRow, config.totalLabel)

    return {
      blockKey: config.blockKey,
      blockTitle: config.blockTitle,
      rows: dynamicRows,
      subtotalRow,
      deductionRow,
      blockTotalRow,
    }
  }

  // ─── Block2: 合同资产坏账准备 ─────────────────────────────────────────────

  function _buildBlock2(): AdjudicationBlock {
    const config = BLOCK_CONFIGS[1]
    const impAgg = crossSheet.impairmentAggregation.value

    const dynamicRowKeys = block2RowKeys.value.length > 0
      ? block2RowKeys.value
      : Object.keys(impAgg)

    const allCategories = new Set([...dynamicRowKeys, ...Object.keys(impAgg)])
    const mergedKeys = Array.from(allCategories)

    const dynamicRows: AdjudicationRow[] = mergedKeys.map(key => {
      const row = _buildDynamicRow('block2', key, key, !!impAgg[key])
      if (impAgg[key]) {
        const map = allResponses.value
        const prefix = `D6-1-adj-block2-${key}`
        const hasManualCurrent = map.has(`${prefix}-currentUnadjusted`)
        if (!hasManualCurrent) {
          return buildRow({
            ...row,
            priorUnadjusted: impAgg[key].prior,
            currentUnadjusted: impAgg[key].current,
            priorAje: row.priorAje,
            priorRje: row.priorRje,
            currentAje: row.currentAje,
            currentRje: row.currentRje,
            reasonAnalysis: row.reasonAnalysis,
            isFromCrossSheet: true,
            isEditable: true,
            isDeduction: false,
            rowType: 'dynamic',
          })
        }
      }
      return row
    })

    const subtotalRow = _buildSubtotalRow(dynamicRows, config.subtotalLabel)
    const deductionRow = _buildDeductionRow('block2', config.deductionLabel)
    const blockTotalRow = _buildBlockTotalRow(subtotalRow, deductionRow, config.totalLabel)

    return {
      blockKey: config.blockKey,
      blockTitle: config.blockTitle,
      rows: dynamicRows,
      subtotalRow,
      deductionRow,
      blockTotalRow,
    }
  }

  // ─── Block3: 合同资产净值 (computed = block1 - block2) ────────────────────

  function _buildBlock3(block1: AdjudicationBlock, block2: AdjudicationBlock): AdjudicationBlock {
    const config = BLOCK_CONFIGS[2]

    // Dynamic rows: net value = block1 row - block2 row (rowKey alignment)
    const allRowKeys = new Set([
      ...block1.rows.map(r => r.rowKey),
      ...block2.rows.map(r => r.rowKey),
    ])

    const dynamicRows: AdjudicationRow[] = Array.from(allRowKeys).map(rowKey => {
      const b1Row = block1.rows.find(r => r.rowKey === rowKey)
      const b2Row = block2.rows.find(r => r.rowKey === rowKey)

      return buildRow({
        rowKey,
        label: rowKey,
        priorUnadjusted: calcNetValue(b1Row?.priorUnadjusted ?? 0, b2Row?.priorUnadjusted ?? 0),
        priorAje: calcNetValue(b1Row?.priorAje ?? 0, b2Row?.priorAje ?? 0),
        priorRje: calcNetValue(b1Row?.priorRje ?? 0, b2Row?.priorRje ?? 0),
        currentUnadjusted: calcNetValue(b1Row?.currentUnadjusted ?? 0, b2Row?.currentUnadjusted ?? 0),
        currentAje: calcNetValue(b1Row?.currentAje ?? 0, b2Row?.currentAje ?? 0),
        currentRje: calcNetValue(b1Row?.currentRje ?? 0, b2Row?.currentRje ?? 0),
        reasonAnalysis: '',
        isFromCrossSheet: true,
        isEditable: false,
        isDeduction: false,
        rowType: 'dynamic',
      })
    })

    // Subtotal = block1.subtotal - block2.subtotal
    const subtotalRow = buildRow({
      rowKey: 'subtotal',
      label: config.subtotalLabel,
      priorUnadjusted: calcNetValue(block1.subtotalRow.priorUnadjusted, block2.subtotalRow.priorUnadjusted),
      priorAje: calcNetValue(block1.subtotalRow.priorAje, block2.subtotalRow.priorAje),
      priorRje: calcNetValue(block1.subtotalRow.priorRje, block2.subtotalRow.priorRje),
      currentUnadjusted: calcNetValue(block1.subtotalRow.currentUnadjusted, block2.subtotalRow.currentUnadjusted),
      currentAje: calcNetValue(block1.subtotalRow.currentAje, block2.subtotalRow.currentAje),
      currentRje: calcNetValue(block1.subtotalRow.currentRje, block2.subtotalRow.currentRje),
      reasonAnalysis: '',
      isFromCrossSheet: true,
      isEditable: false,
      isDeduction: false,
      rowType: 'subtotal',
    })

    // Deduction = block1.deduction - block2.deduction
    const deductionRow = buildRow({
      rowKey: 'deduction',
      label: config.deductionLabel,
      priorUnadjusted: calcNetValue(block1.deductionRow.priorUnadjusted, block2.deductionRow.priorUnadjusted),
      priorAje: calcNetValue(block1.deductionRow.priorAje, block2.deductionRow.priorAje),
      priorRje: calcNetValue(block1.deductionRow.priorRje, block2.deductionRow.priorRje),
      currentUnadjusted: calcNetValue(block1.deductionRow.currentUnadjusted, block2.deductionRow.currentUnadjusted),
      currentAje: calcNetValue(block1.deductionRow.currentAje, block2.deductionRow.currentAje),
      currentRje: calcNetValue(block1.deductionRow.currentRje, block2.deductionRow.currentRje),
      reasonAnalysis: '',
      isFromCrossSheet: true,
      isEditable: false,
      isDeduction: true,
      rowType: 'deduction',
    })

    // Block total = block1.blockTotal - block2.blockTotal
    const blockTotalRow = buildRow({
      rowKey: 'blockTotal',
      label: config.totalLabel,
      priorUnadjusted: calcNetValue(block1.blockTotalRow.priorUnadjusted, block2.blockTotalRow.priorUnadjusted),
      priorAje: calcNetValue(block1.blockTotalRow.priorAje, block2.blockTotalRow.priorAje),
      priorRje: calcNetValue(block1.blockTotalRow.priorRje, block2.blockTotalRow.priorRje),
      currentUnadjusted: calcNetValue(block1.blockTotalRow.currentUnadjusted, block2.blockTotalRow.currentUnadjusted),
      currentAje: calcNetValue(block1.blockTotalRow.currentAje, block2.blockTotalRow.currentAje),
      currentRje: calcNetValue(block1.blockTotalRow.currentRje, block2.blockTotalRow.currentRje),
      reasonAnalysis: '',
      isFromCrossSheet: true,
      isEditable: false,
      isDeduction: false,
      rowType: 'block_total',
    })

    return {
      blockKey: config.blockKey,
      blockTitle: config.blockTitle,
      rows: dynamicRows,
      subtotalRow,
      deductionRow,
      blockTotalRow,
    }
  }

  // ─── Blocks Computed ───────────────────────────────────────────────────────

  const blocks: ComputedRef<AdjudicationBlock[]> = computed(() => {
    const block1 = _buildBlock1()
    const block2 = _buildBlock2()
    const block3 = _buildBlock3(block1, block2)
    return [block1, block2, block3]
  })

  // ─── Trial Balance Diff ────────────────────────────────────────────────────

  const trialBalanceDiff: ComputedRef<number> = computed(() => {
    const b = blocks.value
    const block3 = b[2]
    if (!block3) return 0
    return block3.blockTotalRow.currentAudited - trialBalanceAmount.value
  })

  // ─── Net Value Validation ──────────────────────────────────────────────────

  const netValueValidation: ComputedRef<{ isValid: boolean; diff: number }> = computed(() => {
    return crossSheet.netValueValidation.value
  })

  // ─── updateCell ────────────────────────────────────────────────────────────

  function updateCell(blockKey: string, rowKey: string, field: string, value: number | string): void {
    const itemId = `D6-1-adj-${blockKey}-${rowKey}-${field}`
    const remarkValue = typeof value === 'number' ? String(value) : value

    // Update allResponses locally for immediate reactivity
    const map = allResponses.value
    const existing = map.get(itemId)
    map.set(itemId, {
      item_id: itemId,
      conclusion: existing?.conclusion ?? null,
      remark: remarkValue,
    })
    // Trigger reactivity
    allResponses.value = new Map(map)

    // Persist
    debouncedSave(itemId, { remark: remarkValue })
  }

  // ─── addDynamicRow ─────────────────────────────────────────────────────────

  function addDynamicRow(blockKey: string): void {
    if (blockKey === 'block3') return // block3 is computed, cannot add rows

    const newKey = generateRowId()
    const keysRef = blockKey === 'block1' ? block1RowKeys : block2RowKeys

    // Add to local row keys
    keysRef.value = [...keysRef.value, newKey]

    // Persist row keys
    const rowKeysItemId = `D6-1-adj-${blockKey}-rowKeys`
    saveImmediate(rowKeysItemId, { remark: JSON.stringify(keysRef.value) })
  }

  // ─── removeDynamicRow ──────────────────────────────────────────────────────

  function removeDynamicRow(blockKey: string, rowKey: string): void {
    if (blockKey === 'block3') return // block3 is computed

    const keysRef = blockKey === 'block1' ? block1RowKeys : block2RowKeys

    // Remove from local row keys
    keysRef.value = keysRef.value.filter(k => k !== rowKey)

    // Persist updated row keys
    const rowKeysItemId = `D6-1-adj-${blockKey}-rowKeys`
    saveImmediate(rowKeysItemId, { remark: JSON.stringify(keysRef.value) })

    // Clean up stored cell data for removed row
    const fieldsToClean = [
      'priorUnadjusted', 'priorAje', 'priorRje',
      'currentUnadjusted', 'currentAje', 'currentRje',
      'reasonAnalysis',
    ]
    const map = allResponses.value
    for (const field of fieldsToClean) {
      map.delete(`D6-1-adj-${blockKey}-${rowKey}-${field}`)
    }
    allResponses.value = new Map(map)
  }

  // ─── publishAdjudicated ────────────────────────────────────────────────────

  function publishAdjudicated(): void {
    const b = blocks.value
    const block3 = b[2]
    if (!block3) return

    const auditedAmount = block3.blockTotalRow.currentAudited

    try {
      eventBus.emit('substantive:adjudicated' as any, {
        wpCode: 'D6',
        accountCode: '1402',
        auditedAmount,
      })
    } catch { /* EventBus publish failure should not block */ }
  }

  // ─── onAdjustmentCreated ───────────────────────────────────────────────────

  function onAdjustmentCreated(payload: any): void {
    if (!payload || payload.wpCode !== 'D6') return

    const { entryType, amount, accountCode } = payload
    if (accountCode !== '1402') return

    // Determine which field to update based on entryType
    const field = entryType === 'AJE' ? 'currentAje' : 'currentRje'

    // Accumulate to block1 blockTotal (原值 level)
    // In practice, the user will specify which block/row to apply the adjustment to
    // For now, we apply to the overall block1 deduction row as a common pattern
    const itemId = `D6-1-adj-block1-deduction-${field}`
    const map = allResponses.value
    const currentVal = getNumFromResponse(map, itemId)
    const newVal = currentVal + parseNum(amount)

    updateCell('block1', 'deduction', field, newVal)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    blocks,
    trialBalanceAmount,
    trialBalanceDiff,
    netValueValidation,
    auditNotes,
    updateCell,
    addDynamicRow,
    removeDynamicRow,
    publishAdjudicated,
    onAdjustmentCreated,
  }
}

export default useD6Adjudication
