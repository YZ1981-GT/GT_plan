/**
 * G10 附注披露 — 分项带入与行结构
 */
import { describe, it, expect } from 'vitest'
import {
  G10_LISTED_MOVEMENT_ROWS,
  G10_SOE_BALANCE_ROWS,
  G10_DISCLOSURE_COL_LABELS,
} from '../g10SchemaRows'
import {
  buildG10DisclosureMovementFromAdjStore,
  buildG10DisclosureBalanceFromAdjStore,
  buildG10DisclosureMovementFromDetailRows,
  buildG10DesignatedDetailFromAdjStore,
  applyG10ListedMovementToStore,
  applyG10SoeBalanceToStore,
  applyG10DisclosurePullToResponses,
  defaultG10ListedDiscStore,
  defaultG10SoeDiscStore,
  movementClosingSum,
  soeCurrentSum,
  summarizeG10DisclosureDirectoryStatus,
} from '../g10DisclosureFromAdj'
import { defaultG10AdjStore } from '../g10AdjStorage'

describe('G10 附注披露行结构', () => {
  it('上市变动表 8 行 + 父行汇总', () => {
    expect(G10_LISTED_MOVEMENT_ROWS).toHaveLength(8)
    expect(G10_LISTED_MOVEMENT_ROWS.filter((r) => r.isParent)).toHaveLength(2)
    expect(G10_DISCLOSURE_COL_LABELS.listed.movement).toMatchObject({
      opening: '期初余额',
      increase: '本期增加',
      decrease: '本期减少',
      closing: '期末余额',
    })
  })

  it('国企余额表 7 行 + 列头对齐 Excel', () => {
    expect(G10_SOE_BALANCE_ROWS).toHaveLength(7)
    expect(G10_DISCLOSURE_COL_LABELS.soe.balance).toMatchObject({
      current: '期末公允价值',
      prior: '期初公允价值',
    })
  })
})

describe('G10 附注 ← G10-1/G10-2 分项带入', () => {
  it('G10-1 book_fv 分项映射到披露桶', () => {
    const store = defaultG10AdjStore()
    store.book_trading_bond = {
      openingUnadjusted: 100,
      closingUnadjusted: 150,
    }
    store.book_derivative_liability = {
      openingUnadjusted: 50,
      closingUnadjusted: 40,
    }
    const movement = buildG10DisclosureMovementFromAdjStore(store)
    expect(movement.trading_bond.openingAmount).toBe(100)
    expect(movement.trading_bond.closingAmount).toBe(150)
    expect(movement.trading_bond.increaseAmount).toBe(50)
    expect(movement.derivative.decreaseAmount).toBe(10)

    const balance = buildG10DisclosureBalanceFromAdjStore(store)
    expect(balance.trading_bond.currentAmount).toBe(150)
    expect(balance.derivative.priorAmount).toBe(50)
  })

  it('G10-2 新字段 movement* 映射到附注增减', () => {
    const fromDetail = buildG10DisclosureMovementFromDetailRows([
      {
        liabilityCategory: '交易类',
        liabilityType: '交易性债券',
        openingFairValue: 100,
        closingFairValue: 130,
        movementInitialAmount: 0,
        movementFvChange: 30,
        currentDecrease: 0,
      },
      {
        liabilityCategory: '指定类',
        liabilityType: '其他',
        liabilityName: '指定债券',
        openingAdjusted: 50,
        closingAdjusted: 80,
        movementInitialAmount: 20,
        movementFvChange: 10,
        currentDecrease: 0,
      },
    ])
    expect(fromDetail.trading_bond.closingAmount).toBe(130)
    expect(fromDetail.trading_bond.increaseAmount).toBe(30)
    expect(fromDetail.designated_bond.closingAmount).toBe(80)
    expect(fromDetail.designated_bond.increaseAmount).toBe(30)
  })

  it('混合工具单独映射 hybrid_tool 披露桶', () => {
    const store = defaultG10AdjStore()
    store.book_hybrid_tool = {
      openingUnadjusted: 10,
      closingUnadjusted: 30,
    }
    const movement = buildG10DisclosureMovementFromAdjStore(store)
    expect(movement.hybrid_tool.closingAmount).toBe(30)
    expect(movement.other_designated.closingAmount).toBe(0)

    const fromDetail = buildG10DisclosureMovementFromDetailRows([
      {
        liabilityCategory: '指定类',
        liabilityType: '结构化产品',
        liabilityName: '混合工具A',
        openingAdjusted: 5,
        closingAdjusted: 15,
      },
    ])
    expect(fromDetail.hybrid_tool.closingAmount).toBe(15)
    expect(fromDetail.other_designated.closingAmount).toBe(0)
  })

  it('applyG10DisclosurePullToResponses 同步上市与国企附注', () => {
    const responses = new Map<string, any>()
    const store = defaultG10AdjStore()
    store.book_trading_bond = { openingUnadjusted: 100, closingUnadjusted: 120 }
    responses.set('G10-adj-rows', { remark: JSON.stringify(store) })
    responses.set('G10-1-adjudicated-amount', { conclusion: '120' })
    const saves: Array<{ id: string; data: any }> = []
    const batch = applyG10DisclosurePullToResponses(
      responses,
      (id, data) => { saves.push({ id, data }) },
      2025,
    )
    expect(saves.map((s) => s.id).sort()).toEqual(['G10-disclosure-listed', 'G10-disclosure-soe'])
    expect(batch.listedStore.movement.mv_trading_bond?.closingAmount).toBe(120)
    expect(batch.soeStore.balance.soe_trading_bond?.currentAmount).toBe(120)
  })

  it('G10-2 明细优先于审定分项', () => {
    const fromAdj = buildG10DisclosureMovementFromAdjStore(defaultG10AdjStore())
    expect(fromAdj.trading_bond.closingAmount).toBe(0)

    const fromDetail = buildG10DisclosureMovementFromDetailRows([
      {
        liabilityType: '交易性债券',
        openingAdjusted: 80,
        closingAdjusted: 120,
        currentIncrease: 40,
        currentDecrease: 0,
      },
    ])
    expect(fromDetail.trading_bond.closingAmount).toBe(120)
    expect(fromDetail.trading_bond.increaseAmount).toBe(40)
  })

  it('无分项时残差写入「其他」', () => {
    const result = applyG10ListedMovementToStore(
      defaultG10ListedDiscStore(),
      buildG10DisclosureMovementFromAdjStore(defaultG10AdjStore()),
      { residualClosing: 999 },
    )
    expect(result.usedResidual).toBe(true)
    expect(result.next.movement.mv_other?.closingAmount).toBe(999)
    expect(movementClosingSum(result.next)).toBe(999)
  })

  it('国企无分项时残差写入 soe_other', () => {
    const result = applyG10SoeBalanceToStore(
      defaultG10SoeDiscStore(),
      buildG10DisclosureBalanceFromAdjStore(defaultG10AdjStore()),
      { residualCurrent: 500 },
    )
    expect(result.usedResidual).toBe(true)
    expect(result.next.balance.soe_other?.currentAmount).toBe(500)
    expect(soeCurrentSum(result.next)).toBe(500)
  })
})

describe('G10 附注 store 默认结构', () => {
  it('上市默认含指定明细与信用风险种子行', () => {
    const store = defaultG10ListedDiscStore()
    expect(store.version).toBe(2)
    expect(store.designatedDetail.designated_1?.label).toBe('发行的普通债权')
    expect(store.fvCreditRisk.fv_1?.label).toBe('发行的普通债权')
    expect(Object.keys(store.movement).length).toBeGreaterThanOrEqual(5)
  })
})

describe('buildG10DesignatedDetailFromAdjStore', () => {
  it('从 G10-1 指定分项带入指定明细表', () => {
    const store = defaultG10AdjStore()
    store.book_designated_bond = {
      openingUnadjusted: 100,
      openingAdjustment: 0,
      closingUnadjusted: 120,
      closingAdjustment: 0,
      reasonAnalysis: '套期指定',
    }
    const detail = buildG10DesignatedDetailFromAdjStore(store)
    expect(Object.keys(detail)).toHaveLength(1)
    expect(detail.designated_1?.openingAmount).toBe(100)
    expect(detail.designated_1?.closingAmount).toBe(120)
    expect(detail.designated_1?.designationReason).toBe('套期指定')
  })
})

describe('summarizeG10DisclosureDirectoryStatus', () => {
  it('汇总上市/国企编制与审定勾稽', () => {
    const listed = defaultG10ListedDiscStore()
    listed.movement.mv_trading_bond = {
      openingAmount: 0,
      increaseAmount: 100,
      decreaseAmount: 0,
      closingAmount: 100,
    }
    const m = new Map<string, { remark?: string; conclusion?: string }>()
    m.set('G10-disclosure-listed', { remark: JSON.stringify(listed) })
    m.set('G10-1-adjudicated-amount', { conclusion: '100' })
    const status = summarizeG10DisclosureDirectoryStatus(m)
    expect(status.adjudicated).toBe(100)
    const listedVar = status.variants.find((v) => v.code === '附注上市')
    expect(listedVar?.filled).toBe(true)
    expect(listedVar?.crossOk).toBe(true)
    const soeVar = status.variants.find((v) => v.code === '附注国企')
    expect(soeVar?.filled).toBe(false)
  })
})
