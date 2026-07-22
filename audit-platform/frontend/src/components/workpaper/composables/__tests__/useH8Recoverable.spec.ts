/**
 * useH8Recoverable / h8RecoverableModel 单元测试
 */
import { describe, it, expect } from 'vitest'
import { ref, computed, nextTick } from 'vue'
import {
  calcRecoverableAmount,
  calcCostOfEquity,
  calcWaccAfterTax,
  calcPreTaxDiscountRate,
  resolveH8FairValue,
  calcH8DisposalTotal,
  checkForecastVsLeaseTerm,
  migrateLegacyH811Params,
  buildH8UpstreamCandidates,
  classifyH810SyncStatus,
  estimateRemainingLeaseYears,
} from '../h8RecoverableModel'
import { useH8Recoverable } from '../useH8Recoverable'

describe('h8RecoverableModel', () => {
  it('calcRecoverableAmount = MAX(公允净额, 现值)', () => {
    expect(calcRecoverableAmount(100, 80)).toBe(100)
    expect(calcRecoverableAmount(50, 90)).toBe(90)
    expect(calcRecoverableAmount(0, 0)).toBe(0)
  })

  it('WACC / CAPM 公式', () => {
    const ke = calcCostOfEquity(2.5, 1, 10) // 2.5 + 1*(10-2.5)=10
    expect(ke).toBe(10)
    const wacc = calcWaccAfterTax(40, 60, 10, 5, 25)
    // E/(D+E)*Ke + D/(D+E)*Kd*(1-t) = 0.6*10 + 0.4*5*0.75 = 6 + 1.5 = 7.5
    expect(wacc).toBeCloseTo(7.5, 5)
    expect(calcPreTaxDiscountRate(7.5, 25)).toBeCloseTo(10, 5)
  })

  it('公允三层次优先级：协议 > 活跃市场 > 估计', () => {
    const fv = {
      assetName: '办公楼租赁',
      salesAgreementPrice: 0,
      salesAgreementNote: '',
      activeMarketPrice: 0,
      activeMarketNote: '',
      estimatedPrice: 100,
      estimatedNote: '',
      legalFees: 5,
      relatedTaxes: 5,
      transportCosts: 0,
      directCosts: 0,
      otherCosts: 0,
      auditNote: '',
    }
    expect(resolveH8FairValue(fv).source).toBe('估计价格')
    fv.activeMarketPrice = 120
    expect(resolveH8FairValue(fv).source).toBe('活跃市场价格')
    fv.salesAgreementPrice = 130
    expect(resolveH8FairValue(fv).source).toBe('销售协议价格')
    expect(calcH8DisposalTotal(fv)).toBe(10)
  })

  it('预测期超过剩余租赁期告警', () => {
    expect(checkForecastVsLeaseTerm(5, 3)).toContain('超过剩余租赁期')
    expect(checkForecastVsLeaseTerm(3, 5)).toBeNull()
    expect(checkForecastVsLeaseTerm(5, 0)).toBeNull()
  })

  it('estimateRemainingLeaseYears 由到期日估算', () => {
    const asOf = new Date('2025-01-01')
    expect(estimateRemainingLeaseYears('2027-01-01', asOf)).toBeCloseTo(2, 0)
    expect(estimateRemainingLeaseYears('', asOf)).toBe(0)
  })

  it('上游候选：有迹象 H8-10 排前', () => {
    const cands = buildH8UpstreamCandidates({
      h10Rows: [
        { rowId: 'a', assetName: '无迹象资产', bookValue: 1, hasIndication: 'N' },
        { rowId: 'b', assetName: '有迹象资产', bookValue: 2, hasIndication: 'Y', contractNo: 'L-9' },
      ],
      h2Rows: [],
    })
    expect(cands[0].name).toBe('有迹象资产')
    expect(cands[0].hasIndication).toBe(true)
    expect(cands[0].contractNo).toBe('L-9')
  })

  it('旧版 H8-11-params 小数折现率迁移为百分数', () => {
    const m = migrateLegacyH811Params({ discountRate: 0.05, forecastYears: 4, annualCashFlow: 1000 })
    expect(m.discountRate).toBe(5)
    expect(m.forecastYears).toBe(4)
    expect(m.annualCashFlow).toBe(1000)
  })

  it('上游候选：H8-10 + H8-2', () => {
    const cands = buildH8UpstreamCandidates({
      h10Params: { bookValue: 50000, impairmentSign: '市场利率上升', assetName: '仓库使用权' },
      h2Rows: [{ rowId: 'r1', assetName: '办公室', contractNo: 'L-01', netValue: 20000 }],
    })
    expect(cands.some(c => c.source === 'H8-10')).toBe(true)
    expect(cands.some(c => c.source === 'H8-2' && c.name === '办公室')).toBe(true)
  })

  it('H8-10 同步状态分类', () => {
    expect(classifyH810SyncStatus({ recoverableAmount: 100 }, { recoverableAmount: 100 }).status).toBe('synced')
    expect(classifyH810SyncStatus({ recoverableAmount: 100 }, { recoverableAmount: 90 }).status).toBe('stale')
    expect(classifyH810SyncStatus({ recoverableAmount: 100, hasSign: '是' }, null).status).toBe('missing-h11')
  })
})

describe('useH8Recoverable', () => {
  function setup(initial: Map<string, any> = new Map()) {
    const allResponses = ref(initial)
    const saved: Array<{ id: string; value: any }> = []
    const api = useH8Recoverable({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: computed(() => allResponses.value),
      isReadonly: ref(false),
      onSave: (id, value) => {
        saved.push({ id, value })
        const map = new Map(allResponses.value)
        map.set(id, { remark: typeof value === 'string' ? value : JSON.stringify(value) })
        allResponses.value = map
      },
    })
    return { api, saved, allResponses }
  }

  it('公允净额 + DCF 取较高者为可收回金额，并回写 H8-10', async () => {
    const { api, saved } = setup()
    await nextTick()

    api.updateAssumption('assetName', '仓库租赁')
    api.updateAssumption('bookValue', 800000)
    api.updateAssumption('discountRate', 10)
    api.updateAssumption('forecastYears', 2)
    api.updateAssumption('growthRate', 0)
    api.updateFvDisposal({ estimatedPrice: 40000, legalFees: 0 })

    api.updateCashFlowCell(api.cashFlowRows.value[0].rowId, 'revenue', 55000)
    api.updateCashFlowCell(api.cashFlowRows.value[0].rowId, 'cost', 0)
    api.updateCashFlowCell(api.cashFlowRows.value[1].rowId, 'revenue', 55000)
    api.updateCashFlowCell(api.cashFlowRows.value[1].rowId, 'cost', 0)

    expect(api.fairValueLessDisposal.value).toBe(40000)
    expect(api.totalPV.value).toBeGreaterThan(40000)
    expect(api.recoverableAmount.value).toBe(api.totalPV.value)
    expect(api.recoverableSource.value).toBe('预计未来现金流量现值')
    expect(api.impliedImpairment.value).toBeGreaterThan(0)

    const res = api.syncToH810()
    expect(res.ok).toBe(true)
    const h10Save = saved.find(s => s.id === 'H8-10-params')
    expect(h10Save).toBeTruthy()
    const parsed = JSON.parse(String(h10Save!.value))
    expect(parsed.recoverableAmount).toBe(api.recoverableAmount.value)
    expect(parsed.fairValueNet).toBe(40000)
  })

  it('未填 D/E 时用手工折现率，避免除零', async () => {
    const { api } = setup()
    await nextTick()
    api.updateAssumption('discountRate', 8)
    api.updateAssumption('forecastYears', 1)
    api.updateCashFlowCell(api.cashFlowRows.value[0].rowId, 'revenue', 1000)
    expect(api.waccAfterTax.value).toBe(0)
    expect(api.effectiveDiscountRate.value).toBe(8)
    expect(api.cashFlowRows.value[0].discountFactor).toBeCloseTo(1 / 1.08, 5)
    expect(Number.isFinite(api.totalPV.value)).toBe(true)
  })

  it('增量借款利率优先于手工折现率（无 WACC 时）', async () => {
    const { api } = setup()
    await nextTick()
    api.updateAssumption('discountRate', 12)
    api.updateAssumption('incrementalBorrowingRate', 6)
    expect(api.effectiveDiscountRate.value).toBe(6)
  })

  it('旧版年金参数可迁移', async () => {
    const map = new Map([
      ['H8-11-params', {
        remark: JSON.stringify({
          discountRate: 0.1,
          forecastYears: 3,
          annualCashFlow: 10000,
          terminalValue: 0,
          bookValue: 80000,
        }),
      }],
    ])
    const { api } = setup(map)
    await nextTick()
    expect(api.assumptions.value.discountRate).toBe(10)
    expect(api.assumptions.value.forecastYears).toBe(3)
    expect(api.assumptions.value.bookValue).toBe(80000)
    expect(api.cashFlowRows.value).toHaveLength(3)
    expect(api.cashFlowRows.value[0].revenue).toBe(10000)
  })

  it('从 H8-10 有迹象行批量建组并缓存公允/DCF', async () => {
    const map = new Map([
      ['H8-10-rows', {
        remark: JSON.stringify([
          {
            rowId: 'r1', assetName: '仓库', contractNo: 'L-1',
            hasIndication: 'Y', bookValue: 100000, indicationDesc: '闲置',
          },
          {
            rowId: 'r2', assetName: '正常资产', hasIndication: 'N', bookValue: 50000,
          },
        ]),
      }],
    ])
    const { api } = setup(map)
    await nextTick()
    const res = api.seedGroupsFromH810Indications()
    expect(res.ok).toBe(true)
    expect(res.count).toBeGreaterThanOrEqual(1)
    const g = api.groups.value.find(x => x.name === '仓库')
    expect(g).toBeTruthy()
    expect(g!.contractNo).toBe('L-1')
    expect(g!.bookValue).toBe(100000)
    api.updateAssumption('discountRate', 10)
    api.updateAssumption('forecastYears', 1)
    api.updateFvDisposal({ estimatedPrice: 20000 })
    api.updateCashFlowCell(api.cashFlowRows.value[0].rowId, 'revenue', 5000)
    // persist 后应缓存
    const active = api.groups.value.find(x => x.groupId === api.activeGroupId.value)
    expect(active?._fairValueNet).toBe(20000)
    expect((active?._pvCashFlows ?? 0)).toBeGreaterThan(0)
    expect(api.buildConclusionDraft()).toContain('可收回金额')
  })
})
