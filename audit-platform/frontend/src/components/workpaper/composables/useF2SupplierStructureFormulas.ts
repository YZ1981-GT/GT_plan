/** F2-68 重要供应商结构分析纯函数层。 */
export type SupplierPeriod = 'current' | 'prior'
export type YesNo = '是' | '否' | ''

export interface SupplierStructureRow {
  id: string
  supplierName: string
  purchaseAmount: number
  relatedProduct: string
  purchaseQuantity: number
  unitPrice: number
  creditPeriod: string
  paymentMethod: string
  transportMethod: string
  otherTerms: string
  isRelatedParty: YesNo
  scaleMatches: YesNo
  scopeMatches: YesNo
  remark: string
  indexRef: string
}

export interface EnrichedSupplierStructureRow extends SupplierStructureRow {
  rank: number
  ratio: number
  impliedAmount: number
  isAmountMismatch: boolean
  isRisk: boolean
}

export interface SupplierStructureSheet {
  currentRows: SupplierStructureRow[]
  priorRows: SupplierStructureRow[]
}

let sequence = 0
export function newSupplierStructureId(): string {
  sequence += 1
  return `f268-${Date.now().toString(36)}-${sequence}`
}

export function emptySupplierStructureRow(): SupplierStructureRow {
  return {
    id: newSupplierStructureId(),
    supplierName: '',
    purchaseAmount: 0,
    relatedProduct: '',
    purchaseQuantity: 0,
    unitPrice: 0,
    creditPeriod: '',
    paymentMethod: '',
    transportMethod: '',
    otherTerms: '',
    isRelatedParty: '',
    scaleMatches: '',
    scopeMatches: '',
    remark: '',
    indexRef: '',
  }
}

export function defaultSupplierStructureSheet(): SupplierStructureSheet {
  return {
    currentRows: [emptySupplierStructureRow()],
    priorRows: [emptySupplierStructureRow()],
  }
}

export function isBlankSupplierStructureRow(row: SupplierStructureRow): boolean {
  return !row.supplierName.trim()
    && !row.purchaseAmount
    && !row.relatedProduct.trim()
    && !row.purchaseQuantity
    && !row.unitPrice
    && !row.creditPeriod.trim()
    && !row.paymentMethod.trim()
    && !row.transportMethod.trim()
    && !row.otherTerms.trim()
    && !row.isRelatedParty
    && !row.scaleMatches
    && !row.scopeMatches
    && !row.remark.trim()
    && !row.indexRef.trim()
}

export function pruneSupplierStructureRows(
  rows: SupplierStructureRow[],
): SupplierStructureRow[] {
  const filled = rows.filter((row) => !isBlankSupplierStructureRow(row))
  return filled.length ? filled : [emptySupplierStructureRow()]
}

export function enrichSupplierStructureRows(
  rows: SupplierStructureRow[],
): EnrichedSupplierStructureRow[] {
  const total = rows.reduce((sum, row) => sum + row.purchaseAmount, 0)
  const rankMap = new Map(
    [...rows]
      .sort((a, b) => b.purchaseAmount - a.purchaseAmount)
      .map((row, index) => [row.id, row.purchaseAmount > 0 ? index + 1 : 0]),
  )
  return rows.map((row) => {
    const impliedAmount = row.purchaseQuantity * row.unitPrice
    const base = Math.max(Math.abs(row.purchaseAmount), Math.abs(impliedAmount))
    const isAmountMismatch = base > 0
      && Math.abs(row.purchaseAmount - impliedAmount) / base > 0.01
      && row.purchaseQuantity > 0
      && row.unitPrice > 0
    return {
      ...row,
      rank: rankMap.get(row.id) || 0,
      ratio: total > 0 ? row.purchaseAmount / total : 0,
      impliedAmount,
      isAmountMismatch,
      isRisk: row.isRelatedParty === '是'
        || row.scaleMatches === '否'
        || row.scopeMatches === '否'
        || isAmountMismatch,
    }
  })
}

export function supplierStructureSummary(rows: SupplierStructureRow[]) {
  const sorted = [...rows].sort((a, b) => b.purchaseAmount - a.purchaseAmount)
  const total = sorted.reduce((sum, row) => sum + row.purchaseAmount, 0)
  const top5 = sorted.slice(0, 5).reduce((sum, row) => sum + row.purchaseAmount, 0)
  const top10 = sorted.slice(0, 10).reduce((sum, row) => sum + row.purchaseAmount, 0)
  return {
    total,
    top5Ratio: total ? top5 / total : 0,
    top10Ratio: total ? top10 / total : 0,
    supplierCount: rows.filter((row) => row.supplierName.trim()).length,
    riskCount: enrichSupplierStructureRows(rows).filter((row) => row.isRisk).length,
  }
}

function num(value: unknown): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function yesNo(value: unknown): YesNo {
  return value === '是' || value === '否' ? value : ''
}

function normalizeRow(raw: Record<string, unknown>, amountKey = 'purchaseAmount'): SupplierStructureRow {
  return {
    id: text(raw.id) || newSupplierStructureId(),
    supplierName: text(raw.supplierName),
    purchaseAmount: num(raw[amountKey]),
    relatedProduct: text(raw.relatedProduct) || text(raw.category),
    purchaseQuantity: num(raw.purchaseQuantity),
    unitPrice: num(raw.unitPrice),
    creditPeriod: text(raw.creditPeriod),
    paymentMethod: text(raw.paymentMethod),
    transportMethod: text(raw.transportMethod),
    otherTerms: text(raw.otherTerms) || text(raw.concentrationEval),
    isRelatedParty: yesNo(raw.isRelatedParty) || yesNo(raw.isRelated),
    scaleMatches: yesNo(raw.scaleMatches),
    scopeMatches: yesNo(raw.scopeMatches),
    remark: text(raw.remark),
    indexRef: text(raw.indexRef) || text(raw.indexNo),
  }
}

/** 兼容旧版 T/T-1/T-2 单行模型，并拆分为本年、上年两个源表区块。 */
function migrateLegacyRows(rows: Record<string, unknown>[]): SupplierStructureSheet {
  const currentRows = rows.map((row) => normalizeRow(row, 'amountT'))
  const priorRows = rows
    .filter((row) => num(row.amountT1) > 0 || text(row.supplierName).trim())
    .map((row) => ({
      ...normalizeRow(row, 'amountT1'),
      id: newSupplierStructureId(),
    }))
  return {
    currentRows: pruneSupplierStructureRows(currentRows),
    priorRows: pruneSupplierStructureRows(priorRows),
  }
}

export function migrateSupplierStructureSheet(parsed: unknown): SupplierStructureSheet {
  if (Array.isArray(parsed)) {
    return migrateLegacyRows(
      parsed.filter((item): item is Record<string, unknown> => !!item && typeof item === 'object'),
    )
  }
  if (parsed && typeof parsed === 'object') {
    const object = parsed as Record<string, unknown>
    const currentRows = Array.isArray(object.currentRows)
      ? object.currentRows
        .filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
        .map((item) => normalizeRow(item))
      : []
    const priorRows = Array.isArray(object.priorRows)
      ? object.priorRows
        .filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
        .map((item) => normalizeRow(item))
      : []
    return {
      currentRows: pruneSupplierStructureRows(currentRows),
      priorRows: pruneSupplierStructureRows(priorRows),
    }
  }
  return defaultSupplierStructureSheet()
}
