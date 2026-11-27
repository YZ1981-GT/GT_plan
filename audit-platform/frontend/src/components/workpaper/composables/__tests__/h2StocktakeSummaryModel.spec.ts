import { describe, expect, it } from 'vitest'
import {
  OBSERVATION_CHECK_DEFS,
  createEmptySummary,
  evaluateSummaryCompleteness,
  fillSummaryFromUpstream,
  mergeAbnormalFromCheckRows,
  normalizeSummary,
  summaryLogicWarnings,
} from '../h2StocktakeSummaryModel'
import { createEmptyPlanForm } from '../h2StocktakePlanModel'
import { createEmptyCheckRow, isStoppedCheckRow } from '../h2StocktakeCheckModel'

describe('H2-14 监盘小结模型', () => {
  it('保存后再读入：全部字段原样读回（原先只保留 5 个字段）', () => {
    const s = createEmptySummary()
    s.bsDateNote = '察看日在资产负债表日后 3 天'
    s.engDept = '工程部'
    s.policyIndex = 'C7'
    s.clientPersonnel.push({ rowId: 'cp-1', department: '工程部', headcount: 2, names: '张三', responsibleArea: 'A 区' })
    s.actualDate = '2026-01-03'
    s.startTime = '09:00'
    s.endTime = '11:30'
    s.observationChecks[3].answer = '一致'
    s.diffExplanationObtained = 'Y'
    s.reviewedBy = '李四'
    const back = normalizeSummary(JSON.parse(JSON.stringify(s)))
    expect(back).toEqual(s)
  })

  it('旧版只存 5 个字段也能读，六问按模板原文补齐', () => {
    const back = normalizeSummary({ overallSituation: '总体', conclusion: '结论', abnormalProjects: [{ name: '一号楼' }] })
    expect(back.overallSituation).toBe('总体')
    expect(back.abnormalProjects[0].name).toBe('一号楼')
    expect(back.abnormalProjects[0].rowId).toBeTruthy()
    expect(back.observationChecks.map((c) => c.label)).toEqual(OBSERVATION_CHECK_DEFS.map((d) => d.label))
  })

  it('闸门：空表全部未通过，时间倒挂不算填齐', () => {
    const s = createEmptySummary()
    expect(evaluateSummaryCompleteness(s).every((c) => !c.ok)).toBe(true)
    s.actualDate = '2026-01-03'
    s.startTime = '10:00'
    s.endTime = '09:00'
    expect(evaluateSummaryCompleteness(s).find((c) => c.id === 'time')!.ok).toBe(false)
    expect(summaryLogicWarnings(s, [], isStoppedCheckRow)).toContain('察看结束时间早于或等于开始时间')
  })

  it('停工工程并入异常并按名去重；未列入时有提示', () => {
    const s = createEmptySummary()
    const row = createEmptyCheckRow('bookToFloor', 1, '二号厂房')
    row.constructionStatus = '停工'
    row.stopReason = '资金不足'
    expect(summaryLogicWarnings(s, [row], isStoppedCheckRow).some((w) => w.includes('二号厂房'))).toBe(true)
    expect(mergeAbnormalFromCheckRows(s, [row], isStoppedCheckRow)).toBe(1)
    expect(mergeAbnormalFromCheckRows(s, [row], isStoppedCheckRow)).toBe(0)
    expect(s.abnormalProjects[0]).toMatchObject({ name: '二号厂房', abnormalType: '停工' })
  })

  it('回填只填空字段，不覆盖已填', () => {
    const s = createEmptySummary()
    s.engDept = '已填部门'
    const plan = createEmptyPlanForm()
    plan.plannedDate = '2026-01-05'
    plan.icResponsible = '计划里的部门'
    fillSummaryFromUpstream(s, plan, [createEmptyCheckRow('bookToFloor', 1, '三号线')])
    expect(s.actualDate).toBe('2026-01-05')
    expect(s.engDept).toBe('已填部门')
    expect(s.projectObservations.map((o) => o.projectName)).toEqual(['三号线'])
  })
})
