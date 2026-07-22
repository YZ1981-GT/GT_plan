import { describe, it, expect } from 'vitest'
import {
  calcBeginAudited,
  calcEndAudited,
  calcChangeAmount,
  calcChangeRate,
  formatChangeRate,
  normalizeI2AdjudicationRow,
  seedAdjudicationFromI22,
  summarizeI2Adjudication,
  applyAjeFromI23,
  serializeI2AdjudicationRow,
} from '../i2AdjudicationModel'

describe('i2AdjudicationModel', () => {
  it('审定 = 未审 + 调整', () => {
    expect(calcBeginAudited(100, -10)).toBe(90)
    expect(calcEndAudited(200, 15)).toBe(215)
  })

  it('变动额/率；期初为 0 时变动率为 null（防 #DIV/0!）', () => {
    expect(calcChangeAmount(100, 130)).toBe(30)
    expect(calcChangeRate(100, 30)).toBe(30)
    expect(calcChangeRate(0, 30)).toBeNull()
    expect(formatChangeRate(null)).toBe('N/A')
  })

  it('兼容旧版滚动字段映射', () => {
    const row = normalizeI2AdjudicationRow({
      projectName: '课题1',
      cipBegin: 50,
      unadjusted: 80,
      aje: 5,
      rje: 0,
      increaseCapitalized: 40,
      decreaseTransfer: 10,
    })
    expect(row.beginUnadj).toBe(50)
    expect(row.beginAudited).toBe(50)
    expect(row.endUnadj).toBe(80)
    expect(row.endAdj).toBe(5)
    expect(row.endAudited).toBe(85)
    expect(row.changeAmount).toBe(35)
  })

  it('从 I2-2 带入', () => {
    const rows = seedAdjudicationFromI22([
      { projectName: '课题1', capBeginAmount: 10, auditedEnd: 40, capIncrease: 35, transferToI1: 5 },
      { projectName: '合计', auditedEnd: 99 },
    ])
    expect(rows).toHaveLength(1)
    expect(rows[0].beginUnadj).toBe(10)
    expect(rows[0].endUnadj).toBe(40)
    expect(rows[0].decreaseTransfer).toBe(5)
  })

  it('I2-3 AJE 分摊到项目行并标近似', () => {
    const base = seedAdjudicationFromI22([
      { projectName: 'A', auditedEnd: 100 },
      { projectName: 'B', auditedEnd: 100 },
    ])
    const { rows, applied, approx } = applyAjeFromI23(base, [{
      lines: [{ accountCode: '1717', debitAmount: 20, creditAmount: 0 }],
    }])
    expect(applied).toBe(2)
    expect(approx).toBe(true)
    expect(rows.every((r) => r.ajeApprox)).toBe(true)
    expect(rows[0].endAdj + rows[1].endAdj).toBeCloseTo(20, 2)
  })

  it('I2-3 按项目名精确匹配不标近似', () => {
    const base = seedAdjudicationFromI22([
      { projectName: 'A', auditedEnd: 100 },
      { projectName: 'B', auditedEnd: 100 },
    ])
    const { rows, approx, matchedByName } = applyAjeFromI23(base, [{
      lines: [{ accountCode: '1717', projectName: 'A', debitAmount: 15, creditAmount: 0 }],
    }])
    expect(matchedByName).toBe(1)
    expect(approx).toBe(false)
    expect(rows.find((r) => r.projectName === 'A')?.endAdj).toBe(15)
    expect(rows.find((r) => r.projectName === 'A')?.ajeApprox).toBe(false)
  })

  it('serialize 保留 audited 兼容字段', () => {
    const row = normalizeI2AdjudicationRow({ projectName: 'X', beginUnadj: 10, endUnadj: 20, endAdj: 3 })
    const ser = serializeI2AdjudicationRow(row)
    expect(ser.audited).toBe(23)
    expect(ser.cipBegin).toBe(10)
  })

  it('汇总期末审定', () => {
    const rows = seedAdjudicationFromI22([
      { projectName: 'A', capBeginAmount: 10, auditedEnd: 30 },
      { projectName: 'B', capBeginAmount: 5, auditedEnd: 15 },
    ])
    const s = summarizeI2Adjudication(rows)
    expect(s.beginAudited).toBe(15)
    expect(s.endAudited).toBe(45)
    expect(s.changeAmount).toBe(30)
  })
})
