import { describe, it, expect } from 'vitest'
import { resolveG10LiabilitySuffix, inferG10AdjudicationRowKey } from '../g10AccountMatch'
import {
  aggregateG10AdjustmentByRow,
  applyG10AdjustmentWritebacks,
  defaultG10AdjStore,
} from '../g10AdjStorage'
import {
  aggregateG10DetailBuckets,
  pushG10DetailToAdjudication,
  pushG10FvToDetail,
  seedG10DetailRowFromAux,
  G10_DETAIL_ROWS_KEY,
} from '../g10CrossHelpers'
import { syncG10DisclosureFromAdjudication } from '../g10DisclosureFromAdj'
import { enrichG10DetailRow } from '../useG10Detail'

describe('g10AccountMatch', () => {
  it('负债类型映射到叶节点 suffix', () => {
    expect(resolveG10LiabilitySuffix({ liabilityType: '衍生金融负债' })).toBe('derivative_liability')
    expect(resolveG10LiabilitySuffix({ liabilityType: '结构化产品' })).toBe('hybrid_tool')
  })

  it('摘要推断回写行', () => {
    expect(inferG10AdjudicationRowKey({ summary: '调整衍生工具公允价值' })).toBe('book_derivative_liability')
  })
})

describe('g10CrossHelpers', () => {
  it('明细三段分解汇总至 (一)(二)(三)', () => {
    const rows = [
      enrichG10DetailRow({
        rowId: 'a',
        liabilityName: '交易性债券',
        openingInitialAmount: 100,
        openingFvAccum: 10,
        movementInitialAmount: 0,
        movementFvChange: 10,
      }, 1),
      enrichG10DetailRow({
        rowId: 'b',
        liabilityName: '衍生金融负债利率互换',
        openingInitialAmount: 50,
        openingFvAccum: 5,
        movementInitialAmount: 0,
        movementFvChange: 0,
      }, 2),
    ]
    const buckets = aggregateG10DetailBuckets(rows)
    expect(buckets.get('trading_bond')?.closingBook).toBe(120)
    expect(buckets.get('trading_bond')?.closingFv).toBe(20)
    expect(buckets.get('derivative_liability')?.closingBook).toBe(55)
  })

  it('G10-2 回写 G10-1', () => {
    const responses = new Map<string, any>()
    const saves: Array<{ id: string; data: any }> = []
    const debouncedSave = (id: string, data: any) => { saves.push({ id, data }) }

    const rows = [
      enrichG10DetailRow({
        rowId: 'a',
        liabilityName: '其他',
        openingInitialAmount: 100,
        openingFvAccum: 0,
        movementInitialAmount: 0,
        movementFvChange: 50,
      }, 1),
    ]
    const n = pushG10DetailToAdjudication(responses, debouncedSave, rows)
    expect(n).toBe(1)
    expect(saves.some((s) => s.id === 'G10-adj-rows')).toBe(true)
    const store = JSON.parse(saves.find((s) => s.id === 'G10-adj-rows')!.data.remark)
    expect(store.book_other.closingUnadjusted).toBe(150)
    expect(store.fv_other.closingUnadjusted).toBe(50)
  })

  it('附注同步 (三) 分项审定数', () => {
    let store = defaultG10AdjStore()
    store = applyG10AdjustmentWritebacks(store, {
      byRow: { book_trading_bond: { closingAje: 10, closingRje: 0 } },
    })
    store.book_trading_bond = {
      ...store.book_trading_bond,
      openingUnadjusted: 80,
      closingUnadjusted: 100,
      closingAJE: 10,
    }
    const disclosure = syncG10DisclosureFromAdjudication(
      [{ rowKey: 'book_trading_bond', currentAmount: 0, priorAmount: 0 }],
      JSON.stringify(store),
      { bookSectionOnly: true },
    )
    expect(disclosure[0].currentAmount).toBe(110)
    expect(disclosure[0].priorAmount).toBe(80)
  })

  it('辅助核算种子 → 明细行', () => {
    const row = seedG10DetailRowFromAux({
      liabilityName: '短期融资券',
      openingBalance: 100,
      closingBalance: 130,
      auxType: '项目',
      auxCode: '001',
    }, 1)
    expect(row.liabilityName).toBe('短期融资券')
    expect(row.liabilityCategory).toBe('交易类')
    expect(row.openingInitialAmount).toBe(100)
    expect(row.movementFvChange).toBe(30)
    expect(row.closingAdjusted).toBe(130)
  })

  // 🔴 C-7（spec g-cycle-single-region-detail-lanes）：`pushG10FvToDetail` 已停用。
  //    层次 / 估值方法的权威源就是 `公允价值测试表G10-5`（第三层次另有 G10-6），
  //    而 `明细表G10-2` 按权威模板重构后（19 列 A..S）没有这两列 ⇒ 回写会造第二真源。
  //    与 G9 的 `pushG9FvToDetail`（G9-4→G9-2）同族错误，同批处置。
  it('pushG10FvToDetail 已停用：恒 0 且不写 store（方向错）', () => {
    const before = JSON.stringify([{ rowId: 'd1', liabilityName: '债券A' }])
    const responses = new Map<string, any>([[G10_DETAIL_ROWS_KEY, { remark: before }]])
    const saves: Array<{ id: string; data: any }> = []
    const n = pushG10FvToDetail(
      responses,
      (id, data) => { saves.push({ id, data }) },
      [{ liabilityName: '债券A', fairValueLevel: 'Level3', valuationMethod: '市场法' }],
    )
    expect(n).toBe(0)
    expect(saves).toEqual([])
    expect(responses.get(G10_DETAIL_ROWS_KEY)?.remark).toBe(before)
  })
})

describe('g10AdjStorage adjustment writeback', () => {
  it('按回写行汇总 2101 净额', () => {
    const wb = aggregateG10AdjustmentByRow([
      {
        accountCode: '2101',
        creditAmount: 100,
        debitAmount: 0,
        adjudicationRowKey: 'book_derivative_liability',
      },
      {
        accountCode: '2101',
        creditAmount: 0,
        debitAmount: 20,
        summary: '债券调整',
      },
    ])
    expect(wb.byRow.book_derivative_liability).toEqual({ closingAje: 100, closingRje: 0 })
    expect(wb.byRow.book_trading_bond).toEqual({ closingAje: -20, closingRje: 0 })
  })
})
