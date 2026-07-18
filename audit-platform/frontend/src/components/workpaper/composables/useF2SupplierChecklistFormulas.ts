/** F2-69 供应商核查清单纯函数层。 */
export const CHECK_METHOD_FIELDS = [
  'registryChecked',
  'internetChecked',
  'interviewChecked',
  'confirmationChecked',
  'siteVisitChecked',
] as const

export type CheckMethodField = typeof CHECK_METHOD_FIELDS[number]

export interface SupplierChecklistRow {
  id: string
  supplierName: string
  selectionReason: string
  visitConclusion: string
  lastVisitDate: string
  reverseEndingBalance: number
  reversePurchaseAmount: number
  confirmationEndingBalance: number
  confirmationPurchaseAmount: number
  registryChecked: boolean
  internetChecked: boolean
  interviewChecked: boolean
  confirmationChecked: boolean
  siteVisitChecked: boolean
  finalIndexRef: string
  remark: string
}

export interface EnrichedSupplierChecklistRow extends SupplierChecklistRow {
  completedMethodCount: number
  completionPct: number
  reverseDifference: number
  confirmationDifference: number
  isAmountMismatch: boolean
  isIncomplete: boolean
  isRisk: boolean
}

let sequence = 0
export function newSupplierChecklistId(): string {
  sequence += 1
  return `f269-${Date.now().toString(36)}-${sequence}`
}

export function emptySupplierChecklistRow(): SupplierChecklistRow {
  return {
    id: newSupplierChecklistId(),
    supplierName: '',
    selectionReason: '',
    visitConclusion: '',
    lastVisitDate: '',
    reverseEndingBalance: 0,
    reversePurchaseAmount: 0,
    confirmationEndingBalance: 0,
    confirmationPurchaseAmount: 0,
    registryChecked: false,
    internetChecked: false,
    interviewChecked: false,
    confirmationChecked: false,
    siteVisitChecked: false,
    finalIndexRef: '',
    remark: '',
  }
}

export function enrichSupplierChecklistRow(
  row: SupplierChecklistRow,
): EnrichedSupplierChecklistRow {
  const completedMethodCount = CHECK_METHOD_FIELDS.filter((field) => row[field]).length
  const hasSupplier = !!row.supplierName.trim()
  const reverseDifference = row.reversePurchaseAmount - row.confirmationPurchaseAmount
  const confirmationDifference = row.reverseEndingBalance - row.confirmationEndingBalance
  const amountBase = Math.max(
    Math.abs(row.reversePurchaseAmount),
    Math.abs(row.confirmationPurchaseAmount),
  )
  const balanceBase = Math.max(
    Math.abs(row.reverseEndingBalance),
    Math.abs(row.confirmationEndingBalance),
  )
  const amountMismatch = amountBase > 0
    && Math.abs(reverseDifference) / amountBase > 0.01
  const balanceMismatch = balanceBase > 0
    && Math.abs(confirmationDifference) / balanceBase > 0.01
  const isAmountMismatch = amountMismatch || balanceMismatch
  const isIncomplete = hasSupplier
    && (!row.selectionReason.trim() || completedMethodCount === 0 || !row.finalIndexRef.trim())
  return {
    ...row,
    completedMethodCount,
    completionPct: completedMethodCount / CHECK_METHOD_FIELDS.length,
    reverseDifference,
    confirmationDifference,
    isAmountMismatch,
    isIncomplete,
    isRisk: isAmountMismatch || isIncomplete,
  }
}

export function isBlankSupplierChecklistRow(row: SupplierChecklistRow): boolean {
  return !row.supplierName.trim()
    && !row.selectionReason.trim()
    && !row.visitConclusion.trim()
    && !row.lastVisitDate
    && !row.reverseEndingBalance
    && !row.reversePurchaseAmount
    && !row.confirmationEndingBalance
    && !row.confirmationPurchaseAmount
    && CHECK_METHOD_FIELDS.every((field) => !row[field])
    && !row.finalIndexRef.trim()
    && !row.remark.trim()
}

export function pruneSupplierChecklistRows(
  rows: SupplierChecklistRow[],
): SupplierChecklistRow[] {
  const filled = rows.filter((row) => !isBlankSupplierChecklistRow(row))
  return filled.length ? filled : [emptySupplierChecklistRow()]
}

export function supplierChecklistSummary(rows: SupplierChecklistRow[]) {
  const enriched = rows.map(enrichSupplierChecklistRow)
  return {
    supplierCount: rows.filter((row) => row.supplierName.trim()).length,
    completedMethods: enriched.reduce((sum, row) => sum + row.completedMethodCount, 0),
    incompleteCount: enriched.filter((row) => row.isIncomplete).length,
    mismatchCount: enriched.filter((row) => row.isAmountMismatch).length,
  }
}

function num(value: unknown): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function bool(value: unknown): boolean {
  return value === true || value === 1 || value === '1' || value === '是'
    || value === 'Y' || value === '√' || value === '已完成'
}

function normalizeRow(raw: Record<string, unknown>): SupplierChecklistRow {
  const legacyChecks = Array.from({ length: 10 }, (_, index) =>
    raw[`check${index + 1}`] === '已完成',
  )
  return {
    id: text(raw.id) || newSupplierChecklistId(),
    supplierName: text(raw.supplierName),
    selectionReason: text(raw.selectionReason) || text(raw.riskCategory),
    visitConclusion: text(raw.visitConclusion) || text(raw.overallEval),
    lastVisitDate: text(raw.lastVisitDate) || text(raw.completeDate),
    reverseEndingBalance: num(raw.reverseEndingBalance),
    reversePurchaseAmount: num(raw.reversePurchaseAmount),
    confirmationEndingBalance: num(raw.confirmationEndingBalance),
    confirmationPurchaseAmount: num(raw.confirmationPurchaseAmount),
    registryChecked: bool(raw.registryChecked) || legacyChecks[0] || legacyChecks[1],
    internetChecked: bool(raw.internetChecked) || legacyChecks[2],
    interviewChecked: bool(raw.interviewChecked) || legacyChecks[3] || legacyChecks[4],
    confirmationChecked: bool(raw.confirmationChecked) || legacyChecks[5] || legacyChecks[6],
    siteVisitChecked: bool(raw.siteVisitChecked) || legacyChecks[7] || legacyChecks[8],
    finalIndexRef: text(raw.finalIndexRef) || text(raw.indexNo),
    remark: text(raw.remark) || text(raw.followUp),
  }
}

export function migrateSupplierChecklistRows(parsed: unknown): SupplierChecklistRow[] {
  if (!Array.isArray(parsed)) return [emptySupplierChecklistRow()]
  return pruneSupplierChecklistRows(
    parsed
      .filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
      .map(normalizeRow),
  )
}
