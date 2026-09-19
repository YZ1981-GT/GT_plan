export type RelationshipType = '' | '控制' | '共同控制' | '重大影响' | '无重大影响'

export type CombinationType =
  | ''
  | '同一控制下企业合并'
  | '非同一控制下企业合并'
  | '非企业合并（投资设立等）'
  | '不适用'

export type JudgmentAnswer = '是' | '否' | '不适用' | ''
export type RiskFlag = '高' | '中' | '低' | '无' | ''

export interface G7ControlDecision {
  /** 可选：对齐 G7-4 名册 */
  investeeId?: string
  investeeName: string
  relationshipType: RelationshipType
  combinationType: CombinationType
  combinationBasis: string
  acquisitionDate: string
  acquisitionDateBasis: string
  priorConclusion: RelationshipType
  conclusionChangeReason: string
}

export interface G7ControlRoute {
  code: string
  label: string
  tone: 'success' | 'warning' | 'info'
}

/** 问卷行（与 UI 下拉一致：是/否/不适用） */
export interface G7ControlQuestionnaireRow {
  dimension: string
  judgmentResult: JudgmentAnswer | string
}

export interface G7ControlQuestionnaireSection {
  id: string
  rows: G7ControlQuestionnaireRow[]
}

export function createEmptyG7ControlDecision(
  investeeName = '',
  investeeId = '',
): G7ControlDecision {
  return {
    investeeId: investeeId || undefined,
    investeeName,
    relationshipType: '',
    combinationType: '',
    combinationBasis: '',
    acquisitionDate: '',
    acquisitionDateBasis: '',
    priorConclusion: '',
    conclusionChangeReason: '',
  }
}

export function deriveG7ControlRoute(decision: G7ControlDecision): G7ControlRoute {
  if (decision.relationshipType === '控制') {
    if (decision.combinationType === '同一控制下企业合并') {
      return { code: 'G7-8', label: '转同一控制下企业合并初始计量测试', tone: 'success' }
    }
    if (decision.combinationType === '非同一控制下企业合并') {
      return { code: 'G7-9', label: '转非同一控制下企业合并初始计量测试', tone: 'success' }
    }
    if (decision.combinationType === '非企业合并（投资设立等）') {
      return { code: 'G7-10', label: '保留初始成本依据，转子公司后续计量测试', tone: 'info' }
    }
    return { code: '', label: '请先判断企业合并类型', tone: 'warning' }
  }

  if (decision.relationshipType === '共同控制' || decision.relationshipType === '重大影响') {
    return { code: 'G7-13~G7-17', label: '转权益法组底稿', tone: 'info' }
  }

  if (decision.relationshipType === '无重大影响') {
    return { code: 'G1/G2', label: '转金融工具相关底稿判断分类与计量', tone: 'info' }
  }

  return { code: '', label: '请先确定投资关系类型', tone: 'warning' }
}

export function validateG7ControlDecision(decision: G7ControlDecision): string[] {
  const errors: string[] = []
  if (!decision.investeeName.trim()) errors.push('被投资单位名称不能为空')
  if (!decision.relationshipType) errors.push('尚未确定投资关系类型')
  if (decision.relationshipType === '控制') {
    if (!decision.combinationType || decision.combinationType === '不适用') {
      errors.push('构成控制时必须判断是否企业合并及同控/非同控类型')
    }
    if (decision.combinationType && decision.combinationType !== '不适用' && !decision.combinationBasis.trim()) {
      errors.push('构成控制时应填写企业合并类型判断依据')
    }
    if (
      (decision.combinationType === '同一控制下企业合并'
        || decision.combinationType === '非同一控制下企业合并')
      && !decision.acquisitionDate
    ) {
      errors.push('企业合并应填写合并日/购买日')
    }
    if (
      (decision.combinationType === '同一控制下企业合并'
        || decision.combinationType === '非同一控制下企业合并')
      && !decision.acquisitionDateBasis.trim()
    ) {
      errors.push('企业合并应填写控制权转移日的判断依据')
    }
  }
  if (
    decision.priorConclusion
    && decision.relationshipType
    && decision.priorConclusion !== decision.relationshipType
    && !decision.conclusionChangeReason.trim()
  ) {
    errors.push('本期结论与前期不一致，应填写变化原因')
  }
  return errors
}

/** 综合判断 section 全部维度须有判断结果（生产保存门禁） */
export function validateQuestionnaireOverall(sections: G7ControlQuestionnaireSection[]): string[] {
  const overall = sections.find(s => s.id === 'overallJudgment')
  if (!overall) return ['综合判断 section 缺失']
  const unanswered = overall.rows
    .filter(r => !String(r.judgmentResult || '').trim())
    .map(r => r.dimension)
  if (unanswered.length) {
    return [`综合判断尚未完成：${unanswered.join('、')}`]
  }
  return []
}

export function validateG7ControlJudgmentForSave(
  decision: G7ControlDecision,
  sections: G7ControlQuestionnaireSection[],
  additional: G7ControlDecision[] = [],
): string[] {
  const errors = [
    ...validateG7ControlDecision(decision),
    ...validateQuestionnaireOverall(sections),
  ]
  additional.forEach((d, i) => {
    for (const msg of validateG7ControlDecision(d)) {
      errors.push(`其他被投资单位#${i + 1}：${msg}`)
    }
  })
  return errors
}

function yesCount(section: G7ControlQuestionnaireSection | undefined): number {
  return section?.rows.filter(r => r.judgmentResult === '是').length ?? 0
}

function overallAnswer(
  sections: G7ControlQuestionnaireSection[],
  dimension: string,
): string {
  const overall = sections.find(s => s.id === 'overallJudgment')
  return String(overall?.rows.find(r => r.dimension === dimension)?.judgmentResult || '').trim()
}

/**
 * 由问卷推导建议的投资关系类型。
 * 优先看 (六) 综合判断显式结论；否则回退三要素「是否有任一“是”」。
 */
export function suggestRelationshipFromQuestionnaire(
  sections: G7ControlQuestionnaireSection[],
): { relationshipType: RelationshipType; basis: string; confidence: 'high' | 'medium' | 'low' } {
  const controlYes = overallAnswer(sections, '控制三要素同时满足') === '是'
  const jointYes = overallAnswer(sections, '共同控制条件满足') === '是'
  const significantYes = overallAnswer(sections, '重大影响条件满足') === '是'

  if (controlYes && !jointYes) {
    return {
      relationshipType: '控制',
      basis: '综合判断「控制三要素同时满足」= 是',
      confidence: 'high',
    }
  }
  if (jointYes && !controlYes) {
    return {
      relationshipType: '共同控制',
      basis: '综合判断「共同控制条件满足」= 是',
      confidence: 'high',
    }
  }
  if (significantYes && !controlYes && !jointYes) {
    return {
      relationshipType: '重大影响',
      basis: '综合判断「重大影响条件满足」= 是',
      confidence: 'high',
    }
  }
  if (controlYes && jointYes) {
    return {
      relationshipType: '控制',
      basis: '综合判断同时勾选控制与共同控制，默认优先控制，请人工复核',
      confidence: 'low',
    }
  }

  const powerYes = yesCount(sections.find(s => s.id === 'power'))
  const returnYes = yesCount(sections.find(s => s.id === 'variableReturns'))
  const linkYes = yesCount(sections.find(s => s.id === 'powerReturnLink'))
  if (powerYes > 0 && returnYes > 0 && linkYes > 0) {
    return {
      relationshipType: '控制',
      basis: `三要素区段均有“是”（权力${powerYes}/可变回报${returnYes}/联系${linkYes}），建议认定为控制`,
      confidence: 'medium',
    }
  }
  if (powerYes > 0 && returnYes > 0) {
    return {
      relationshipType: '',
      basis: '权力与可变回报有“是”但缺联系，需结合综合判断人工定论',
      confidence: 'low',
    }
  }
  return {
    relationshipType: '',
    basis: '问卷尚未形成可建议的关系类型',
    confidence: 'low',
  }
}

/** CAS33 三要素粗判（供测试与提示）：三区段均有“是”→ control */
export function deriveControlTriadHint(
  sections: G7ControlQuestionnaireSection[],
): 'control' | 'partial_power_return' | 'no_control' {
  const powerYes = yesCount(sections.find(s => s.id === 'power'))
  const returnYes = yesCount(sections.find(s => s.id === 'variableReturns'))
  const linkYes = yesCount(sections.find(s => s.id === 'powerReturnLink'))
  if (powerYes > 0 && returnYes > 0 && linkYes > 0) return 'control'
  if (powerYes > 0 && returnYes > 0) return 'partial_power_return'
  return 'no_control'
}

export function buildG7ControlConclusion(decision: G7ControlDecision): string {
  const route = deriveG7ControlRoute(decision)
  const dateText = decision.acquisitionDate
    ? `控制权转移日为 ${decision.acquisitionDate}`
    : '不涉及合并日/购买日判断'
  const combinationText = decision.relationshipType === '控制'
    ? `，交易分类为${decision.combinationType || '尚未确定'}`
    : ''
  return `经审查，对${decision.investeeName || '该被投资单位'}的关系认定为${decision.relationshipType || '尚未确定'}${combinationText}；${dateText}。后续处理：${route.code ? `${route.code} ` : ''}${route.label}。`
}

/** 兼容 axios / ResponseWrapper：优先 content（实现见 g7AiText） */
export { extractG7AiText, extractG7SubAiText } from './g7AiText'


function asDecision(raw: any): G7ControlDecision | null {
  if (!raw || typeof raw !== 'object') return null
  const name = String(raw.investeeName ?? '').trim()
  if (!name && !raw.relationshipType) return null
  return {
    investeeId: String(raw.investeeId ?? '').trim() || undefined,
    investeeName: name,
    relationshipType: (raw.relationshipType ?? '') as RelationshipType,
    combinationType: (raw.combinationType ?? '') as CombinationType,
    combinationBasis: String(raw.combinationBasis ?? ''),
    acquisitionDate: String(raw.acquisitionDate ?? ''),
    acquisitionDateBasis: String(raw.acquisitionDateBasis ?? ''),
    priorConclusion: (raw.priorConclusion ?? '') as RelationshipType,
    conclusionChangeReason: String(raw.conclusionChangeReason ?? ''),
  }
}

/** 主决策 + additionalDecisions，供 G7-8/9 同步抽取 */
export function listG7ControlDecisions(payload: unknown): G7ControlDecision[] {
  let data = payload
  if (typeof data === 'string') {
    try { data = JSON.parse(data) } catch { return [] }
  }
  const root = (data as any)?.controlJudgment ?? data
  if (!root || typeof root !== 'object') return []
  const out: G7ControlDecision[] = []
  const primary = asDecision(root.decision)
  if (primary?.investeeName) out.push(primary)
  const extras = Array.isArray(root.additionalDecisions) ? root.additionalDecisions : []
  for (const item of extras) {
    const d = asDecision(item)
    if (d?.investeeName) out.push(d)
  }
  return out
}

export function filterDecisionsByCombination(
  decisions: G7ControlDecision[],
  combinationType: CombinationType,
): string[] {
  const names: string[] = []
  const seen = new Set<string>()
  for (const d of decisions) {
    if (d.relationshipType !== '控制') continue
    if (d.combinationType !== combinationType) continue
    const name = d.investeeName.trim()
    if (!name || seen.has(name)) continue
    seen.add(name)
    names.push(name)
  }
  return names
}
