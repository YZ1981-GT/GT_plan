/**
 * F2-33~35 检查表 — 共享类型与公式
 */
import { parseNum, calcSubtotal } from './useF2InvValFormulaEngine'
import type { ChecklistResponse } from './useF2ValuationFormData'

export interface InspectionCheckRow {
  id: string
  seq: number
  party: string
  docNo: string
  itemName: string
  amount: number
  voucherNo: string
  remark: string
  daysOutstanding?: number
  sampleSource?: string
}

/** 存货科目组（1401~1411，抽凭/截止测试用） */
export const F2_INVENTORY_ACCOUNT_CODES = '1401,1402,1403,1404,1405,1406,1407,1408,1409,1410,1411'

export function emptyInspectionRow(seq: number, sampleSource?: string): InspectionCheckRow {
  return {
    id: `f2ic-${Date.now().toString(36)}-${seq}`,
    seq,
    party: '', docNo: '', itemName: '', amount: 0, voucherNo: '', remark: '',
    sampleSource,
  }
}

export function calcInspectionCoverage(checkedTotal: number, bookTotal: number): number {
  return bookTotal ? (checkedTotal / bookTotal) * 100 : 0
}

export function readBookTotal(allResponses: Map<string, ChecklistResponse>, sheetCode: string): number {
  return parseNum(allResponses.get(`${sheetCode}-book-total`)?.remark)
}
