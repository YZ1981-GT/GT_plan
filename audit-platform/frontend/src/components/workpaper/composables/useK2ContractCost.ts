/**
 * useK2ContractCost — K2-4 合同取得成本明细表 composable（23列3区段Tab，57公式）
 *
 * 管理动态合同取得成本行，23列宽表拆3区段：
 *   区段0 "合同"：合同编号/客户/合同金额/取得成本类型/是否资本化
 *   区段1 "摊销"：期初余额/本期增加/本期摊销/期末余额(公式)
 *   区段2 "检查"：摊销方法/摊销期/凭证号/结论
 *
 * 核心功能：
 * - 期末余额=期初+增加-摊销（资产类公式）
 * - CAS14资本化判断（增量成本+预期可收回+与合同直接相关）
 * - 与K2-5摊销测算交叉验证
 * - 合计与K2-1审定合同取得成本一致
 * - 动态行+导入导出
 * - JSON打包存储 "K2-4-rows"
 *
 * Spec: .kiro/specs/k2-other-current-assets/
 * Task: 3.4
 * Requirements: 4.1-4.6
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcAssetEndBalance, calcSubtotal } from './useK2FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K2ContractCostRow {
  rowId: string
  // Section 0 合同
  contractNo: string          // 合同编号
  customer: string            // 客户
  contractAmount: number      // 合同金额
  costType: string            // 取得成本类型（佣金/手续费/其他）
  isCapitalized: boolean      // 是否资本化
  // CAS14三条件
  isIncremental: boolean      // 增量成本
  isRecoverable: boolean      // 预期可收回
  isDirectlyRelated: boolean  // 与合同直接相关
  // Section 1 摊销
  beginBalance: number        // 期初余额
  periodIncrease: number      // 本期增加
  periodAmort: number         // 本期摊销
  endBalance: number          // 期末余额（公式：期初+增加-摊销）
  // Section 2 检查
  amortMethod: string         // 摊销方法（直线法/进度法）
  amortPeriod: number         // 摊销期（月）
  voucherRef: string          // 凭证号
  conclusion: string          // 结论
  remark: string              // 备注
}

export type K2ContractCostSection = 0 | 1 | 2

export const K2_CONTRACT_SECTION_LABELS = ['合同', '摊销', '检查'] as const

export interface K2ContractCostSubtotals {
  contractAmount: number
  beginBalance: number
  periodIncrease: number
  periodAmort: number
  endBalance: number
  count: number
}

export interface K2ContractColumn {
  key: string
  label: string
  width: number
  editable: boolean
  type: 'text' | 'number' | 'formula' | 'select' | 'boolean'
  options?: string[]
  tooltip?: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'K2-4-rows'

const COST_TYPE_OPTIONS = ['佣金', '手续费', '差旅费', '投标费', '其他']
const AMORT_METHOD_OPTIONS = ['直线法', '进度法']
const CONCLUSION_OPTIONS = ['正常', '异常', '待确认']

/** Section 0 合同区段列定义 */
const CONTRACT_COLUMNS: K2ContractColumn[] = [
  { key: 'contractNo', label: '合同编号', width: 130, editable: true, type: 'text' },
  { key: 'customer', label: '客户', width: 150, editable: true, type: 'text' },
  { key: 'contractAmount', label: '合同金额', width: 130, editable: true, type: 'number' },
  { key: 'costType', label: '取得成本类型', width: 120, editable: true, type: 'select', options: COST_TYPE_OPTIONS },
  { key: 'isCapitalized', label: '是否资本化', width: 100, editable: true, type: 'boolean' },
  { key: 'isIncremental', label: '增量成本', width: 90, editable: true, type: 'boolean', tooltip: 'CAS14条件1' },
  { key: 'isRecoverable', label: '预期可收回', width: 100, editable: true, type: 'boolean', tooltip: 'CAS14条件2' },
  { key: 'isDirectlyRelated', label: '直接相关', width: 90, editable: true, type: 'boolean', tooltip: 'CAS14条件3' },
]

/** Section 1 摊销区段列定义 */
const AMORT_COLUMNS: K2ContractColumn[] = [
  { key: 'contractNo', label: '合同编号', width: 130, editable: false, type: 'text' },
  { key: 'beginBalance', label: '期初余额', width: 130, editable: true, type: 'number' },
  { key: 'periodIncrease', label: '本期增加', width: 120, editable: true, type: 'number' },
  { key: 'periodAmort', label: '本期摊销', width: 120, editable: true, type: 'number' },
  { key: 'endBalance', label: '期末余额', width: 130, editable: false, type: 'formula', tooltip: '期末=期初+增加-摊销' },
]

/** Section 2 检查区段列定义 */
const CHECK_COLUMNS: K2ContractColumn[] = [
  { key: 'contractNo', label: '合同编号', width: 130, editable: false, type: 'text' },
  { key: 'amortMethod', label: '摊销方法', width: 100, editable: true, type: 'select', options: AMORT_METHOD_OPTIONS },
  { key: 'amortPeriod', label: '摊销期(月)', width: 100, editable: true, type: 'number' },
  { key: 'voucherRef', label: '凭证号', width: 120, editable: true, type: 'text' },
  { key: 'conclusion', label: '结论', width: 100, editable: true, type: 'select', options: CONCLUSION_OPTIONS },
  { key: 'remark', label: '备注', width: 180, editable: true, type: 'text' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK2ContractCost(
  allResponses: Ref<Map<string, any>>,
  options?: {
    onSave?: (itemId: string, value: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<K2ContractCostRow[]>([])
  const activeSection = ref<K2ContractCostSection>(0)
  const activeRowIndex = ref<number>(-1)

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadRows(): void {
    const item = allResponses.value.get(ITEM_ID_ROWS)
    const raw = item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : null)
    if (!raw) { rows.value = []; return }
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed) && parsed.length > 0) {
        rows.value = parsed.map(_normalizeRow)
      } else {
        rows.value = []
      }
    } catch {
      rows.value = []
    }
  }

  function _normalizeRow(raw: any): K2ContractCostRow {
    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      contractNo: raw.contractNo ?? '',
      customer: raw.customer ?? '',
      contractAmount: Number(raw.contractAmount) || 0,
      costType: raw.costType ?? '',
      isCapitalized: raw.isCapitalized === true,
      isIncremental: raw.isIncremental === true,
      isRecoverable: raw.isRecoverable === true,
      isDirectlyRelated: raw.isDirectlyRelated === true,
      beginBalance: Number(raw.beginBalance) || 0,
      periodIncrease: Number(raw.periodIncrease) || 0,
      periodAmort: Number(raw.periodAmort) || 0,
      endBalance: Number(raw.endBalance) || 0,
      amortMethod: raw.amortMethod ?? '直线法',
      amortPeriod: Number(raw.amortPeriod) || 0,
      voucherRef: raw.voucherRef ?? '',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── Recalc ────────────────────────────────────────────────────────────────

  function _recalcRow(row: K2ContractCostRow): void {
    // 期末余额 = 期初 + 增加 - 摊销（资产类公式，摊销视为贷方减少）
    row.endBalance = calcAssetEndBalance(row.beginBalance, row.periodIncrease, row.periodAmort)
  }

  function recalcAll(): void {
    for (const row of rows.value) _recalcRow(row)
  }

  // ─── Capitalization Judgment (CAS14 3 conditions) ──────────────────────────

  /**
   * CAS14资本化判断：三个条件均满足时建议资本化
   */
  const capitalizationSuggestions: ComputedRef<Map<string, boolean>> = computed(() => {
    const map = new Map<string, boolean>()
    for (const row of rows.value) {
      map.set(row.rowId, row.isIncremental && row.isRecoverable && row.isDirectlyRelated)
    }
    return map
  })

  // ─── Computed: Subtotals ───────────────────────────────────────────────────

  const subtotals: ComputedRef<K2ContractCostSubtotals> = computed(() => {
    const r = rows.value
    return {
      contractAmount: calcSubtotal(r.map((x) => x.contractAmount)),
      beginBalance: calcSubtotal(r.map((x) => x.beginBalance)),
      periodIncrease: calcSubtotal(r.map((x) => x.periodIncrease)),
      periodAmort: calcSubtotal(r.map((x) => x.periodAmort)),
      endBalance: calcSubtotal(r.map((x) => x.endBalance)),
      count: r.length,
    }
  })

  // ─── Section Switching ─────────────────────────────────────────────────────

  function switchSection(section: K2ContractCostSection): void {
    activeSection.value = section
  }

  const activeColumns = computed(() => {
    switch (activeSection.value) {
      case 0: return CONTRACT_COLUMNS
      case 1: return AMORT_COLUMNS
      case 2: return CHECK_COLUMNS
      default: return CONTRACT_COLUMNS
    }
  })

  const sections = [
    { key: 0 as K2ContractCostSection, label: '合同', columns: CONTRACT_COLUMNS },
    { key: 1 as K2ContractCostSection, label: '摊销', columns: AMORT_COLUMNS },
    { key: 2 as K2ContractCostSection, label: '检查', columns: CHECK_COLUMNS },
  ]

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _recalcRow(row)
    _persist()
  }

  // ─── Dynamic Row Add (Req 4.6) ─────────────────────────────────────────────

  async function addRow(): Promise<void> {
    try {
      const { value: contractNo } = await ElMessageBox.prompt(
        '请输入合同编号',
        '新增合同取得成本',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '例如：HT-2025-001',
          inputValidator: (val) => (!val?.trim() ? '合同编号不能为空' : true),
        },
      )
      if (!contractNo?.trim()) return

      const newRow: K2ContractCostRow = {
        rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        contractNo: contractNo.trim(),
        customer: '',
        contractAmount: 0,
        costType: '',
        isCapitalized: false,
        isIncremental: false,
        isRecoverable: false,
        isDirectlyRelated: false,
        beginBalance: 0,
        periodIncrease: 0,
        periodAmort: 0,
        endBalance: 0,
        amortMethod: '直线法',
        amortPeriod: 0,
        voucherRef: '',
        conclusion: '',
        remark: '',
      }

      rows.value.push(newRow)
      activeRowIndex.value = rows.value.length - 1
      _persist()
    } catch {
      // 用户取消
    }
  }

  // ─── Remove Row ────────────────────────────────────────────────────────────

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx < 0) return
    rows.value.splice(idx, 1)
    if (activeRowIndex.value >= rows.value.length) {
      activeRowIndex.value = rows.value.length - 1
    }
    _persist()
  }

  // ─── Import / Export ───────────────────────────────────────────────────────

  function importRows(data: any[]): void {
    rows.value = data.map((raw) => {
      const row = _normalizeRow(raw)
      _recalcRow(row)
      return row
    })
    activeRowIndex.value = rows.value.length > 0 ? 0 : -1
    _persist()
  }

  function exportRows(): K2ContractCostRow[] {
    return [...rows.value]
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    options?.onSave?.(ITEM_ID_ROWS, JSON.stringify(rows.value))
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadRows(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    activeSection,
    activeRowIndex,
    subtotals,
    activeColumns,
    sections,
    capitalizationSuggestions,
    switchSection,
    updateCell,
    recalcAll,
    addRow,
    removeRow,
    importRows,
    exportRows,
  }
}
