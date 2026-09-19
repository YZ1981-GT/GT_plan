import { describe, it, expect } from 'vitest'
import {
  buildG13CategorySkeleton,
  buildG13CategoryTotalRow,
  aggregateDesignatedOfWhich,
} from '../g13CategorySkeleton'
import {
  isDesignatedInstrument,
  mapBelongToOfWhichRow,
  mapBelongToAdjRow,
  detailRowMatchesCategory,
} from '../g13Constants'
import { mergeG13SourceSeeds, type G13SourcePullSeed, type G13MergeTargetRow } from '../g13SourceDetailPull'
import { parseNum } from '../useG13FormulaEngine'

describe('isDesignatedInstrument / mapBelongToOfWhichRow', () => {
  it('识别指定类并映射「其中」行', () => {
    expect(isDesignatedInstrument('指定FVTPL')).toBe(true)
    expect(isDesignatedInstrument('股票', '指定为FVTPL')).toBe(true)
    expect(isDesignatedInstrument('股票')).toBe(false)
    expect(mapBelongToOfWhichRow('G1', '指定FVTPL')).toBe('designated_fv_assets')
    expect(mapBelongToOfWhichRow('G10', '指定FVTPL')).toBe('designated_fv_liabilities')
    expect(mapBelongToOfWhichRow('G8', '指定FVTPL')).toBe('designated_fv_other')
    expect(mapBelongToOfWhichRow('G1', '股票')).toBeNull()
  })

  it('主行映射不受指定影响（其中为备忘子集）', () => {
    expect(mapBelongToAdjRow('G1', '指定FVTPL')).toBe('trading_assets')
    expect(mapBelongToAdjRow('G9', '衍生工具负债')).toBe('derivative_liabilities')
  })
})

describe('buildG13CategorySkeleton', () => {
  const rows = [
    {
      rowId: '1',
      belongAccount: 'G1',
      instrumentType: '股票',
      currentUnadjusted: 100,
      adjustment: 0,
      currentAudited: 100,
      cost: 1000,
      periodFvChange: 100,
      cumulativeFvChange: 100,
      fairValue: 1100,
      amountInPl: 100,
    },
    {
      rowId: '2',
      belongAccount: 'G1',
      instrumentType: '指定FVTPL',
      currentUnadjusted: 40,
      adjustment: 0,
      currentAudited: 40,
      cost: 200,
      periodFvChange: 40,
      cumulativeFvChange: 40,
      fairValue: 240,
      amountInPl: 40,
    },
    {
      rowId: '3',
      belongAccount: 'G9',
      instrumentType: '衍生工具',
      currentUnadjusted: 20,
      adjustment: 0,
      currentAudited: 20,
      cost: 0,
      periodFvChange: 20,
      cumulativeFvChange: 20,
      fairValue: 20,
      amountInPl: 20,
    },
  ]

  it('主行含全部工具；其中仅含指定；合计排除其中', () => {
    const sk = buildG13CategorySkeleton(rows)
    const trading = sk.find((r) => r.rowKey === 'trading_assets')!
    const ofWhich = sk.find((r) => r.rowKey === 'designated_fv_assets')!
    const deriv = sk.find((r) => r.rowKey === 'derivative_assets')!

    expect(trading.currentAudited).toBe(140) // 100+40
    expect(trading.instrumentCount).toBe(2)
    expect(ofWhich.currentAudited).toBe(40)
    expect(ofWhich.instrumentCount).toBe(1)
    expect(ofWhich.kind).toBe('ofWhich')
    expect(deriv.currentAudited).toBe(20)

    const total = buildG13CategoryTotalRow(sk)
    // 合计 = trading 140 + deriv 20 = 160（不含其中 40）
    expect(total.currentAudited).toBe(160)
    expect(total.bsReconciled).toBe(true)
    expect(total.plReconciled).toBe(true)
  })

  it('aggregateDesignatedOfWhich 仅汇总指定', () => {
    const agg = aggregateDesignatedOfWhich(rows)
    expect(agg.designated_fv_assets.audited).toBe(40)
    expect(agg.designated_fv_liabilities).toBeUndefined()
  })
})

describe('detailRowMatchesCategory', () => {
  it('主行含指定子集；其中仅指定', () => {
    expect(detailRowMatchesCategory({ belongAccount: 'G1', instrumentType: '股票' }, 'trading_assets')).toBe(true)
    expect(detailRowMatchesCategory({ belongAccount: 'G1', instrumentType: '指定FVTPL' }, 'trading_assets')).toBe(true)
    expect(detailRowMatchesCategory({ belongAccount: 'G1', instrumentType: '指定FVTPL' }, 'designated_fv_assets')).toBe(true)
    expect(detailRowMatchesCategory({ belongAccount: 'G1', instrumentType: '股票' }, 'designated_fv_assets')).toBe(false)
    expect(detailRowMatchesCategory({ belongAccount: 'G9', instrumentType: '衍生工具' }, 'derivative_assets')).toBe(true)
  })
})

describe('mergeG13SourceSeeds', () => {
  function enrich(raw: Partial<G13MergeTargetRow> & { rowId: string }): G13MergeTargetRow & { allReconciled?: boolean } {
    const currentUnadjusted = parseNum(raw.currentUnadjusted)
    const adjustment = parseNum(raw.adjustment)
    const currentAudited = currentUnadjusted + adjustment
    const amountInPl = parseNum(raw.amountInPl)
    const cost = parseNum(raw.cost)
    const cum = parseNum(raw.cumulativeFvChange)
    const fairValue = parseNum(raw.fairValue)
    const bsOk = (cost === 0 && cum === 0 && fairValue === 0) || Math.abs(cost + cum - fairValue) <= 0.01
    const plOk = Math.abs(amountInPl - currentAudited) <= 0.01
    return {
      rowId: raw.rowId,
      seq: parseNum(raw.seq) || 0,
      instrumentName: raw.instrumentName ?? '',
      belongAccount: raw.belongAccount ?? '',
      instrumentType: raw.instrumentType ?? '',
      openingFairValue: parseNum(raw.openingFairValue),
      closingFairValue: parseNum(raw.closingFairValue),
      currentUnadjusted,
      adjustment,
      cost,
      periodFvChange: parseNum(raw.periodFvChange),
      cumulativeFvChange: cum,
      fairValue,
      amountInPl,
      sourceIndex: raw.sourceIndex ?? '',
      crossVerification: (raw.crossVerification as string) ?? 'pending',
      remark: raw.remark ?? '',
      allReconciled: bsOk && plOk,
    }
  }

  it('新增行 + 空字段才更新', () => {
    const existing: G13MergeTargetRow[] = [enrich({
      rowId: 'e1',
      seq: 1,
      instrumentName: '已有A',
      belongAccount: 'G1',
      cost: 500,
      periodFvChange: 0,
    })]
    const seeds: G13SourcePullSeed[] = [
      {
        instrumentName: '已有A',
        belongAccount: 'G1',
        instrumentType: '股票',
        openingFairValue: 100,
        closingFairValue: 130,
        currentUnadjusted: 30,
        cost: 999,
        periodFvChange: 30,
        cumulativeFvChange: 30,
        fairValue: 130,
        amountInPl: 30,
        sourceIndex: 'wp:G1-1',
        remark: '自 G1-2 带入',
      },
      {
        instrumentName: '新工具B',
        belongAccount: 'G8',
        instrumentType: '其他',
        openingFairValue: 50,
        closingFairValue: 60,
        currentUnadjusted: 10,
        cost: 50,
        periodFvChange: 10,
        cumulativeFvChange: 10,
        fairValue: 60,
        amountInPl: 10,
        sourceIndex: 'wp:G8-1',
        remark: '自 G8-2 带入',
      },
    ]
    const result = mergeG13SourceSeeds(existing, seeds, enrich as any, () => 'new-id')
    expect(result.added).toBe(1)
    expect(result.updated).toBe(1)
    expect(result.rows[0].cost).toBe(500)
    expect(result.rows[0].periodFvChange).toBe(30)
    expect(result.rows[1].instrumentName).toBe('新工具B')
  })

  it('新增勾稽通过行标记 consistent', () => {
    const seeds: G13SourcePullSeed[] = [{
      instrumentName: 'OK',
      belongAccount: 'G1',
      instrumentType: '股票',
      openingFairValue: 100,
      closingFairValue: 130,
      currentUnadjusted: 30,
      cost: 100,
      periodFvChange: 30,
      cumulativeFvChange: 30,
      fairValue: 130,
      amountInPl: 30,
      sourceIndex: 'wp:G1-1',
      remark: '带入',
    }]
    const result = mergeG13SourceSeeds([], seeds, enrich as any, () => 'id1')
    expect(result.added).toBe(1)
    expect(result.rows[0].crossVerification).toBe('consistent')
    expect(result.touchedRowIds).toContain('id1')
  })
})
