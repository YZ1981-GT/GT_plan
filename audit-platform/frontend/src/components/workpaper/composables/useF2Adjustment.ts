/**
 * useF2Adjustment — F2-14 调整分录（10列）
 * Spec: .kiro/specs/f2-inventory-main/ Task 8.1
 * 比照 useD4Adjustment / useF3Adjustment
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal, isDebitCreditBalanced } from './useF2InvMaiFormulaEngine'
import type { ChecklistResponse } from './useF2FormData'

export interface F2AdjustmentRow {
  rowId: string
  seq: number
  summary: string
  accountCode: string
  accountName: string
  debitAmount: number
  creditAmount: number
  entryType: 'AJE' | 'RJE'
  indexRef: string
  remark: string
  noteItem: string
}

export const F2_INVENTORY_ACCOUNTS = [
  { code: '1401', name: '原材料' },
  { code: '1402', name: '材料采购在途' },
  { code: '1403', name: '周转材料' },
  { code: '1404', name: '自制半成品' },
  { code: '1405', name: '委托加工物资' },
  { code: '1406', name: '库存商品' },
  { code: '1407', name: '发出商品' },
  { code: '1408', name: '开发产品' },
  { code: '1409', name: '开发成本' },
  { code: '1410', name: '合同履约成本' },
  { code: '1411', name: '消耗性生物资产' },
  { code: '1412', name: '存货跌价准备' },
  { code: '5001', name: '主营业务成本' },
  { code: '6401', name: '主营业务成本' },
  { code: '6001', name: '主营业务收入' },
] as const

const STORAGE_KEY = 'F2-14-rows'

function generateRowId(): string {
  return `f2a-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function emptyRow(seq: number): F2AdjustmentRow {
  return {
    rowId: generateRowId(),
    seq,
    summary: '',
    accountCode: '1401',
    accountName: '原材料',
    debitAmount: 0,
    creditAmount: 0,
    entryType: 'AJE',
    indexRef: '',
    remark: '',
    noteItem: '',
  }
}

function safeParseRows(jsonStr: string | null | undefined): F2AdjustmentRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any, i: number) => ({
      ...emptyRow(i + 1),
      rowId: raw.rowId || raw.id || generateRowId(),
      seq: raw.seq ?? i + 1,
      summary: raw.summary || raw.description || '',
      accountCode: raw.accountCode || '1401',
      accountName: raw.accountName || '原材料',
      debitAmount: parseNum(raw.debitAmount),
      creditAmount: parseNum(raw.creditAmount),
      entryType: raw.entryType === 'RJE' ? 'RJE' : 'AJE',
      indexRef: raw.indexRef || '',
      remark: raw.remark || '',
      noteItem: raw.noteItem || '',
    }))
  } catch {
    return []
  }
}

export function useF2Adjustment(options: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const storedData = ref<F2AdjustmentRow[]>([])

  function loadRows(): void {
    storedData.value = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    if (storedData.value.length === 0) storedData.value = [emptyRow(1)]
  }

  watch(() => allResponses.value.get(STORAGE_KEY)?.remark, () => {
    if (storedData.value.length === 0) loadRows()
  }, { immediate: true })

  const rows: ComputedRef<F2AdjustmentRow[]> = computed(() => storedData.value)

  const debitTotal = computed(() => calcSubtotal(rows.value.map((r) => r.debitAmount)))
  const creditTotal = computed(() => calcSubtotal(rows.value.map((r) => r.creditAmount)))
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)
  const isBalanced = computed(() =>
    isDebitCreditBalanced(
      rows.value.map((r) => r.debitAmount),
      rows.value.map((r) => r.creditAmount),
    ),
  )

  function publishAdjustments(): void {
    for (const row of rows.value) {
      if (row.debitAmount === 0 && row.creditAmount === 0) continue
      try {
        window.dispatchEvent(new CustomEvent('adjustment:created', {
          detail: {
            wpCode: 'F2',
            entryType: row.entryType,
            amount: Math.max(row.debitAmount, row.creditAmount),
            accountCode: row.accountCode,
            accountName: row.accountName,
            description: row.summary,
          },
        }))
      } catch { /* silent */ }
    }
  }

  function persistRows(): void {
    allResponses.value.set(STORAGE_KEY, {
      item_id: STORAGE_KEY,
      conclusion: null,
      remark: JSON.stringify(storedData.value),
    })
    debounceSave()
    publishAdjustments()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function flushSave(): void {
    const item = allResponses.value.get(STORAGE_KEY)
    if (item) window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items: [item] } }))
  }

  function addRow(): void {
    if (readonly.value) return
    storedData.value.push(emptyRow(storedData.value.length + 1))
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

    if (field === 'accountCode') {
      row.accountCode = String(value ?? '')
      const acc = F2_INVENTORY_ACCOUNTS.find((a) => a.code === row.accountCode)
      if (acc) row.accountName = acc.name
    } else if (field === 'accountName') {
      row.accountName = String(value ?? '')
      const acc = F2_INVENTORY_ACCOUNTS.find((a) => a.name === row.accountName)
      if (acc) row.accountCode = acc.code
    } else if (field === 'debitAmount' || field === 'creditAmount') {
      ;(row as any)[field] = parseNum(value)
    } else if (field === 'entryType') {
      row.entryType = value === 'RJE' ? 'RJE' : 'AJE'
    } else {
      ;(row as any)[field] = String(value ?? '')
    }
    persistRows()
  }

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; flushSave() }
  })

  return {
    rows,
    debitTotal,
    creditTotal,
    balanceDiff,
    isBalanced,
    accountOptions: F2_INVENTORY_ACCOUNTS,
    addRow,
    removeRow,
    updateCell,
    publishAdjustments,
  }
}

export default useF2Adjustment
