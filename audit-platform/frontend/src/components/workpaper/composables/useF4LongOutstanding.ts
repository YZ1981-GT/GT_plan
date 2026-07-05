/**
 * useF4LongOutstanding — F4-5 长期挂账检查逻辑
 *
 * Spec: .kiro/specs/f4-accounts-payable/ Task 5.3
 * 挂账天数公式 + 高亮（>2年橙色，>3年红色）
 * 合计行（总额/2年以上/3年以上/建议转收入）+ 动态行增删
 * Requirements: 8.1~8.6
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcOutstandingDays, calcSubtotal } from './useF4AccPayFormulaEngine'
import type { ChecklistResponse } from './useF4FormData'

// ─── 类型定义 ─────────────────────────────────────────────────────────────────

export interface LongOutstandingRow {
  rowId: string
  seq: number
  creditor: string
  amount: number
  startDate: string
  outstandingDays: number          // 公式=当前日期-挂账起始日
  paymentNature: string
  reason: string
  hasDispute: string
  shouldTransferIncome: string
  suggestion: string
  remark: string
  // 高亮标记
  highlightLevel: 'none' | 'orange' | 'red'
}

export interface F4LongOutstandingColumn {
  prop: keyof LongOutstandingRow | string
  label: string
  width?: number
  minWidth?: number
  formula?: string
  editable?: boolean
}

export const F4_LONG_OUTSTANDING_COLUMNS: F4LongOutstandingColumn[] = [
  { prop: 'seq', label: '序号', width: 60 },
  { prop: 'creditor', label: '债权人', minWidth: 130, editable: true },
  { prop: 'amount', label: '挂账金额', minWidth: 120, editable: true },
  { prop: 'startDate', label: '挂账起始日', minWidth: 110, editable: true },
  { prop: 'outstandingDays', label: '挂账天数', minWidth: 100, formula: '当前日期-起始日', editable: false },
  { prop: 'paymentNature', label: '款项性质', minWidth: 100, editable: true },
  { prop: 'reason', label: '挂账原因', minWidth: 140, editable: true },
  { prop: 'hasDispute', label: '合同纠纷', minWidth: 90, editable: true },
  { prop: 'shouldTransferIncome', label: '转营业外收入', minWidth: 110, editable: true },
  { prop: 'suggestion', label: '处理建议', minWidth: 140, editable: true },
  { prop: 'remark', label: '备注', minWidth: 120, editable: true },
]

// ─── 内部存储类型 ─────────────────────────────────────────────────────────────

interface StoredLongOutstandingRow {
  rowId: string
  seq: number
  creditor: string
  amount: number
  startDate: string
  paymentNature: string
  reason: string
  hasDispute: string
  shouldTransferIncome: string
  suggestion: string
  remark: string
}

export interface UseF4LongOutstandingOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

// ─── 常量 ─────────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'F4-5-rows'
const NOTE_KEY = 'F4-5-note'
const DAYS_2_YEARS = 365 * 2
const DAYS_3_YEARS = 365 * 3

// ─── 工具函数 ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `f4lo-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function emptyStored(seq: number): StoredLongOutstandingRow {
  return {
    rowId: generateRowId(),
    seq,
    creditor: '',
    amount: 0,
    startDate: '',
    paymentNature: '',
    reason: '',
    hasDispute: '否',
    shouldTransferIncome: '否',
    suggestion: '',
    remark: '',
  }
}

function computeRow(stored: StoredLongOutstandingRow): LongOutstandingRow {
  let outstandingDays = 0
  if (stored.startDate) {
    const start = new Date(stored.startDate)
    if (!isNaN(start.getTime())) {
      outstandingDays = calcOutstandingDays(new Date(), start)
    }
  }
  let highlightLevel: 'none' | 'orange' | 'red' = 'none'
  if (outstandingDays > DAYS_3_YEARS) highlightLevel = 'red'
  else if (outstandingDays > DAYS_2_YEARS) highlightLevel = 'orange'

  return { ...stored, outstandingDays, highlightLevel }
}

function safeParseRows(jsonStr: string | null | undefined): StoredLongOutstandingRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any, i: number) => ({
      ...emptyStored(i + 1),
      rowId: raw.rowId || raw.id || generateRowId(),
      seq: raw.seq ?? i + 1,
      creditor: raw.creditor || '',
      amount: parseNum(raw.amount),
      startDate: raw.startDate || '',
      paymentNature: raw.paymentNature || '',
      reason: raw.reason || '',
      hasDispute: raw.hasDispute || '否',
      shouldTransferIncome: raw.shouldTransferIncome || '否',
      suggestion: raw.suggestion || '',
      remark: raw.remark || '',
    }))
  } catch {
    return []
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useF4LongOutstanding(options: UseF4LongOutstandingOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const storedData = ref<StoredLongOutstandingRow[]>([])
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

  const rows: ComputedRef<LongOutstandingRow[]> = computed(() => storedData.value.map(computeRow))

  // ─── 汇总统计 ─────────────────────────────────────────────────────────────

  const summary = computed(() => {
    const all = rows.value
    const totalAmount = calcSubtotal(all.map((r) => r.amount))
    const over2YearAmount = calcSubtotal(all.filter((r) => r.outstandingDays > DAYS_2_YEARS).map((r) => r.amount))
    const over3YearAmount = calcSubtotal(all.filter((r) => r.outstandingDays > DAYS_3_YEARS).map((r) => r.amount))
    const transferAmount = calcSubtotal(
      all.filter((r) => r.shouldTransferIncome === '是').map((r) => r.amount),
    )
    return { totalAmount, over2YearAmount, over3YearAmount, transferAmount }
  })

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
    const strFields = ['creditor', 'startDate', 'paymentNature', 'reason', 'hasDispute',
      'shouldTransferIncome', 'suggestion', 'remark']
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

  function rowClassName({ row }: { row: LongOutstandingRow }): string {
    if (row.highlightLevel === 'red') return 'long-outstanding-red'
    if (row.highlightLevel === 'orange') return 'long-outstanding-orange'
    return ''
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
    columns: F4_LONG_OUTSTANDING_COLUMNS,
  }
}

export default useF4LongOutstanding
