/**
 * useG1Detail — G1-2 明细表（35列 → 5区段）
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  calcClosingQuantity,
  calcFairValue,
  calcFairValueChange,
  calcRealizedGain,
  calcAuditedAmount,
  calcSubtotal,
} from '../composables/useG1TraFinFormulaEngine'
import type { ChecklistResponse } from '../composables/useF1FormData'

export interface G1DetailRow {
  id: string
  securityName: string
  securityCode: string
  investType: string
  market: string
  acquisitionDate: string
  initialCost: number
  openingQty: number
  boughtQty: number
  soldQty: number
  closingQty: number
  openingCost: number
  addedCost: number
  reducedCost: number
  closingCost: number
  unitFv: number
  closingFv: number
  fvLevel: string
  openingFv: number
  fvChange: number
  disposalProceeds: number
  disposalCost: number
  realizedGain: number
  unadjusted: number
  aje: number
  rje: number
  adjusted: number
}

const DATA_KEY = 'G1-2-rows'

function emptyRow(id: string): G1DetailRow {
  return {
    id, securityName: '', securityCode: '', investType: 'stock', market: '',
    acquisitionDate: '', initialCost: 0, openingQty: 0, boughtQty: 0, soldQty: 0, closingQty: 0,
    openingCost: 0, addedCost: 0, reducedCost: 0, closingCost: 0, unitFv: 0, closingFv: 0,
    fvLevel: '1', openingFv: 0, fvChange: 0, disposalProceeds: 0, disposalCost: 0, realizedGain: 0,
    unadjusted: 0, aje: 0, rje: 0, adjusted: 0,
  }
}

function enrich(r: G1DetailRow): G1DetailRow {
  const closingQty = calcClosingQuantity(r.openingQty, r.boughtQty, r.soldQty)
  const closingCost = r.openingCost + r.addedCost - r.reducedCost
  const closingFv = calcFairValue(closingQty, r.unitFv)
  const fvChange = calcFairValueChange(closingFv, r.openingFv)
  const realizedGain = calcRealizedGain(r.disposalProceeds, r.disposalCost)
  const adjusted = calcAuditedAmount(r.unadjusted, r.aje, r.rje)
  return { ...r, closingQty, closingCost, closingFv, fvChange, realizedGain, adjusted }
}

function loadRows(map: Map<string, ChecklistResponse>): G1DetailRow[] {
  const raw = map.get(DATA_KEY)?.conclusion
  if (!raw) return [enrich(emptyRow('1'))]
  try {
    const parsed = JSON.parse(raw) as G1DetailRow[]
    return parsed.length ? parsed.map(enrich) : [enrich(emptyRow('1'))]
  } catch {
    return [enrich(emptyRow('1'))]
  }
}

export function useG1Detail(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const segment = ref<'basic' | 'holding' | 'fv' | 'pl' | 'adj'>('basic')
  const rows = ref<G1DetailRow[]>(loadRows(opts.allResponses.value))

  const totals = computed(() => ({
    closingCost: calcSubtotal(rows.value.map((r) => r.closingCost)),
    closingFv: calcSubtotal(rows.value.map((r) => r.closingFv)),
    adjusted: calcSubtotal(rows.value.map((r) => r.adjusted)),
  }))

  function persist() {
    if (!opts.isReadonly.value) opts.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value) })
  }

  function updateRow(id: string, patch: Partial<G1DetailRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? enrich({ ...r, ...patch }) : r))
    persist()
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('证券名称', '新增明细')
      rows.value = [...rows.value, enrich({ ...emptyRow(String(Date.now())), securityName: value })]
      persist()
    } catch { /* cancelled */ }
  }

  function removeRow(id: string) {
    if (opts.isReadonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.id !== id)
    persist()
  }

  return { segment, rows, totals, updateRow, addRow, removeRow }
}
