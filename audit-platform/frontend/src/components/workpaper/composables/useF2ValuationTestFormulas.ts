/**
 * F2-38~40 计价测试 — 共享类型与公式
 */
import {
  calcSubtotal,
  calcWeightedAvgPrice,
  calcStandardCost,
  calcPriceVariance,
  calcQuantityVariance,
  calcVarianceRate,
  isVarianceExceeding,
} from './useF2InvValFormulaEngine'

export type ValuationTestMethod = 'weighted-avg' | 'fifo' | 'standard-cost'

export interface ValuationTestRow {
  rowId: string
  seq: number
  voucherNo: string
  itemName: string
  openingQty: number
  openingAmt: number
  inboundQty: number
  inboundAmt: number
  issueQty: number
  bookIssueAmt: number
  fifoUnitPrice: number
  stdPrice: number
  stdQty: number
  actPrice: number
  actQty: number
  auditIssueAmt: number
  varianceAmt: number
  varianceRate: number | '' | 'N/A'
}

export interface SamplingParams {
  population: string
  sampleSize: number
  method: string
  confidence: string
  tolerableError: string
  conclusion: string
}

export function newValuationTestRowId(): string {
  return `f2vt-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

export function emptyValuationTestRow(seq: number): ValuationTestRow {
  return {
    rowId: newValuationTestRowId(),
    seq,
    voucherNo: '',
    itemName: '',
    openingQty: 0,
    openingAmt: 0,
    inboundQty: 0,
    inboundAmt: 0,
    issueQty: 0,
    bookIssueAmt: 0,
    fifoUnitPrice: 0,
    stdPrice: 0,
    stdQty: 0,
    actPrice: 0,
    actQty: 0,
    auditIssueAmt: 0,
    varianceAmt: 0,
    varianceRate: '',
  }
}

export function enrichValuationTestRow(
  raw: ValuationTestRow,
  method: ValuationTestMethod,
): ValuationTestRow {
  const row = { ...raw }
  let auditIssueAmt = row.auditIssueAmt
  if (method === 'weighted-avg') {
    const unit = calcWeightedAvgPrice(row.openingAmt, row.inboundAmt, row.openingQty, row.inboundQty)
    auditIssueAmt = unit * row.issueQty
  } else if (method === 'fifo') {
    auditIssueAmt = row.fifoUnitPrice * row.issueQty
  } else {
    const std = calcStandardCost(row.stdPrice, row.stdQty)
    const act = row.actPrice * row.actQty
    void calcPriceVariance(row.actPrice, row.stdPrice, row.actQty)
    void calcQuantityVariance(row.actQty, row.stdQty, row.stdPrice)
    auditIssueAmt = act
    if (row.bookIssueAmt === 0) row.bookIssueAmt = std
  }
  const varianceAmt = auditIssueAmt - row.bookIssueAmt
  const varianceRate = calcVarianceRate(row.bookIssueAmt, auditIssueAmt)
  return { ...row, auditIssueAmt, varianceAmt, varianceRate }
}

export function calcValuationTestTotals(rows: ValuationTestRow[]) {
  return {
    bookIssueAmt: calcSubtotal(rows.map((r) => r.bookIssueAmt)),
    auditIssueAmt: calcSubtotal(rows.map((r) => r.auditIssueAmt)),
    varianceAmt: calcSubtotal(rows.map((r) => r.varianceAmt)),
  }
}

export function countExceeding(rows: ValuationTestRow[], thresholdRate: number): number {
  return rows.filter((r) => isVarianceExceeding(r.varianceRate, thresholdRate)).length
}

export { isVarianceExceeding }
