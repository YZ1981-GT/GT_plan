import { describe, expect, it } from 'vitest'
import {
  calcG10FairValueDiff,
  pushG10FvDiffToAdjustment,
  selectG10FvDiffTargets,
  buildG10FvProcedureSummary,
  buildG10AdjustmentProcedureSummary,
  G10A_FV_PROGRAM_NOS,
  G10A_ADJUSTMENT_PROGRAM_NOS,
  collectG10AProcedureMarks,
} from '../g10FvCrossHelpers'

describe('g10FvCrossHelpers', () => {
  it('calcG10FairValueDiff = 审定 − 未审', () => {
    expect(calcG10FairValueDiff(120, 100)).toBe(20)
    expect(calcG10FairValueDiff(80, 100)).toBe(-20)
  })

  it('selectG10FvDiffTargets 按 B15 筛选', () => {
    const { targets, skipped } = selectG10FvDiffTargets({
      rows: [
        { liabilityName: 'A', fairValueDiff: 50, closingAuditedFV: 150, closingUnadjustedFV: 100 },
        { liabilityName: 'B', fairValueDiff: 5, closingAuditedFV: 105, closingUnadjustedFV: 100 },
      ],
      performanceMateriality: 30,
    })
    expect(targets).toHaveLength(1)
    expect(targets[0].liabilityName).toBe('A')
    expect(skipped).toHaveLength(1)
  })

  it('pushG10FvDiffToAdjustment 负债上升 Dr6101/Cr2101 并回写', () => {
    const saves: Array<{ id: string; data: any }> = []
    const responses = new Map<string, { remark?: string }>()
    const n = pushG10FvDiffToAdjustment(
      responses as any,
      (id, data) => {
        saves.push({ id, data })
        responses.set(id, data as any)
      },
      [{
        summary: 'G10-5 公允测试差异：衍生负债',
        amount: 100,
        liabilityName: '衍生负债',
        liabilityType: '衍生金融负债',
        indexRef: 'G10-5',
      }],
    )
    expect(n).toBe(1)
    const rows = JSON.parse(String(saves.find((s) => s.id === 'G10-aje-rows')?.data.remark))
    expect(rows).toHaveLength(2)
    const g2101 = rows.find((r: any) => r.accountCode === '2101')
    const g6101 = rows.find((r: any) => r.accountCode === '6101')
    expect(g2101.creditAmount).toBe(100)
    expect(g6101.debitAmount).toBe(100)
    const wb = JSON.parse(String(saves.find((s) => s.id === 'G10-adj-writeback')?.data.remark))
    const rowWb = wb.byRow.book_derivative_liability
    expect(typeof rowWb === 'object' ? rowWb.closingAje : rowWb).toBe(100)
  })

  it('buildG10FvProcedureSummary 与 G10A seq9 程序号', () => {
    const s = buildG10FvProcedureSummary({
      rowCount: 3,
      diffCount: 1,
      level3Count: 1,
      auditedTotal: 1000,
      l3RowCount: 2,
      validationErrors: 0,
    })
    expect(s).toContain('G10-5')
    expect(s).toContain('G10-6 L3')
    expect(G10A_FV_PROGRAM_NOS).toEqual([9])
  })

  it('buildG10AdjustmentProcedureSummary 含 G10-5 来源与回写', () => {
    const s = buildG10AdjustmentProcedureSummary({
      rowCount: 4,
      ajeCount: 2,
      rjeCount: 2,
      balanced: true,
      net2101: 80,
      fvPlNet: 80,
      writebackRows: 1,
      fromG105: 2,
      fromG104: 0,
      pendingG104: 0,
    })
    expect(s).toContain('G10-3')
    expect(s).toContain('G10-5 来源 2')
    expect(s).toContain('借贷平衡')
    expect(G10A_ADJUSTMENT_PROGRAM_NOS).toEqual([3, 4])
  })

  it('collectG10AProcedureMarks 汇总回填步骤', () => {
    const m = new Map<string, { conclusion?: string; remark?: string }>()
    m.set('G10A-fv-complete', { conclusion: 'completed' })
    m.set('G10A-classification-complete', { conclusion: 'completed' })
    m.set('G10A-detail-complete', { conclusion: 'completed' })
    m.set('G10A-adjudication-complete', { conclusion: 'completed' })
    m.set('G10A-adjustment-complete', { conclusion: 'completed' })
    const marks = collectG10AProcedureMarks(m)
    expect(marks.map((x) => x.key)).toEqual(['detail', 'adjudication', 'adjustment', 'fv', 'classification'])
  })
})
