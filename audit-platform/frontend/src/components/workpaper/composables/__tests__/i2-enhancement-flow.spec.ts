/**
 * i2-enhancement-flow.spec.ts — I2-5/10/15 增强链路纯函数冒烟
 * 覆盖：TB 阈值预算 / 认定闸门 / 薪酬勾稽 / 减值事件载荷
 */
import { describe, it, expect } from 'vitest'
import {
  createDefaultBundle,
  emptyCompositionRow,
  syncDerivedFromComposition,
  summarizeAnalysisAnomalies,
  buildAnalysisConclusionDraft,
} from '../i2AnalysisModel'
import {
  emptyI2WorkHourRow,
  recomputeI2WorkHourRow,
  validateWorkHourAgainstStaff,
  reconcileWorkHourSalaryVsAnalysis,
  summarizeI2WorkHourRows,
  buildWorkHourConclusionDraft,
} from '../i2WorkHourModel'
import {
  emptyI2ImpairmentRow,
  recomputeI2ImpairmentRow,
  summarizeI2Impairment,
  buildI2ImpairmentEventDetail,
  buildI2ImpairmentAdjustmentHint,
} from '../i2ImpairmentModel'

describe('I2 enhancement flow smoke', () => {
  it('I2-5: budget anomaly + conclusion draft', () => {
    const b = createDefaultBundle()
    b.compositionMeta.revenueCurrent = 10000
    b.compositionMeta.revenuePrior = 10000
    b.compositionMeta.growthThreshold = 0.2
    b.compositionRows = [
      emptyCompositionRow({
        itemName: '人工费',
        currentAmount: 1500,
        priorAmount: 1000,
        budgetAmount: 1000,
      }),
    ]
    const synced = syncDerivedFromComposition(b)
    expect(synced.compositionRows[0].isAnomaly).toBe(true)
    expect(synced.peerIndicators[0].current).toBeCloseTo(0.15)
    const draft = buildAnalysisConclusionDraft(synced)
    expect(draft).toMatch(/15\.00%|1500/)
    expect(summarizeAnalysisAnomalies(synced).compositionAnomalyCount).toBeGreaterThan(0)
  })

  it('I2-10: staff gate blocks unrecognized + salary reconcile', () => {
    const hours = [
      recomputeI2WorkHourRow(emptyI2WorkHourRow({
        staffName: '张三',
        projectName: 'P1',
        hours: 80,
        totalHours: 160,
        allocationBasis: '工时表',
        salaryAccrual: 5000,
      })),
      recomputeI2WorkHourRow(emptyI2WorkHourRow({
        staffName: '李四',
        projectName: 'P1',
        hours: 40,
        totalHours: 160,
        allocationBasis: '考勤记录',
        salaryAccrual: 2000,
      })),
    ]
    const staff = [
      { staffName: '张三', conclusion: '认定为研发人员' },
      { staffName: '李四', conclusion: '不予认定' },
    ]
    const gate = validateWorkHourAgainstStaff(hours, staff)
    expect(gate.ok).toBe(false)
    expect(gate.messages.some((m) => m.includes('李四'))).toBe(true)

    const salaryTotal = summarizeI2WorkHourRows(hours).totalSalary
    const rec = reconcileWorkHourSalaryVsAnalysis(salaryTotal, 7000)
    expect(rec.ok).toBe(true)
    expect(rec.diff).toBeCloseTo(0)

    const draft = buildWorkHourConclusionDraft(summarizeI2WorkHourRows(hours))
    expect(draft).toContain('2 条')
  })

  it('I2-15: event detail + adjustment hint for supplement', () => {
    const rows = [
      recomputeI2ImpairmentRow(emptyI2ImpairmentRow({
        name: '项目A',
        hasIndication: 'Y',
        indicationDesc: '商业化受阻',
        bookValue: 1000,
        dcfValue: 400,
        alreadyProvided: 100,
        indexRef: 'I2-16',
      })),
    ]
    const s = summarizeI2Impairment(rows)
    expect(s.totalSupplement).toBe(500) // ⑥=600 ⑧=500
    const detail = buildI2ImpairmentEventDetail(s)
    expect(detail.wpCode).toBe('I2')
    expect(detail.sheetCode).toBe('I2-15')
    expect(detail.totalRequiredProvision).toBe(500)
    const hint = buildI2ImpairmentAdjustmentHint(s.totalSupplement)
    expect(hint).toMatch(/资产减值损失|开发支出/)
  })
})
