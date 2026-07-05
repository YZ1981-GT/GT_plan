/**
 * useG2Adjudication 单元测试 — G2-1 审定表（借方科目 1132 应收利息）
 *
 * Spec: .kiro/specs/g2-interest-receivable/ Task 4.2
 * 验证：借方余额公式方向、合计行汇总、差异=审定-试算表数
 * Requirements: 3.3~3.7
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useG2Adjudication } from '../useG2Adjudication'
import type { ChecklistResponse } from '../useF1FormData'

function setup(seed?: Record<string, string>) {
  const map = new Map<string, ChecklistResponse>()
  if (seed) {
    for (const [k, v] of Object.entries(seed)) {
      map.set(k, { item_id: k, conclusion: null, remark: v })
    }
  }
  const allResponses = ref(map)
  const adj = useG2Adjudication({
    wpId: ref('wp-1'),
    projectId: ref('proj-1'),
    allResponses,
    isReadonly: ref(false),
  })
  return { adj, allResponses }
}

describe('useG2Adjudication — 借方科目审定公式', () => {
  it('期末未审 = 期初审定 + 借方 - 贷方（借方科目方向）', () => {
    const rows = JSON.stringify([
      {
        rowKey: 'bond-interest',
        label: '债权投资利息',
        openingUnadjusted: 1000,
        openingAJE: 100,
        openingRJE: -50,
        periodDebit: 500,
        periodCredit: 200,
        closingAJE: 0,
        closingRJE: 0,
        indexRef: '',
      },
    ])
    const { adj } = setup({ 'G2-1-adj-rows': rows })
    const row = adj.dataRows.value[0]
    // 期初审定 = 1000 + 100 + (-50) = 1050
    expect(row.openingAdjusted).toBe(1050)
    // 期末未审 = 期初审定(1050) + 借方(500) - 贷方(200) = 1350
    expect(row.closingUnadjusted).toBe(1350)
    // 期末审定 = 未审(1350) + AJE(0) + RJE(0) = 1350
    expect(row.closingAdjusted).toBe(1350)
  })

  it('期末审定 = 期末未审 + AJE + RJE', () => {
    const rows = JSON.stringify([
      {
        rowKey: 'deposit-interest',
        label: '定期存款利息',
        openingUnadjusted: 2000,
        openingAJE: 0,
        openingRJE: 0,
        periodDebit: 300,
        periodCredit: 100,
        closingAJE: 50,
        closingRJE: -20,
        indexRef: '',
      },
    ])
    const { adj } = setup({ 'G2-1-adj-rows': rows })
    const row = adj.dataRows.value[0]
    // 期初审定 = 2000
    // 期末未审 = 2000 + 300 - 100 = 2200
    expect(row.closingUnadjusted).toBe(2200)
    // 期末审定 = 2200 + 50 + (-20) = 2230
    expect(row.closingAdjusted).toBe(2230)
  })

  it('合计行汇总所有数据行', () => {
    const rows = JSON.stringify([
      {
        rowKey: 'bond-interest',
        label: '债权投资利息',
        openingUnadjusted: 1000,
        openingAJE: 0,
        openingRJE: 0,
        periodDebit: 200,
        periodCredit: 0,
        closingAJE: 0,
        closingRJE: 0,
        indexRef: '',
      },
      {
        rowKey: 'deposit-interest',
        label: '定期存款利息',
        openingUnadjusted: 500,
        openingAJE: 0,
        openingRJE: 0,
        periodDebit: 100,
        periodCredit: 50,
        closingAJE: 0,
        closingRJE: 0,
        indexRef: '',
      },
    ])
    const { adj } = setup({ 'G2-1-adj-rows': rows })
    const total = adj.subtotalRow.value
    // 期初审定合计 = 1000 + 500 = 1500
    expect(total.openingAdjusted).toBe(1500)
    // 期末未审合计：row1= 1000+200-0=1200, row2= 500+100-50=550, total=1750
    expect(total.closingUnadjusted).toBe(1750)
    // 期末审定 = 1750 (no AJE/RJE)
    expect(total.closingAdjusted).toBe(1750)
  })

  it('差异 = 审定合计 - 试算表数', () => {
    const rows = JSON.stringify([
      {
        rowKey: 'bond-interest',
        label: '债权投资利息',
        openingUnadjusted: 1000,
        openingAJE: 0,
        openingRJE: 0,
        periodDebit: 500,
        periodCredit: 0,
        closingAJE: 0,
        closingRJE: 0,
        indexRef: '',
      },
    ])
    // 期末审定 = 1000 + 500 - 0 = 1500; 试算表数 = 1400; 差异 = 100
    const { adj } = setup({ 'G2-1-adj-rows': rows, 'G2-1-adj-tb-1132': '1400' })
    expect(adj.trialBalanceAmount.value).toBe(1400)
    expect(adj.subtotalRow.value.closingAdjusted).toBe(1500)
    expect(adj.variance.value).toBe(100)
    expect(adj.hasVarianceHighlight.value).toBe(true)
  })

  it('差异=0时无红色标记', () => {
    const rows = JSON.stringify([
      {
        rowKey: 'bond-interest',
        label: '债权投资利息',
        openingUnadjusted: 800,
        openingAJE: 0,
        openingRJE: 0,
        periodDebit: 200,
        periodCredit: 0,
        closingAJE: 0,
        closingRJE: 0,
        indexRef: '',
      },
    ])
    // 期末审定 = 800 + 200 = 1000; 试算表数 = 1000
    const { adj } = setup({ 'G2-1-adj-rows': rows, 'G2-1-adj-tb-1132': '1000' })
    expect(adj.variance.value).toBe(0)
    expect(adj.hasVarianceHighlight.value).toBe(false)
  })

  it('默认行结构包含4个项目', () => {
    const { adj } = setup()
    expect(adj.dataRows.value.length).toBe(4)
    expect(adj.dataRows.value[0].item).toBe('债权投资利息')
    expect(adj.dataRows.value[1].item).toBe('其他债权投资利息')
    expect(adj.dataRows.value[2].item).toBe('定期存款利息')
    expect(adj.dataRows.value[3].item).toBe('其他')
  })
})
