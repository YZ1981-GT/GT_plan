/**
 * useF4RelatedParty — F4-6 关联方检查逻辑
 *
 * Spec: .kiro/specs/f4-accounts-payable/ Task 5.4
 * 贷方余额公式 + 占比公式 + 集中度>30%橙色
 * 合计行 + 动态行增删
 * Requirements: 9.1~9.6
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcCreditBalance,
  calcConcentration,
  calcSubtotal,
} from './useF4AccPayFormulaEngine'
import type { ChecklistResponse } from './useF4FormData'

// ─── 类型定义 ─────────────────────────────────────────────────────────────────

export interface RelatedPartyAPRow {
  rowId: string
  seq: number
  partyName: string
  relationship: string
  paymentNature: string
  openingBalance: number
  currentIncrease: number
  currentDecrease: number
  closingBalance: number           // 公式=期初+贷方增加-借方减少
  concentration: number            // 占比(公式)
  settlementCycle: string
  isOverdue: string
  fairness: string
  aging: string
  auditEvaluation: string
  remark: string
  // 标记
  isHighConcentration: boolean
}

export interface F4RelatedPartyColumn {
  prop: keyof RelatedPartyAPRow | string
  label: string
  width?: number
  minWidth?: number
  formula?: string
  editable?: boolean
}

export const F4_RELATED_PARTY_COLUMNS: F4RelatedPartyColumn[] = [
  { prop: 'seq', label: '序号', width: 60 },
  { prop: 'partyName', label: '关联方名称', minWidth: 130, editable: true },
  { prop: 'relationship', label: '关联关系', minWidth: 110, editable: true },
  { prop: 'paymentNature', label: '款项性质', minWidth: 100, editable: true },
  { prop: 'openingBalance', label: '期初余额', minWidth: 110, editable: true },
  { prop: 'currentIncrease', label: '本期增加', minWidth: 110, editable: true },
  { prop: 'currentDecrease', label: '本期减少', minWidth: 110, editable: true },
  { prop: 'closingBalance', label: '期末余额', minWidth: 110, formula: '期初+增加-减少', editable: false },
  { prop: 'concentration', label: '占比(%)', minWidth: 90, formula: '余额/总额×100', editable: false },
  { prop: 'settlementCycle', label: '结算周期', minWidth: 100, editable: true },
  { prop: 'isOverdue', label: '是否超期', minWidth: 80, editable: true },
  { prop: 'fairness', label: '定价公允性', minWidth: 100, editable: true },
  { prop: 'aging', label: '账龄', minWidth: 90, editable: true },
  { prop: 'auditEvaluation', label: '审计评价', minWidth: 140, editable: true },
  { prop: 'remark', label: '备注', minWidth: 120, editable: true },
]

// ─── 内部存储类型 ─────────────────────────────────────────────────────────────

interface StoredRelatedPartyRow {
  rowId: string
  seq: number
  partyName: string
  relationship: string
  paymentNature: string
  openingBalance: number
  currentIncrease: number
  currentDecrease: number
  settlementCycle: string
  isOverdue: string
  fairness: string
  aging: string
  auditEvaluation: string
  remark: string
}

export interface UseF4RelatedPartyOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

// ─── 常量 ─────────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'F4-6-rows'
const NOTE_KEY = 'F4-6-note'
const CONCENTRATION_THRESHOLD = 30

// ─── 工具函数 ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `f4rp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function emptyStored(seq: number): StoredRelatedPartyRow {
  return {
    rowId: generateRowId(),
    seq,
    partyName: '',
    relationship: '',
    paymentNature: '',
    openingBalance: 0,
    currentIncrease: 0,
    currentDecrease: 0,
    settlementCycle: '',
    isOverdue: '否',
    fairness: '公允',
    aging: '',
    auditEvaluation: '',
    remark: '',
  }
}

function computeRow(stored: StoredRelatedPartyRow, totalClosing: number): RelatedPartyAPRow {
  const closingBalance = calcCreditBalance(stored.openingBalance, stored.currentIncrease, stored.currentDecrease)
  const concentration = calcConcentration(closingBalance, totalClosing)
  const isHighConcentration = concentration > CONCENTRATION_THRESHOLD
  return { ...stored, closingBalance, concentration, isHighConcentration }
}

function safeParseRows(jsonStr: string | null | undefined): StoredRelatedPartyRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any, i: number) => ({
      ...emptyStored(i + 1),
      rowId: raw.rowId || raw.id || generateRowId(),
      seq: raw.seq ?? i + 1,
      partyName: raw.partyName || '',
      relationship: raw.relationship || '',
      paymentNature: raw.paymentNature || '',
      openingBalance: parseNum(raw.openingBalance),
      currentIncrease: parseNum(raw.currentIncrease),
      currentDecrease: parseNum(raw.currentDecrease),
      settlementCycle: raw.settlementCycle || '',
      isOverdue: raw.isOverdue || '否',
      fairness: raw.fairness || '公允',
      aging: raw.aging || '',
      auditEvaluation: raw.auditEvaluation || '',
      remark: raw.remark || '',
    }))
  } catch {
    return []
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useF4RelatedParty(options: UseF4RelatedPartyOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const storedData = ref<StoredRelatedPartyRow[]>([])
  const auditNote = ref('')

  // ─── 加载 ─────────────────────────────────────────────────────────────────

  function loadRows(): void {
    storedData.value = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    if (storedData.value.length === 0) storedData.value = [emptyStored(1)]
  }

  watch(() => allResponses.value.get(STORAGE_KEY)?.remark, () => {
    if (storedData.value.length === 0) loadRows()
  }, { immediate: true })

  watch(() => allResponses.value.get(NOTE_KEY)?.remark, (v) => {
    auditNote.value = v || ''
  }, { immediate: true })

  // ─── 计算行 ───────────────────────────────────────────────────────────────

  /** 总期末余额用于计算各行占比 */
  const totalClosing = computed(() => {
    return calcSubtotal(
      storedData.value.map((r) => calcCreditBalance(r.openingBalance, r.currentIncrease, r.currentDecrease)),
    )
  })

  const rows: ComputedRef<RelatedPartyAPRow[]> = computed(() => {
    const t = totalClosing.value
    return storedData.value.map((r) => computeRow(r, t))
  })

  // ─── 汇总统计 ─────────────────────────────────────────────────────────────

  const summary = computed(() => ({
    totalClosing: totalClosing.value,
    overdueCount: rows.value.filter((r) => r.isOverdue === '是').length,
    highConcentrationCount: rows.value.filter((r) => r.isHighConcentration).length,
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
    const strFields = ['partyName', 'relationship', 'paymentNature', 'settlementCycle',
      'isOverdue', 'fairness', 'aging', 'auditEvaluation', 'remark']
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

  watch(auditNote, (val) => {
    allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
    debounceSave()
  })

  // ─── 样式 ─────────────────────────────────────────────────────────────────

  function rowClassName({ row }: { row: RelatedPartyAPRow }): string {
    return row.isHighConcentration ? 'concentration-warn' : ''
  }

  // ─── 清理 ─────────────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; flushSave() }
  })

  return {
    rows,
    totalClosing,
    summary,
    auditNote,
    addRow,
    removeRow,
    updateCell,
    rowClassName,
    columns: F4_RELATED_PARTY_COLUMNS,
  }
}

export default useF4RelatedParty
