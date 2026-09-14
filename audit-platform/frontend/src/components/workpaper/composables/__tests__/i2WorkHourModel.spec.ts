/**
 * i2WorkHourModel — I2-10 工时检查公式/建议结论/带入 单测
 */
import { describe, it, expect } from 'vitest'
import {
  calcWorkHourRatio,
  suggestWorkHourConclusion,
  recomputeI2WorkHourRow,
  emptyI2WorkHourRow,
  normalizeI2WorkHourRow,
  seedWorkHourFromStaff,
  seedWorkHourFromDetail,
  validateI2WorkHourPrep,
  validateWorkHourAgainstStaff,
  assertI2WorkHourCanConclude,
  reconcileWorkHourSalaryVsAnalysis,
  summarizeI2WorkHourRows,
  buildWorkHourConclusionDraft,
} from '../i2WorkHourModel'

describe('i2WorkHourModel formulas', () => {
  it('ratio = hours / totalHours', () => {
    expect(calcWorkHourRatio(80, 160)).toBe(0.5)
    expect(calcWorkHourRatio(80, 0)).toBe(0)
  })

  it('suggest: 工时>总工时 → 偏高', () => {
    expect(suggestWorkHourConclusion({
      staffName: '张三', hours: 200, totalHours: 160, ratio: 0, allocationBasis: '工时表', salaryAccrual: 0,
    })).toBe('偏高')
  })

  it('suggest: 占比≥95% 有依据 → 合理（全时研发）', () => {
    expect(suggestWorkHourConclusion({
      staffName: '李四', hours: 160, totalHours: 160, ratio: 1, allocationBasis: '工时表', salaryAccrual: 10000,
    })).toBe('合理')
  })

  it('suggest: 占比≥95% 无依据 → 待核实', () => {
    expect(suggestWorkHourConclusion({
      staffName: '李四', hours: 160, totalHours: 160, ratio: 1, allocationBasis: '', salaryAccrual: 10000,
    })).toBe('待核实')
  })

  it('suggest: 占比低且有薪酬 → 偏低', () => {
    expect(suggestWorkHourConclusion({
      staffName: '王五', hours: 20, totalHours: 160, ratio: 0.125, allocationBasis: '工时表', salaryAccrual: 5000,
    })).toBe('偏低')
  })

  it('suggest: 有工时无依据 → 待核实', () => {
    expect(suggestWorkHourConclusion({
      staffName: '赵六', hours: 80, totalHours: 160, ratio: 0.5, allocationBasis: '', salaryAccrual: 0,
    })).toBe('待核实')
  })

  it('suggest: 正常 → 合理', () => {
    expect(suggestWorkHourConclusion({
      staffName: '钱七', hours: 100, totalHours: 160, ratio: 0.625, allocationBasis: '考勤记录', salaryAccrual: 8000,
    })).toBe('合理')
  })
})

describe('normalize / seed / validate', () => {
  it('legacy row maps hours/totalHours/ratio', () => {
    const row = normalizeI2WorkHourRow({
      staffName: '旧数据', projectName: 'ABC', month: '2024-06', hours: 80, totalHours: 160, conclusion: '合理',
    })
    expect(row.ratio).toBe(0.5)
    expect(row.conclusion).toBe('合理')
    expect(row.projectName).toBe('ABC')
  })

  it('seedWorkHourFromStaff skips 不予认定 and splits projects', () => {
    const seeded = seedWorkHourFromStaff([
      { staffName: 'A', conclusion: '认定为研发人员', projects: 'ABC、DEF', rdHourRatio: 60, attachmentIndex: 'A1' },
      { staffName: 'B', conclusion: '不予认定', projects: 'XYZ' },
    ])
    expect(seeded).toHaveLength(2)
    expect(seeded.map((r) => r.projectName).sort()).toEqual(['ABC', 'DEF'])
    expect(seeded[0].hours).toBe(60)
    expect(seeded[0].totalHours).toBe(100)
  })

  it('seedWorkHourFromDetail builds project shells', () => {
    const seeded = seedWorkHourFromDetail([
      { projectName: '项目甲', projectCode: 'P001', startDate: '2024-01-01', endDate: '2024-12-31' },
      { projectName: '合计' },
    ])
    expect(seeded).toHaveLength(1)
    expect(seeded[0].projectCode).toBe('P001')
    expect(seeded[0].projectPeriod).toContain('2024-01-01')
  })

  it('validate flags missing basis and share-pay without note', () => {
    const row = recomputeI2WorkHourRow(emptyI2WorkHourRow({
      staffName: '测', projectName: 'P', hours: 40, totalHours: 160, hasShareBasedPay: 'Y',
    }), { refreshSuggested: true })
    const v = validateI2WorkHourPrep([row])
    expect(v.ok).toBe(false)
    expect(v.messages.some((m) => m.includes('分配依据'))).toBe(true)
    expect(v.messages.some((m) => m.includes('股份支付'))).toBe(true)
  })

  it('summarize and conclusion draft', () => {
    const rows = [
      recomputeI2WorkHourRow(emptyI2WorkHourRow({
        staffName: 'A', hours: 200, totalHours: 160, allocationBasis: '工时表', salaryAccrual: 10000,
      })),
      recomputeI2WorkHourRow(emptyI2WorkHourRow({
        staffName: 'B', hours: 20, totalHours: 160, allocationBasis: '考勤记录', salaryAccrual: 2000,
      })),
    ]
    const s = summarizeI2WorkHourRows(rows)
    expect(s.totalHours).toBe(220)
    expect(s.totalSalary).toBe(12000)
    expect(s.highRatioCount).toBe(1) // 200/160 > 95%
    expect(s.lowRatioCount).toBe(1)
    const draft = buildWorkHourConclusionDraft(s)
    expect(draft).toContain('2 条')
    expect(draft).toMatch(/偏高|偏低/)
  })
})

describe('I2-9 ↔ I2-10 staff gate (validateWorkHourAgainstStaff)', () => {
  const staffRows = [
    { staffName: '张三', conclusion: '认定为研发人员' },
    { staffName: '李四', conclusion: '不予认定' },
    { staffName: '王五', conclusion: '待核实' },
  ]

  it('passes when staff is accepted (认定为研发人员) and has activity', () => {
    const rows = [
      recomputeI2WorkHourRow(emptyI2WorkHourRow({ staffName: '张三', hours: 100, salaryAccrual: 5000 })),
    ]
    const gate = validateWorkHourAgainstStaff(rows, staffRows)
    expect(gate.ok).toBe(true)
    expect(gate.messages).toHaveLength(0)
  })

  it('fails when staffName not in accepted set but has hours>0', () => {
    const rows = [
      recomputeI2WorkHourRow(emptyI2WorkHourRow({ staffName: '王五', hours: 40, salaryAccrual: 0 })),
    ]
    const gate = validateWorkHourAgainstStaff(rows, staffRows)
    expect(gate.ok).toBe(false)
    expect(gate.messages[0]).toContain('王五')
  })

  it('fails when staffName not in accepted set but salaryAccrual>0.01', () => {
    const rows = [
      recomputeI2WorkHourRow(emptyI2WorkHourRow({ staffName: '未知人员', hours: 0, salaryAccrual: 100 })),
    ]
    const gate = validateWorkHourAgainstStaff(rows, staffRows)
    expect(gate.ok).toBe(false)
  })

  it('flags with distinct message when staff explicitly 不予认定 but still has salary/hours', () => {
    const rows = [
      recomputeI2WorkHourRow(emptyI2WorkHourRow({ staffName: '李四', hours: 80, salaryAccrual: 3000 })),
    ]
    const gate = validateWorkHourAgainstStaff(rows, staffRows)
    expect(gate.ok).toBe(false)
    expect(gate.messages[0]).toContain('不予认定')
  })

  it('passes when no activity (hours=0 and salaryAccrual<=0.01) even if not accepted', () => {
    const rows = [
      recomputeI2WorkHourRow(emptyI2WorkHourRow({ staffName: '陌生人', hours: 0, salaryAccrual: 0 })),
    ]
    const gate = validateWorkHourAgainstStaff(rows, staffRows)
    expect(gate.ok).toBe(true)
  })

  it('assertI2WorkHourCanConclude mirrors validateWorkHourAgainstStaff', () => {
    const rows = [
      recomputeI2WorkHourRow(emptyI2WorkHourRow({ staffName: '李四', hours: 80, salaryAccrual: 3000 })),
    ]
    expect(assertI2WorkHourCanConclude(rows, staffRows).ok).toBe(false)
  })
})

describe('reconcileWorkHourSalaryVsAnalysis', () => {
  it('ok when within tolerance 0.01', () => {
    const r = reconcileWorkHourSalaryVsAnalysis(10000, 10000.005)
    expect(r.ok).toBe(true)
    expect(r.diff).toBeCloseTo(-0.005)
  })

  it('flags mismatch beyond tolerance', () => {
    const r = reconcileWorkHourSalaryVsAnalysis(10500, 10000)
    expect(r.ok).toBe(false)
    expect(r.diff).toBe(500)
    expect(r.diffRate).toBeCloseTo(0.05)
    expect(r.message).toContain('差异')
  })

  it('includes TB 6602 comparison when provided', () => {
    const okMsg = reconcileWorkHourSalaryVsAnalysis(10000, 10000, 10000)
    expect(okMsg.message).toContain('TB 6602 一致')
    const mismatchMsg = reconcileWorkHourSalaryVsAnalysis(10000, 10000, 9500)
    expect(mismatchMsg.message).toContain('TB 6602')
    expect(mismatchMsg.message).toContain('差异')
  })
})
