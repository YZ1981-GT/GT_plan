/**
 * useG10L3Reconciliation — G10-6 第三层次公允价值调节表（负债方向：新增/终止）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { parseNum, calcL3Reconciliation } from './useG10FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface G10L3Row {
  rowId: string
  seq: number
  liabilityName: string
  openingBalance: number
  currentNew: number
  currentTerminated: number
  transferIntoL3: number
  transferOutOfL3: number
  fairValueChange: number
  interestExpense: number
  otherChanges: number
  closingBalance: number
  reportedClosing: number
  variance: number
  remark: string
}

const ITEM_ID = 'G10-l3-rows'
function genId() { return `g10l3-${Date.now().toString(36)}` }

export function enrichG10L3Row(raw: Partial<G10L3Row> & { rowId: string }): G10L3Row {
  const opening = parseNum(raw.openingBalance)
  const currentNew = parseNum(raw.currentNew)
  const currentTerminated = parseNum(raw.currentTerminated)
  const transferIntoL3 = parseNum(raw.transferIntoL3)
  const transferOutOfL3 = parseNum(raw.transferOutOfL3)
  const fairValueChange = parseNum(raw.fairValueChange)
  const interestExpense = parseNum(raw.interestExpense)
  const otherChanges = parseNum(raw.otherChanges)
  const closingBalance = calcL3Reconciliation(
    opening, currentNew, currentTerminated,
    transferIntoL3, transferOutOfL3, fairValueChange, interestExpense, otherChanges,
  )
  const reportedClosing = parseNum(raw.reportedClosing ?? raw.closingBalance)
  return {
    rowId: raw.rowId,
    seq: parseNum(raw.seq) || 0,
    liabilityName: raw.liabilityName ?? '',
    openingBalance: opening,
    currentNew,
    currentTerminated,
    transferIntoL3,
    transferOutOfL3,
    fairValueChange,
    interestExpense,
    otherChanges,
    closingBalance,
    reportedClosing,
    variance: reportedClosing - closingBalance,
    remark: raw.remark ?? '',
  }
}

export function useG10L3Reconciliation(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const rows = ref<G10L3Row[]>([])

  watch(() => opts.allResponses.value.get(ITEM_ID)?.remark, (j) => {
    try {
      rows.value = j
        ? JSON.parse(j).map((r: any, i: number) => enrichG10L3Row({ ...r, rowId: r.rowId || genId(), seq: r.seq ?? i + 1 }))
        : []
    } catch { rows.value = [] }
  }, { immediate: true })

  const varianceRows = computed(() => rows.value.filter((r) => Math.abs(r.variance) > 0.01))

  function persist() {
    opts.debouncedSave(ITEM_ID, { remark: JSON.stringify(rows.value.map((r) => ({
      rowId: r.rowId, seq: r.seq, liabilityName: r.liabilityName,
      openingBalance: r.openingBalance, currentNew: r.currentNew, currentTerminated: r.currentTerminated,
      transferIntoL3: r.transferIntoL3, transferOutOfL3: r.transferOutOfL3,
      fairValueChange: r.fairValueChange, interestExpense: r.interestExpense, otherChanges: r.otherChanges,
      reportedClosing: r.reportedClosing, remark: r.remark,
    }))) })
  }

  function updateCell(rowId: string, field: keyof G10L3Row, value: unknown) {
    if (opts.isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const next = [...rows.value]
    next[idx] = enrichG10L3Row({ ...next[idx], [field]: value })
    rows.value = next
    persist()
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('负债名称', '新增L3调节行', { inputPattern: /\S+/ })
      const row = enrichG10L3Row({ rowId: genId(), seq: rows.value.length + 1, liabilityName: value ?? '' })
      rows.value = [...rows.value, row]
      persist()
    } catch { /* cancel */ }
  }

  function removeRow(rowId: string) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId).map((r, i) => enrichG10L3Row({ ...r, seq: i + 1 }))
    persist()
  }

  function reloadFromStore(): void {
    const j = opts.allResponses.value.get(ITEM_ID)?.remark
    try {
      rows.value = j
        ? JSON.parse(j).map((r: any, i: number) => enrichG10L3Row({ ...r, rowId: r.rowId || genId(), seq: r.seq ?? i + 1 }))
        : []
    } catch { rows.value = [] }
  }

  return {
    rows,
    varianceRows,
    updateCell,
    addRow,
    removeRow,
    reloadFromStore,
    persist,
    ITEM_ID,
  }
}
