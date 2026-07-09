/**
 * useK2Amortization — K2-5 摊销测算表 composable（28列，最多66行，37公式）
 *
 * 管理摊销测算行（从K2-4合同取得成本数据来源）：
 *   区段0 "基础"：合同编号/取得成本/摊销方法/摊销期(月)/起始日
 *   区段1 "测算"：本期应摊销(公式)/累计摊销/摊余成本(公式)/企业摊销/差异(公式)/结论
 *
 * 核心功能：
 * - 使用 useK2AmortizationEngine 纯函数：calcStraightLineAmort/calcProgressAmort/calcAmortizedBalance/calcAmortVariance
 * - el-segmented 方法切换（直线法/进度法）
 * - 差异高亮（红色当>重要性水平）
 * - 虚拟滚动数据管理（66行，实际渲染在Vue组件层）
 * - JSON打包存储 "K2-5-rows"
 *
 * Spec: .kiro/specs/k2-other-current-assets/
 * Task: 3.4
 * Requirements: 5.1-5.7
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcStraightLineAmort,
  calcProgressAmort,
  calcAmortizedBalance,
  calcAmortVariance,
} from './useK2AmortizationEngine'
import { calcSubtotal } from './useK2FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type K2AmortMethod = '直线法' | '进度法'

export interface K2AmortRow {
  rowId: string
  // 基础
  contractNo: string            // 合同编号
  cost: number                  // 取得成本
  method: K2AmortMethod         // 摊销方法
  totalPeriods: number          // 摊销期总期数（月）
  currentPeriods: number        // 本期期数（月，直线法用）
  startDate: string             // 起始日（YYYY-MM-DD）
  currentProgress: number       // 本期履约进度（0~1，进度法用）
  priorProgress: number         // 上期履约进度（0~1，进度法用）
  // 测算（含公式列）
  calculatedAmort: number       // 本期应摊销（公式）
  accumulatedAmort: number      // 累计已摊销
  amortizedBalance: number      // 摊余成本（公式：cost - accumulated）
  bookedAmort: number           // 企业账面摊销
  variance: number              // 差异（公式：计算-账面）
  conclusion: string            // 结论
  remark: string                // 备注
}

export type K2AmortSection = 0 | 1

export const K2_AMORT_SECTION_LABELS = ['基础', '测算'] as const

export interface K2AmortSubtotals {
  cost: number
  calculatedAmort: number
  accumulatedAmort: number
  amortizedBalance: number
  bookedAmort: number
  variance: number
  count: number
}

export interface K2AmortColumn {
  key: string
  label: string
  width: number
  editable: boolean
  type: 'text' | 'number' | 'formula' | 'select' | 'date' | 'percent'
  options?: string[]
  tooltip?: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'K2-5-rows'
const ITEM_ID_MATERIALITY = 'K2-5-materiality'

const METHOD_OPTIONS: K2AmortMethod[] = ['直线法', '进度法']
const CONCLUSION_OPTIONS = ['正常', '差异不重大', '差异重大-需调整', '待确认']

/** Section 0 基础区段列 */
const BASIC_COLUMNS: K2AmortColumn[] = [
  { key: 'contractNo', label: '合同编号', width: 130, editable: true, type: 'text' },
  { key: 'cost', label: '取得成本', width: 130, editable: true, type: 'number' },
  { key: 'method', label: '摊销方法', width: 100, editable: true, type: 'select', options: METHOD_OPTIONS },
  { key: 'totalPeriods', label: '摊销期(月)', width: 100, editable: true, type: 'number' },
  { key: 'currentPeriods', label: '本期期数(月)', width: 110, editable: true, type: 'number', tooltip: '直线法使用' },
  { key: 'startDate', label: '起始日', width: 120, editable: true, type: 'date' },
  { key: 'currentProgress', label: '本期进度', width: 100, editable: true, type: 'percent', tooltip: '进度法使用(0~1)' },
  { key: 'priorProgress', label: '上期进度', width: 100, editable: true, type: 'percent', tooltip: '进度法使用(0~1)' },
]

/** Section 1 测算区段列 */
const CALC_COLUMNS: K2AmortColumn[] = [
  { key: 'contractNo', label: '合同编号', width: 130, editable: false, type: 'text' },
  { key: 'calculatedAmort', label: '本期应摊销', width: 130, editable: false, type: 'formula', tooltip: '直线:cost/总期×本期期数; 进度:cost×(本期进度-上期进度)' },
  { key: 'accumulatedAmort', label: '累计摊销', width: 120, editable: true, type: 'number' },
  { key: 'amortizedBalance', label: '摊余成本', width: 130, editable: false, type: 'formula', tooltip: '取得成本-累计摊销' },
  { key: 'bookedAmort', label: '企业摊销', width: 120, editable: true, type: 'number' },
  { key: 'variance', label: '差异', width: 110, editable: false, type: 'formula', tooltip: '测算摊销-企业摊销' },
  { key: 'conclusion', label: '结论', width: 120, editable: true, type: 'select', options: CONCLUSION_OPTIONS },
  { key: 'remark', label: '备注', width: 180, editable: true, type: 'text' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK2Amortization(
  allResponses: Ref<Map<string, any>>,
  options?: {
    onSave?: (itemId: string, value: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<K2AmortRow[]>([])
  const activeSection = ref<K2AmortSection>(0)
  const activeRowIndex = ref<number>(-1)
  const materiality = ref<number>(0) // 重要性水平

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

    // 重要性水平
    const matItem = allResponses.value.get(ITEM_ID_MATERIALITY)
    const matRaw = matItem?.remark ?? matItem?.conclusion ?? ''
    materiality.value = Number(matRaw) || 0
  }

  function _normalizeRow(raw: any): K2AmortRow {
    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      contractNo: raw.contractNo ?? '',
      cost: Number(raw.cost) || 0,
      method: raw.method === '进度法' ? '进度法' : '直线法',
      totalPeriods: Number(raw.totalPeriods) || 0,
      currentPeriods: Number(raw.currentPeriods) || 0,
      startDate: raw.startDate ?? '',
      currentProgress: Number(raw.currentProgress) || 0,
      priorProgress: Number(raw.priorProgress) || 0,
      calculatedAmort: Number(raw.calculatedAmort) || 0,
      accumulatedAmort: Number(raw.accumulatedAmort) || 0,
      amortizedBalance: Number(raw.amortizedBalance) || 0,
      bookedAmort: Number(raw.bookedAmort) || 0,
      variance: Number(raw.variance) || 0,
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── Recalc (Engine Dispatch) ──────────────────────────────────────────────

  function _recalcRow(row: K2AmortRow): void {
    // 根据方法计算本期应摊销
    if (row.method === '直线法') {
      row.calculatedAmort = calcStraightLineAmort(row.cost, row.totalPeriods, row.currentPeriods)
    } else {
      row.calculatedAmort = calcProgressAmort(row.cost, row.currentProgress, row.priorProgress)
    }
    // 摊余成本
    row.amortizedBalance = calcAmortizedBalance(row.cost, row.accumulatedAmort)
    // 差异
    row.variance = calcAmortVariance(row.calculatedAmort, row.bookedAmort)
  }

  function recalcAll(): void {
    for (const row of rows.value) _recalcRow(row)
  }

  // ─── Computed: Subtotals ───────────────────────────────────────────────────

  const subtotals: ComputedRef<K2AmortSubtotals> = computed(() => {
    const r = rows.value
    return {
      cost: calcSubtotal(r.map((x) => x.cost)),
      calculatedAmort: calcSubtotal(r.map((x) => x.calculatedAmort)),
      accumulatedAmort: calcSubtotal(r.map((x) => x.accumulatedAmort)),
      amortizedBalance: calcSubtotal(r.map((x) => x.amortizedBalance)),
      bookedAmort: calcSubtotal(r.map((x) => x.bookedAmort)),
      variance: calcSubtotal(r.map((x) => x.variance)),
      count: r.length,
    }
  })

  // ─── Variance Highlighting (Req 5.6) ──────────────────────────────────────

  /**
   * 差异超过重要性水平的行ID集合（红色标记）
   */
  const varianceExceedRows: ComputedRef<Set<string>> = computed(() => {
    const exceedSet = new Set<string>()
    if (materiality.value <= 0) return exceedSet
    for (const row of rows.value) {
      if (Math.abs(row.variance) > materiality.value) {
        exceedSet.add(row.rowId)
      }
    }
    return exceedSet
  })

  // ─── Section Switching ─────────────────────────────────────────────────────

  function switchSection(section: K2AmortSection): void {
    activeSection.value = section
  }

  const activeColumns = computed(() => {
    return activeSection.value === 0 ? BASIC_COLUMNS : CALC_COLUMNS
  })

  const sections = [
    { key: 0 as K2AmortSection, label: '基础', columns: BASIC_COLUMNS },
    { key: 1 as K2AmortSection, label: '测算', columns: CALC_COLUMNS },
  ]

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _recalcRow(row)
    _persist()
  }

  // ─── Method Switching (el-segmented) ───────────────────────────────────────

  function switchMethod(rowId: string, method: K2AmortMethod): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    row.method = method
    _recalcRow(row)
    _persist()
  }

  // ─── Add Row ───────────────────────────────────────────────────────────────

  function addRow(contractNo?: string, cost?: number, method?: K2AmortMethod): void {
    const newRow: K2AmortRow = {
      rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      contractNo: contractNo ?? '',
      cost: cost ?? 0,
      method: method ?? '直线法',
      totalPeriods: 0,
      currentPeriods: 0,
      startDate: '',
      currentProgress: 0,
      priorProgress: 0,
      calculatedAmort: 0,
      accumulatedAmort: 0,
      amortizedBalance: cost ?? 0,
      bookedAmort: 0,
      variance: 0,
      conclusion: '',
      remark: '',
    }
    rows.value.push(newRow)
    activeRowIndex.value = rows.value.length - 1
    _persist()
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

  function exportRows(): K2AmortRow[] {
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
    materiality,
    subtotals,
    activeColumns,
    sections,
    varianceExceedRows,
    switchSection,
    switchMethod,
    updateCell,
    recalcAll,
    addRow,
    removeRow,
    importRows,
    exportRows,
  }
}
