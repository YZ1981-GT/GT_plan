import { describe, it, expect } from 'vitest'
import {
  calcG10AuditSampleSize,
  calcG10SuggestedSampleSize,
  defaultG10ScopeSamplingParams,
  g10VoucherInspectionRatio,
} from '../g10VoucherConstants'
import {
  applyG10DerivativeWizardToRows,
  evaluateG10DerivativeWizard,
  defaultG10DerivativeWizardState,
} from '../g10DerivativeDecision'
import { buildG10VoucherSamplingMemo } from '../useG10VoucherCheck'
import { G10_DERIVATIVE_SEED } from '../g10DerivativeSeed'
import { defaultG10SamplingParams } from '../g10VoucherConstants'

describe('g10VoucherConstants sampling', () => {
  it('样本量公式', () => {
    const n = calcG10AuditSampleSize({
      bookValue: 100000,
      riskFactor: 1,
      tolerableMisstatement: 5000,
      expectedMisstatement: 500,
      expansionFactor: 1.6,
    })
    expect(n).toBeGreaterThan(0)
  })

  it('检查比例', () => {
    expect(g10VoucherInspectionRatio(3000, 10000)).toBeCloseTo(0.3)
    expect(g10VoucherInspectionRatio(100, 0)).toBeNull()
  })

  it('建议样本量', () => {
    const scope = defaultG10ScopeSamplingParams()
    scope.bookValue = 50000
    scope.tolerableMisstatement = 2000
    scope.riskOfIncorrectAcceptance = 5
    expect(calcG10SuggestedSampleSize(scope)).toBeGreaterThan(0)
  })
})

describe('buildG10VoucherSamplingMemo', () => {
  it('备忘含科目 2101 与分表', () => {
    const md = buildG10VoucherSamplingMemo({
      params: defaultG10SamplingParams(),
      rows: [],
      conclusion: '未见异常',
    })
    expect(md).toContain('G10-7')
    expect(md).toContain('2101')
    expect(md).toContain('本期发生额检查')
    expect(md).toContain('期后处置')
  })
})

describe('g10DerivativeDecision', () => {
  it('B 全否 → 无衍生', () => {
    const state = defaultG10DerivativeWizardState()
    const keys = [
      'interestRate', 'financialPrice', 'commodityPrice', 'exchangeRate',
      'index', 'creditRating', 'otherFinancial', 'otherNonFinancial',
    ] as const
    for (const k of keys) state.variableAnswers[k] = 'no'
    const r = evaluateG10DerivativeWizard(state)
    expect(r.hasDerivative).toBe(false)
    expect(r.measurement).toBe('none')
  })

  it('D 三条件均满足 → 应拆分', () => {
    const state = defaultG10DerivativeWizardState()
    const keys = [
      'interestRate', 'financialPrice', 'commodityPrice', 'exchangeRate',
      'index', 'creditRating', 'otherFinancial', 'otherNonFinancial',
    ] as const
    for (const k of keys) state.variableAnswers[k] = k === 'interestRate' ? 'yes' : 'no'
    state.embeddedSeparateTransfer = 'no'
    state.embeddedSameCounterparty = 'yes'
    state.d1NotCloselyRelated = 'yes'
    state.d2StandaloneDerivative = 'yes'
    state.d3NotFvtpl = 'yes'
    state.canMeasureSeparately = 'yes'
    const r = evaluateG10DerivativeWizard(state)
    expect(r.shouldSplit).toBe(true)
    expect(r.measurement).toBe('split_fvtpl')
  })

  it('向导自动勾选问卷行', () => {
    const state = defaultG10DerivativeWizardState()
    const keys = [
      'interestRate', 'financialPrice', 'commodityPrice', 'exchangeRate',
      'index', 'creditRating', 'otherFinancial', 'otherNonFinancial',
    ] as const
    for (const k of keys) state.variableAnswers[k] = k === 'interestRate' ? 'yes' : 'no'
    state.embeddedSeparateTransfer = 'no'
    state.embeddedSameCounterparty = 'yes'
    state.d1NotCloselyRelated = 'yes'
    state.d2StandaloneDerivative = 'yes'
    state.d3NotFvtpl = 'yes'
    state.canMeasureSeparately = 'yes'
    state.contractReviewNote = '已审阅贷款合同'

    const seedRows = G10_DERIVATIVE_SEED.map((s, i) => ({
      checkItem: s.checkItem,
      checkArea: s.checkArea,
      sectionNo: s.sectionNo,
      compliance: '' as const,
      checkResult: '',
      auditConclusion: '',
      indexRef: '',
      remark: '',
      rowId: `r${i}`,
    }))
    const { filled, rows } = applyG10DerivativeWizardToRows(seedRows, state)
    expect(filled).toBeGreaterThan(10)
    const defRow = rows.find((r) => r.checkItem.includes('衍生工具定义'))
    expect(defRow?.compliance).toBe('compliant')
    const hedgeRow = rows.find((r) => r.checkItem.includes('套期关系文档'))
    expect(hedgeRow?.compliance).toBe('not_applicable')
  })
})
