/**
 * useF2DetailSummary — F2-2 明细汇总表（从 F2-3~13 聚合，含 F2-10 开发产品）
 * Spec: .kiro/specs/f2-inventory-main/ Req 4.1~4.6
 */
import { computed, type Ref } from 'vue'
import { calcSubtotal, calcUnitPrice } from './useF2InvMaiFormulaEngine'
import { readRowJson, type ChecklistResponse } from './useF2FormData'
import { F2_DETAIL_SHEET_CONFIGS } from '../f2/detail/f2DetailSheetConfigs'
import type { F2DetailRow } from './useF2DetailSheet'
import type { DevProductRow } from './useF2DevProductSheet'

export interface F2SummaryRow {
  sheetCode: string
  label: string
  hasQuantity: boolean
  openingQty: number
  openingUnitPrice: number | ''
  openingAmt: number
  increaseQty: number
  increaseUnitPrice: number | ''
  increaseAmt: number
  decreaseQty: number
  decreaseUnitPrice: number | ''
  decreaseAmt: number
  closingQty: number
  closingUnitPrice: number | ''
  closingAmt: number
  agingLt1: number
  aging1to2: number
  aging2to3: number
  agingGt3: number
  agingTotal: number
  agingMismatch: boolean
}

function fmtPrice(amt: number, qty: number, hasQuantity: boolean): number | '' {
  if (!hasQuantity) return amt ? calcUnitPrice(amt, 1) : ''
  return calcUnitPrice(amt, qty)
}

function loadDevProductTotals(map: Map<string, ChecklistResponse>): Omit<F2SummaryRow, 'sheetCode' | 'label' | 'hasQuantity'> {
  const raw = readRowJson(map.get('F2-10-rows'))
  if (!raw) {
    return emptyTotals()
  }
  try {
    const rows = JSON.parse(raw) as DevProductRow[]
    const openingAmt = calcSubtotal(rows.map((r) => r.landOpen + r.buildOpen + r.intOpen + r.otherOpen))
    const increaseAmt = calcSubtotal(rows.map((r) => r.landIn + r.buildIn + r.intIn + r.otherIn))
    const decreaseAmt = calcSubtotal(rows.map((r) => r.landOut + r.buildOut + r.intOut + r.otherOut + r.transferOut))
    const closingAmt = calcSubtotal(rows.map((r) => {
      const land = r.landOpen + r.landIn - r.landOut
      const build = r.buildOpen + r.buildIn - r.buildOut
      const int = r.intOpen + r.intIn - r.intOut
      const other = r.otherOpen + r.otherIn - r.otherOut
      return land + build + int + other - r.transferOut
    }))
    const agingLt1 = calcSubtotal(rows.map((r) => r.agingLt1))
    const aging1to2 = calcSubtotal(rows.map((r) => r.aging1to2))
    const aging2to3 = calcSubtotal(rows.map((r) => r.aging2to3))
    const agingGt3 = calcSubtotal(rows.map((r) => r.agingGt3))
    const agingTotal = agingLt1 + aging1to2 + aging2to3 + agingGt3
    return {
      openingQty: 0,
      openingUnitPrice: '',
      openingAmt,
      increaseQty: 0,
      increaseUnitPrice: '',
      increaseAmt,
      decreaseQty: 0,
      decreaseUnitPrice: '',
      decreaseAmt,
      closingQty: 0,
      closingUnitPrice: '',
      closingAmt,
      agingLt1,
      aging1to2,
      aging2to3,
      agingGt3,
      agingTotal,
      agingMismatch: Math.abs(agingTotal - closingAmt) > 0.01,
    }
  } catch {
    return emptyTotals()
  }
}

function emptyTotals(): Omit<F2SummaryRow, 'sheetCode' | 'label' | 'hasQuantity'> {
  return {
    openingQty: 0, openingUnitPrice: '', openingAmt: 0,
    increaseQty: 0, increaseUnitPrice: '', increaseAmt: 0,
    decreaseQty: 0, decreaseUnitPrice: '', decreaseAmt: 0,
    closingQty: 0, closingUnitPrice: '', closingAmt: 0,
    agingLt1: 0, aging1to2: 0, aging2to3: 0, agingGt3: 0,
    agingTotal: 0, agingMismatch: false,
  }
}

function loadDetailTotals(
  map: Map<string, ChecklistResponse>,
  sheetCode: string,
  hasQuantity: boolean,
): Omit<F2SummaryRow, 'sheetCode' | 'label' | 'hasQuantity'> {
  if (sheetCode === 'F2-10') return loadDevProductTotals(map)

  const raw = readRowJson(map.get(`${sheetCode}-rows`))
  if (!raw) return emptyTotals()

  try {
    const rows = JSON.parse(raw) as F2DetailRow[]
    const openingQty = hasQuantity ? calcSubtotal(rows.map((r) => r.openingQty ?? 0)) : 0
    const openingAmt = calcSubtotal(rows.map((r) => r.openingAmt))
    const increaseQty = hasQuantity ? calcSubtotal(rows.map((r) => r.increaseQty ?? 0)) : 0
    const increaseAmt = calcSubtotal(rows.map((r) => r.increaseAmt))
    const decreaseQty = hasQuantity ? calcSubtotal(rows.map((r) => r.decreaseQty ?? 0)) : 0
    const decreaseAmt = calcSubtotal(rows.map((r) => r.decreaseAmt))
    const closingQty = hasQuantity ? calcSubtotal(rows.map((r) => r.closingQty ?? 0)) : 0
    const closingAmt = calcSubtotal(rows.map((r) => r.closingAmt ?? 0))
    const agingLt1 = calcSubtotal(rows.map((r) => r.agingLt1 ?? 0))
    const aging1to2 = calcSubtotal(rows.map((r) => r.aging1to2 ?? 0))
    const aging2to3 = calcSubtotal(rows.map((r) => r.aging2to3 ?? 0))
    const agingGt3 = calcSubtotal(rows.map((r) => r.agingGt3 ?? 0))
    const agingTotal = agingLt1 + aging1to2 + aging2to3 + agingGt3

    return {
      openingQty,
      openingUnitPrice: fmtPrice(openingAmt, openingQty, hasQuantity),
      openingAmt,
      increaseQty,
      increaseUnitPrice: fmtPrice(increaseAmt, increaseQty, hasQuantity),
      increaseAmt,
      decreaseQty,
      decreaseUnitPrice: fmtPrice(decreaseAmt, decreaseQty, hasQuantity),
      decreaseAmt,
      closingQty,
      closingUnitPrice: fmtPrice(closingAmt, closingQty, hasQuantity),
      closingAmt,
      agingLt1,
      aging1to2,
      aging2to3,
      agingGt3,
      agingTotal,
      agingMismatch: Math.abs(agingTotal - closingAmt) > 0.01,
    }
  } catch {
    return emptyTotals()
  }
}

export function useF2DetailSummary(allResponses: Ref<Map<string, ChecklistResponse>>) {
  const rows = computed((): F2SummaryRow[] =>
    Object.values(F2_DETAIL_SHEET_CONFIGS).map((cfg) => ({
      sheetCode: cfg.sheetCode,
      label: cfg.categoryLabel,
      hasQuantity: cfg.hasQuantity,
      ...loadDetailTotals(allResponses.value, cfg.sheetCode, cfg.hasQuantity),
    })),
  )

  const totals = computed((): F2SummaryRow => ({
    sheetCode: '',
    label: '合计',
    hasQuantity: true,
    openingQty: calcSubtotal(rows.value.map((r) => r.openingQty)),
    openingUnitPrice: '',
    openingAmt: calcSubtotal(rows.value.map((r) => r.openingAmt)),
    increaseQty: calcSubtotal(rows.value.map((r) => r.increaseQty)),
    increaseUnitPrice: '',
    increaseAmt: calcSubtotal(rows.value.map((r) => r.increaseAmt)),
    decreaseQty: calcSubtotal(rows.value.map((r) => r.decreaseQty)),
    decreaseUnitPrice: '',
    decreaseAmt: calcSubtotal(rows.value.map((r) => r.decreaseAmt)),
    closingQty: calcSubtotal(rows.value.map((r) => r.closingQty)),
    closingUnitPrice: '',
    closingAmt: calcSubtotal(rows.value.map((r) => r.closingAmt)),
    agingLt1: calcSubtotal(rows.value.map((r) => r.agingLt1)),
    aging1to2: calcSubtotal(rows.value.map((r) => r.aging1to2)),
    aging2to3: calcSubtotal(rows.value.map((r) => r.aging2to3)),
    agingGt3: calcSubtotal(rows.value.map((r) => r.agingGt3)),
    agingTotal: calcSubtotal(rows.value.map((r) => r.agingTotal)),
    agingMismatch: rows.value.some((r) => r.agingMismatch),
  }))

  const agingMismatchCount = computed(() => rows.value.filter((r) => r.agingMismatch).length)

  return { rows, totals, agingMismatchCount }
}
