/**
 * useG9Detail — G9-2 明细表（28列 → 3区段 Tab）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { G9_CLASSIFICATION_OPTIONS, G9_FV_LEVEL_OPTIONS } from './g9Constants'
import { parseNum, calcAdjustedAmount, calcEndingBalance, calcSubtotal } from './useG9FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface G9DetailRow {
  rowId: string
  seq: number
  assetName: string
  classification: string
  initialInvestDate: string
  maturityDate: string
  holdingQuantity: number
  faceValueOrCost: number
  measurementAttribute: string
  isRelatedParty: boolean
  openingBalance: number
  openingAdjustment: number
  openingAdjusted: number
  increaseAmount: number
  decreaseAmount: number
  fvChangeAmount: number
  interestIncome: number
  impairmentLoss: number
  ociChange: number
  closingBalance: number
  closingAdjustment: number
  closingAdjusted: number
  fairValueLevel: string
  valuationMethod: string
  confirmationStatus: string
  ociCumulative: number
  impairmentProvision: number
  remark: string
}

const ITEM_ID_ROWS = 'G9-detail-rows'

function genId(): string {
  return `g9d-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
}

export function enrichG9DetailRow(raw: Partial<G9DetailRow> & { rowId: string }, seq: number): G9DetailRow {
  const openingAdjusted = calcAdjustedAmount(
    parseNum(raw.openingBalance),
    parseNum(raw.openingAdjustment),
    0,
  )
  const closingBalance = calcEndingBalance(
    openingAdjusted,
    parseNum(raw.increaseAmount),
    parseNum(raw.decreaseAmount),
    parseNum(raw.fvChangeAmount),
    parseNum(raw.interestIncome),
    parseNum(raw.impairmentLoss),
  )
  const closingAdjusted = calcAdjustedAmount(closingBalance, parseNum(raw.closingAdjustment), 0)
  return {
    rowId: raw.rowId,
    seq,
    assetName: raw.assetName ?? '',
    classification: raw.classification ?? G9_CLASSIFICATION_OPTIONS[0],
    initialInvestDate: raw.initialInvestDate ?? '',
    maturityDate: raw.maturityDate ?? '',
    holdingQuantity: parseNum(raw.holdingQuantity),
    faceValueOrCost: parseNum(raw.faceValueOrCost),
    measurementAttribute: raw.measurementAttribute ?? '',
    isRelatedParty: !!raw.isRelatedParty,
    openingBalance: parseNum(raw.openingBalance),
    openingAdjustment: parseNum(raw.openingAdjustment),
    openingAdjusted,
    increaseAmount: parseNum(raw.increaseAmount),
    decreaseAmount: parseNum(raw.decreaseAmount),
    fvChangeAmount: parseNum(raw.fvChangeAmount),
    interestIncome: parseNum(raw.interestIncome),
    impairmentLoss: parseNum(raw.impairmentLoss),
    ociChange: parseNum(raw.ociChange),
    closingBalance,
    closingAdjustment: parseNum(raw.closingAdjustment),
    closingAdjusted,
    fairValueLevel: raw.fairValueLevel ?? G9_FV_LEVEL_OPTIONS[1],
    valuationMethod: raw.valuationMethod ?? '',
    confirmationStatus: raw.confirmationStatus ?? '',
    ociCumulative: parseNum(raw.ociCumulative),
    impairmentProvision: parseNum(raw.impairmentProvision),
    remark: raw.remark ?? '',
  }
}

function parseRows(json: string | null | undefined): G9DetailRow[] {
  if (!json) return []
  try {
    const arr = JSON.parse(json)
    if (!Array.isArray(arr)) return []
    return arr.map((r: any, i: number) => enrichG9DetailRow({ ...r, rowId: r.rowId || r.id || genId() }, i + 1))
  } catch {
    return []
  }
}

export function useG9Detail(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const activeTab = ref('basic')
  const activeRowIndex = ref(0)

  const rows = computed(() => parseRows(opts.allResponses.value.get(ITEM_ID_ROWS)?.remark))

  const classificationSubtotals = computed(() => {
    const result: Record<string, number> = {}
    for (const cls of G9_CLASSIFICATION_OPTIONS) {
      const filtered = rows.value.filter((r) => r.classification === cls)
      result[cls] = calcSubtotal(filtered.map((r) => r.closingAdjusted))
    }
    result['总计'] = calcSubtotal(rows.value.map((r) => r.closingAdjusted))
    return result
  })

  function persist(list: G9DetailRow[]): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(list) })
  }

  function updateRow(rowId: string, patch: Partial<G9DetailRow>): void {
    if (opts.isReadonly.value) return
    const list = rows.value.map((r) => (r.rowId === rowId ? enrichG9DetailRow({ ...r, ...patch, rowId }, r.seq) : r))
    persist(list)
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入资产名称', '新增明细行', { inputPlaceholder: '资产名称' })
      const name = (value ?? '').trim()
      if (!name) return
      const list = [...rows.value, enrichG9DetailRow({ rowId: genId(), assetName: name }, rows.value.length + 1)]
      persist(list)
    } catch { /* cancelled */ }
  }

  function removeRow(rowId: string): void {
    if (opts.isReadonly.value) return
    const list = rows.value.filter((r) => r.rowId !== rowId).map((r, i) => enrichG9DetailRow(r, i + 1))
    persist(list)
  }

  watch(activeTab, () => { /* row sync via activeRowIndex */ })

  return {
    rows,
    activeTab,
    activeRowIndex,
    classificationSubtotals,
    updateRow,
    addRow,
    removeRow,
    classificationOptions: G9_CLASSIFICATION_OPTIONS,
    fvLevelOptions: G9_FV_LEVEL_OPTIONS,
  }
}
