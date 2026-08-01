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
  /** 该行由四表库审定表预填（adjudication_prefill）自动取数，本会话内标注（Tier B / R2.1）。 */
  isFourTableSeed?: boolean
}

/**
 * 四表库审定表预填行（render 返回的 `adjudication_prefill` 元素）。
 * spec: d-cycle-four-table-extraction-formulas —— D6 仅 block1（原值）四表可填，
 * `opening_balance`/`closing_balance` 映射 block1 原值行的期初/期末未审数。
 */
export interface AdjudicationPrefillRow {
  code: string
  name: string
  opening_balance: number
  closing_balance: number
  block?: string
  source?: string
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
  /**
   * 四表库审定表预填种子（render 返回的 `adjudication_prefill`）。
   * 灰度开关关闭 / block1 已有数据时后端不下发（undefined），前端零回归。
   * spec: d-cycle-four-table-extraction-formulas (R2.1/2.2/2.3, Property 2/9/11)
   */
  adjudicationPrefill?: Ref<AdjudicationPrefillRow[] | undefined>
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
  const { allResponses, crossSheet, saveImmediate, debouncedSave, wpId, projectId, adjudicationPrefill } = options

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

  // ─── Tier B 四表库审定表预填（自动取数）─────────────────────────────────────
  // spec: d-cycle-four-table-extraction-formulas (R2.1/2.2/2.3, Property 2/9/11)
  // 本会话内被四表库预填种子创建的 block1 行键（用于「自动取数」标注，
  // 非持久化——reload 后 block1 已填、后端不再下发 prefill，标注自然消失）。
  const fourTableSeededKeys = ref<Set<string>>(new Set())
  let _prefillSeeded = false

  /**
   * 镜像后端 `_block1_has_user_data`：block1（原值）锚点是否已有用户/既有一键取数录入。
   * rowKeys 清单非空，或任一 per-field 期初/期末未审非空 → 视为已填（手工优先）。
   */
  function _block1HasUserData(): boolean {
    const map = allResponses.value
    const rowKeysStr = getStrFromResponse(map, 'D6-1-adj-block1-rowKeys')
    if (rowKeysStr && safeParseArray(rowKeysStr).length > 0) return true
    for (const [itemId, val] of map.entries()) {
      if (!itemId.startsWith('D6-1-adj-block1-')) continue
      if (itemId === 'D6-1-adj-block1-rowKeys') continue
      if (itemId.endsWith('-priorUnadjusted') || itemId.endsWith('-currentUnadjusted')) {
        if ((val?.remark ?? '').trim()) return true
      }
    }
    return false
  }

  /**
   * 消费 `adjudication_prefill`：block1 原值无持久化行/值、且无 D6-2 明细聚合时，
   * 从四表库叶子子科目建行、seed 期初/期末未审（priorUnadjusted=期初余额，
   * currentUnadjusted=期末余额），标注自动取数（isFourTableSeed）。
   *
   * 手工优先（Property 2）：block1 已有用户/一键取数（`_block1HasUserData`）
   * 或既有明细导入聚合（`crossSheet.originalValueAggregation` 非空）时不 seed，不覆盖。
   * seed 走正常保存路径持久化（rowKeys 用 saveImmediate、字段用 debouncedSave，
   * 与 addDynamicRow/updateCell 一致），编辑后即成普通值；后续 render 见 block1 已填
   * 不再下发 prefill，故不会重复 seed。整个过程仅执行一次（`_prefillSeeded` 守卫）。
   */
  function _maybeSeedFromPrefill(): void {
    if (_prefillSeeded) return
    const prefill = adjudicationPrefill?.value
    if (!prefill || prefill.length === 0) return

    // 手工优先：block1 已有持久化行/值（后端通常也已省略 prefill）
    if (_block1HasUserData()) { _prefillSeeded = true; return }
    // 既有明细导入优先：D6-2 明细已聚合出原值行 → 视为已填，不 seed（R2.3）
    if (Object.keys(crossSheet.originalValueAggregation.value).length > 0) {
      _prefillSeeded = true
      return
    }

    const block1Prefill = prefill.filter(r => (r.block ?? 'block1') === 'block1')
    if (block1Prefill.length === 0) { _prefillSeeded = true; return }

    const map = allResponses.value
    const newKeys: string[] = []
    const seen = new Set<string>()
    for (const row of block1Prefill) {
      // 一行一叶子子科目：名称作为 rowKey/label（与 crossSheet 聚合 key 语义一致）
      const rowKey = (row.name || row.code || '').trim()
      if (!rowKey || seen.has(rowKey)) continue
      seen.add(rowKey)
      newKeys.push(rowKey)
      const prefix = `D6-1-adj-block1-${rowKey}`
      map.set(`${prefix}-priorUnadjusted`, {
        item_id: `${prefix}-priorUnadjusted`, conclusion: null, remark: String(row.opening_balance ?? 0),
      })
      map.set(`${prefix}-currentUnadjusted`, {
        item_id: `${prefix}-currentUnadjusted`, conclusion: null, remark: String(row.closing_balance ?? 0),
      })
    }

    if (newKeys.length === 0) { _prefillSeeded = true; return }

    const rowKeysItemId = 'D6-1-adj-block1-rowKeys'
    const rowKeysRemark = JSON.stringify(newKeys)
    map.set(rowKeysItemId, { item_id: rowKeysItemId, conclusion: null, remark: rowKeysRemark })

    // 先置守卫再触发响应式，避免 watch 重入重复 seed
    _prefillSeeded = true
    fourTableSeededKeys.value = new Set(newKeys)
    block1RowKeys.value = [...newKeys]
    allResponses.value = new Map(map)

    // 走正常保存路径持久化（不新造键；rowKeys 结构性即时保存、字段值 debounce 保存）
    void saveImmediate(rowKeysItemId, { remark: rowKeysRemark })
    for (const rowKey of newKeys) {
      const prefix = `D6-1-adj-block1-${rowKey}`
      debouncedSave(`${prefix}-priorUnadjusted`, {
        remark: allResponses.value.get(`${prefix}-priorUnadjusted`)?.remark ?? '0',
      })
      debouncedSave(`${prefix}-currentUnadjusted`, {
        remark: allResponses.value.get(`${prefix}-currentUnadjusted`)?.remark ?? '0',
      })
    }
  }

  // 触发 seed：allResponses 加载完成（父组件 isLoading 门控保证挂载时已加载）或
  // prefill 到达时尝试一次；条件不满足时 no-op（灰度关/无 prefill → 零回归 Property 9）。
  watch(
    [allResponses, () => adjudicationPrefill?.value],
    () => _maybeSeedFromPrefill(),
    { immediate: true },
  )

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

    // 标注四表库自动取数行（本会话内 seed 的 block1 行）
    const taggedRows = dynamicRows.map(r =>
      fourTableSeededKeys.value.has(r.rowKey) ? { ...r, isFourTableSeed: true } : r,
    )

    const subtotalRow = _buildSubtotalRow(taggedRows, config.subtotalLabel)
    const deductionRow = _buildDeductionRow('block1', config.deductionLabel)
    const blockTotalRow = _buildBlockTotalRow(subtotalRow, deductionRow, config.totalLabel)

    return {
      blockKey: config.blockKey,
      blockTitle: config.blockTitle,
      rows: taggedRows,
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
      // 合同资产科目为 1141（report_config 报表行 BS-011 四准则一致）；
      // 原 `1402` 是在途物资（存货类），属误用。
      eventBus.emit('substantive:adjudicated' as any, {
        wpCode: 'D6',
        accountCode: '1141',
        auditedAmount,
      })
    } catch { /* EventBus publish failure should not block */ }
  }

  // ─── onAdjustmentCreated ───────────────────────────────────────────────────

  function onAdjustmentCreated(payload: any): void {
    if (!payload || payload.wpCode !== 'D6') return

    const { entryType, amount, accountCode } = payload
    if (accountCode !== '1141') return

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
