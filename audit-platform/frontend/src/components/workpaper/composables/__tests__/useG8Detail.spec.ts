/**
 * G8-2 明细表 — 完整性 / OCI滚动 / 公允合计 / 辅助核算种子
 */
import { describe, it, expect } from 'vitest'
import {
  enrichG8DetailRow,
  resolveFairValueTotal,
  resolveOciCumulative,
  scanG8DetailIntegrity,
  seedRowFromAux,
} from '../useG8Detail'
import { calcFairValueAmount, calcOciCumulativeEnding } from '../useG8FormulaEngine'

describe('calcOciCumulativeEnding', () => {
  it('期初+本期−转入', () => {
    expect(calcOciCumulativeEnding(100, 20, 5)).toBe(115)
  })
})

describe('resolveOciCumulative', () => {
  it('preferRoll 覆盖手工累计', () => {
    expect(resolveOciCumulative(10, 5, 2, 999, { preferRoll: true })).toBe(13)
  })

  it('累计为空时用公式', () => {
    expect(resolveOciCumulative(10, 5, 0, 0)).toBe(15)
  })
})

describe('resolveFairValueTotal', () => {
  it('有数量×单价且无手工合计时用乘积', () => {
    expect(resolveFairValueTotal(100, 1.5, 0)).toBe(150)
  })

  it('preferProduct 覆盖手工合计', () => {
    expect(resolveFairValueTotal(100, 1.5, 999, { preferProduct: true })).toBe(150)
  })

  it('手工合计与乘积不一致时保留手工', () => {
    expect(resolveFairValueTotal(100, 1.5, 160)).toBe(160)
  })
})

describe('enrichG8DetailRow', () => {
  it('兼容 sharesHeld 别名', () => {
    const row = enrichG8DetailRow(
      { rowId: '1', investeeName: '甲', sharesHeld: 200, pricePerShare: 2 } as any,
      1,
      { preferFvProduct: true },
    )
    expect(row.shareCount).toBe(200)
    expect(row.fairValueTotal).toBe(400)
  })

  it('滚动公式：期末余额与审定', () => {
    const row = enrichG8DetailRow(
      {
        rowId: '1',
        openingBalance: 100,
        openingAdjustment: 10,
        increaseAmount: 20,
        decreaseAmount: 5,
        fvChangeAmount: 8,
        closingAdjustment: -3,
      } as any,
      1,
    )
    expect(row.openingAdjusted).toBe(110)
    expect(row.closingBalance).toBe(133)
    expect(row.closingAdjusted).toBe(130)
  })

  it('OCI 滚动 preferOciRoll', () => {
    const row = enrichG8DetailRow(
      {
        rowId: '1',
        ociOpeningCumulative: 50,
        ociCurrentChange: 10,
        ociToRetainedEarnings: 5,
        ociCumulativeChange: 0,
      } as any,
      1,
      { preferOciRoll: true },
    )
    expect(row.ociCumulativeChange).toBe(55)
  })
})

describe('seedRowFromAux', () => {
  it('轧差入 FV 变动以勾稽期末', () => {
    const row = seedRowFromAux(
      {
        investeeName: '丁公司',
        openingBalance: 100,
        closingBalance: 130,
        auxType: '往来单位',
        auxCode: 'D01',
      },
      1,
    )
    expect(row.investeeName).toBe('丁公司')
    expect(row.openingBalance).toBe(100)
    expect(row.fvChangeAmount).toBe(30)
    expect(row.closingBalance).toBe(130)
    expect(row.fairValueTotal).toBe(130)
  })
})

describe('scanG8DetailIntegrity', () => {
  it('缺指定原因 / Level3 缺估值 / OCI↔FV / 公允↔审定', () => {
    const rows = [
      enrichG8DetailRow(
        {
          rowId: 'a',
          investeeName: '甲公司',
          openingBalance: 100,
          fvChangeAmount: 10,
          ociCurrentChange: 20,
          fairValueLevel: 'Level3',
          shareCount: 10,
          pricePerShare: 12,
          fairValueTotal: 100,
        } as any,
        1,
      ),
    ]
    const issues = scanG8DetailIntegrity(rows)
    const fields = issues.map((i) => i.field)
    expect(fields).toContain('designationReason')
    expect(fields).toContain('valuationMethod')
    expect(fields).toContain('ociCurrentChange')
    expect(fields).toContain('fairValueTotal')
  })

  it('OCI 滚动不一致提示', () => {
    const rows = [
      enrichG8DetailRow(
        {
          rowId: 'x',
          investeeName: '戊',
          designationReason: '长期持有',
          ociOpeningCumulative: 10,
          ociCurrentChange: 5,
          ociToRetainedEarnings: 0,
          ociCumulativeChange: 99,
        } as any,
        1,
      ),
    ]
    // enrich 在累计非空且未 preferRoll 时保留 99 → 应触发滚动提示
    expect(scanG8DetailIntegrity(rows).some((i) => i.field === 'ociCumulativeChange')).toBe(true)
  })

  it('完整行无提示', () => {
    const product = calcFairValueAmount(10, 11)
    const rows = [
      enrichG8DetailRow(
        {
          rowId: 'b',
          investeeName: '乙公司',
          openingBalance: product,
          designationReason: '战略性长期持有',
          fairValueLevel: 'Level1',
          shareCount: 10,
          pricePerShare: 11,
          fairValueTotal: product,
          fvChangeAmount: 0,
          ociCurrentChange: 0,
          ociOpeningCumulative: 0,
          ociCumulativeChange: 0,
        } as any,
        1,
        { preferFvProduct: true, preferOciRoll: true },
      ),
    ]
    expect(scanG8DetailIntegrity(rows)).toEqual([])
  })

  it('OCI转入留存收益须填转入原因', () => {
    const rows = [
      enrichG8DetailRow(
        {
          rowId: 'c',
          investeeName: '丙',
          designationReason: '长期持有',
          ociToRetainedEarnings: 50,
        } as any,
        1,
        { preferOciRoll: true },
      ),
    ]
    expect(scanG8DetailIntegrity(rows).some((i) => i.field === 'transferReason')).toBe(true)
  })
})
