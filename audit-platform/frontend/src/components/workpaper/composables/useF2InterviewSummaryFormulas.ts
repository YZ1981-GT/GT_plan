/** F2-71 供应商访谈记录汇总表：转置矩阵（访谈项目×供应商）纯函数层。 */
export const F2_71_OBJECTIVE = '审计目标：通过对主要供应商实地走访/访谈，验证采购交易的真实性与商业合理性，核对地址、交易金额及往来余额，识别关联关系及异常交易迹象。'

export const INTERVIEW_METHODS = ['实地走访', '视频访谈', '电话访谈', '书面问询'] as const
export type InterviewMethod = typeof INTERVIEW_METHODS[number]

export type YesNo = '是' | '否' | ''

export interface InterviewSummaryEntity {
  id: string
  /** 附件槽位：ItemAttachment 的 itemIndex，跨排序保持稳定。 */
  attSlot: number
  supplierName: string
  interviewDate: string
  reason: string
  method: InterviewMethod | ''
  registeredAddress: string
  visitAddress: string
  interviewee: string
  auditors: string
  otherParticipants: string
  tripInfo: string
  onSiteConfirmation: YesNo
  focusPoints: string
  contractCheck: string
  transactionAmountMatch: YesNo
  balanceMatch: YesNo
  conclusion: string
  recordIndex: string
}

export type InterviewSummaryField = Exclude<keyof InterviewSummaryEntity, 'id' | 'attSlot'>

const COMPLETENESS_FIELDS: InterviewSummaryField[] = [
  'interviewDate', 'reason', 'method', 'interviewee',
  'auditors', 'focusPoints', 'conclusion', 'recordIndex',
]

const ABNORMAL_CONCLUSION_KEYWORDS = ['异常', '疑点', '不一致', '无法确认', '受限']

export interface EnrichedInterviewSummaryEntity extends InterviewSummaryEntity {
  completedCount: number
  completionPct: number
  /** 提示2第1条：走访地址与注册地址是否一致。 */
  isAddressMismatch: boolean
  riskFlags: string[]
  isRisk: boolean
}

let sequence = 0
export function newInterviewSummaryId(): string {
  sequence += 1
  return `f271-${Date.now().toString(36)}-${sequence}`
}

export function emptyInterviewSummaryEntity(attSlot = 1): InterviewSummaryEntity {
  return {
    id: newInterviewSummaryId(),
    attSlot,
    supplierName: '',
    interviewDate: '',
    reason: '',
    method: '',
    registeredAddress: '',
    visitAddress: '',
    interviewee: '',
    auditors: '',
    otherParticipants: '',
    tripInfo: '',
    onSiteConfirmation: '',
    focusPoints: '',
    contractCheck: '',
    transactionAmountMatch: '',
    balanceMatch: '',
    conclusion: '',
    recordIndex: '',
  }
}

function normalizeAddress(value: string): string {
  return value.replace(/[\s，,。.\-—()（）]/g, '')
}

export function enrichInterviewSummaryEntity(
  entity: InterviewSummaryEntity,
): EnrichedInterviewSummaryEntity {
  const completedCount = COMPLETENESS_FIELDS
    .filter((field) => String(entity[field] ?? '').trim()).length
  const registered = normalizeAddress(entity.registeredAddress)
  const visited = normalizeAddress(entity.visitAddress)
  const isAddressMismatch = !!registered && !!visited && registered !== visited
  const riskFlags: string[] = []
  if (isAddressMismatch) riskFlags.push('走访与注册地址不一致')
  if (entity.transactionAmountMatch === '否') riskFlags.push('交易金额不符')
  if (entity.balanceMatch === '否') riskFlags.push('往来金额不符')
  if (entity.onSiteConfirmation === '否') riskFlags.push('未现场函证')
  // 先剔除“未见异常/无异常/不存在异常”等否定表述，避免误报
  const conclusionForScan = entity.conclusion
    .replace(/未见(重大)?异常|无(重大)?异常|不存在(重大)?异常|未发现(重大)?异常/g, '')
  if (ABNORMAL_CONCLUSION_KEYWORDS.some((keyword) => conclusionForScan.includes(keyword))) {
    riskFlags.push('结论存疑')
  }
  return {
    ...entity,
    completedCount,
    completionPct: completedCount / COMPLETENESS_FIELDS.length,
    isAddressMismatch,
    riskFlags,
    isRisk: riskFlags.length > 0,
  }
}

export function isBlankInterviewSummaryEntity(entity: InterviewSummaryEntity): boolean {
  return Object.entries(entity)
    .filter(([key]) => key !== 'id' && key !== 'attSlot')
    .every(([, value]) => !String(value ?? '').trim())
}

export function pruneInterviewSummaryEntities(
  entities: InterviewSummaryEntity[],
): InterviewSummaryEntity[] {
  const filled = entities.filter((entity) => !isBlankInterviewSummaryEntity(entity))
  return filled.length ? filled : [emptyInterviewSummaryEntity()]
}

export function nextAttSlot(entities: InterviewSummaryEntity[]): number {
  return entities.reduce((max, entity) => Math.max(max, entity.attSlot || 0), 0) + 1
}

export function interviewSummarySummary(entities: InterviewSummaryEntity[]) {
  const enriched = entities.map(enrichInterviewSummaryEntity)
  const named = enriched.filter((entity) => entity.supplierName.trim())
  return {
    supplierCount: named.length,
    riskCount: named.filter((entity) => entity.isRisk).length,
    incompleteCount: named.filter((entity) => entity.completionPct < 1).length,
  }
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function yesNo(value: unknown): YesNo {
  return value === '是' || value === '否' ? value : ''
}

function method(value: unknown): InterviewMethod | '' {
  if (value === '现场访谈') return '实地走访'
  return (INTERVIEW_METHODS as readonly string[]).includes(value as string)
    ? (value as InterviewMethod)
    : ''
}

/** 兼容旧版 9 列平铺模型（summary/concerns/intervieweeTitle 等字段）。 */
function normalizeEntity(raw: Record<string, unknown>, index: number): InterviewSummaryEntity {
  const title = text(raw.intervieweeTitle)
  const interviewee = text(raw.interviewee)
  const summary = text(raw.summary)
  const concerns = text(raw.concerns)
  return {
    ...emptyInterviewSummaryEntity(),
    id: text(raw.id) || newInterviewSummaryId(),
    attSlot: typeof raw.attSlot === 'number' && raw.attSlot > 0 ? raw.attSlot : index + 1,
    supplierName: text(raw.supplierName),
    interviewDate: text(raw.interviewDate),
    reason: text(raw.reason),
    method: method(raw.method),
    registeredAddress: text(raw.registeredAddress),
    visitAddress: text(raw.visitAddress),
    interviewee: title ? `${interviewee}（${title}）` : interviewee,
    auditors: text(raw.auditors),
    otherParticipants: text(raw.otherParticipants),
    tripInfo: text(raw.tripInfo),
    onSiteConfirmation: yesNo(raw.onSiteConfirmation),
    focusPoints: text(raw.focusPoints)
      || [summary, concerns ? `关注：${concerns}` : ''].filter(Boolean).join('；'),
    contractCheck: text(raw.contractCheck),
    transactionAmountMatch: yesNo(raw.transactionAmountMatch),
    balanceMatch: yesNo(raw.balanceMatch),
    conclusion: text(raw.conclusion),
    recordIndex: text(raw.recordIndex),
  }
}

export function migrateInterviewSummaryEntities(parsed: unknown): InterviewSummaryEntity[] {
  if (!Array.isArray(parsed)) return [emptyInterviewSummaryEntity()]
  return pruneInterviewSummaryEntities(
    parsed
      .filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
      .map((item, index) => normalizeEntity(item, index)),
  )
}
