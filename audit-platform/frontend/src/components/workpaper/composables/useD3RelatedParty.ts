/**
 * useD3RelatedParty — D3-6 关联关系及交易检查表核心逻辑 composable
 *
 * Spec: .kiro/specs/d3-prepaid-accounts/
 * Task: 12.1
 *
 * 职责：
 * - 定义 RelatedPartyRow 类型（10列）
 * - rows reactive（从D3-rp-rows加载JSON）
 * - 从crossSheet.relatedPartyRows导入功能
 * - 行内公式（期末=期初+贷方-借方）
 * - subtotalRow computed
 * - addRow/removeRow/updateCell
 * - auditNote/conclusion 双向绑定
 *
 * Requirements: 10.1-10.9
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal, calcRelatedPartyEndBalance } from './useD3FormulaEngine'
import type { ChecklistResponse } from './useD3FormData'
import type { RelatedPartyImportRow } from './useD3CrossSheet'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface RelatedPartyRow {
  rowId: string
  partyName: string          // 关联方名称
  relationship: string       // 关联关系
  priorBalance: number       // 期初余额
  debit: number              // 借方发生
  credit: number             // 贷方发生
  endBalance: number         // 期末余额 = 期初 + 贷方 - 借方
  agingDescription: string   // 发生时间及账龄
  natureDescription: string  // 发生原因（款项性质）
  indexRef: string           // 索引号
  remark: string             // 备注
}

export interface UseD3RelatedPartyOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'D3-rp-rows'
const ITEM_ID_NOTE = 'D3-rp-note'
const ITEM_ID_CONCLUSION = 'D3-rp-conclusion'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `row-${crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2)}`
}

function safeParseRows(jsonStr: string | null | undefined): RelatedPartyRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed.map(normalizeRow) : []
  } catch {
    return []
  }
}

function normalizeRow(raw: any): RelatedPartyRow {
  const prior = parseNum(raw.priorBalance)
  const debit = parseNum(raw.debit)
  const credit = parseNum(raw.credit)
  return {
    rowId: raw.rowId || generateRowId(),
    partyName: raw.partyName || '',
    relationship: raw.relationship || '',
    priorBalance: prior,
    debit,
    credit,
    endBalance: calcRelatedPartyEndBalance(prior, credit, debit),
    agingDescription: raw.agingDescription || '',
    natureDescription: raw.natureDescription || '',
    indexRef: raw.indexRef || '',
    remark: raw.remark || '',
  }
}

function createEmptyRow(): RelatedPartyRow {
  return {
    rowId: generateRowId(),
    partyName: '',
    relationship: '',
    priorBalance: 0,
    debit: 0,
    credit: 0,
    endBalance: 0,
    agingDescription: '',
    natureDescription: '',
    indexRef: '',
    remark: '',
  }
}

/** 对单行重新计算期末余额公式 */
function recalcRow(row: RelatedPartyRow): RelatedPartyRow {
  return {
    ...row,
    endBalance: calcRelatedPartyEndBalance(row.priorBalance, row.credit, row.debit),
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD3RelatedParty(options: UseD3RelatedPartyOptions) {
  const { allResponses, debouncedSave, isReadonly } = options

  // ─── Reactive rows ───────────────────────────────────────────────────

  const rows = ref<RelatedPartyRow[]>([])

  watch(
    () => allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (jsonStr) => { rows.value = safeParseRows(jsonStr) },
    { immediate: true },
  )

  // ─── Persist ─────────────────────────────────────────────────────────

  function persistRows(): void {
    debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  // ─── subtotalRow computed ────────────────────────────────────────────

  const subtotalRow: ComputedRef<{ priorBalance: number; debit: number; credit: number; endBalance: number }> = computed(() => {
    return {
      priorBalance: calcSubtotal(rows.value.map(r => r.priorBalance)),
      debit: calcSubtotal(rows.value.map(r => r.debit)),
      credit: calcSubtotal(rows.value.map(r => r.credit)),
      endBalance: calcSubtotal(rows.value.map(r => r.endBalance)),
    }
  })

  // ─── Import from crossSheet ──────────────────────────────────────────

  function importFromCrossSheet(relatedPartyRows: RelatedPartyImportRow[]): void {
    if (isReadonly.value) return
    if (relatedPartyRows.length === 0) return

    const imported: RelatedPartyRow[] = relatedPartyRows.map(r => {
      const prior = r.priorAudited
      const debit = r.debit
      const credit = r.credit
      return {
        rowId: generateRowId(),
        partyName: r.customerName,
        relationship: r.relationType,
        priorBalance: prior,
        debit,
        credit,
        endBalance: calcRelatedPartyEndBalance(prior, credit, debit),
        agingDescription: '',
        natureDescription: '',
        indexRef: '',
        remark: '',
      }
    })

    rows.value = [...rows.value, ...imported]
    persistRows()
  }

  // ─── addRow / removeRow / updateCell ─────────────────────────────────

  function addRow(): void {
    if (isReadonly.value) return
    rows.value = [...rows.value, createEmptyRow()]
    persistRows()
  }

  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    rows.value = rows.value.filter(r => r.rowId !== rowId)
    persistRows()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return

    const row = { ...rows.value[idx] }
    if (['priorBalance', 'debit', 'credit'].includes(field)) {
      ;(row as any)[field] = parseNum(value)
    } else {
      ;(row as any)[field] = value
    }

    // Recalculate endBalance formula
    const recalculated = recalcRow(row)

    const newRows = [...rows.value]
    newRows[idx] = recalculated
    rows.value = newRows
    persistRows()
  }

  // ─── Audit Note / Conclusion ─────────────────────────────────────────

  const auditNote = ref('')
  const conclusion = ref('')

  watch(
    () => allResponses.value.get(ITEM_ID_NOTE)?.remark,
    (val) => { auditNote.value = val || '' },
    { immediate: true },
  )

  watch(
    () => allResponses.value.get(ITEM_ID_CONCLUSION)?.remark,
    (val) => { conclusion.value = val || '' },
    { immediate: true },
  )

  watch(() => auditNote.value, (val) => { debouncedSave(ITEM_ID_NOTE, { remark: val }) })
  watch(() => conclusion.value, (val) => { debouncedSave(ITEM_ID_CONCLUSION, { remark: val }) })

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    rows,
    subtotalRow,
    auditNote,
    conclusion,
    addRow,
    removeRow,
    updateCell,
    importFromCrossSheet,
  }
}

export default useD3RelatedParty
