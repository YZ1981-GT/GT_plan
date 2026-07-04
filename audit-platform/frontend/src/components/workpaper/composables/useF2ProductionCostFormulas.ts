/**
 * F2-41~44 生产成本组 — 共享类型与公式
 */
import {
  calcSubtotal,
  calcChangeRate,
  calcAllocationRatio,
  calcChangeAmount,
} from './useF2InvValFormulaEngine'
import { readValRowJson, type ChecklistResponse } from './useF2ValuationFormData'

export interface ProductionCostRow {
  rowId: string
  productName: string
  dmOpening: number
  dmInput: number
  dmTransfer: number
  dlOpening: number
  dlInput: number
  dlTransfer: number
  ohOpening: number
  ohInput: number
  ohTransfer: number
  remark: string
}

export interface DirectLaborRow {
  rowId: string
  department: string
  jobType: string
  headcount: number
  hours: number
  wageRate: number
  actualLabor: number
  remark: string
}

export interface OverheadRow {
  rowId: string
  costItem: string
  budgetAmt: number
  actualAmt: number
  allocatedAmt: number
  remark: string
}

export interface AllocationRow {
  rowId: string
  productName: string
  allocationBase: number
  materialAlloc: number
  laborAlloc: number
  overheadAlloc: number
  remark: string
}

export function newRowId(): string {
  return `f2pc-${Date.now().toString(36)}`
}

export function calcProductionPeriodEnd(opening: number, input: number, transfer: number): number {
  return opening + input - transfer
}

export function enrichProductionRow(r: ProductionCostRow) {
  const dmClosing = calcProductionPeriodEnd(r.dmOpening, r.dmInput, r.dmTransfer)
  const dlClosing = calcProductionPeriodEnd(r.dlOpening, r.dlInput, r.dlTransfer)
  const ohClosing = calcProductionPeriodEnd(r.ohOpening, r.ohInput, r.ohTransfer)
  return {
    ...r,
    dmClosing,
    dlClosing,
    ohClosing,
    totalOpening: r.dmOpening + r.dlOpening + r.ohOpening,
    totalInput: r.dmInput + r.dlInput + r.ohInput,
    totalTransfer: r.dmTransfer + r.dlTransfer + r.ohTransfer,
    totalClosing: dmClosing + dlClosing + ohClosing,
  }
}

export function enrichLaborRow(r: DirectLaborRow, grandTotal: number) {
  const calculatedLabor = r.headcount * r.hours * r.wageRate
  const variance = calcChangeAmount(calculatedLabor, r.actualLabor)
  const varianceRate = calcChangeRate(r.actualLabor, calculatedLabor)
  const laborTotal = calculatedLabor
  const sharePct = grandTotal ? calcAllocationRatio(laborTotal, grandTotal) : 0
  return { ...r, calculatedLabor, variance, varianceRate, laborTotal, sharePct }
}

export function enrichOverheadRow(r: OverheadRow) {
  const variance = calcChangeAmount(r.actualAmt, r.budgetAmt)
  const varianceRate = calcChangeRate(r.budgetAmt, r.actualAmt)
  const allocMismatch = Math.abs(r.allocatedAmt - r.actualAmt) > 0.01
  return { ...r, variance, varianceRate, allocMismatch }
}

export function enrichAllocationRow(
  r: AllocationRow,
  baseTotal: number,
  totals: { material: number; labor: number; overhead: number },
) {
  const baseRatio = baseTotal ? calcAllocationRatio(r.allocationBase, baseTotal) : 0
  const totalAlloc = r.materialAlloc + r.laborAlloc + r.overheadAlloc
  const expectedTotal = (totals.material + totals.labor + totals.overhead) * (baseRatio / 100)
  const variance = totalAlloc - expectedTotal
  return { ...r, baseRatio, totalAlloc, variance }
}

export function parseRows<T>(json: string | null | undefined, fallback: () => T[]): T[] {
  if (!json) return fallback()
  try {
    const arr = JSON.parse(json)
    return Array.isArray(arr) && arr.length ? arr : fallback()
  } catch {
    return fallback()
  }
}

export function sumProductionClosing(rows: ProductionCostRow[]): number {
  return calcSubtotal(rows.map((r) => enrichProductionRow(r).totalClosing))
}

export function sumLaborActual(rows: DirectLaborRow[]): number {
  return calcSubtotal(rows.map((r) => r.actualLabor))
}

export function sumOverheadActual(rows: OverheadRow[]): number {
  return calcSubtotal(rows.map((r) => r.actualAmt))
}

export function readSourceTotals(allResponses: Map<string, ChecklistResponse>) {
  const pRows = parseRows<ProductionCostRow>(readValRowJson(allResponses.get('F2-41-rows')), () => [])
  const lRows = parseRows<DirectLaborRow>(readValRowJson(allResponses.get('F2-42-rows')), () => [])
  const oRows = parseRows<OverheadRow>(readValRowJson(allResponses.get('F2-43-rows')), () => [])
  return {
    material: sumProductionClosing(pRows),
    labor: sumLaborActual(lRows),
    overhead: sumOverheadActual(oRows),
  }
}
