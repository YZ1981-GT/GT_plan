/**
 * useG8Detail — G8-2 明细表（24列 → 2区段 Tab）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { G8_FV_LEVEL_OPTIONS, G8_VALUATION_METHOD_OPTIONS } from './g8Constants'
import { parseNum, calcAdjustedAmount, calcEndingBalance, calcSubtotal } from './useG8FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface G8DetailRow {
  rowId: string
  seq: number
  investeeName: string
  investmentRatio: number
  openingBalance: number
  openingAdjustment: number
  openingAdjusted: number
  increaseAmount: number
  decreaseAmount: number
  fvChangeAmount: number
  closingBalance: number
  closingAdjustment: number
  closingAdjusted: number
  designationReason: string
  ociCumulativeChange: number
  ociCurrentChange: number
  ociToRetainedEarnings: number
  transferReason: string
  confirmationStatus: string
  fairValueLevel: string
  valuationMethod: string
  shareCount: number
  pricePerShare: number
  fairValueTotal: number
  remark: string
}

const ITEM_ID_ROWS = 'G8-detail-rows'

function genId(): string {
  return `g8d-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
}

export function enrichG8DetailRow(raw: Partial<G8DetailRow> & { rowId: string }, seq: number): G8DetailRow {
  const openingAdjusted = calcAdjustedAmount(parseNum(raw.openingBalance), parseNum(raw.openingAdjustment))
  const closingBalance = calcEndingBalance(
    openingAdjusted,
    parseNum(raw.increaseAmount),
    parseNum(raw.decreaseAmount),
    parseNum(raw.fvChangeAmount),
  )
  const closingAdjusted = calcAdjustedAmount(closingBalance, parseNum(raw.closingAdjustment))
  return {
    rowId: raw.rowId,
    seq,
    investeeName: raw.investeeName ?? '',
    investmentRatio: parseNum(raw.investmentRatio),
    openingBalance: parseNum(raw.openingBalance),
    openingAdjustment: parseNum(raw.openingAdjustment),
    openingAdjusted,
    increaseAmount: parseNum(raw.increaseAmount),
    decreaseAmount: parseNum(raw.decreaseAmount),
    fvChangeAmount: parseNum(raw.fvChangeAmount),
    closingBalance,
    closingAdjustment: parseNum(raw.closingAdjustment),
    closingAdjusted,
    designationReason: raw.designationReason ?? '',
    ociCumulativeChange: parseNum(raw.ociCumulativeChange),
    ociCurrentChange: parseNum(raw.ociCurrentChange),
    ociToRetainedEarnings: parseNum(raw.ociToRetainedEarnings),
    transferReason: raw.transferReason ?? '',
    confirmationStatus: raw.confirmationStatus ?? '',
    fairValueLevel: raw.fairValueLevel ?? G8_FV_LEVEL_OPTIONS[1],
    valuationMethod: raw.valuationMethod ?? '',
    shareCount: parseNum(raw.shareCount),
    pricePerShare: parseNum(raw.pricePerShare),
    fairValueTotal: parseNum(raw.fairValueTotal),
    remark: raw.remark ?? '',
  }
}

function parseRows(json: string | null | undefined): G8DetailRow[] {
  if (!json) return []
  try {
    const arr = JSON.parse(json)
    if (!Array.isArray(arr)) return []
    return arr.map((r: any, i: number) => enrichG8DetailRow({ ...r, rowId: r.rowId || r.id || genId() }, i + 1))
  } catch {
    return []
  }
}

export function useG8Detail(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const activeTab = ref<'basic' | 'fv_oci'>('basic')
  const activeRowIndex = ref(0)

  const rows = computed(() => parseRows(opts.allResponses.value.get(ITEM_ID_ROWS)?.remark))

  const totals = computed(() => ({
    openingAdjusted: calcSubtotal(rows.value.map((r) => r.openingAdjusted)),
    increaseAmount: calcSubtotal(rows.value.map((r) => r.increaseAmount)),
    decreaseAmount: calcSubtotal(rows.value.map((r) => r.decreaseAmount)),
    fvChangeAmount: calcSubtotal(rows.value.map((r) => r.fvChangeAmount)),
    closingBalance: calcSubtotal(rows.value.map((r) => r.closingBalance)),
    closingAdjusted: calcSubtotal(rows.value.map((r) => r.closingAdjusted)),
    ociCurrentChange: calcSubtotal(rows.value.map((r) => r.ociCurrentChange)),
    fairValueTotal: calcSubtotal(rows.value.map((r) => r.fairValueTotal)),
  }))

  function persist(list: G8DetailRow[]): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(list) })
  }

  function updateRow(rowId: string, patch: Partial<G8DetailRow>): void {
    if (opts.isReadonly.value) return
    const list = rows.value.map((r) => (r.rowId === rowId ? enrichG8DetailRow({ ...r, ...patch, rowId }, r.seq) : r))
    persist(list)
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入被投资单位名称', '新增明细行', { inputPlaceholder: '被投资单位名称' })
      const name = (value ?? '').trim()
      if (!name) return
      const list = [...rows.value, enrichG8DetailRow({ rowId: genId(), investeeName: name }, rows.value.length + 1)]
      persist(list)
    } catch { /* cancelled */ }
  }

  function removeRow(rowId: string): void {
    if (opts.isReadonly.value) return
    const list = rows.value.filter((r) => r.rowId !== rowId).map((r, i) => enrichG8DetailRow(r, i + 1))
    persist(list)
  }

  watch(activeTab, () => { /* row sync via activeRowIndex */ })

  return {
    rows,
    activeTab,
    activeRowIndex,
    totals,
    updateRow,
    addRow,
    removeRow,
    fvLevelOptions: G8_FV_LEVEL_OPTIONS,
    valuationMethodOptions: G8_VALUATION_METHOD_OPTIONS,
  }
}
