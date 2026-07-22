import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, computed } from 'vue'

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn() },
}))

import { api as apiProxy } from '@/services/apiProxy'
import { useH3Impairment } from '../useH3Impairment'
import { K11_H3_ITEM_IDS } from '../h3ImpairmentCrossSheet'

function setup(initial: Record<string, any> = {}) {
  const store = new Map<string, any>(Object.entries(initial))
  const allResponses = ref(store)

  const api = useH3Impairment({
    allResponses: computed(() => allResponses.value) as any,
    wpId: ref('wp-h3-test'),
    getValue: (id: string) => store.get(id),
    setValue: (id: string, value: any) => { store.set(id, value) },
    saveImmediate: async () => {},
  })

  return { api, store }
}

function calcRowWithSupplement(supplement: number) {
  return {
    rowId: 'r1',
    assetName: '写字楼',
    category: '房屋、建筑物',
    bookValue: 100000,
    recoverableAmount: 100000 - supplement,
    alreadyProvided: 0,
    hasIndication: 'Y' as const,
  }
}

function mockK11ChecklistApi(checklist: Array<{ item_id: string; remark?: string; conclusion?: string }>, wpId = 'wp-k11-1') {
  vi.mocked(apiProxy.get).mockImplementation(async (url: string) => {
    if (String(url).includes('wp-id-by-code')) {
      return { wp_id: wpId }
    }
    if (String(url).includes('checklist-responses')) {
      return checklist
    }
    return {}
  })
}

describe('useH3Impairment H3-11 recoverable', () => {
  it('recoverableAmount = MAX(fairValueNet, DCF) via legacy keys', () => {
    const { api } = setup({
      'H3-11-fv-disposal': {
        assetName: '测试物业',
        activeMarketPrice: 5000000,
        legalFees: 100000,
      },
      'H3-11-dcf-assumptions': {
        discountRate: 10,
        forecastYears: 5,
        terminalGrowth: 2,
        annualRent: 600000,
        annualCost: 100000,
        usePreTaxRate: true,
      },
    })

    expect(api.fairValueLessDisposal.value).toBe(4900000)
    expect(api.dcfResult.value.totalPV).toBeGreaterThan(0)
    expect(api.recoverableAmount.value).toBe(
      Math.max(api.fairValueLessDisposal.value, api.dcfResult.value.totalPV),
    )
  })

  it('uses DCF when fair value net is zero', () => {
    const { api } = setup({
      'H3-11-dcf-assumptions': {
        discountRate: 10,
        forecastYears: 5,
        terminalGrowth: 2,
        annualRent: 500000,
        annualCost: 50000,
      },
    })
    expect(api.fairValueLessDisposal.value).toBe(0)
    expect(api.recoverableAmount.value).toBe(api.dcfResult.value.totalPV)
    expect(api.recoverableSource.value).toBe('预计未来现金流量现值(DCF)')
  })

  it('pushRecoverableToH10 writes to calc rows', () => {
    const { api, store } = setup({
      'H3-11-fv-disposal': { assetName: 'A座', activeMarketPrice: 2000000 },
      'H3-11-dcf-assumptions': {
        discountRate: 10,
        forecastYears: 3,
        terminalGrowth: 1,
        annualRent: 100000,
        annualCost: 20000,
      },
      'H3-10-calc-rows': [{
        rowId: 'r1',
        assetName: 'A座',
        bookValue: 2500000,
        recoverableAmount: 0,
      }],
    })

    const result = api.pushRecoverableToH10()
    expect(result.ok).toBe(true)
    const rows = store.get('H3-10-calc-rows') as any[]
    expect(rows[0].recoverableAmount).toBe(api.recoverableAmount.value)
    expect(rows[0].impairmentAmount).toBe(Math.max(2500000 - api.recoverableAmount.value, 0))
    expect(rows[0].fairValueLessDisposal).toBe(api.fairValueLessDisposal.value)
    expect(rows[0].dcfValue).toBe(api.dcfResult.value.totalPV)
  })

  it('default calc rows seed three IP categories', () => {
    const { api } = setup()
    expect(api.calcRows.value.length).toBe(3)
    expect(api.calcRows.value.map((r) => r.category)).toEqual([
      '房屋、建筑物',
      '土地使用权',
      '在建工程',
    ])
  })

  it('forceSyncFromH11 writes ③④ to matching row', () => {
    const { api, store } = setup({
      'H3-11-groups': [{
        groupId: 'g1',
        name: 'A座',
        bookValue: 2500000,
        dcfAssumptions: { discountRate: 10, forecastYears: 3, terminalGrowth: 1, annualRent: 100000, annualCost: 20000, usePreTaxRate: true },
        waccParams: { taxRate: 25, totalDebt: 0, totalEquity: 0, costOfDebt: 5, riskFreeRate: 2.5, beta: 1, marketReturn: 10 },
        fvDisposal: { assetName: 'A座', activeMarketPrice: 2000000, legalFees: 0, relatedTaxes: 0, transportCosts: 0, directCosts: 0, otherCosts: 0 },
      }],
      'H3-11-active-group': 'g1',
      'H3-10-calc-rows': [{
        rowId: 'r1',
        assetName: 'A座',
        category: '房屋、建筑物',
        bookValue: 2500000,
        hasIndication: 'Y',
      }],
    })

    const result = api.forceSyncFromH11()
    expect(result.updated).toBe(1)
    const rows = store.get('H3-10-calc-rows') as any[]
    expect(rows[0].dcfValue).toBeGreaterThan(0)
    expect(rows[0].fairValueLessDisposal).toBe(2000000)
    expect(rows[0].recoverableAmount).toBeGreaterThan(0)
  })

  it('WACC drives effective discount rate when D/E provided', () => {
    const { api } = setup({
      'H3-11-wacc-params': {
        taxRate: 25,
        totalDebt: 4000000,
        totalEquity: 6000000,
        costOfDebt: 5,
        riskFreeRate: 2.5,
        beta: 1.2,
        marketReturn: 10,
      },
      'H3-11-dcf-assumptions': {
        discountRate: 8,
        forecastYears: 5,
        terminalGrowth: 2,
        annualRent: 300000,
        annualCost: 50000,
        usePreTaxRate: true,
      },
    })

    expect(api.waccAfterTax.value).toBeGreaterThan(0)
    expect(api.effectiveDiscountRate.value).toBe(api.preTaxDiscountRate.value)
    expect(api.effectiveDiscountRate.value).not.toBe(8)
  })

  it('sensitivity matrix uses recoverable amount not DCF only', () => {
    const { api } = setup({
      'H3-11-fv-disposal': { estimatedPrice: 3000000 },
      'H3-11-dcf-assumptions': {
        discountRate: 10,
        forecastYears: 5,
        terminalGrowth: 2,
        annualRent: 100000,
        annualCost: 80000,
      },
    })
    const baseCol = api.sensitivityCols.value[1]
    const baseRow = api.sensitivityRows.value[1]
    expect(baseRow[baseCol]).toBe(api.recoverableAmount.value)
  })

  it('multi-group: add and switch groups independently', () => {
    const { api } = setup()
    api.addRecoverableGroup('A座')
    api.addRecoverableGroup('B座')
    expect(api.groups.value.length).toBe(3)

    const bId = api.groups.value.find((g) => g.name === 'B座')!.groupId
    api.setActiveGroup(bId)
    api.activeGroup.value.fvDisposal.activeMarketPrice = 8888888
    api.updateFvDisposal()

    const aId = api.groups.value.find((g) => g.name === 'A座')!.groupId
    api.setActiveGroup(aId)
    expect(api.fvDisposal.value.activeMarketPrice).toBe(0)

    api.setActiveGroup(bId)
    expect(api.fvDisposal.value.activeMarketPrice).toBe(8888888)
  })

  it('importFairValueFromH38 fills active group', () => {
    const { api } = setup({
      'H3-8-calc-rows': [{
        rowId: 'fv1',
        assetName: '写字楼A',
        appraisalValue: 12000000,
        marketRef: 11500000,
        bookValue: 13000000,
        discountRate: 9,
        rentAssumption: 50000,
      }],
    })
    api.activeGroup.value.name = '写字楼A'
    const result = api.importFairValueFromH38('fv1')
    expect(result.ok).toBe(true)
    expect(api.fvDisposal.value.activeMarketPrice).toBe(12000000)
    expect(api.fvDisposal.value.estimatedPrice).toBe(11500000)
    expect(api.assumptions.value.annualRent).toBe(600000)
    expect(api.bookValue.value).toBe(13000000)
  })

  it('importRentalFromH14 fills annual rent', () => {
    const { api } = setup({
      'H3-14-contract-rows': [{
        rowId: 'rent1',
        assetName: '商铺B',
        expectedRent: 480000,
        monthlyRent: 40000,
      }],
    })
    api.activeGroup.value.name = '商铺B'
    const result = api.importRentalFromH14('rent1')
    expect(result.ok).toBe(true)
    expect(api.assumptions.value.annualRent).toBe(480000)
  })

  it('terminal sensitivity axis returns 5 points per axis', () => {
    const { api } = setup({
      'H3-11-dcf-assumptions': {
        discountRate: 10,
        forecastYears: 5,
        terminalGrowth: 2,
        annualRent: 200000,
        annualCost: 50000,
      },
    })
    expect(api.terminalSensitivityByRate.value.length).toBe(5)
    expect(api.terminalSensitivityByGrowth.value.length).toBe(5)
    const mid = api.terminalSensitivityByRate.value[2]
    expect(mid.invalid).toBe(false)
    expect(mid.terminalValueDiscounted).toBeGreaterThan(0)
  })

  it('importBookValuesFromH32 maps H3-2 rows to calc table', () => {
    const { api, store } = setup({
      'H3-2-cost-rows': [{
        rowId: 'dc1',
        assetName: '写字楼A',
        assetType: '房屋',
        costEnd: 3000000,
        accDepEnd: 500000,
        impairmentEnd: 80000,
      }],
      'H3-10-calc-rows': [{
        rowId: 'r1',
        assetName: '写字楼A',
        category: '房屋、建筑物',
      }],
    })
    const result = api.importBookValuesFromH32()
    expect(result.updated).toBe(1)
    const rows = store.get('H3-10-calc-rows') as any[]
    expect(rows[0].bookValue).toBe(2500000)
    expect(rows[0].alreadyProvided).toBe(80000)
  })

  it('importFromStocktakeConcerns applies H3-9 payload', () => {
    const { api } = setup({
      'H3-10-stocktake-concerns': {
        items: [{
          source: 'H3-9',
          assetName: '空置商铺',
          reason: '空置',
          bookValue: 1200000,
          suggest: 'impairment',
          checkRowId: 'st1',
        }],
      },
      'H3-10-calc-rows': [{
        rowId: 'r1',
        assetName: '其他物业',
        category: '房屋、建筑物',
      }],
    })
    const result = api.importFromStocktakeConcerns()
    expect(result.added).toBe(1)
    const row = api.calcRows.value.find((r) => r.assetName === '空置商铺')
    expect(row?.hasIndication).toBe('Y')
    expect(row?.bookValue).toBe(1200000)
  })

  it('pushAllGroupsToH10 writes all groups', () => {
    const { api, store } = setup({
      'H3-11-groups': [
        {
          groupId: 'g1', name: 'A', bookValue: 1000,
          dcfAssumptions: { discountRate: 10, forecastYears: 3, terminalGrowth: 1, annualRent: 0, annualCost: 0, residualValue: 0, usePreTaxRate: true },
          waccParams: { taxRate: 25, totalDebt: 0, totalEquity: 0, costOfDebt: 5, riskFreeRate: 2.5, beta: 1, marketReturn: 10 },
          fvDisposal: { assetName: 'A', activeMarketPrice: 800, legalFees: 0, relatedTaxes: 0, transportCosts: 0, directCosts: 0, otherCosts: 0 },
        },
        {
          groupId: 'g2', name: 'B', bookValue: 2000,
          dcfAssumptions: { discountRate: 10, forecastYears: 3, terminalGrowth: 1, annualRent: 0, annualCost: 0, residualValue: 0, usePreTaxRate: true },
          waccParams: { taxRate: 25, totalDebt: 0, totalEquity: 0, costOfDebt: 5, riskFreeRate: 2.5, beta: 1, marketReturn: 10 },
          fvDisposal: { assetName: 'B', activeMarketPrice: 1500, legalFees: 0, relatedTaxes: 0, transportCosts: 0, directCosts: 0, otherCosts: 0 },
        },
      ],
      'H3-11-active-group': 'g1',
    })
    const result = api.pushAllGroupsToH10()
    expect(result.ok).toBe(true)
    expect(result.count).toBe(2)
    const rows = store.get('H3-10-calc-rows') as any[]
    expect(rows.length).toBe(2)
  })
})

describe('useH3Impairment reconcileWithK11', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('matches K11-2-investment-property-occurrence against H3-10 supplement', async () => {
    const { api } = setup({
      'H3-10-calc-rows': [calcRowWithSupplement(50000)],
    })
    mockK11ChecklistApi([
      { item_id: K11_H3_ITEM_IDS.occurrence, remark: '50000' },
      { item_id: K11_H3_ITEM_IDS.sourceWpAmount, remark: '99999' },
    ])

    const result = await api.reconcileWithK11('proj-1')

    expect(result.isMatch).toBe(true)
    expect(result.h10Supplement).toBe(50000)
    expect(result.k11Amount).toBe(50000)
    expect(result.diff).toBeCloseTo(0)
    expect(result.source).toBe(K11_H3_ITEM_IDS.occurrence)
    expect(api.k11Reconcile.value.isMatch).toBe(true)
  })

  it('reports diff when K11 occurrence differs from supplement', async () => {
    const { api } = setup({
      'H3-10-calc-rows': [calcRowWithSupplement(50000)],
    })
    mockK11ChecklistApi([
      { item_id: K11_H3_ITEM_IDS.occurrence, remark: '45000' },
    ])

    const result = await api.reconcileWithK11('proj-1')

    expect(result.isMatch).toBe(false)
    expect(result.diff).toBeCloseTo(5000)
    expect(result.message).toContain('勾稽差异')
  })

  it('falls back to K11-source-H3-amount when occurrence key missing', async () => {
    const { api } = setup({
      'H3-10-calc-rows': [calcRowWithSupplement(12000)],
    })
    mockK11ChecklistApi([
      { item_id: K11_H3_ITEM_IDS.sourceWpAmount, remark: '12000' },
    ])

    const result = await api.reconcileWithK11('proj-1')

    expect(result.isMatch).toBe(true)
    expect(result.k11Amount).toBe(12000)
    expect(result.source).toBe(K11_H3_ITEM_IDS.sourceWpAmount)
  })

  it('falls back to K11-2-detail-rows JSON for H3 lines', async () => {
    const { api } = setup({
      'H3-10-calc-rows': [calcRowWithSupplement(8000)],
    })
    mockK11ChecklistApi([
      {
        item_id: K11_H3_ITEM_IDS.detailRows,
        remark: JSON.stringify([
          { assetCategory: '投资性房地产减值准备', sourceWp: 'H3', currentOccurrence: 3000 },
          { assetCategory: '其他', sourceWp: 'F2', currentOccurrence: 1000 },
          { assetCategory: '投资性房地产减值损失', sourceWp: 'H3', currentProvision: 5000 },
        ]),
      },
    ])

    const result = await api.reconcileWithK11('proj-1')

    expect(result.isMatch).toBe(true)
    expect(result.k11Amount).toBe(8000)
    expect(result.source).toBe('K11-2 明细(投资性房地产行)')
  })

  it('returns message when projectId missing', async () => {
    const { api } = setup({
      'H3-10-calc-rows': [calcRowWithSupplement(1000)],
    })

    const result = await api.reconcileWithK11('')

    expect(result.k11Amount).toBeNull()
    expect(result.message).toContain('缺少 projectId')
  })

  it('returns message when K11 workpaper not found', async () => {
    const { api } = setup({
      'H3-10-calc-rows': [calcRowWithSupplement(1000)],
    })
    vi.mocked(apiProxy.get).mockResolvedValue({ wp_id: null })

    const result = await api.reconcileWithK11('proj-1')

    expect(result.k11Amount).toBeNull()
    expect(result.message).toContain('未找到 K11')
  })
})
