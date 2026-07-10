/**
 * useD2RelatedParty — 关联方D2-6核心逻辑 composable
 *
 * Spec: .kiro/specs/d2-accounts-receivable-refactor/
 * Task: 10.1
 *
 * 职责：
 * - RelatedPartyRow 类型定义（12列）
 * - rows reactive + totalRow computed (SUMs)
 * - addRow / removeRow 动态行管理
 * - importFromDetail() — 从D2-2筛选关联方客户导入
 * - 行公式: endBalance = prior + debit - credit; bookValue = endBalance - badDebt
 * - updateCell + debounce 2s 保存
 *
 * Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
 */
import { ref, computed, watch, onBeforeUnmount, type ComputedRef } from 'vue'
import { parseNum } from './useD2FormulaEngine'
import type { UseD2BaseOptions } from './useD2Adjudication'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface RelatedPartyRow {
  rowId: string
  debtorName: string           // 关联方名称
  relationType: string         // 关联关系类型
  transactionType: string      // 交易类型
  priorBalance: number         // 期初余额
  debitAmount: number          // 本期借方发生额
  creditAmount: number         // 本期贷方发生额
  endBalance: number           // 期末余额 = prior + debit - credit
  badDebtProvision: number     // 坏账准备
  bookValue: number            // 账面价值 = endBalance - badDebt
  isArmsLength: string         // 是否公允交易 (Y/N)
  remark: string               // 备注
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY = 'D2-related-party-rows'
const NOTE_KEY = 'D2-related-party-note'
const CONCLUSION_KEY = 'D2-related-party-conclusion'

/** 需要SUM求和的金额字段 */
const NUMERIC_SUM_FIELDS: (keyof RelatedPartyRow)[] = [
  'priorBalance', 'debitAmount', 'creditAmount',
  'endBalance', 'badDebtProvision', 'bookValue',
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `rp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function createEmptyRow(): RelatedPartyRow {
  return {
    rowId: generateRowId(),
    debtorName: '',
    relationType: '',
    transactionType: '',
    priorBalance: 0,
    debitAmount: 0,
    creditAmount: 0,
    endBalance: 0,
    badDebtProvision: 0,
    bookValue: 0,
    isArmsLength: '',
    remark: '',
  }
}

/** 行公式重算 */
function recalcRow(row: RelatedPartyRow): RelatedPartyRow {
  row.endBalance = row.priorBalance + row.debitAmount - row.creditAmount
  row.bookValue = row.endBalance - row.badDebtProvision
  return row
}

function parseRows(jsonStr: string | null | undefined): RelatedPartyRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any) => recalcRow({
      rowId: raw.rowId || generateRowId(),
      debtorName: raw.debtorName || '',
      relationType: raw.relationType || '',
      transactionType: raw.transactionType || '',
      priorBalance: parseNum(raw.priorBalance),
      debitAmount: parseNum(raw.debitAmount),
      creditAmount: parseNum(raw.creditAmount),
      endBalance: parseNum(raw.endBalance),
      badDebtProvision: parseNum(raw.badDebtProvision),
      bookValue: parseNum(raw.bookValue),
      isArmsLength: raw.isArmsLength || '',
      remark: raw.remark || '',
    }))
  } catch {
    return []
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD2RelatedParty(options: UseD2BaseOptions) {
  const { allResponses, isReadonly } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const rows = ref<RelatedPartyRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Load from allResponses ────────────────────────────────────────────

  function loadRows(): void {
    const resp = allResponses.value.get(STORAGE_KEY)
    rows.value = parseRows(resp?.remark)
    auditNote.value = allResponses.value.get(NOTE_KEY)?.remark ?? ''
    auditConclusion.value = allResponses.value.get(CONCLUSION_KEY)?.remark ?? ''
  }

  watch(
    () => allResponses.value.get(STORAGE_KEY)?.remark,
    () => {
      if (rows.value.length === 0) {
        loadRows()
      }
    },
    { immediate: true }
  )

  // ─── Total Row ─────────────────────────────────────────────────────────

  const totalRow: ComputedRef<Pick<RelatedPartyRow, 'priorBalance' | 'debitAmount' | 'creditAmount' | 'endBalance' | 'badDebtProvision' | 'bookValue'>> = computed(() => {
    const result: any = {}
    for (const field of NUMERIC_SUM_FIELDS) {
      result[field] = rows.value.reduce((sum, r) => sum + parseNum((r as any)[field]), 0)
    }
    return result
  })

  // ─── Import from D2-2 Detail ───────────────────────────────────────────

  /**
   * 从D2-2明细表筛选关联方客户（relationType≠'非关联方'）导入
   */
  function importFromDetail(): void {
    if (isReadonly.value) return

    const detailJson = allResponses.value.get('D2-detail-rows')?.remark
    if (!detailJson) return

    try {
      const detailRows = JSON.parse(detailJson)
      if (!Array.isArray(detailRows)) return

      const filtered = detailRows.filter(
        (row: any) => {
          const rel = row.relationType || ''
          return rel !== '' && rel !== '非关联方'
        }
      )

      const imported: RelatedPartyRow[] = filtered.map((row: any) => {
        const newRow = createEmptyRow()
        newRow.debtorName = row.debtorName || row.clientName || ''
        newRow.relationType = row.relationType || ''
        newRow.priorBalance = parseNum(row.priorAudited)
        newRow.endBalance = parseNum(row.currentAudited ?? row.auditedBalance)
        return recalcRow(newRow)
      })

      if (imported.length > 0) {
        rows.value = [...rows.value, ...imported]
        debounceSave()
      }
    } catch {
      // silent
    }
  }

  // ─── Row Management ────────────────────────────────────────────────────

  function addRow(): void {
    if (isReadonly.value) return
    rows.value.push(createEmptyRow())
    debounceSave()
  }

  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)
    debounceSave()
  }

  // ─── Update Cell ───────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    if (isReadonly.value) return
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    const key = field as keyof RelatedPartyRow
    if (key === 'rowId') return

    if (NUMERIC_SUM_FIELDS.includes(key) && key !== 'endBalance' && key !== 'bookValue') {
      ;(row as any)[key] = parseNum(value)
    } else if (key !== 'endBalance' && key !== 'bookValue') {
      ;(row as any)[key] = String(value)
    }

    recalcRow(row)
    debounceSave()
  }

  // ─── Serialization & Save ──────────────────────────────────────────────

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function flushSave(): void {
    const json = JSON.stringify(rows.value)
    allResponses.value.set(STORAGE_KEY, {
      item_id: STORAGE_KEY,
      conclusion: null,
      remark: json,
    })
    dispatchSaveEvent(json)
  }

  function dispatchSaveEvent(json: string): void {
    try {
      const items = [{ item_id: STORAGE_KEY, conclusion: null, remark: json }]
      window.dispatchEvent(new CustomEvent('d2:save-items', { detail: { items } }))
    } catch {
      // silent
    }
  }

  function saveText(key: string, value: string): void {
    if (isReadonly.value) return
    const item = { item_id: key, conclusion: null, remark: value }
    allResponses.value.set(key, item)
    try {
      window.dispatchEvent(new CustomEvent('d2:save-items', { detail: { items: [item] } }))
    } catch { /* silent */ }
  }

  function saveAuditNote(value: string): void {
    auditNote.value = value
    saveText(NOTE_KEY, value)
  }

  function saveAuditConclusion(value: string): void {
    auditConclusion.value = value
    saveText(CONCLUSION_KEY, value)
  }

  // ─── Lifecycle ─────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    rows,
    totalRow,
    auditNote,
    auditConclusion,
    addRow,
    removeRow,
    updateCell,
    importFromDetail,
    loadRows,
    saveAuditNote,
    saveAuditConclusion,
  }
}

export default useD2RelatedParty
