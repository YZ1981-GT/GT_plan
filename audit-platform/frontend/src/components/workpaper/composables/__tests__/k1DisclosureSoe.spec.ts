import { describe, it, expect } from 'vitest'
import { PRESET_SEGMENTS } from '@/composables/useAgingConfig'
import {
  buildDefaultMethodRows,
  buildBalanceStageMovementsFromK17,
  buildGovGrantFromK1Detail,
  buildPortfolioAgingRows,
  calcBalanceStageTieOut,
  calcMethodTieOut,
  emptyK1SoePayload,
  parseK1SoePayload,
  recomputeMethodRows,
  splitK1DetailByProvisionMethod,
} from '../k1DisclosureModel'
import { buildK1SoeSubTableData, buildK1SoeSyncPayloads } from '../k1DisclosureSyncPayload'
import { K1_SOE_SUBTABLE } from '../k1NoteSectionMap'

describe('k1SoeDisclosureModel', () => {
  it('recomputeMethodRows calculates totals and percentages', () => {
    const rows = recomputeMethodRows([
      {
        rowId: 'a', rowKey: 'individual', label: '单项',
        endBalance: 300, endBalancePct: null, endProvision: 30, endEclRate: null, endBookValue: 0,
        priorBalance: 0, priorBalancePct: null, priorProvision: 0, priorEclRate: null, priorBookValue: 0,
        editable: true,
      },
      {
        rowId: 'b', rowKey: 'portfolio', label: '组合',
        endBalance: 700, endBalancePct: null, endProvision: 70, endEclRate: null, endBookValue: 0,
        priorBalance: 0, priorBalancePct: null, priorProvision: 0, priorEclRate: null, priorBookValue: 0,
        editable: true,
      },
      {
        rowId: 'c', rowKey: 'total', label: '合计',
        endBalance: 0, endBalancePct: 100, endProvision: 0, endEclRate: null, endBookValue: 0,
        priorBalance: 0, priorBalancePct: 100, priorProvision: 0, priorEclRate: null, priorBookValue: 0,
        editable: false,
      },
    ])
    const total = rows.find((r) => r.rowKey === 'total')
    expect(total?.endBalance).toBe(1000)
    expect(total?.endProvision).toBe(100)
    expect(rows.find((r) => r.rowKey === 'individual')?.endBalancePct).toBe(30)
  })

  it('buildGovGrantFromK1Detail filters subsidy nature', () => {
    const rows = buildGovGrantFromK1Detail([
      {
        id: '1', counterparty: '财政局', nature: '政府补助-技改', beginBalance: 0, endBalance: 50000,
        badDebtProvision: 0, stage: 1, relatedParty: '否', agingPrior: {}, agingAudited: { within1: 50000 }, remark: '2026年收回',
      },
      {
        id: '2', counterparty: '供应商', nature: '押金', beginBalance: 0, endBalance: 1000,
        badDebtProvision: 0, stage: 1, relatedParty: '否', agingPrior: {}, agingAudited: {}, remark: '',
      },
    ])
    expect(rows).toHaveLength(1)
    expect(rows[0].unitName).toBe('财政局')
  })

  it('parseK1SoePayload handles V2 JSON', () => {
    const p = parseK1SoePayload({ version: 2, methodRows: buildDefaultMethodRows() }, PRESET_SEGMENTS.FIVE_YEAR)
    expect(p.version).toBe(2)
    expect(p.methodRows.length).toBe(3)
  })

  it('calcMethodTieOut detects mismatch', () => {
    const rows = recomputeMethodRows([
      {
        rowId: 'a', rowKey: 'individual', label: '单项',
        endBalance: 100, endBalancePct: null, endProvision: 0, endEclRate: null, endBookValue: 0,
        priorBalance: 0, priorBalancePct: null, priorProvision: 0, priorEclRate: null, priorBookValue: 0,
        editable: true,
      },
      {
        rowId: 'b', rowKey: 'portfolio', label: '组合',
        endBalance: 0, endBalancePct: null, endProvision: 0, endEclRate: null, endBookValue: 0,
        priorBalance: 0, priorBalancePct: null, priorProvision: 0, priorEclRate: null, priorBookValue: 0,
        editable: true,
      },
      {
        rowId: 'c', rowKey: 'total', label: '合计',
        endBalance: 0, endBalancePct: 100, endProvision: 0, endEclRate: null, endBookValue: 0,
        priorBalance: 0, priorBalancePct: 100, priorProvision: 0, priorEclRate: null, priorBookValue: 0,
        editable: false,
      },
    ])
    const tie = calcMethodTieOut(rows, 500)
    expect(tie.matched).toBe(false)
  })

  it('splitK1DetailByProvisionMethod excludes individual sub-rows from portfolio', () => {
    const details = [
      { id: '1', counterparty: '甲公司', nature: '', beginBalance: 0, endBalance: 100, badDebtProvision: 10, stage: 3, relatedParty: '否', agingPrior: {}, agingAudited: { within1: 100 }, remark: '' },
      { id: '2', counterparty: '乙公司', nature: '', beginBalance: 0, endBalance: 200, badDebtProvision: 0, stage: 1, relatedParty: '否', agingPrior: {}, agingAudited: { within1: 200 }, remark: '' },
    ]
    const k13 = {
      version: 2,
      mainRows: [
        { id: 'sub1', category: 'individual', label: '甲公司', isSubRow: true, isFixed: false, priorAudited: 5, currentAudited: 10, currentProvision: 0, currentReversal: 0, currentWriteOff: 0, priorBook: 0, priorAdj: 0, currentBook: 0, currentAdj: 0, reason: '' },
        { id: 'port', category: 'portfolio', label: '按组合计提', isSubRow: false, isFixed: true, priorAudited: 0, currentAudited: 0, currentProvision: 0, currentReversal: 0, currentWriteOff: 0, priorBook: 0, priorAdj: 0, currentBook: 0, currentAdj: 0, reason: '' },
        { id: 'tot', category: 'total', label: '合计', isSubRow: false, isFixed: true, priorAudited: 5, currentAudited: 10, currentProvision: 0, currentReversal: 0, currentWriteOff: 0, priorBook: 0, priorAdj: 0, currentBook: 0, currentAdj: 0, reason: '' },
      ],
      stageMovements: [],
    }
    const split = splitK1DetailByProvisionMethod(details, k13)
    expect(split.individualDetails).toHaveLength(1)
    expect(split.portfolioDetails).toHaveLength(1)
    expect(split.portfolioDetails[0].counterparty).toBe('乙公司')
  })

  it('buildBalanceStageMovementsFromK17 aggregates opening and stage transfers', () => {
    const details = [
      { id: '1', counterparty: '甲', nature: '', beginBalance: 80, endBalance: 100, badDebtProvision: 0, stage: 2, relatedParty: '否', agingPrior: {}, agingAudited: {}, remark: '' },
      { id: '2', counterparty: '乙', nature: '', beginBalance: 50, endBalance: 40, badDebtProvision: 0, stage: 1, relatedParty: '否', agingPrior: {}, agingAudited: {}, remark: '' },
    ]
    const stageRows = [
      { counterparty: '甲', endBalance: 100, priorStage: 1 as const, stage: 2 as const },
      { counterparty: '乙', endBalance: 40, priorStage: 1 as const, stage: 1 as const },
    ] as any[]
    const movements = buildBalanceStageMovementsFromK17(stageRows, details)
    const opening = movements.find((r) => r.key === 'opening')
    const closing = movements.find((r) => r.key === 'closing')
    expect(opening?.stage1).toBe(130) // 80+50
    expect(closing?.stage1).toBe(40)
    expect(closing?.stage2).toBe(100)
    const tie = calcBalanceStageTieOut(movements, 140)
    expect(tie.matched).toBe(true)
  })
})

describe('k1SoeDisclosureSyncPayload', () => {
  it('buildK1SoeSubTableData uses SOE note sub-table names', () => {
    const snap = emptyK1SoePayload()
    snap.portfolioAgingRows = buildPortfolioAgingRows(
      PRESET_SEGMENTS.FIVE_YEAR,
      { end: { within1: 100, y1to2: 0, y2to3: 0, y3to4: 0, y4to5: 0, over5: 0 }, prior: {} },
      { end: 5, prior: 0 },
    )
    const data = buildK1SoeSubTableData(snap)
    expect(data[K1_SOE_SUBTABLE.aging]).toBeDefined()
    expect(data[K1_SOE_SUBTABLE.eclMovement]).toBeDefined()
    expect(data[K1_SOE_SUBTABLE.balanceMovement]).toBeDefined()
    expect(data[K1_SOE_SUBTABLE.portfolioOther]?.length).toBeGreaterThan(0)
  })

  it('buildK1SoeSyncPayloads 附带 columns（源对齐中文列头）', () => {
    const snap = emptyK1SoePayload()
    const [payload] = buildK1SoeSyncPayloads('wp-k1', null, snap)
    expect(payload).toBeDefined()
    const cols = payload.columns!
    expect(Object.keys(cols)).toContain(K1_SOE_SUBTABLE.aging)
    // 账龄表：期末数/期初数（国企两列口径）
    expect(cols[K1_SOE_SUBTABLE.aging].map((c) => c.label)).toEqual(['账龄', '期末数', '期初数'])
    expect(cols[K1_SOE_SUBTABLE.aging][0].is_label).toBe(true)
    // 政府补助表源对齐五列
    expect(cols[K1_SOE_SUBTABLE.govGrant].map((c) => c.label)).toEqual([
      '单位名称', '政府补助项目名称', '期末余额', '期末账龄', '预计收取的时间_金额及依据',
    ])
  })
})
