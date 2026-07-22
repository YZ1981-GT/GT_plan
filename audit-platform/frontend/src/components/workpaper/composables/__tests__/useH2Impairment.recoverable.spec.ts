/**
 * H2-15/16 impairment / recoverable / WACC tests
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import {
  calcCostOfEquity,
  calcWaccAfterTax,
  calcPreTaxDiscountRate,
  resolveFairValue,
  calcDisposalTotal,
  buildImpairmentAjePair,
  buildUpstreamCandidates,
  useH2Impairment,
  type FairValueDisposal,
} from '../useH2Impairment'

const YES = "\u662f"
const NO = "\u5426"
const STOPPED = "\u505c\u5de5"
const BUILDING = "\u65bd\u5de5\u4e2d"

function baseFv(overrides: Partial<FairValueDisposal> = {}): FairValueDisposal {
  return {
    projectName: 'CIP-A',
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

describe('H2-16 CAPM / WACC', () => {
  it('Ke formula', () => {
    expect(calcCostOfEquity(2.5, 1.2, 10)).toBeCloseTo(11.5, 6)
  })
  it('after-tax WACC', () => {
    expect(calcWaccAfterTax(40, 60, 11.5, 5, 25)).toBeCloseTo(8.4, 6)
  })
  it('WACC=0 when D+E=0', () => {
    expect(calcWaccAfterTax(0, 0, 10, 5, 25)).toBe(0)
  })
  it('pre-tax rate', () => {
    expect(calcPreTaxDiscountRate(8.4, 25)).toBeCloseTo(11.2, 6)
  })
})

describe('H2-16 fair value', () => {
  it('prefer sales agreement', () => {
    const r = resolveFairValue(baseFv({
      salesAgreementPrice: 100,
      activeMarketPrice: 90,
      estimatedPrice: 80,
    }))
    expect(r.source).toBe("\u9500\u552e\u534f\u8bae\u4ef7\u683c")
    expect(r.value).toBe(100)
  })
  it('active market when no agreement', () => {
    const r = resolveFairValue(baseFv({ activeMarketPrice: 90, estimatedPrice: 80 }))
    expect(r.source).toBe("\u6d3b\u8dc3\u5e02\u573a\u4ef7\u683c")
    expect(r.value).toBe(90)
  })
  it('disposal total', () => {
    expect(calcDisposalTotal(baseFv({
      legalFees: 1, relatedTaxes: 2, transportCosts: 3, directCosts: 4, otherCosts: 5,
    }))).toBe(15)
  })
  it('FV less disposal >= 0', () => {
    const fv = resolveFairValue(baseFv({ estimatedPrice: 100 })).value
    const disposal = calcDisposalTotal(baseFv({ legalFees: 15 }))
    expect(Math.max(fv - disposal, 0)).toBe(85)
  })
})

describe('H2-16 composable', () => {
  function setup() {
    const allResponses = ref(new Map<string, any>())
    const onSave = vi.fn((itemId: string, value: any) => {
      allResponses.value.set(itemId, {
        item_id: itemId,
        remark: typeof value === 'string' ? value : JSON.stringify(value),
      })
    })
    const api = useH2Impairment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      isReadonly: ref(false),
      section: 'recoverable',
      onSave,
    })
    return { api, onSave, allResponses }
  }

  it('recoverable = MAX(FV, DCF)', () => {
    const { api } = setup()
    api.updateFvDisposal({ estimatedPrice: 500000, legalFees: 10000 })
    api.updateAssumption('discountRate', 10)
    api.updateAssumption('growthRate', 0)
    api.updateAssumption('forecastYears', 3)
    for (const row of api.cashFlowRows.value) {
      api.updateCashFlowCell(row.rowId, 'revenue', 300000)
      api.updateCashFlowCell(row.rowId, 'cost', 50000)
    }
    expect(api.fairValueLessDisposal.value).toBe(490000)
    expect(api.recoverableAmount.value).toBe(Math.max(api.fairValueLessDisposal.value, api.totalPV.value))
  })

  it('growth >0 without basis warns', () => {
    const { api } = setup()
    api.updateAssumption('growthRate', 2)
    api.updateAssumption('growthRateBasis', '')
    expect(api.growthWarnings.value.length).toBeGreaterThan(0)
  })

  it('growth above industry warns', () => {
    const { api } = setup()
    api.updateAssumption('growthRate', 5)
    api.updateAssumption('industryGrowthRate', 3)
    api.updateAssumption('growthRateBasis', 'mgmt')
    expect(api.growthWarnings.value.some(m => m.includes("\u884c\u4e1a"))).toBe(true)
  })

  it('r<=g invalidates TV', () => {
    const { api } = setup()
    api.updateAssumption('discountRate', 3)
    api.updateAssumption('growthRate', 4)
    expect(api.rateInvalid.value).toBe(true)
    expect(api.tvPresent.value).toBe(0)
  })

  it('syncToH215 writes cols 3/4 and formulas', () => {
    const { api } = setup()
    api.addCalcRow('Plant')
    api.updateCalcCell(api.calcRows.value[0].rowId, 'hasSign', YES)
    api.updateCalcCell(api.calcRows.value[0].rowId, 'bookedProvision', 50000)
    api.updateAssumption('projectName', 'Plant')
    api.updateAssumption('bookValue', 1000000)
    api.updateFvDisposal({ estimatedPrice: 800000 })
    const res = api.syncToH215()
    expect(res.ok).toBe(true)
    const row = api.calcRows.value.find(r => r.name === 'Plant')
    expect(row?.fairValueNet).toBe(api.fairValueLessDisposal.value)
    expect(row?.pvCashFlows).toBe(api.totalPV.value)
    expect(row?.recoverableAmount).toBe(api.recoverableAmount.value)
    expect(row?.bookValue).toBe(1000000)
    expect(row?.wpIndex).toBe('H2-16')
    expect(row?.requiredProvision).toBe(Math.max(1000000 - (row?.recoverableAmount ?? 0), 0))
    expect(row?.periodAdjustment).toBe((row?.requiredProvision ?? 0) - 50000)
  })

  it('legacy fair-value value', () => {
    const allResponses = ref(new Map<string, any>([
      ['H2-16-fair-value', { item_id: 'H2-16-fair-value', remark: JSON.stringify({ value: 12345 }) }],
    ]))
    const api = useH2Impairment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      isReadonly: ref(false),
      section: 'recoverable',
    })
    expect(api.fvDisposal.value.estimatedPrice).toBe(12345)
    expect(api.fairValueLessDisposal.value).toBe(12345)
  })
})

describe('H2-15 formulas', () => {
  function setup() {
    const allResponses = ref(new Map<string, any>())
    const onSave = vi.fn((itemId: string, value: any) => {
      allResponses.value.set(itemId, {
        item_id: itemId,
        remark: typeof value === 'string' ? value : JSON.stringify(value),
      })
    })
    const api = useH2Impairment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      isReadonly: ref(false),
      section: 'impairment',
      onSave,
    })
    return { api }
  }

  it('col5/6/8 formulas', () => {
    const { api } = setup()
    api.addCalcRow('A')
    const id = api.calcRows.value[0].rowId
    api.updateCalcCell(id, 'hasSign', YES)
    api.updateCalcCell(id, 'bookValue', 1000)
    api.updateCalcCell(id, 'fairValueNet', 600)
    api.updateCalcCell(id, 'pvCashFlows', 700)
    api.updateCalcCell(id, 'bookedProvision', 100)
    const row = api.calcRows.value[0]
    expect(row.recoverableAmount).toBe(700)
    expect(row.requiredProvision).toBe(300)
    expect(row.periodAdjustment).toBe(200)
  })

  it('no sign => periodAdj=0', () => {
    const { api } = setup()
    api.addCalcRow('B')
    const id = api.calcRows.value[0].rowId
    api.updateCalcCell(id, 'bookValue', 1000)
    api.updateCalcCell(id, 'bookedProvision', 80)
    api.updateCalcCell(id, 'hasSign', NO)
    const row = api.calcRows.value[0]
    expect(row.periodAdjustment).toBe(0)
    expect(row.requiredProvision).toBe(80)
  })

  it('negative col8 CAS8 warning', () => {
    const { api } = setup()
    api.addCalcRow('C')
    const id = api.calcRows.value[0].rowId
    api.updateCalcCell(id, 'hasSign', YES)
    api.updateCalcCell(id, 'bookValue', 1000)
    api.updateCalcCell(id, 'fairValueNet', 950)
    api.updateCalcCell(id, 'bookedProvision', 200)
    expect(api.cas8ReversalRows.value.length).toBe(1)
    expect(api.calcRows.value[0].periodAdjustment).toBe(-150)
  })

  it('legacy recoverableAmount only', () => {
    const allResponses = ref(new Map<string, any>([
      ['H2-15-test-rows', {
        item_id: 'H2-15-test-rows',
        remark: JSON.stringify([{
          rowId: 'r1', name: 'old', bookValue: 500, recoverableAmount: 400, method: 'DCF', remark: '',
        }]),
      }],
    ]))
    const api = useH2Impairment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      isReadonly: ref(false),
      section: 'impairment',
    })
    const row = api.calcRows.value[0]
    expect(row.recoverableAmount).toBe(400)
    expect(row.requiredProvision).toBe(100)
  })
})

describe('H2-15 import from H2-2/H2-1 and push AJE', () => {
  function setup(seed?: Map<string, any>) {
    const allResponses = ref(seed ?? new Map<string, any>())
    const onSave = vi.fn((itemId: string, value: any) => {
      allResponses.value.set(itemId, {
        item_id: itemId,
        remark: typeof value === 'string' ? value : JSON.stringify(value),
      })
    })
    const api = useH2Impairment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      isReadonly: ref(false),
      section: 'impairment',
      onSave,
    })
    return { api, allResponses, onSave }
  }

  it('buildImpairmentAjePair', () => {
    const pair = buildImpairmentAjePair({ projectName: 'Plant', amount: 123.456, seqStart: 1 })
    expect(pair).toHaveLength(2)
    expect(pair[0].accountCode).toBe('6701')
    expect(pair[0].debit).toBe(123.46)
    expect(pair[1].accountCode).toBe('1604')
    expect(pair[1].credit).toBe(123.46)
  })

  it('import book/provision from H2-2', () => {
    const { api } = setup(new Map([
      ['H2-2-rows', {
        item_id: 'H2-2-rows',
        remark: JSON.stringify([
          { name: 'PlantA', cipEnd: 1000000, endAudited: 0, impairmentEnd: 80000 },
          { name: 'PlantB', cipEnd: 500000, endAudited: 480000, impairmentEnd: 0 },
        ]),
      }],
      ['H2-1-rows', {
        item_id: 'H2-1-rows',
        remark: JSON.stringify([
          { name: 'PlantA', endAudited: 1000000 },
          { name: 'PlantB', endAudited: 480000 },
        ]),
      }],
    ]))
    const res = api.importBookValuesFromH2()
    expect(res.ok).toBe(true)
    expect(res.source).toBe('H2-2')
    expect(res.added).toBe(2)
    const a = api.calcRows.value.find(r => r.name === 'PlantA')
    const b = api.calcRows.value.find(r => r.name === 'PlantB')
    expect(a?.bookValue).toBe(1000000)
    expect(a?.bookedProvision).toBe(80000)
    expect(b?.bookValue).toBe(480000)
    expect(b?.bookedProvision).toBe(0)
  })

  it('fallback to H2-1 when H2-2 empty', () => {
    const { api } = setup(new Map([
      ['H2-1-rows', {
        item_id: 'H2-1-rows',
        remark: JSON.stringify([{ name: 'AdjPlant', endAudited: 200000 }]),
      }],
    ]))
    const res = api.importBookValuesFromH2()
    expect(res.ok).toBe(true)
    expect(res.source).toBe('H2-1')
    expect(api.calcRows.value[0].bookValue).toBe(200000)
  })

  it('push AJE for supplement; skip reversal; idempotent replace', () => {
    const { api, allResponses } = setup()
    api.addCalcRow('Supp')
    const id1 = api.calcRows.value[0].rowId
    api.updateCalcCell(id1, 'hasSign', YES)
    api.updateCalcCell(id1, 'bookValue', 1000)
    api.updateCalcCell(id1, 'fairValueNet', 700)
    api.updateCalcCell(id1, 'bookedProvision', 50)

    api.addCalcRow('Rev')
    const id2 = api.calcRows.value[1].rowId
    api.updateCalcCell(id2, 'hasSign', YES)
    api.updateCalcCell(id2, 'bookValue', 1000)
    api.updateCalcCell(id2, 'fairValueNet', 950)
    api.updateCalcCell(id2, 'bookedProvision', 200)

    const res = api.pushAjeDraftToH23()
    expect(res.ok).toBe(true)
    expect(res.added).toBe(2)
    expect(res.skippedReversal).toBe(1)
    expect(res.amount).toBe(250)

    const h23 = JSON.parse(allResponses.value.get('H2-3-rows')!.remark)
    expect(h23).toHaveLength(2)
    expect(h23[0].accountCode).toBe('6701')
    expect(h23[0].debit).toBe(250)
    expect(h23[1].accountCode).toBe('1604')
    expect(h23[1].credit).toBe(250)

    expect(api.pushAjeDraftToH23().ok).toBe(true)
    expect(JSON.parse(allResponses.value.get('H2-3-rows')!.remark)).toHaveLength(2)
  })
})

describe('H2-16 multi-group / upstream', () => {
  function setup(seed?: Map<string, any>) {
    const allResponses = ref(seed ?? new Map<string, any>())
    const onSave = vi.fn((itemId: string, value: any) => {
      allResponses.value.set(itemId, {
        item_id: itemId,
        remark: typeof value === 'string' ? value : JSON.stringify(value),
      })
    })
    const api = useH2Impairment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      isReadonly: ref(false),
      section: 'recoverable',
      onSave,
    })
    return { api, allResponses }
  }

  it('add/switch groups keep assumptions', () => {
    const { api } = setup()
    api.updateAssumption('projectName', 'G1')
    api.updateAssumption('bookValue', 100)
    const id1 = api.activeGroupId.value
    api.addGroup('G2')
    expect(api.groups.value.length).toBe(2)
    expect(api.assumptions.value.projectName).toBe('G2')
    api.updateAssumption('bookValue', 200)
    api.setActiveGroup(id1)
    expect(api.assumptions.value.projectName).toBe('G1')
    expect(api.assumptions.value.bookValue).toBe(100)
  })

  it('H2-13 stopped without book => pending', () => {
    const { api } = setup(new Map([
      ['H2-13-rows', {
        item_id: 'H2-13-rows',
        remark: JSON.stringify([
          { rowId: 's1', name: 'Stopped', constructionStatus: STOPPED },
          { rowId: 's2', name: 'Active', constructionStatus: BUILDING },
        ]),
      }],
    ]))
    const cand = api.upstreamCandidates.value.find(c => c.source === 'H2-13' && c.name === 'Stopped')
    expect(cand).toBeTruthy()
    expect(cand!.bookValueReady).toBe(false)
    const res = api.importUpstreamCandidate(cand!.key)
    expect(res.ok).toBe(true)
    expect(api.activeGroup.value.bookValuePending).toBe(true)
    expect(api.assumptions.value.projectName).toBe('Stopped')
  })

  it('corrupt H2-13 => empty candidates', () => {
    const { api } = setup(new Map([
      ['H2-13-rows', { item_id: 'H2-13-rows', remark: '{not-json' }],
    ]))
    expect(() => api.upstreamCandidates.value).not.toThrow()
    expect(api.upstreamCandidates.value.filter(c => c.source === 'H2-13')).toHaveLength(0)
  })

  it('H2-2 fills H2-13 candidate book', () => {
    const list = buildUpstreamCandidates({
      h213Rows: [{ rowId: 's1', name: 'Plant', constructionStatus: STOPPED }],
      h22Rows: [{ rowId: 'd1', name: 'Plant', netValue: 888 }],
    })
    const c = list.find(x => x.name === 'Plant')
    expect(c?.bookValueReady).toBe(true)
    expect(c?.bookValue).toBe(888)
  })

  it('sync then stale after H2-15 edit', () => {
    const { api } = setup()
    api.addCalcRow('PlantX')
    api.updateAssumption('projectName', 'PlantX')
    api.updateAssumption('bookValue', 1000000)
    api.updateFvDisposal({ estimatedPrice: 800000 })
    expect(api.syncToH215().ok).toBe(true)
    expect(api.syncChecks.value.find(c => c.name === 'PlantX')?.status).toBe('synced')
    const row = api.calcRows.value.find(r => r.name === 'PlantX')!
    api.updateCalcCell(row.rowId, 'fairValueNet', 1)
    expect(api.syncChecks.value.find(c => c.name === 'PlantX')?.status).toBe('stale')
  })

  it('batch syncAllGroupsToH215', () => {
    const { api } = setup()
    api.updateAssumption('projectName', 'A')
    api.updateFvDisposal({ estimatedPrice: 10 })
    api.addGroup('B')
    api.updateFvDisposal({ estimatedPrice: 20 })
    const res = api.syncAllGroupsToH215()
    expect(res.ok).toBe(true)
    expect(res.synced).toBeGreaterThanOrEqual(2)
    expect(api.calcRows.value.some(r => r.name === 'A')).toBe(true)
    expect(api.calcRows.value.some(r => r.name === 'B')).toBe(true)
  })
})
