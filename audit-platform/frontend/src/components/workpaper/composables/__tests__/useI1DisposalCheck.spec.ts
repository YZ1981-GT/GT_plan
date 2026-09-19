/**
 * useI1DisposalCheck — 对齐 Excel I1-6 公式
 */
import { describe, it, expect } from 'vitest'
import {
  calcI1DisposalNet,
  calcI1DisposalGainLoss,
  normalizeI1DisposalRow,
  validateI1DisposalPrep,
  seedI1DisposalFromDetail,
  buildI1DisposalConclusionDraft,
  emptyI1DisposalRow,
} from '../useI1DisposalCheck'

describe('calcI1DisposalNet / GainLoss', () => {
  it('净值 E = B − C − D', () => {
    expect(calcI1DisposalNet(1000, 200, 50)).toBe(750)
  })

  it('净损益 I = H − G − E（含清理费用）', () => {
    // 收入 900 − 费用 50 − 净值 750 = 100
    expect(calcI1DisposalGainLoss(900, 50, 750)).toBe(100)
    // 旧公式 income−net 会得到 150，错误
    expect(calcI1DisposalGainLoss(900, 0, 750)).toBe(150)
  })
})

describe('normalizeI1DisposalRow', () => {
  it('兼容旧 disposalType / approvalDoc', () => {
    const row = normalizeI1DisposalRow({
      name: '专利X',
      disposalType: '出售',
      originalCost: 1000,
      accAmort: 100,
      impairment: 0,
      disposalIncome: 800,
      disposalCost: 20,
      approvalDoc: 'I1-6-1',
    })
    expect(row.disposalMethod).toBe('出售')
    expect(row.netBookValue).toBe(900)
    expect(row.disposalGainLoss).toBe(800 - 20 - 900) // -120
    expect(row.attachmentIndex).toBe('I1-6-1')
  })
})

describe('validateI1DisposalPrep', () => {
  it('出售未填收入时告警', () => {
    const row = emptyI1DisposalRow({
      name: '商标A',
      disposalMethod: '出售',
      saleApproved: 'Y',
      saleProceduresComplete: 'Y',
      salePriceFair: 'Y',
      voucherNo: '记-1',
      disposalIncome: 0,
    })
    const v = validateI1DisposalPrep([row])
    expect(v.ok).toBe(false)
    expect(v.messages.some((m) => m.includes('清理收入'))).toBe(true)
  })
})

describe('seedI1DisposalFromDetail', () => {
  it('识别原值减少行', () => {
    const rows = seedI1DisposalFromDetail([
      { name: '软件B', costDecrease: 500, amortTransferOut: 100, impairmentReversal: 0 },
      { name: '无减少', costDecrease: 0 },
    ])
    expect(rows).toHaveLength(1)
    expect(rows[0].name).toBe('软件B')
    expect(rows[0].originalCost).toBe(500)
    expect(rows[0].accAmort).toBe(100)
  })
})

describe('buildI1DisposalConclusionDraft', () => {
  it('含关键汇总', () => {
    const text = buildI1DisposalConclusionDraft([
      emptyI1DisposalRow({
        name: 'A',
        disposalMethod: '出售',
        originalCost: 100,
        disposalIncome: 80,
        conclusion: '有异常',
      }),
    ])
    expect(text).toContain('减少 1 项')
    expect(text).toContain('异常/勾稽不一致 1 项')
  })
})

describe('H10 发布字段', () => {
  it('emptyI1DisposalRow 可产出 H10 所需净损益', () => {
    const row = emptyI1DisposalRow({
      name: '软件A',
      originalCost: 100,
      disposalIncome: 80,
      disposalCost: 5,
      accAmort: 10,
      impairment: 0,
    })
    expect(row.netBookValue).toBe(90)
    expect(row.disposalGainLoss).toBe(-15)
  })
})
