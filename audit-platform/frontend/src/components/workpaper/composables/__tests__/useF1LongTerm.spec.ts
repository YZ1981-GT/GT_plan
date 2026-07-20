/**
 * useF1LongTerm 纯函数单测 — F1-5 13 列逻辑
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedBalance,
  recalcLongTermRow,
  normalizeLongTermRow,
  mergeLongTermFromImport,
  createEmptyLongTermRow,
} from '../useF1LongTerm'

describe('useF1LongTerm helpers', () => {
  it('calcAuditedBalance = endBalance - badDebt', () => {
    expect(calcAuditedBalance(1000, 100)).toBe(900)
    expect(calcAuditedBalance(1000, 0)).toBe(1000)
  })

  it('recalcLongTermRow updates auditedBalance', () => {
    const row = recalcLongTermRow({
      ...createEmptyLongTermRow(),
      endBalance: 500,
      badDebtProvision: 50,
    })
    expect(row.auditedBalance).toBe(450)
  })

  it('normalizeLongTermRow migrates legacy settlementAmount / unsettledReason', () => {
    const row = normalizeLongTermRow({
      customerName: '甲',
      endBalance: 200,
      unsettledReason: '工程未完工',
      settlementAmount: 30,
      badDebtProvision: 10,
    })
    expect(row.reason).toBe('工程未完工')
    expect(row.postSettlementAmount).toBe(30)
    expect(row.auditedBalance).toBe(190)
  })

  it('normalizeYn maps 是/否', () => {
    const row = normalizeLongTermRow({ isLitigation: '是', transferToOtherReceivable: '否' })
    expect(row.isLitigation).toBe('Y')
    expect(row.transferToOtherReceivable).toBe('N')
  })

  it('mergeLongTermFromImport updates same customer and keeps reason', () => {
    const existing = [
      recalcLongTermRow({
        ...createEmptyLongTermRow(),
        customerName: '甲',
        endBalance: 100,
        reason: '已填原因',
        aging: '1-2年',
      }),
    ]
    const merged = mergeLongTermFromImport(existing, [
      {
        customerName: '甲',
        endAudited: 180,
        agingDescription: '2-3年',
        agingAudited: { y2to3: 180 },
      },
      {
        customerName: '乙',
        endAudited: 50,
        agingDescription: '1-2年',
        agingAudited: { y1to2: 50 },
      },
    ])
    expect(merged).toHaveLength(2)
    const a = merged.find(r => r.customerName === '甲')!
    expect(a.endBalance).toBe(180)
    expect(a.aging).toBe('2-3年')
    expect(a.reason).toBe('已填原因')
    expect(merged.find(r => r.customerName === '乙')!.endBalance).toBe(50)
  })

  it('buildSuggestedAdjustmentRows emits impairment AJE and reclass RJE', async () => {
    const { buildSuggestedAdjustmentRows, createEmptyLongTermRow, recalcLongTermRow } = await import('../useF1LongTerm')
    const rows = [
      recalcLongTermRow({
        ...createEmptyLongTermRow(),
        customerName: '甲',
        endBalance: 1000,
        badDebtProvision: 200,
        transferToOtherReceivable: 'N',
      }),
      recalcLongTermRow({
        ...createEmptyLongTermRow(),
        customerName: '乙',
        endBalance: 500,
        transferToOtherReceivable: 'Y',
      }),
    ]
    const suggested = buildSuggestedAdjustmentRows(rows)
    expect(suggested.some(s => s.description.includes('减值') && s.debitAmount === 200)).toBe(true)
    expect(suggested.some(s => s.description.includes('其他应收') && s.category.includes('重分类'))).toBe(true)
  })
})
