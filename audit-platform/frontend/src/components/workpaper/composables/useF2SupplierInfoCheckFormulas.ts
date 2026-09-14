/** F2-70 供应商信息核查表：转置矩阵（核查项目×供应商）纯函数层。 */
export const F2_70_OBJECTIVE = '审计目标：资产负债表中记录的存货真实存在，且已经记录的存货交易均已入账。通过核查主要供应商的工商、网站、股权及关键人员信息，识别其与被审计单位及其关联方、主要人员的重合关系，评价供应商的真实性和商业实质。'

export type YesNo = '是' | '否' | ''

export interface SupplierInfoEntity {
  id: string
  supplierName: string
  creditCode: string
  registeredAddress: string
  officeAddress: string
  websiteUrl: string
  websiteIp: string
  companyEmail: string
  establishDate: string
  registeredCapital: string
  businessScope: string
  staffScale: string
  legalRepresentative: string
  shareholder1: string
  shareholder2: string
  shareholder3: string
  shareholder4: string
  shareholder5: string
  chairman: string
  generalManager: string
  otherManagers: string
  keyHandlers: string
  actualController: string
  isRelatedParty: YesNo
  isAlsoCustomer: YesNo
  businessStatus: string
  isDishonest: YesNo
  infoSource: string
  remark: string
}

export type SupplierInfoField = Exclude<keyof SupplierInfoEntity, 'id'>

/** 完整度考核的基础项（源表核查项目的必填部分）。 */
const COMPLETENESS_FIELDS: SupplierInfoField[] = [
  'creditCode', 'registeredAddress', 'establishDate', 'registeredCapital',
  'legalRepresentative', 'shareholder1', 'actualController',
  'isRelatedParty', 'businessStatus', 'infoSource',
]

const ABNORMAL_STATUS_KEYWORDS = ['注销', '吊销', '停业', '清算', '异常', '迁出']

export interface EnrichedSupplierInfoEntity extends SupplierInfoEntity {
  completedCount: number
  completionPct: number
  isStatusAbnormal: boolean
  riskFlags: string[]
  isRisk: boolean
}

let sequence = 0
export function newSupplierInfoId(): string {
  sequence += 1
  return `f270-${Date.now().toString(36)}-${sequence}`
}

export function emptySupplierInfoEntity(): SupplierInfoEntity {
  return {
    id: newSupplierInfoId(),
    supplierName: '',
    creditCode: '',
    registeredAddress: '',
    officeAddress: '',
    websiteUrl: '',
    websiteIp: '',
    companyEmail: '',
    establishDate: '',
    registeredCapital: '',
    businessScope: '',
    staffScale: '',
    legalRepresentative: '',
    shareholder1: '',
    shareholder2: '',
    shareholder3: '',
    shareholder4: '',
    shareholder5: '',
    chairman: '',
    generalManager: '',
    otherManagers: '',
    keyHandlers: '',
    actualController: '',
    isRelatedParty: '',
    isAlsoCustomer: '',
    businessStatus: '',
    isDishonest: '',
    infoSource: '',
    remark: '',
  }
}

export function enrichSupplierInfoEntity(
  entity: SupplierInfoEntity,
): EnrichedSupplierInfoEntity {
  const completedCount = COMPLETENESS_FIELDS
    .filter((field) => String(entity[field] ?? '').trim()).length
  const isStatusAbnormal = ABNORMAL_STATUS_KEYWORDS
    .some((keyword) => entity.businessStatus.includes(keyword))
  const riskFlags: string[] = []
  if (entity.isRelatedParty === '是') riskFlags.push('关联方')
  if (entity.isAlsoCustomer === '是') riskFlags.push('同为客户')
  if (entity.isDishonest === '是') riskFlags.push('失信名单')
  if (isStatusAbnormal) riskFlags.push('经营状态异常')
  return {
    ...entity,
    completedCount,
    completionPct: completedCount / COMPLETENESS_FIELDS.length,
    isStatusAbnormal,
    riskFlags,
    isRisk: riskFlags.length > 0,
  }
}

export function isBlankSupplierInfoEntity(entity: SupplierInfoEntity): boolean {
  return Object.entries(entity)
    .filter(([key]) => key !== 'id')
    .every(([, value]) => !String(value ?? '').trim())
}

export function pruneSupplierInfoEntities(
  entities: SupplierInfoEntity[],
): SupplierInfoEntity[] {
  const filled = entities.filter((entity) => !isBlankSupplierInfoEntity(entity))
  return filled.length ? filled : [emptySupplierInfoEntity()]
}

export function supplierInfoSummary(entities: SupplierInfoEntity[]) {
  const enriched = entities.map(enrichSupplierInfoEntity)
  const named = enriched.filter((entity) => entity.supplierName.trim())
  return {
    supplierCount: named.length,
    riskCount: named.filter((entity) => entity.isRisk).length,
    incompleteCount: named.filter((entity) => entity.completionPct < 1).length,
  }
}

function text(value: unknown): string {
  if (typeof value === 'string') return value
  if (typeof value === 'number' && Number.isFinite(value) && value !== 0) return String(value)
  return ''
}

function yesNo(value: unknown): YesNo {
  return value === '是' || value === '否' ? value : ''
}

/** 兼容旧版主从档案模型（operatingAddress/checkMethod 等字段）。 */
function normalizeEntity(raw: Record<string, unknown>): SupplierInfoEntity {
  return {
    ...emptySupplierInfoEntity(),
    id: text(raw.id) || newSupplierInfoId(),
    supplierName: text(raw.supplierName),
    creditCode: text(raw.creditCode),
    registeredAddress: text(raw.registeredAddress) || text(raw.operatingAddress),
    officeAddress: text(raw.officeAddress),
    websiteUrl: text(raw.websiteUrl),
    websiteIp: text(raw.websiteIp),
    companyEmail: text(raw.companyEmail),
    establishDate: text(raw.establishDate),
    registeredCapital: text(raw.registeredCapital),
    businessScope: text(raw.businessScope),
    staffScale: text(raw.staffScale) || text(raw.employeeCount),
    legalRepresentative: text(raw.legalRepresentative),
    shareholder1: text(raw.shareholder1) || text(raw.shareholderInfo),
    shareholder2: text(raw.shareholder2),
    shareholder3: text(raw.shareholder3),
    shareholder4: text(raw.shareholder4),
    shareholder5: text(raw.shareholder5),
    chairman: text(raw.chairman),
    generalManager: text(raw.generalManager),
    otherManagers: text(raw.otherManagers),
    keyHandlers: text(raw.keyHandlers) || text(raw.mainCustomers),
    actualController: text(raw.actualController),
    isRelatedParty: yesNo(raw.isRelatedParty),
    isAlsoCustomer: yesNo(raw.isAlsoCustomer),
    businessStatus: text(raw.businessStatus) || text(raw.financialStatus),
    isDishonest: yesNo(raw.isDishonest),
    infoSource: text(raw.infoSource) || text(raw.checkMethod),
    remark: text(raw.remark) || text(raw.checkConclusion),
  }
}

export function migrateSupplierInfoEntities(parsed: unknown): SupplierInfoEntity[] {
  if (!Array.isArray(parsed)) return [emptySupplierInfoEntity()]
  return pruneSupplierInfoEntities(
    parsed
      .filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
      .map(normalizeEntity),
  )
}
