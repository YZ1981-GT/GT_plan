/**
 * useG4EclStageClassification — 对齐源底稿 G4-9 的单元测试
 */
import { describe, it, expect } from 'vitest'
import {
  useG4EclStageClassification,
  SECTION_ONE_COUNT,
  SECTION_TWO_COUNT,
  SECTION_THREE_COUNT,
  SECTION_ONE_LABELS,
  SECTION_THREE_LABELS,
} from '../useG4EclStageClassification'
import { determineStage } from '@/composables/useG4EclFormulaEngine'

describe('useG4EclStageClassification — 源模板对齐', () => {
  it('检查项数量为 14 + 3 + 9', () => {
    expect(SECTION_ONE_COUNT).toBe(14)
    expect(SECTION_TWO_COUNT).toBe(3)
    expect(SECTION_THREE_COUNT).toBe(9)
    expect(SECTION_ONE_LABELS).toHaveLength(14)
    expect(SECTION_THREE_LABELS).toHaveLength(9)
  })

  it('包含债投特有已减值项与逾期30日推定', () => {
    expect(SECTION_ONE_LABELS.some(l => l.includes('逾期'))).toBe(true)
    expect(SECTION_THREE_LABELS.some(l => l.includes('回售'))).toBe(true)
    expect(SECTION_THREE_LABELS.some(l => l.includes('其他债券违约'))).toBe(true)
    expect(SECTION_THREE_LABELS.some(l => l.includes('丧失清偿能力'))).toBe(true)
  })

  it('新增行默认结构完整，auditStage=Stage1', () => {
    const logic = useG4EclStageClassification()
    logic.addRow('测试债券A')
    const row = logic.rows.value[0]
    expect(row.sectionOneChecks).toHaveLength(14)
    expect(row.sectionTwoChecks).toHaveLength(3)
    expect(row.sectionThreeChecks).toHaveLength(9)
    expect(row.sectionOneChecks.every(c => c.hint.length > 0)).toBe(true)
    expect(row.auditStage).toBe('Stage1')
    expect(row.sectionConclusions).toEqual({
      significantIncrease: '',
      lowCreditRisk: '',
      creditImpairment: '',
    })
  })

  it('SICR=是 且 低风险豁免 → Stage1；SICR=是 无豁免 → Stage2', () => {
    const logic = useG4EclStageClassification()
    logic.addRow('债券B')
    const id = logic.rows.value[0].id

    logic.updateCheckValue(id, 'significantIncrease', 0, '是')
    expect(logic.rows.value[0].hasSignificantIncrease).toBe(true)
    expect(logic.rows.value[0].auditStage).toBe('Stage2')

    logic.updateCheckValue(id, 'lowCreditRisk', 0, '是')
    logic.updateCheckValue(id, 'lowCreditRisk', 1, '是')
    logic.updateCheckValue(id, 'lowCreditRisk', 2, '是')
    expect(logic.rows.value[0].hasLowCreditRisk).toBe(true)
    expect(logic.rows.value[0].auditStage).toBe('Stage1')
  })

  it('已减值优先于 SICR 与低风险', () => {
    expect(determineStage(true, true, true)).toBe('Stage3')
    const logic = useG4EclStageClassification()
    logic.addRow('债券C')
    const id = logic.rows.value[0].id
    logic.updateCheckValue(id, 'significantIncrease', 13, '是') // 逾期
    logic.updateCheckValue(id, 'creditImpairment', 2, '是') // 不能履行回售
    expect(logic.rows.value[0].auditStage).toBe('Stage3')
  })

  it('从 G4-2 明细导入并预填逾期≥30日 SICR', () => {
    const logic = useG4EclStageClassification()
    const result = logic.importFromDetailRows([
      {
        investProject: '甲公司债',
        closingAudited: 1000000,
        stageClassification: 'Stage1',
        maturityDate: '2020-01-01',
      },
      {
        investProject: '乙公司债',
        closingAudited: 500000,
        stageClassification: 'Stage2',
        maturityDate: '2099-12-31',
      },
    ], { asOfDate: '2023-12-31' })

    expect(result.added).toBe(2)
    expect(result.prefilledOverdue).toBe(1)
    expect(logic.rows.value).toHaveLength(2)
    const a = logic.rows.value.find(r => r.investProject === '甲公司债')!
    expect(a.bookBalance).toBe(1000000)
    expect(a.sectionOneChecks[13].value).toBe('是')
    expect(a.hasSignificantIncrease).toBe(true)
    expect(a.auditStage).toBe('Stage2')
    const b = logic.rows.value.find(r => r.investProject === '乙公司债')!
    expect(b.companyStage).toBe('Stage2')
    expect(b.sectionOneChecks[13].value).toBe('否')
  })
})
