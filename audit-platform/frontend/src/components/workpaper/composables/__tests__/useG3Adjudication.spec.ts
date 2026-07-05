/**
 * useG3Adjudication 单元测试 — G3-1 审定表（借方科目 1131 应收股利）
 *
 * Spec: .kiro/specs/g3-dividend-receivable/ Task 4.2
 * 验证：借方余额公式方向、合计行汇总、差异=审定-试算表数
 * Requirements: 3.3~3.7
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useG3Adjudication } from '../useG3Adjudication'
import type { ChecklistResponse } from '../useF1FormData'

function setup(seed?: Record<string, string>) {
  const map = new Map<string, ChecklistResponse>()
  if (seed) {
    for (const [k, v] of Object.entries(seed)) {
      map.set(k, { item_id: k, conclusion: null, remark: v })
    }
  }
  const allResponses = ref(map)
  const adj = useG3Adjudication({
    wpId: ref('wp-1'),
    projectId: ref('proj-1'),
    allResponses,
    isReadonly: ref(false),
  })
  return { adj, allResponses }
}

describe('useG3Adjudication — 借方科目审定公式', () => {
  it('期末未审 = 期初审定 + 本期宣告 - 本期收回（借方科目方向）', () => {
    const rows = JSON.stringify([
      {
        id: 'inv-1',
        investeeName: '甲公司',
        shareholdingRatio: 20,
        openingUnadjusted: 1000,
        openingAJE: 100,
        openingRJE: -50,
        currentDeclared: 500,
        currentReceived: 200,
        closingAJE: 0,
        closingRJE: 0,
        remark: '',
        indexRef: '',
      },
    ])
    const { adj } = setup({ 'G3-1-adj-rows': rows })
    const row = adj.dataRows.value[0]
    // 期初审定 = 1000 + 100 + (-50) = 1050
    expect(row.openingAdjusted).toBe(1050)
    // 期末未审 = 期初审定(1050) + 宣告(500) - 收回(200) = 1350
    expect(row.closingUnadjusted).toBe(1350)
    // 期末审定 = 未审(1350) + AJE(0) + RJE(0) = 1350
    expect(row.closingAdjusted).toBe(1350)
  })

  it('期末审定 = 期末未审 + AJE + RJE', () => {
    const rows = JSON.stringify([
      {
        id: 'inv-2',
        investeeName: '乙公司',
        shareholdingRatio: 30,
        openingUnadjusted: 2000,
        openingAJE: 0,
        openingRJE: 0,
        currentDeclared: 300,
        currentReceived: 100,
        closingAJE: 50,
        closingRJE: -20,
        remark: '',
        indexRef: '',
      },
    ])
    const { adj } = setup({ 'G3-1-adj-rows': rows })
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
        id: 'inv-1',
        investeeName: '甲公司',
        shareholdingRatio: 20,
        openingUnadjusted: 1000,
        openingAJE: 0,
        openingRJE: 0,
        currentDeclared: 200,
        currentReceived: 0,
        closingAJE: 0,
        closingRJE: 0,
        remark: '',
        indexRef: '',
      },
      {
        id: 'inv-2',
        investeeName: '乙公司',
        shareholdingRatio: 30,
        openingUnadjusted: 500,
        openingAJE: 0,
        openingRJE: 0,
        currentDeclared: 100,
        currentReceived: 50,
        closingAJE: 0,
        closingRJE: 0,
        remark: '',
        indexRef: '',
      },
    ])
    const { adj } = setup({ 'G3-1-adj-rows': rows })
    const total = adj.subtotalRow.value
    // 期初未审合计 = 1000 + 500 = 1500
    expect(total.openingUnadjusted).toBe(1500)
    // 期初审定合计 = 1000 + 500 = 1500
    expect(total.openingAdjusted).toBe(1500)
    // 宣告合计 = 200 + 100 = 300
    expect(total.currentDeclared).toBe(300)
    // 收回合计 = 0 + 50 = 50
    expect(total.currentReceived).toBe(50)
    // 期末未审合计：row1= 1000+200-0=1200, row2= 500+100-50=550, total=1750
    expect(total.closingUnadjusted).toBe(1750)
    // 期末审定 = 1750 (no AJE/RJE)
    expect(total.closingAdjusted).toBe(1750)
  })

  it('差异 = 审定合计 - 试算表数', () => {
    const rows = JSON.stringify([
      {
        id: 'inv-1',
        investeeName: '甲公司',
        shareholdingRatio: 20,
        openingUnadjusted: 1000,
        openingAJE: 0,
        openingRJE: 0,
        currentDeclared: 500,
        currentReceived: 0,
        closingAJE: 0,
        closingRJE: 0,
        remark: '',
        indexRef: '',
      },
    ])
    // 期末审定 = 1000 + 500 - 0 = 1500; 试算表数 = 1400; 差异 = 100
    const { adj } = setup({ 'G3-1-adj-rows': rows, 'G3-1-adj-tb-1131': '1400' })
    expect(adj.trialBalanceAmount.value).toBe(1400)
    expect(adj.subtotalRow.value.closingAdjusted).toBe(1500)
    expect(adj.variance.value).toBe(100)
    expect(adj.hasVarianceHighlight.value).toBe(true)
  })

  it('差异=0时无红色标记', () => {
    const rows = JSON.stringify([
      {
        id: 'inv-1',
        investeeName: '甲公司',
        shareholdingRatio: 20,
        openingUnadjusted: 800,
        openingAJE: 0,
        openingRJE: 0,
        currentDeclared: 200,
        currentReceived: 0,
        closingAJE: 0,
        closingRJE: 0,
        remark: '',
        indexRef: '',
      },
    ])
    // 期末审定 = 800 + 200 = 1000; 试算表数 = 1000
    const { adj } = setup({ 'G3-1-adj-rows': rows, 'G3-1-adj-tb-1131': '1000' })
    expect(adj.variance.value).toBe(0)
    expect(adj.hasVarianceHighlight.value).toBe(false)
  })
})
