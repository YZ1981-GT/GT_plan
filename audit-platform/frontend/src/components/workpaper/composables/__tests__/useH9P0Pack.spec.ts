/**

 * H9 P0：AJE 回写、IBR 归一、IE sheet 归一

 */

import { describe, it, expect } from 'vitest'

import { ref } from 'vue'

import { useH9Adjudication } from '../useH9Adjudication'

import { normalizeIbrRate } from '../useH9Amortization'

import { normalizeH9ImportSheet } from '../useH9ImportExport'

import { useH9Amortization } from '../useH9Amortization'



function makeMap(entries: Record<string, unknown>) {

  const m = new Map<string, any>()

  for (const [k, v] of Object.entries(entries)) {

    m.set(k, { item_id: k, remark: typeof v === 'string' ? v : JSON.stringify(v) })

  }

  return m

}



describe('normalizeIbrRate', () => {

  it('百分数 >1 转为小数', () => {

    expect(normalizeIbrRate(5.5)).toBeCloseTo(0.055)

    expect(normalizeIbrRate(100)).toBeCloseTo(1)

  })



  it('已是小数则保持', () => {

    expect(normalizeIbrRate(0.055)).toBeCloseTo(0.055)

    expect(normalizeIbrRate(0)).toBe(0)

  })

})



describe('normalizeH9ImportSheet', () => {

  it('H9-5 历史别名 → H9-4', () => {

    expect(normalizeH9ImportSheet('H9-5')).toBe('H9-4')

    expect(normalizeH9ImportSheet('H9-2')).toBe('H9-2')

  })

})



describe('useH9Adjudication — syncAjeRjeFromAdjustment', () => {

  it('按科目名从 H9-4 回写负债贷−借、融资费用借−贷', () => {

    const saved: Record<string, any> = {}

    const allResponses = ref(makeMap({

      'H9-1-rows': [{

        rowId: 'L1', name: '租赁负债合计', block: 'liability',

        beginBalance: 1000, creditAmount: 50, debitAmount: 200,

        unadjusted: 850, aje: 0, rje: 0, reclassification: 0,

      }, {

        rowId: 'U1', name: '未确认融资费用合计', block: 'unearned',

        beginBalance: 100, creditAmount: 30, debitAmount: 20,

        unadjusted: 90, aje: 0, rje: 0, reclassification: 0,

      }],

      'H9-4-rows': [

        { category: 'AJE', accountName: '租赁负债', debitAmount: 0, creditAmount: 100 },

        { category: 'AJE', accountName: '使用权资产', debitAmount: 100, creditAmount: 0 },

        { category: 'RJE', accountName: '未确认融资费用', debitAmount: 20, creditAmount: 0 },

        { category: 'RJE', accountName: '一年内到期的非流动负债', debitAmount: 0, creditAmount: 20 },

      ],

    }))



    const api = useH9Adjudication({

      wpId: ref('wp'),

      projectId: ref('p'),

      allResponses,

      onSave: (id, v) => { saved[id] = v },

    })



    const res = api.syncAjeRjeFromAdjustment(0, 0)

    expect(res.applied).toBe(true)

    expect(api.liabilityRows.value[0].aje).toBe(100) // credit − debit

    expect(api.liabilityRows.value[0].rje).toBe(0)

    expect(api.unearnedRows.value[0].rje).toBe(20) // debit − credit

  })



  it('无科目命中时使用事件净额落到 liability', () => {

    const allResponses = ref(makeMap({

      'H9-1-rows': [{

        rowId: 'L1', name: '租赁负债合计', block: 'liability',

        beginBalance: 0, creditAmount: 0, debitAmount: 0,

        unadjusted: 100, aje: 0, rje: 0,

      }],

      'H9-4-rows': [

        { category: 'AJE', accountName: '其他', debitAmount: 50, creditAmount: 50 },

      ],

    }))

    const api = useH9Adjudication({

      wpId: ref('wp'), projectId: ref('p'), allResponses,

      onSave: () => {},

    })

    const res = api.syncAjeRjeFromAdjustment(12, 3)

    expect(res.applied).toBe(true)

    expect(api.liabilityRows.value[0].aje).toBe(12)

    expect(api.liabilityRows.value[0].rje).toBe(3)

  })

})



describe('useH9Amortization — 本期利息口径 + IBR', () => {

  it('5.5% IBR 按小数计息，并落库本期/全期利息键', () => {

    const saved: Record<string, any> = {}

    const allResponses = ref(makeMap({

      'H9-2-rows': [{

        contractNo: 'C-1',

        lessor: '甲',

        beginBalance: 120000,

        ibrRate: 5.5, // 百分数

        leaseTerm: 24,

        repayment: 12000, // 年付款 → 月 1000

      }],

    }))



    const api = useH9Amortization({

      wpId: ref('wp'),

      projectId: ref('p'),

      allResponses,

      onSave: (id, v) => { saved[id] = v },

    })



    expect(api.selectedContract.value?.ibrRate).toBeCloseTo(0.055)

    expect(api.schedule.value.length).toBe(24)

    // 首期利息 = 120000 * (0.055/12)

    expect(api.schedule.value[0].interest).toBeCloseTo(120000 * (0.055 / 12), 5)

    expect(api.validation.value.currentPeriodInterest).toBeGreaterThan(0)

    expect(api.validation.value.currentPeriodInterest)

      .toBeLessThan(api.validation.value.totalInterest)



    api.save()

    expect(saved['H9-amort-total-interest']).toBe(api.validation.value.totalInterest)

    expect(saved['H9-amort-current-interest']).toBe(api.validation.value.currentPeriodInterest)

  })

})


