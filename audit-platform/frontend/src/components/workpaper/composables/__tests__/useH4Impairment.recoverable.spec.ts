/**
 * H4-8 recoverable amount tests
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import {
  calcCostOfEquity,
  calcWaccAfterTax,
  calcPreTaxDiscountRate,
  resolveFairValue,
  calcDisposalTotal,
  buildH4UpstreamCandidates,
  classifyH48SyncStatus,
  useH4Recoverable,
  type H4FairValueDisposal,
} from '../useH4Recoverable'

function baseFv(overrides: Partial<H4FairValueDisposal> = {}): H4FairValueDisposal {
  return {
    materialName: '钢材',
    salesAgreementPrice: 0,
    salesAgreementNote: '',
    activeMarketPrice: 0,
    activeMarketNote: '',
    estimatedPrice: 0,
    estimatedNote: '',
    legalFees: 0,
    relatedTaxes: 0,
    transportCosts: 0,
    directCosts: 0,
    otherCosts: 0,
    auditNote: '',
    ...overrides,
  }
}

describe('H4-8 CAPM / WACC', () => {
  it('Ke / WACC / pre-tax', () => {
    expect(calcCostOfEquity(2.5, 1.2, 10)).toBeCloseTo(11.5, 6)
    expect(calcWaccAfterTax(40, 60, 11.5, 5, 25)).toBeCloseTo(8.4, 6)
    expect(calcWaccAfterTax(0, 0, 10, 5, 25)).toBe(0)
    expect(calcPreTaxDiscountRate(8.4, 25)).toBeCloseTo(11.2, 6)
  })
})

describe('H4-8 fair value hierarchy', () => {
  it('prefer sales agreement then market then estimate', () => {
    expect(resolveFairValue(baseFv({
      salesAgreementPrice: 100,
      activeMarketPrice: 90,
      estimatedPrice: 80,
    })).source).toBe('销售协议价格')
    expect(resolveFairValue(baseFv({
      activeMarketPrice: 90,
      estimatedPrice: 80,
    })).source).toBe('活跃市场价格')
    expect(resolveFairValue(baseFv({ estimatedPrice: 80 })).value).toBe(80)
  })

  it('disposal total and net >= 0', () => {
    expect(calcDisposalTotal(baseFv({
      legalFees: 1, relatedTaxes: 2, transportCosts: 3, directCosts: 4, otherCosts: 5,
    }))).toBe(15)
    const fv = resolveFairValue(baseFv({ estimatedPrice: 100 })).value
    const disposal = calcDisposalTotal(baseFv({ legalFees: 15 }))
    expect(Math.max(fv - disposal, 0)).toBe(85)
  })
})

describe('H4 upstream / sync', () => {
  it('build candidates from H4-7 / H4-2 / H4-6', () => {
    const list = buildH4UpstreamCandidates({
      h47Rows: [{ rowId: 'a', name: '电缆', bookValue: 100, hasSign: '是' }],
      h42Rows: [{ rowId: 'b', name: '电缆', endAmount: 120 }, { rowId: 'c', name: '水泥', endAmount: 50 }],
      h46Rows: [{ rowId: 'd', name: '阀门', diffQuantity: 1, bookAmount: 0 }],
    })
    expect(list.find(c => c.name === '电缆')?.bookValue).toBe(100)
    expect(list.find(c => c.name === '电缆')?.source).toBe('H4-7')
    expect(list.some(c => c.name === '水泥' && c.source === 'H4-2')).toBe(true)
    expect(list.some(c => c.name === '阀门' && c.source === 'H4-6')).toBe(true)
  })

  it('classify sync status', () => {
    expect(classifyH48SyncStatus(
      { fairValueNet: 1, pvCashFlows: 2, recoverableAmount: 2, hasSign: '否' },
      null,
    ).status).toBe('no-test')
    expect(classifyH48SyncStatus(
      { fairValueNet: 1, pvCashFlows: 2, recoverableAmount: 2, hasSign: '是' },
      null,
    ).status).toBe('missing-h8')
    expect(classifyH48SyncStatus(
      { fairValueNet: 10, pvCashFlows: 20, recoverableAmount: 20, hasSign: '是' },
      { fairValueNet: 10, pvCashFlows: 20, recoverableAmount: 20 },
    ).status).toBe('synced')
    expect(classifyH48SyncStatus(
      { fairValueNet: 10, pvCashFlows: 20, recoverableAmount: 20, hasSign: '是' },
      { fairValueNet: 11, pvCashFlows: 20, recoverableAmount: 20 },
    ).status).toBe('stale')
  })
})

describe('useH4Recoverable', () => {
  function setup() {
    const allResponses = ref(new Map<string, any>())
    const onSave = vi.fn((itemId: string, value: any) => {
      allResponses.value.set(itemId, {
        item_id: itemId,
        remark: typeof value === 'string' ? value : JSON.stringify(value),
      })
    })
    const api = useH4Recoverable({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      isReadonly: ref(false),
      onSave,
    })
    return { api, onSave, allResponses }
  }

  it('recoverable = MAX(FV, DCF) and sync to H4-7-calc-rows', () => {
    const { api, allResponses } = setup()
    api.updateAssumption('materialName', '工程物资A')
    api.updateAssumption('bookValue', 1000000)
    api.updateFvDisposal({ estimatedPrice: 500000, legalFees: 10000 })
    api.updateAssumption('discountRate', 10)
    api.updateAssumption('growthRate', 0)
    api.updateAssumption('forecastYears', 3)
    for (const row of api.cashFlowRows.value) {
      api.updateCashFlowCell(row.rowId, 'revenue', 300000)
      api.updateCashFlowCell(row.rowId, 'cost', 50000)
    }
    expect(api.fairValueLessDisposal.value).toBe(490000)
    expect(api.recoverableAmount.value).toBe(
      Math.max(api.fairValueLessDisposal.value, api.totalPV.value),
    )

    const res = api.syncToH47()
    expect(res.ok).toBe(true)
    expect(api.h47CalcRows.value[0].name).toBe('工程物资A')
    expect(api.h47CalcRows.value[0].recoverableAmount).toBe(api.recoverableAmount.value)
    expect(api.h47CalcRows.value[0].wpIndex).toBe('H4-8')
    expect(allResponses.value.get('H4-7-calc-rows')?.remark).toContain('工程物资A')
  })

  it('growth >0 without basis warns; rate<=g invalidates terminal', () => {
    const { api } = setup()
    api.updateAssumption('growthRate', 2)
    expect(api.growthWarnings.value.length).toBeGreaterThan(0)
    api.updateAssumption('discountRate', 1)
    api.updateAssumption('growthRate', 2)
    expect(api.rateInvalid.value).toBe(true)
    expect(api.tvPresent.value).toBe(0)
  })

  it('manual rate when D+E empty avoids div0', () => {
    const { api } = setup()
    api.updateWaccParams({ totalDebt: 0, totalEquity: 0 })
    api.updateAssumption('discountRate', 12)
    expect(api.waccAfterTax.value).toBe(0)
    expect(api.effectiveDiscountRate.value).toBe(12)
  })
})
