/** F2-67 识别未披露关联方：人员身份交叉核对纯函数。 */
export const F2_67_OBJECTIVE = '主要或异常供应商（包括施工单位）是否与被审计单位存在关联方关系。'

export const MATCH_FIELDS = [
  'personalSupplier',
  'supplierLegalPerson',
  'contractSignee',
  'formerPurchasingStaff',
  'financeDept',
  'managementDept',
  'technologyDept',
  'productionDept',
  'marketingDept',
  'otherDept',
] as const

export type MatchField = typeof MATCH_FIELDS[number]
export type MatchJudgment = 'Y' | 'N' | ''

export interface UndisclosedPartyRow {
  id: string
  name: string
  personalSupplier: number
  supplierLegalPerson: number
  contractSignee: number
  formerPurchasingStaff: number
  financeDept: number
  managementDept: number
  technologyDept: number
  productionDept: number
  marketingDept: number
  otherDept: number
  isRelated: MatchJudgment
  identity: string
  annualPurchaseAmount: number
  note: string
  indexRef: string
}

export interface EnrichedUndisclosedPartyRow extends UndisclosedPartyRow {
  total: number
  suggestedRelated: MatchJudgment
  isAbnormal: boolean
}

let sequence = 0
export function newUndisclosedPartyId(): string {
  sequence += 1
  return `f267-${Date.now().toString(36)}-${sequence}`
}

export function emptyUndisclosedPartyRow(): UndisclosedPartyRow {
  return {
    id: newUndisclosedPartyId(),
    name: '',
    personalSupplier: 0,
    supplierLegalPerson: 0,
    contractSignee: 0,
    formerPurchasingStaff: 0,
    financeDept: 0,
    managementDept: 0,
    technologyDept: 0,
    productionDept: 0,
    marketingDept: 0,
    otherDept: 0,
    isRelated: '',
    identity: '',
    annualPurchaseAmount: 0,
    note: '',
    indexRef: '',
  }
}

export function calcUndisclosedMatchTotal(row: UndisclosedPartyRow): number {
  return MATCH_FIELDS.reduce((sum, field) => sum + (Number(row[field]) || 0), 0)
}

export function enrichUndisclosedPartyRow(
  row: UndisclosedPartyRow,
): EnrichedUndisclosedPartyRow {
  const total = calcUndisclosedMatchTotal(row)
  const suggestedRelated: MatchJudgment = total > 0 ? 'Y' : row.name.trim() ? 'N' : ''
  const judgment = row.isRelated || suggestedRelated
  return {
    ...row,
    total,
    suggestedRelated,
    isAbnormal: judgment === 'Y',
  }
}

export function isBlankUndisclosedPartyRow(row: UndisclosedPartyRow): boolean {
  return !row.name.trim()
    && calcUndisclosedMatchTotal(row) === 0
    && !row.isRelated
    && !row.identity.trim()
    && !row.annualPurchaseAmount
    && !row.note.trim()
    && !row.indexRef.trim()
}

export function pruneBlankUndisclosedPartyRows(
  rows: UndisclosedPartyRow[],
): UndisclosedPartyRow[] {
  const filled = rows.filter((row) => !isBlankUndisclosedPartyRow(row))
  return filled.length ? filled : [emptyUndisclosedPartyRow()]
}

function num(value: unknown): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function normalizeRow(raw: Record<string, unknown>): UndisclosedPartyRow {
  const legacyRelation = text(raw.relationType)
  const legacyDisclosed = text(raw.isDisclosed)
  return {
    id: text(raw.id) || newUndisclosedPartyId(),
    name: text(raw.name) || text(raw.supplierName),
    personalSupplier: num(raw.personalSupplier),
    supplierLegalPerson: num(raw.supplierLegalPerson),
    contractSignee: num(raw.contractSignee),
    formerPurchasingStaff: num(raw.formerPurchasingStaff),
    financeDept: num(raw.financeDept),
    managementDept: num(raw.managementDept),
    technologyDept: num(raw.technologyDept),
    productionDept: num(raw.productionDept),
    marketingDept: num(raw.marketingDept),
    otherDept: num(raw.otherDept),
    isRelated: raw.isRelated === 'Y' || raw.isRelated === 'N'
      ? raw.isRelated
      : legacyDisclosed === '否' && legacyRelation ? 'Y' : '',
    identity: text(raw.identity)
      || [legacyRelation, text(raw.relationToClient)].filter(Boolean).join(' / '),
    annualPurchaseAmount: num(raw.annualPurchaseAmount),
    note: text(raw.note) || text(raw.checkConclusion) || text(raw.remark),
    indexRef: text(raw.indexRef) || text(raw.indexNo),
  }
}

export function migrateUndisclosedPartyRows(parsed: unknown): UndisclosedPartyRow[] {
  if (!Array.isArray(parsed)) return [emptyUndisclosedPartyRow()]
  return pruneBlankUndisclosedPartyRows(
    parsed
      .filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
      .map(normalizeRow),
  )
}
