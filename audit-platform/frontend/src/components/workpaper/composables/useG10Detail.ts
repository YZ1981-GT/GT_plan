/**
 * useG10Detail — G10-2 明细表（24列 → 2区段 Tab）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { G10_LIABILITY_TYPE_OPTIONS, G10_FV_LEVEL_OPTIONS } from './g10Constants'
import {
  parseNum,
  calcCreditBalance,
  calcAdjustedAmount,
  calcSubtotal,
} from './useG10FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface G10DetailRow {
  rowId: string
  seq: number
  liabilityName: string
  liabilityType: string
  counterparty: string
  contractDate: string
  maturityDate: string
  initialAmount: number
  openingBalance: number
  openingAdjusted: number
  currentIncrease: number
  currentDecrease: number
  closingBalance: number
  closingAdjusted: number
  fairValueLevel: string
  valuationMethod: string
  openingFairValue: number
  closingFairValue: number
  fairValueChange: number
  profitLossAmount: number
  isDerivative: boolean
  hostContractDesc: string
  embeddedDerivativeJudgment: string
  confirmationStatus: string
  remark: string
}

const ITEM_ID_ROWS = 'G10-detail-rows'

function genId(): string {
  return `g10d-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
}

export function enrichG10DetailRow(raw: Partial<G10DetailRow> & { rowId: string }, seq: number): G10DetailRow {
  const openingAdjusted = parseNum(raw.openingAdjusted ?? raw.openingBalance)
  const currentIncrease = parseNum(raw.currentIncrease)
  const currentDecrease = parseNum(raw.currentDecrease)
  const closingBalance = calcCreditBalance(openingAdjusted, currentIncrease, currentDecrease)
  const closingAdjustment = parseNum((raw as any).closingAdjustment)
  const closingAdjusted = calcAdjustedAmount(closingBalance, closingAdjustment)
  const openingFv = parseNum(raw.openingFairValue)
  const closingFv = parseNum(raw.closingFairValue)
  return {
    rowId: raw.rowId,
    seq,
    liabilityName: raw.liabilityName ?? '',
    liabilityType: raw.liabilityType ?? G10_LIABILITY_TYPE_OPTIONS[0],
    counterparty: raw.counterparty ?? '',
    contractDate: raw.contractDate ?? '',
    maturityDate: raw.maturityDate ?? '',
    initialAmount: parseNum(raw.initialAmount),
    openingBalance: parseNum(raw.openingBalance),
    openingAdjusted,
    currentIncrease,
    currentDecrease,
    closingBalance,
    closingAdjusted,
    fairValueLevel: raw.fairValueLevel ?? 'Level2',
    valuationMethod: raw.valuationMethod ?? '',
    openingFairValue: openingFv,
    closingFairValue: closingFv,
    fairValueChange: closingFv - openingFv,
    profitLossAmount: parseNum(raw.profitLossAmount),
    isDerivative: !!raw.isDerivative,
    hostContractDesc: raw.hostContractDesc ?? '',
    embeddedDerivativeJudgment: raw.embeddedDerivativeJudgment ?? '',
    confirmationStatus: raw.confirmationStatus ?? '',
    remark: raw.remark ?? '',
  }
}

function parseRows(json: string | null | undefined): G10DetailRow[] {
  if (!json) return []
  try {
    const arr = JSON.parse(json)
    if (!Array.isArray(arr)) return []
    return arr.map((r: any, i: number) => enrichG10DetailRow({ ...r, rowId: r.rowId || r.id || genId() }, i + 1))
  } catch {
    return []
  }
}

export function useG10Detail(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const rows = ref<G10DetailRow[]>([])
  const activeTab = ref<'basic' | 'fv'>('basic')
  const activeRowIndex = ref(0)

  watch(
    () => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (json) => { rows.value = parseRows(json) },
    { immediate: true },
  )

  function persist(): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
    try {
      window.dispatchEvent(new CustomEvent('g10:detail-updated'))
    } catch { /* silent */ }
  }

  function updateRow(rowId: string, patch: Partial<G10DetailRow>): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r, i) =>
      r.rowId === rowId ? enrichG10DetailRow({ ...r, ...patch, rowId }, i + 1) : r,
    )
    persist()
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入负债名称', '新增明细行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
      })
      if (!value?.trim()) return
      rows.value = [...rows.value, enrichG10DetailRow({ rowId: genId(), liabilityName: value.trim() }, rows.value.length + 1)]
      persist()
    } catch { /* cancelled */ }
  }

  function removeRow(rowId: string): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value
      .filter((r) => r.rowId !== rowId)
      .map((r, i) => enrichG10DetailRow(r, i + 1))
    persist()
  }

  function reloadFromStore(): void {
    rows.value = parseRows(opts.allResponses.value.get(ITEM_ID_ROWS)?.remark)
  }

  function setActiveRowIndex(index: number): void {
    activeRowIndex.value = index
  }

  const totalRow = computed(() => ({
    closingAdjusted: calcSubtotal(rows.value.map((r) => r.closingAdjusted)),
    openingAdjusted: calcSubtotal(rows.value.map((r) => r.openingAdjusted)),
    closingFairValue: calcSubtotal(rows.value.map((r) => r.closingFairValue)),
    profitLossAmount: calcSubtotal(rows.value.map((r) => r.profitLossAmount)),
  }))

  return {
    rows,
    activeTab,
    activeRowIndex,
    totalRow,
    G10_LIABILITY_TYPE_OPTIONS,
    G10_FV_LEVEL_OPTIONS,
    updateRow,
    addRow,
    removeRow,
    reloadFromStore,
    setActiveRowIndex,
    ITEM_ID_ROWS,
  }
}
