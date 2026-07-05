/**
 * useF4SubstantiveAnalysis — F4-4 实质性分析逻辑
 *
 * Spec: .kiro/specs/f4-accounts-payable/ Task 5.2
 * 公式链：变动额=本期-上期 / 变动率=(本期-上期)/上期×100 / 预期差异=本期-预期
 * 变动率>20% 橙色标记
 * Requirements: 7.1~7.6
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcChangeAmount,
  calcChangeRate,
  isChangeRateExceeding,
  calcSubtotal,
} from './useF4AccPayFormulaEngine'
import type { ChecklistResponse } from './useF4FormData'

// ─── 类型定义 ─────────────────────────────────────────────────────────────────

export interface SubstantiveAnalysisRow {
  rowId: string
  seq: number
  item: string                     // 分析项目
  currentAmount: number            // 本期金额
  priorAmount: number              // 上期金额
  changeAmount: number             // 变动额(公式=本期-上期)
  changeRate: number | 'N/A'       // 变动率(公式)
  expectedValue: number            // 预期值
  expectedDifference: number       // 预期差异(公式=本期-预期)
  explanation: string              // 分析说明
  // 标记
  isHighChange: boolean
}

export interface F4SubstantiveColumn {
  prop: keyof SubstantiveAnalysisRow | string
  label: string
  width?: number
  minWidth?: number
  formula?: string
  editable?: boolean
}

export const F4_SUBSTANTIVE_COLUMNS: F4SubstantiveColumn[] = [
  { prop: 'seq', label: '序号', width: 60 },
  { prop: 'item', label: '分析项目', minWidth: 150, editable: true },
  { prop: 'currentAmount', label: '本期金额', minWidth: 120, editable: true },
  { prop: 'priorAmount', label: '上期金额', minWidth: 120, editable: true },
  { prop: 'changeAmount', label: '变动额', minWidth: 110, formula: '本期-上期', editable: false },
  { prop: 'changeRate', label: '变动率(%)', minWidth: 100, formula: '(本期-上期)/上期×100', editable: false },
  { prop: 'expectedValue', label: '预期值', minWidth: 120, editable: true },
  { prop: 'expectedDifference', label: '预期差异', minWidth: 110, formula: '本期-预期', editable: false },
  { prop: 'explanation', label: '分析说明', minWidth: 180, editable: true },
]

// ─── 内部存储类型 ─────────────────────────────────────────────────────────────

interface StoredSubstantiveRow {
  rowId: string
  seq: number
  item: string
  currentAmount: number
  priorAmount: number
  expectedValue: number
  explanation: string
}

export interface UseF4SubstantiveAnalysisOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

// ─── 工具函数 ─────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'F4-4-rows'
const NOTE_KEY = 'F4-4-note'
const CHANGE_THRESHOLD = 20

function generateRowId(): string {
  return `f4sa-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function emptyStored(seq: number): StoredSubstantiveRow {
  return {
    rowId: generateRowId(),
    seq,
    item: '',
    currentAmount: 0,
    priorAmount: 0,
    expectedValue: 0,
    explanation: '',
  }
}

function computeRow(stored: StoredSubstantiveRow): SubstantiveAnalysisRow {
  const changeAmount = calcChangeAmount(stored.currentAmount, stored.priorAmount)
  const changeRate = calcChangeRate(stored.currentAmount, stored.priorAmount)
  const expectedDifference = stored.currentAmount - stored.expectedValue
  const isHighChange = isChangeRateExceeding(changeRate, CHANGE_THRESHOLD)
  return {
    ...stored,
    changeAmount,
    changeRate,
    expectedDifference,
    isHighChange,
  }
}

function safeParseRows(jsonStr: string | null | undefined): StoredSubstantiveRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any, i: number) => ({
      ...emptyStored(i + 1),
      rowId: raw.rowId || raw.id || generateRowId(),
      seq: raw.seq ?? i + 1,
      item: raw.item || '',
      currentAmount: parseNum(raw.currentAmount),
      priorAmount: parseNum(raw.priorAmount),
      expectedValue: parseNum(raw.expectedValue),
      explanation: raw.explanation || '',
    }))
  } catch {
    return []
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useF4SubstantiveAnalysis(options: UseF4SubstantiveAnalysisOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const storedData = ref<StoredSubstantiveRow[]>([])
  const auditConclusion = ref('')

  // ─── 加载 ─────────────────────────────────────────────────────────────────

  function loadRows(): void {
    storedData.value = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    if (storedData.value.length === 0) storedData.value = [emptyStored(1)]
  }

  watch(() => allResponses.value.get(STORAGE_KEY)?.remark, () => {
    if (storedData.value.length === 0) loadRows()
  }, { immediate: true })

  watch(() => allResponses.value.get(NOTE_KEY)?.remark, (v) => {
    auditConclusion.value = v || ''
  }, { immediate: true })

  // ─── 计算行 ───────────────────────────────────────────────────────────────

  const rows: ComputedRef<SubstantiveAnalysisRow[]> = computed(() => storedData.value.map(computeRow))

  const summary = computed(() => ({
    totalCurrent: calcSubtotal(rows.value.map((r) => r.currentAmount)),
    totalPrior: calcSubtotal(rows.value.map((r) => r.priorAmount)),
    highChangeCount: rows.value.filter((r) => r.isHighChange).length,
  }))

  // ─── 动态行操作 ───────────────────────────────────────────────────────────

  function addRow(): void {
    if (readonly.value) return
    storedData.value.push(emptyStored(storedData.value.length + 1))
    persistRows()
  }

  function removeRow(rowId: string): void {
    if (readonly.value || storedData.value.length <= 1) return
    const idx = storedData.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    storedData.value.splice(idx, 1)
    storedData.value.forEach((r, i) => { r.seq = i + 1 })
    persistRows()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (readonly.value) return
    const row = storedData.value.find((r) => r.rowId === rowId)
    if (!row) return
    const strFields = ['item', 'explanation']
    if (strFields.includes(field)) (row as any)[field] = String(value ?? '')
    else (row as any)[field] = parseNum(value)
    persistRows()
  }

  // ─── 持久化 ───────────────────────────────────────────────────────────────

  function persistRows(): void {
    allResponses.value.set(STORAGE_KEY, {
      item_id: STORAGE_KEY,
      conclusion: null,
      remark: JSON.stringify(storedData.value),
    })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function flushSave(): void {
    const items = [allResponses.value.get(STORAGE_KEY), allResponses.value.get(NOTE_KEY)].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f4:save-items', { detail: { items } }))
  }

  watch(auditConclusion, (val) => {
    allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
    debounceSave()
  })

  // ─── 样式 ─────────────────────────────────────────────────────────────────

  function rowClassName({ row }: { row: SubstantiveAnalysisRow }): string {
    return row.isHighChange ? 'high-change-row' : ''
  }

  // ─── 清理 ─────────────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; flushSave() }
  })

  return {
    rows,
    summary,
    auditConclusion,
    addRow,
    removeRow,
    updateCell,
    rowClassName,
    columns: F4_SUBSTANTIVE_COLUMNS,
  }
}

export default useF4SubstantiveAnalysis
