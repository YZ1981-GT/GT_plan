/** F2-72 供应商访谈记录：逐家正式访谈问卷纯函数层。 */

export const F2_72_OBJECTIVE =
  '审计目标：通过对主要供应商的正式访谈，核实交易真实性、商业合理性及关联关系，留存可复核的访谈证据。'

export interface InterviewQuestionDef {
  key: string
  section: string
  prompt: string
  /** 红色提示题：可按项目风险改写题干。 */
  editablePrompt?: boolean
  placeholder?: string
}

/** 源表固定十一项访谈提纲（可按被审计单位与供应商风险改写第10、11题）。 */
export const F2_72_QUESTIONS: InterviewQuestionDef[] = [
  {
    key: 'q1',
    section: '一、访谈对象介绍',
    prompt: '请介绍一下您的姓名、公司、职位、具体负责的工作等。',
    placeholder: '姓名、公司、职位、职责……',
  },
  {
    key: 'q2',
    section: '二、公司基本情况',
    prompt: '请介绍一下贵公司的基本情况，包括股东情况、管理层情况、主要业务及产品、所处行业、规模、人员数量、产能、场地面积等。',
    placeholder: '股东、管理层、主营产品、行业、规模、人数、产能、场地……',
  },
  {
    key: 'q3',
    section: '三、业务关系建立',
    prompt: '贵公司与被审计单位的业务关系何时开始、如何建立？',
    placeholder: '合作起始时间、建立途径……',
  },
  {
    key: 'q4',
    section: '四、合同条款与纠纷',
    prompt: '请说明与被审计单位相关合同的主要条款、有无纠纷及解决情况。',
    placeholder: '合同主要条款、纠纷及解决……',
  },
  {
    key: 'q5',
    section: '五、本期交易情况',
    prompt: '请说明本期向被审计单位销售的产品种类、金额、占贵公司当年销售额比例、定价方式、交货及结算方式、有无期末余额。',
    placeholder: '产品种类、金额、占比、定价、交货结算、余额……',
  },
  {
    key: 'q6',
    section: '六、产品市场情况',
    prompt: '贵公司主要产品的年销售额、主要客户及平均售价情况如何？',
    placeholder: '主要产品销售额、主要客户、均价……',
  },
  {
    key: 'q7',
    section: '七、自产与外协',
    prompt: '销售给被审计单位的货物是否由贵公司自行生产？如否，自产与外协的数量/重量、外协厂家名称是什么？',
    placeholder: '自产/外协比例、外协厂家……',
  },
  {
    key: 'q8',
    section: '八、其他资金往来',
    prompt: '除上述业务往来外，贵公司与被审计单位是否存在其他资金往来？',
    placeholder: '有无拆借、代垫、往来款等……',
  },
  {
    key: 'q9',
    section: '九、关联关系核查',
    prompt: '贵公司及实际控制人与被审计单位的实际控制人、董监高、主要客户等是否存在持股、任职、亲属或其他利益关系？是否存在业务或资金往来？',
    placeholder: '持股/任职/亲属关系、业务或资金往来……',
  },
  {
    key: 'q10',
    section: '十、专项关注事项',
    prompt: '如存在大额预付款或其他异常安排，请说明原因、资金用途及交货计划。',
    editablePrompt: true,
    placeholder: '按项目风险改写本题后填写……',
  },
  {
    key: 'q11',
    section: '十一、其他问题',
    prompt: '其他需要补充说明的事项。',
    editablePrompt: true,
    placeholder: '其他补充……',
  },
]

export interface InterviewQaItem {
  key: string
  prompt: string
  answer: string
}

export interface InterviewDetailEntity {
  id: string
  /** ItemAttachment 槽位，跨排序保持稳定。 */
  attSlot: number
  supplierName: string
  interviewee: string
  interviewTimePlace: string
  participants: string
  interviewDate: string
  location: string
  qaItems: InterviewQaItem[]
  intervieweeSign: string
  auditorSign: string
  otherSign: string
  signDate: string
  declarationAck: boolean
  conclusion: string
  remark: string
}

export interface EnrichedInterviewDetailEntity extends InterviewDetailEntity {
  answeredCount: number
  requiredCount: number
  completionPct: number
  isIncomplete: boolean
  riskFlags: string[]
  isRisk: boolean
}

const CORE_KEYS = ['q1', 'q2', 'q3', 'q5', 'q7', 'q8', 'q9'] as const

let sequence = 0
export function newInterviewDetailId(): string {
  sequence += 1
  return `f272-${Date.now().toString(36)}-${sequence}`
}

export function defaultQaItems(): InterviewQaItem[] {
  return F2_72_QUESTIONS.map((q) => ({
    key: q.key,
    prompt: q.prompt,
    answer: '',
  }))
}

export function emptyInterviewDetailEntity(attSlot = 1): InterviewDetailEntity {
  return {
    id: newInterviewDetailId(),
    attSlot,
    supplierName: '',
    interviewee: '',
    interviewTimePlace: '',
    participants: '',
    interviewDate: '',
    location: '',
    qaItems: defaultQaItems(),
    intervieweeSign: '',
    auditorSign: '',
    otherSign: '',
    signDate: '',
    declarationAck: false,
    conclusion: '',
    remark: '',
  }
}

export function enrichInterviewDetailEntity(
  entity: InterviewDetailEntity,
): EnrichedInterviewDetailEntity {
  const answers = new Map(entity.qaItems.map((item) => [item.key, item]))
  const answeredCount = entity.qaItems.filter((item) => item.answer.trim()).length
  const requiredCount = CORE_KEYS.length
  const coreFilled = CORE_KEYS.filter((key) => (answers.get(key)?.answer || '').trim()).length
  const riskFlags: string[] = []
  const q7 = (answers.get('q7')?.answer || '')
  const q8 = (answers.get('q8')?.answer || '')
  const q9 = (answers.get('q9')?.answer || '')
  if (/外协|委外|代工/.test(q7) && !/无外协|全部自产|自行生产/.test(q7)) {
    riskFlags.push('存在外协生产')
  }
  if (/有|存在|拆借|代垫|往来/.test(q8) && !/无其他|不存在|没有/.test(q8)) {
    riskFlags.push('存在其他资金往来')
  }
  if (/有|存在|持股|任职|亲属|关联/.test(q9) && !/无关联|不存在|没有/.test(q9)) {
    riskFlags.push('可能存在关联关系')
  }
  if (!entity.declarationAck && entity.supplierName.trim()) {
    riskFlags.push('真实性声明未确认')
  }
  const isIncomplete = !entity.supplierName.trim()
    || !entity.interviewee.trim()
    || !entity.interviewDate.trim()
    || coreFilled < requiredCount
    || !entity.conclusion.trim()
  return {
    ...entity,
    answeredCount,
    requiredCount,
    completionPct: answeredCount / Math.max(entity.qaItems.length, 1),
    isIncomplete,
    riskFlags,
    isRisk: riskFlags.length > 0 || isIncomplete,
  }
}

export function isBlankInterviewDetailEntity(entity: InterviewDetailEntity): boolean {
  if (entity.supplierName.trim() || entity.interviewee.trim() || entity.conclusion.trim()) return false
  return entity.qaItems.every((item) => !item.answer.trim() && item.prompt === (
    F2_72_QUESTIONS.find((q) => q.key === item.key)?.prompt || item.prompt
  ))
}

export function pruneInterviewDetailEntities(
  entities: InterviewDetailEntity[],
): InterviewDetailEntity[] {
  const filled = entities.filter((entity) => !isBlankInterviewDetailEntity(entity))
  return filled.length ? filled : [emptyInterviewDetailEntity()]
}

export function nextInterviewAttSlot(entities: InterviewDetailEntity[]): number {
  return entities.reduce((max, entity) => Math.max(max, entity.attSlot || 0), 0) + 1
}

export function interviewDetailSummary(entities: InterviewDetailEntity[]) {
  const enriched = entities.map(enrichInterviewDetailEntity)
  const named = enriched.filter((entity) => entity.supplierName.trim())
  return {
    interviewCount: named.length,
    incompleteCount: named.filter((entity) => entity.isIncomplete).length,
    riskCount: named.filter((entity) => entity.riskFlags.length > 0).length,
  }
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function mergeQaItems(rawItems: unknown, legacyPairs: unknown): InterviewQaItem[] {
  const defaults = defaultQaItems()
  const byKey = new Map(defaults.map((item) => [item.key, { ...item }]))

  if (Array.isArray(rawItems)) {
    for (const raw of rawItems) {
      if (!raw || typeof raw !== 'object') continue
      const row = raw as Record<string, unknown>
      const key = text(row.key) || `custom-${byKey.size + 1}`
      const existing = byKey.get(key)
      byKey.set(key, {
        key,
        prompt: text(row.prompt) || existing?.prompt || text(row.question) || '',
        answer: text(row.answer),
      })
    }
  }

  // 旧版自由问答：按题序回填答案，多余问答追加为自定义题
  if (Array.isArray(legacyPairs)) {
    let idx = 0
    const keys = defaults.map((item) => item.key)
    for (const raw of legacyPairs) {
      if (!raw || typeof raw !== 'object') continue
      const row = raw as Record<string, unknown>
      const question = text(row.question)
      const answer = text(row.answer)
      if (!question && !answer) continue
      const key = keys[idx]
      if (key && byKey.has(key) && !byKey.get(key)!.answer) {
        const item = byKey.get(key)!
        if (question) item.prompt = question
        item.answer = answer
        idx += 1
      } else {
        const customKey = `custom-${byKey.size + 1}`
        byKey.set(customKey, { key: customKey, prompt: question || '补充问题', answer })
      }
    }
  }

  // 保持默认题顺序，其后追加自定义题
  const ordered: InterviewQaItem[] = defaults.map((item) => byKey.get(item.key) || item)
  for (const [key, item] of byKey) {
    if (!defaults.some((d) => d.key === key)) ordered.push(item)
  }
  return ordered
}

function normalizeEntity(raw: Record<string, unknown>, index: number): InterviewDetailEntity {
  const date = text(raw.interviewDate)
  const location = text(raw.location)
  const timePlace = text(raw.interviewTimePlace)
    || [date, location].filter(Boolean).join(' / ')
  return {
    ...emptyInterviewDetailEntity(),
    id: text(raw.id) || newInterviewDetailId(),
    attSlot: typeof raw.attSlot === 'number' && raw.attSlot > 0 ? raw.attSlot : index + 1,
    supplierName: text(raw.supplierName),
    interviewee: text(raw.interviewee),
    interviewTimePlace: timePlace,
    participants: text(raw.participants),
    interviewDate: date,
    location,
    qaItems: mergeQaItems(raw.qaItems, raw.qaPairs),
    intervieweeSign: text(raw.intervieweeSign),
    auditorSign: text(raw.auditorSign),
    otherSign: text(raw.otherSign),
    signDate: text(raw.signDate),
    declarationAck: Boolean(raw.declarationAck),
    conclusion: text(raw.conclusion) || text(raw.auditFocus),
    remark: text(raw.remark) || text(raw.topic),
  }
}

export function migrateInterviewDetailEntities(parsed: unknown): InterviewDetailEntity[] {
  if (!Array.isArray(parsed)) return [emptyInterviewDetailEntity()]
  return pruneInterviewDetailEntities(
    parsed
      .filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
      .map((item, index) => normalizeEntity(item, index)),
  )
}
