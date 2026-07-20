import { describe, expect, it } from 'vitest'
import {
  buildG7ControlConclusion,
  deriveG7ControlRoute,
  extractG7SubAiText,
  suggestRelationshipFromQuestionnaire,
  validateG7ControlDecision,
  type G7ControlDecision,
} from '../g7ControlJudgmentModel'

function decision(overrides: Partial<G7ControlDecision> = {}): G7ControlDecision {
  return {
    investeeName: '甲公司',
    relationshipType: '控制',
    combinationType: '同一控制下企业合并',
    combinationBasis: '合并前后均由A集团最终控制且超过一年',
    acquisitionDate: '2026-01-01',
    acquisitionDateBasis: '已获批准、支付对价并接管经营财务决策',
    priorConclusion: '控制',
    conclusionChangeReason: '',
    ...overrides,
  }
}

describe('g7ControlJudgmentModel', () => {
  it('routes same-control combination to G7-8', () => {
    expect(deriveG7ControlRoute(decision()).code).toBe('G7-8')
  })

  it('routes non-same-control combination to G7-9', () => {
    expect(deriveG7ControlRoute(decision({
      combinationType: '非同一控制下企业合并',
      combinationBasis: '合并前后最终控制方不同',
    })).code).toBe('G7-9')
  })

  it('routes joint control and significant influence to equity method papers', () => {
    expect(deriveG7ControlRoute(decision({
      relationshipType: '共同控制',
      combinationType: '不适用',
      combinationBasis: '',
      acquisitionDate: '',
      acquisitionDateBasis: '',
    })).code).toBe('G7-13~G7-17')
  })

  it('requires combination type, date and supporting basis for control', () => {
    const errors = validateG7ControlDecision(decision({
      combinationType: '',
      combinationBasis: '',
      acquisitionDate: '',
      acquisitionDateBasis: '',
    }))
    expect(errors).toContain('构成控制时必须判断是否企业合并及同控/非同控类型')
  })

  it('requires reason when current conclusion differs from prior period', () => {
    const errors = validateG7ControlDecision(decision({
      priorConclusion: '重大影响',
      conclusionChangeReason: '',
    }))
    expect(errors).toContain('本期结论与前期不一致，应填写变化原因')
  })

  it('builds conclusion with route and acquisition date', () => {
    const text = buildG7ControlConclusion(decision())
    expect(text).toContain('同一控制下企业合并')
    expect(text).toContain('2026-01-01')
    expect(text).toContain('G7-8')
  })

  it('suggests control from overall judgment row', () => {
    const hint = suggestRelationshipFromQuestionnaire([
      { id: 'power', rows: [] },
      {
        id: 'overallJudgment',
        rows: [{ dimension: '控制三要素同时满足', judgmentResult: '是' }],
      },
    ])
    expect(hint.relationshipType).toBe('控制')
    expect(hint.confidence).toBe('high')
  })

  it('parses AI content field', () => {
    expect(extractG7SubAiText({ data: { content: 'AI正文' } })).toBe('AI正文')
  })
})
