export type RelationshipType = '' | '控制' | '共同控制' | '重大影响' | '无重大影响'

export type CombinationType =
  | ''
  | '同一控制下企业合并'
  | '非同一控制下企业合并'
  | '非企业合并（投资设立等）'
  | '不适用'

export interface G7ControlDecision {
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
