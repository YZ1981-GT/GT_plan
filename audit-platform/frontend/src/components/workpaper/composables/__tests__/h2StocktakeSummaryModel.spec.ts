/**
 * H2-14 监盘小结模型单元测试
 */
import { describe, it, expect } from 'vitest'
import {
  createEmptyH2SummaryForm,
  normalizeH2SummaryForm,
  draftObservationsFromCheckRows,
  draftAbnormalsFromCheckRows,
  calcH2SummaryCompleteness,
  draftH2Conclusion,
  isTimeRangeValid,
  OBSERVATION_CHECK_DEFS,
} from '../h2StocktakeSummaryModel'

describe('h2StocktakeSummaryModel', () => {
  it('createEmpty has 6 observation checks', () => {
    const f = createEmptyH2SummaryForm()
    expect(f.observationChecks).toHaveLength(6)
    expect(f.observationChecks.map((c) => c.id)).toEqual(OBSERVATION_CHECK_DEFS.map((d) => d.id))
  })

  it('normalize merges legacy overallSituation/conclusion', () => {
    const f = normalizeH2SummaryForm({
      overallSituation: '旧版总体',
      conclusion: '旧版结论',
      abnormalProjects: [{ name: 'A', abnormalType: '停工', description: 'd', suggestion: '关注减值' }],
    })
    expect(f.overallSituation).toBe('旧版总体')
    expect(f.conclusion).toBe('旧版结论')
    expect(f.abnormalProjects).toHaveLength(1)
    expect(f.abnormalProjects[0].name).toBe('A')
    expect(f.observationChecks).toHaveLength(6)
  })

  it('draftObservationsFromCheckRows maps H2-13 fields', () => {
    const rows = draftObservationsFromCheckRows([
      {
        name: '厂房扩建',
        siteLocation: '东区',
        visibleProgress: 60,
        constructionStatus: '施工中',
        progressDifference: '略快',
        photos: 'P-1',
        auditConclusion: '存在',
        remark: '',
      },
    ])
    expect(rows).toHaveLength(1)
    expect(rows[0].projectName).toBe('厂房扩建')
    expect(rows[0].location).toBe('东区')
    expect(rows[0].photoIndex).toBe('P-1')
    expect(rows[0].progressDescription).toContain('形象进度约 60%')
  })

  it('draftAbnormalsFromCheckRows detects 停工 and 进度异常', () => {
    const abn = draftAbnormalsFromCheckRows([
      {
        name: '停工项',
        constructionStatus: '停工',
        progressDifference: '',
        auditConclusion: '',
        remark: '资金链',
      },
      {
        name: '进度项',
        constructionStatus: '施工中',
        progressDifference: '账面80%现场50%',
        auditConclusion: '',
        remark: '',
      },
    ])
    expect(abn.some((a) => a.abnormalType === '停工' && a.name === '停工项')).toBe(true)
    expect(abn.some((a) => a.abnormalType === '进度异常' && a.name === '进度项')).toBe(true)
  })

  it('completeness and conclusion draft', () => {
    const f = createEmptyH2SummaryForm()
    expect(calcH2SummaryCompleteness(f).every((c) => !c.ok)).toBe(true)
    f.bsDateNote = '与报表日一致'
    f.engDept = '工程部'
    f.actualDate = '2025-12-20'
    f.projectObservations = [
      {
        rowId: '1',
        seq: 1,
        projectName: 'X',
        diagramIndex: '',
        location: '',
        progressDescription: 'ok',
        photoIndex: '',
        constructionStatus: '施工中',
        visibleProgress: 50,
      },
    ]
    f.clientPersonnel = [
      { rowId: 'c1', seq: 1, department: '工程', headcount: 1, names: '张三', responsibleArea: '全场' },
    ]
    f.observationChecks[0].answer = '一致'
    f.conclusion = '达标'
    expect(calcH2SummaryCompleteness(f).every((c) => c.ok)).toBe(true)

    const text = draftH2Conclusion(f, { total: 1, inProgress: 1, stopped: 0, completed: 0 })
    expect(text).toContain('覆盖在建工程项目')
  })

  it('isTimeRangeValid', () => {
    expect(isTimeRangeValid('09:00', '17:00')).toBe(true)
    expect(isTimeRangeValid('17:00', '09:00')).toBe(false)
    expect(isTimeRangeValid('', '09:00')).toBe(true)
  })
})
