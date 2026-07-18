import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import {
  calcF4PayableTurnover,
  calcF4PaymentDays,
  calcF4Purchases,
  extractF4TopCreditors,
  useF4SubstantiveAnalysis,
} from '../composables/useF4SubstantiveAnalysis'
import type { ChecklistResponse } from '../composables/useF4FormData'

function responseMap(entries: Array<[string, unknown]>) {
  return ref(new Map<string, ChecklistResponse>(
    entries.map(([key, value]) => [key, {
      item_id: key,
      conclusion: null,
      remark: typeof value === 'string' ? value : JSON.stringify(value),
    }]),
  ))
}

describe('F4-4 付款期分析公式', () => {
  it('采购成本=主营业务成本+期末存货-期初存货', () => {
    expect(calcF4Purchases(1000, 100, 250)).toBe(1150)
  })

  it('周转率=采购成本/平均应付账款，支付天数=365/周转率', () => {
    const turnover = calcF4PayableTurnover(1000, 100, 250, 800, 1200)
    expect(turnover).toBe(1.15)
    expect(calcF4PaymentDays(turnover)).toBeCloseTo(317.3913, 4)
  })

  it('平均应付账款或周转率为0时返回null而非除零', () => {
    expect(calcF4PayableTurnover(1000, 0, 0, 100, -100)).toBeNull()
    expect(calcF4PaymentDays(0)).toBeNull()
    expect(calcF4PaymentDays(null)).toBeNull()
  })
})

describe('F4-4 前十名债权人动态取数', () => {
  const detailRows = [
    {
      rowId: 'a1', creditor: '甲公司', paymentNature: '货款',
      openingUnadjusted: 100, currentCredit: 50,
    },
    {
      rowId: 'a2', creditor: '甲公司', paymentNature: '服务费',
      openingUnadjusted: 50, currentCredit: 25,
    },
    {
      rowId: 'b1', creditor: '乙公司', paymentNature: '工程款',
      openingUnadjusted: 0, currentCredit: 300,
    },
    {
      rowId: 'c1', creditor: '丙公司', paymentNature: '设备款',
      openingUnadjusted: 500, currentDebit: 500,
    },
    { rowId: 'blank', creditor: '', openingUnadjusted: 999 },
  ]

  it('按实际名称归集重复债权人并按期末余额降序，不生成占位行', () => {
    const rows = extractF4TopCreditors(JSON.stringify(detailRows))
    expect(rows.map((row) => row.creditor)).toEqual(['乙公司', '甲公司', '丙公司'])
    expect(rows[0]).toMatchObject({
      creditor: '乙公司',
      currentBalance: 300,
      priorBalance: 0,
      changeRate: 'N/A',
      sourcePaymentNature: '工程款',
    })
    expect(rows[1].currentBalance).toBe(225)
    expect(rows[1].priorBalance).toBe(150)
    expect(rows[1].sourcePaymentNature).toBe('货款、服务费')
    expect(rows.every((row) => !/^债权人\\d+$/.test(row.creditor))).toBe(true)
  })

  it('实际超过10名时只取期末审定数最大的10名', () => {
    const rows = Array.from({ length: 12 }, (_, index) => ({
      rowId: `r${index}`,
      creditor: `供应商${index + 1}`,
      openingUnadjusted: index + 1,
    }))
    const top = extractF4TopCreditors(JSON.stringify(rows))
    expect(top).toHaveLength(10)
    expect(top[0].creditor).toBe('供应商12')
    expect(top.some((row) => row.creditor === '供应商1')).toBe(false)
  })
})

describe('useF4SubstantiveAnalysis — F4-1/F4-2联动', () => {
  it('本期期初期末应付账款联动审定数据，手工输入成本存货后自动计算', () => {
    const allResponses = responseMap([
      ['F4-1-adj-nature-rows', [{
        rowKey: 'goods',
        label: '货款',
        isFixed: true,
        openingUnadjusted: 1000,
      }]],
      ['F4-2-rows', [{
        rowId: 'd1',
        creditor: '甲供应商',
        paymentNature: '货款',
        openingUnadjusted: 1000,
        currentCredit: 200,
      }]],
    ])
    const composable = useF4SubstantiveAnalysis({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      isReadonly: ref(false),
    })

    composable.updateTurnoverInput('currentOperatingCost', 1000)
    composable.updateTurnoverInput('currentOpeningInventory', 100)
    composable.updateTurnoverInput('currentClosingInventory', 200)

    const byKey = new Map(composable.turnoverRows.value.map((row) => [row.rowKey, row]))
    expect(byKey.get('openingPayable')?.currentAmount).toBe(1000)
    expect(byKey.get('closingPayable')?.currentAmount).toBe(1200)
    expect(byKey.get('turnoverRate')?.currentAmount).toBe(1)
    expect(byKey.get('paymentDays')?.currentAmount).toBe(365)

    expect(composable.topCreditors.value).toHaveLength(1)
    expect(composable.topCreditors.value[0].creditor).toBe('甲供应商')
  })

  it('发生原因默认取F4-2款项性质，用户补充后优先显示补充内容', () => {
    const allResponses = responseMap([
      ['F4-2-rows', [{
        rowId: 'd1',
        creditor: '甲供应商',
        paymentNature: '货款',
        openingUnadjusted: 100,
      }]],
    ])
    const composable = useF4SubstantiveAnalysis({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      isReadonly: ref(false),
    })
    const row = composable.topCreditors.value[0]
    expect(row.reason).toBe('货款')
    composable.updateCreditorReason(row.rowId, '原材料采购增长，结算期尚未届满')
    expect(composable.topCreditors.value[0].reason).toBe('原材料采购增长，结算期尚未届满')
  })
})
