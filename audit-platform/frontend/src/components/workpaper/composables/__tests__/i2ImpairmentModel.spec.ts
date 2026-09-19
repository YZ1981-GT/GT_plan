/**
 * i2ImpairmentModel — I2-15 公式/闸门/带入 单测
 */
import { describe, it, expect } from 'vitest'
import {
  calcI2ImpairmentRecoverable,
  calcI2RequiredImpairment,
  calcI2ImpairmentAdjustment,
  resolveI2NeedTest,
  recomputeI2ImpairmentRow,
  emptyI2ImpairmentRow,
  normalizeI2ImpairmentRow,
  seedRowsFromI2Detail,
  validateI2ImpairmentPrep,
  summarizeI2Impairment,
  buildI2ImpairmentAdjustmentHint,
  buildI2ImpairmentEventDetail,
} from '../i2ImpairmentModel'

describe('i2ImpairmentModel formulas', () => {
  it('⑤ = MAX(③,④) when needTest', () => {
    expect(calcI2ImpairmentRecoverable(100, 200, true)).toBe(200)
    expect(calcI2ImpairmentRecoverable(300, 200, true)).toBe(300)
    expect(calcI2ImpairmentRecoverable(100, 200, false)).toBe(0)
  })

  it('⑥ = MAX(②−⑤,0) only when needTest', () => {
    expect(calcI2RequiredImpairment(1000, 600, true)).toBe(400)
    expect(calcI2RequiredImpairment(1000, 1200, true)).toBe(0)
    expect(calcI2RequiredImpairment(1000, 600, false)).toBe(0)
  })

  it('⑧ = ⑥−⑦ allows negative reversal', () => {
    expect(calcI2ImpairmentAdjustment(400, 100)).toBe(300)
    expect(calcI2ImpairmentAdjustment(100, 400)).toBe(-300)
  })

  it('resolveI2NeedTest: 有迹象须测；无迹象默认可强制', () => {
    expect(resolveI2NeedTest('Y')).toBe(true)
    expect(resolveI2NeedTest('N')).toBe(false)
    expect(resolveI2NeedTest('N', true)).toBe(true)
    expect(resolveI2NeedTest('', true)).toBe(true)
    expect(resolveI2NeedTest('')).toBe(false)
  })
})

describe('recomputeI2ImpairmentRow', () => {
  it('full chain ②→⑤→⑥→⑧ and auto conclusion 需补提', () => {
    const row = recomputeI2ImpairmentRow(emptyI2ImpairmentRow({
      name: '项目A',
      hasIndication: 'Y',
      indicationDesc: '商业化失败',
      bookValue: 1000,
      fairValueLessDisposal: 200,
      dcfValue: 500,
      alreadyProvided: 100,
    }))
    expect(row.needTest).toBe(true)
    expect(row.recoverableAmount).toBe(500)
    expect(row.shouldProvision).toBe(500)
    expect(row.difference).toBe(400)
    expect(row.conclusion).toBe('需补提')
  })

  it('无迹象不测：⑤⑥⑧为0，结论无需测试', () => {
    const row = recomputeI2ImpairmentRow(emptyI2ImpairmentRow({
      name: '项目B',
      hasIndication: 'N',
      bookValue: 800,
      fairValueLessDisposal: 100,
      dcfValue: 200,
      alreadyProvided: 50,
    }))
    expect(row.needTest).toBe(false)
    expect(row.recoverableAmount).toBe(0)
    expect(row.shouldProvision).toBe(0)
    expect(row.difference).toBe(0)
    expect(row.conclusion).toBe('无需测试')
  })

  it('legacy flat recoverableAmount maps to ④', () => {
    const row = normalizeI2ImpairmentRow({
      name: '旧行',
      bookValue: 1000,
      recoverableAmount: 700,
      alreadyProvided: 0,
    })
    expect(row.needTest).toBe(true)
    expect(row.dcfValue).toBe(700)
    expect(row.recoverableAmount).toBe(700)
    expect(row.shouldProvision).toBe(300)
  })
})

describe('seed / validate / summary', () => {
  it('seedRowsFromI2Detail uses 期末−摊销 as ② and capImpairment as ⑦', () => {
    const seeded = seedRowsFromI2Detail([
      {
        rowId: 'd1',
        projectName: '研发一号',
        capEndAmount: 1200,
        capAmortization: 200,
        capImpairment: 50,
        capNetValue: 950,
      },
      { projectName: '合计', capEndAmount: 9999 },
    ])
    expect(seeded).toHaveLength(1)
    expect(seeded[0].name).toBe('研发一号')
    expect(seeded[0].bookValue).toBe(1000)
    expect(seeded[0].alreadyProvided).toBe(50)
  })

  it('validate flags missing indication desc and missing recoverable', () => {
    const row = recomputeI2ImpairmentRow(emptyI2ImpairmentRow({
      name: '缺描述',
      hasIndication: 'Y',
      bookValue: 500,
    }))
    const v = validateI2ImpairmentPrep([row])
    expect(v.ok).toBe(false)
    expect(v.messages.some((m) => m.includes('迹象描述'))).toBe(true)
    expect(v.messages.some((m) => m.includes('可收回'))).toBe(true)
  })

  it('summarize splits supplement and reversal', () => {
    const rows = [
      recomputeI2ImpairmentRow(emptyI2ImpairmentRow({
        name: 'A', hasIndication: 'Y', indicationDesc: 'x',
        bookValue: 1000, dcfValue: 400, alreadyProvided: 100,
      })),
      recomputeI2ImpairmentRow(emptyI2ImpairmentRow({
        name: 'B', hasIndication: 'Y', indicationDesc: 'y',
        bookValue: 500, dcfValue: 500, alreadyProvided: 200,
      })),
    ]
    const s = summarizeI2Impairment(rows)
    // A: ⑥=600 ⑧=500; B: ⑥=0 ⑧=-200
    expect(s.totalSupplement).toBe(500)
    expect(s.totalReversal).toBe(200)
    expect(s.totalDifference).toBe(300)
  })
})

describe('buildI2ImpairmentAdjustmentHint', () => {
  it('returns empty string when supplement <= 0', () => {
    expect(buildI2ImpairmentAdjustmentHint(0)).toBe('')
    expect(buildI2ImpairmentAdjustmentHint(-100)).toBe('')
  })

  it('builds 借/贷 adjustment entry hint when supplement > 0', () => {
    const hint = buildI2ImpairmentAdjustmentHint(1234.56)
    expect(hint).toContain('借：资产减值损失')
    expect(hint).toContain('贷：开发支出减值准备')
    expect(hint).toContain('1,234.56')
  })
})

describe('buildI2ImpairmentEventDetail', () => {
  it('maps summary to impairment:calculated event payload', () => {
    const summary = summarizeI2Impairment([
      recomputeI2ImpairmentRow(emptyI2ImpairmentRow({
        name: 'A', hasIndication: 'Y', indicationDesc: 'x',
        bookValue: 1000, dcfValue: 400, alreadyProvided: 100,
      })),
    ])
    const detail = buildI2ImpairmentEventDetail(summary)
    expect(detail).toEqual({
      wpCode: 'I2',
      wp_code: 'I2',
      sheetCode: 'I2-15',
      totalRequiredProvision: summary.totalSupplement,
      amount: summary.totalSupplement,
      label: '本期补提⑧',
      impairmentAmount: summary.totalShouldProvision,
    })
    expect(detail.amount).toBe(500)
  })
})
