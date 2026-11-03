import { describe, expect, it } from 'vitest'
import {
  buildG12DisclosureSyncPatch,
  calcG12DisclosureReconciliationDiff,
  migrateG12DisclosureRows,
} from '../g12DisclosureSync'
import { G12_DISCLOSURE_LISTED_ROWS, G12_DISCLOSURE_SOE_ROWS } from '../g12Constants'

describe('migrateG12DisclosureRows', () => {
  it('上市：旧版多行合并为 net_hedge', () => {
    const migrated = migrateG12DisclosureRows([
      { rowKey: 'net_hedge', currentAmount: 100, priorAmount: 80 },
      { rowKey: 'item_fv', currentAmount: 30, priorAmount: 10 },
      { rowKey: 'cf_reserve', currentAmount: 20, priorAmount: 5 },
    ], 'listed')
    expect(migrated).toHaveLength(1)
    expect(migrated[0].rowKey).toBe('net_hedge')
    expect(migrated[0].currentAmount).toBe(150)
    expect(migrated[0].priorAmount).toBe(95)
  })

  it('国企：旧 key 映射至两行来源', () => {
    const migrated = migrateG12DisclosureRows([
      { rowKey: 'item_fv', currentAmount: 40, priorAmount: 12 },
      { rowKey: 'cf_reserve', currentAmount: 15, priorAmount: 8 },
    ], 'soe')
    expect(migrated.map((r) => r.rowKey).sort()).toEqual(['cf_reserve_to_pl', 'hedged_fv_to_pl'])
    const hedged = migrated.find((r) => r.rowKey === 'hedged_fv_to_pl')
    const cf = migrated.find((r) => r.rowKey === 'cf_reserve_to_pl')
    expect(hedged?.currentAmount).toBe(40)
    expect(cf?.currentAmount).toBe(15)
  })
})

describe('buildG12DisclosureSyncPatch', () => {
  const listedBase = G12_DISCLOSURE_LISTED_ROWS.map((d) => ({
    rowKey: d.rowKey,
    label: d.label,
    currentAmount: 91,
    priorAmount: 81,
    changeAmount: 10,
    changeRate: 10 / 81,
    remark: '已存值',
  }))

  it('上市：同步 G12-1 审定合计并报告真实变化', () => {
    const patch = buildG12DisclosureSyncPatch(listedBase, {
      variant: 'listed',
      adjudicatedTotal: 888,
      priorStore: { net_hedge: { priorUnadjusted: 700, priorAdjustment: 0 } },
    })
    expect(patch.rows[0].currentAmount).toBe(888)
    expect(patch.rows[0].priorAmount).toBe(700)
    expect(patch).toMatchObject({ sourceFound: true, changed: true, fieldsChanged: 2 })
  })

  it('上市：来源字段缺失时保留非零已存值且不报告变化', () => {
    const patch = buildG12DisclosureSyncPatch(listedBase, {
      variant: 'listed',
      adjudicatedTotal: null,
      priorStore: { net_hedge: {} },
      adjudicationRows: [{ rowKey: 'net_hedge' }],
    })
    expect(patch.rows[0]).toMatchObject({ currentAmount: 91, priorAmount: 81, remark: '已存值' })
    expect(patch).toMatchObject({ sourceFound: false, changed: false, fieldsChanged: 0 })
  })

  it('上市：明确 0 是有效来源，可覆盖非零已存值', () => {
    const patch = buildG12DisclosureSyncPatch(listedBase, {
      variant: 'listed',
      adjudicatedTotal: 0,
      priorStore: { net_hedge: { priorAudited: 0 } },
    })
    expect(patch.rows[0]).toMatchObject({ currentAmount: 0, priorAmount: 0 })
    expect(patch).toMatchObject({ sourceFound: true, changed: true, fieldsChanged: 2 })
  })

  it('上市：仅本期有来源时更新本期并保留非零上期值', () => {
    const patch = buildG12DisclosureSyncPatch(listedBase, {
      variant: 'listed',
      adjudicatedTotal: 123,
      priorStore: {},
    })
    expect(patch.rows[0]).toMatchObject({ currentAmount: 123, priorAmount: 81 })
    expect(patch).toMatchObject({ sourceFound: true, changed: true, fieldsChanged: 1 })
  })

  it('国企：自 G12-2 明细拆分两项', () => {
    const soeBase = G12_DISCLOSURE_SOE_ROWS.map((d, index) => ({
      rowKey: d.rowKey,
      label: d.label,
      currentAmount: 10 + index,
      priorAmount: 20 + index,
      changeAmount: -10,
      changeRate: -0.5,
      remark: '已存值',
    }))
    const hedgeJson = JSON.stringify([
      { rowKind: 'fv_allocation', purchasePortion: 120, salesPortion: 200, instrumentFvCumulative: 320 },
      { rowKind: 'amortization', hedgeAdjAmortization: 35 },
    ])
    const patch = buildG12DisclosureSyncPatch(soeBase, {
      variant: 'soe',
      adjudicatedTotal: 235,
      priorStore: {
        item_fv: { priorUnadjusted: 100 },
        cf_reserve: { priorUnadjusted: 20 },
      },
      hedgeDetailJson: hedgeJson,
    })
    expect(patch.rows.find((r) => r.rowKey === 'hedged_fv_to_pl')?.currentAmount).toBe(120)
    expect(patch.rows.find((r) => r.rowKey === 'cf_reserve_to_pl')?.currentAmount).toBe(35)
    expect(patch.rows.find((r) => r.rowKey === 'hedged_fv_to_pl')?.priorAmount).toBe(100)
    expect(patch.rows.find((r) => r.rowKey === 'cf_reserve_to_pl')?.priorAmount).toBe(20)
    expect(patch).toMatchObject({ sourceFound: true, changed: true, fieldsChanged: 4 })
  })

  it('国企：明细只有一侧字段时只 patch 该侧，另一侧保留非零值', () => {
    const soeBase = G12_DISCLOSURE_SOE_ROWS.map((d, index) => ({
      rowKey: d.rowKey,
      label: d.label,
      currentAmount: 41 + index,
      priorAmount: 51 + index,
      changeAmount: -10,
      changeRate: -0.2,
      remark: '已存值',
    }))
    const patch = buildG12DisclosureSyncPatch(soeBase, {
      variant: 'soe',
      adjudicatedTotal: null,
      priorStore: {},
      hedgeDetailJson: JSON.stringify([{ rowKind: 'fv_allocation', purchasePortion: 0 }]),
    })
    expect(patch.rows.find((r) => r.rowKey === 'hedged_fv_to_pl')?.currentAmount).toBe(0)
    expect(patch.rows.find((r) => r.rowKey === 'cf_reserve_to_pl')?.currentAmount).toBe(42)
    expect(patch).toMatchObject({ sourceFound: true, changed: true, fieldsChanged: 1 })
  })
})

describe('calcG12DisclosureReconciliationDiff', () => {
  it('无审定数时返回 null', () => {
    expect(calcG12DisclosureReconciliationDiff(100, null)).toBeNull()
  })

  it('计算差异', () => {
    expect(calcG12DisclosureReconciliationDiff(100, 95)).toBe(5)
  })
})
