/**
 * G6-2 明细表公式与分类单测
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  enrichG6DetailRow,
  G6_DETAIL_SEGMENTS,
  G6_CATEGORY_LABELS,
  useG6MainDetail,
  type OtherBondDetailRow,
} from '../useG6MainDetail'
import {
  calcPeriodEndComponent,
  calcFvAuditedAmount,
  calcDetailReportAmount,
  calcSubtotal,
} from '@/composables/useG6MainFormulaEngine'
import type { ChecklistResponse } from '../useF1FormData'

function baseRow(partial: Partial<OtherBondDetailRow> = {}): OtherBondDetailRow {
  return {
    id: 'r1',
    seq: 1,
    investCategory: '国债',
    investProject: '测试债',
    securitiesCode: '',
    faceValue: 1000,
    bookQuantity: 0,
    couponRate: 0.03,
    effectiveRate: 0.032,
    maturityDate: '2027-06-30',
    openingCost: 1000,
    openingInterestAdj: -20,
    openingAccruedInterest: 10,
    openingSubtotal: 0,
    openingFairValue: 1050,
    openingPeriodFvChange: 50,
    openingCumulativeFvChange: 50,
    openingAdjustment: -10,
    openingAudited: 0,
    openingNonCurrentDeduct: 100,
    openingReportAmount: 0,
    periodCostChange: 200,
    periodInterestAdjChange: 5,
    periodAccruedInterestChange: 8,
    periodChangeSubtotal: 0,
    closingCost: 0,
    closingInterestAdj: 0,
    closingAccruedInterest: 0,
    closingSubtotal: 0,
    closingFairValue: 1280,
    closingPeriodFvChange: 30,
    closingCumulativeFvChange: 80,
    closingAdjustment: 20,
    closingAudited: 0,
    oneYearBalance: 150,
    closingReportAmount: 0,
    correspondenceStatus: '',
    indexRef: '',
    ...partial,
  }
}

describe('G6-2 公式引擎 P9–P11', () => {
  it('期末分项 = 期初 + 本期变动', () => {
    expect(calcPeriodEndComponent(1000, 200)).toBe(1200)
    expect(calcPeriodEndComponent(-20, 5)).toBe(-15)
  })

  it('审定数 = 公允价值 + 调整数', () => {
    expect(calcFvAuditedAmount(1050, -10)).toBe(1040)
  })

  it('报表数 = 审定数 − 扣减', () => {
    expect(calcDetailReportAmount(1040, 100)).toBe(940)
  })
})

describe('enrichG6DetailRow 对齐 Excel', () => {
  it('完整公式链', () => {
    const r = enrichG6DetailRow(baseRow())
    expect(r.openingSubtotal).toBe(calcSubtotal(1000, -20, 10)) // 990
    expect(r.openingAudited).toBe(1040)
    expect(r.openingReportAmount).toBe(940)
    expect(r.periodChangeSubtotal).toBe(213)
    expect(r.closingCost).toBe(1200)
    expect(r.closingInterestAdj).toBe(-15)
    expect(r.closingAccruedInterest).toBe(18)
    expect(r.closingSubtotal).toBe(1203)
    expect(r.closingAudited).toBe(1300)
    expect(r.closingReportAmount).toBe(1150)
  })
})

describe('G6_DETAIL_SEGMENTS 结构', () => {
  it('4 区段对齐 Excel', () => {
    expect(G6_DETAIL_SEGMENTS.map((s) => s.key)).toEqual([
      'basic', 'opening', 'period', 'closing',
    ])
  })

  it('基础信息含证券代码与持仓数量', () => {
    const basic = G6_DETAIL_SEGMENTS.find((s) => s.key === 'basic')!
    const props = basic.columns.map((c) => c.prop)
    expect(props).toContain('securitiesCode')
    expect(props).toContain('bookQuantity')
  })

  it('分类标题含其他流动资产', () => {
    expect(G6_CATEGORY_LABELS['一年内到期']).toContain('其他流动资产')
    expect(G6_CATEGORY_LABELS['超过一年']).toContain('超过一年')
  })
})

describe('useG6MainDetail 加载保留跨表字段', () => {
  it('migrate 保留 securitiesCode / bookQuantity 别名', () => {
    const map = new Map<string, ChecklistResponse>()
    map.set('G6-2-rows', {
      item_id: 'G6-2-rows',
      conclusion: JSON.stringify([
        {
          id: 'x1',
          investProject: '国开债',
          bondCode: '101001',
          holding_quantity: 120,
          faceValue: 100,
          maturityDate: '2028-01-01',
        },
      ]),
      remark: null,
    })
    map.set('G6-2-balance-sheet-date', {
      item_id: 'G6-2-balance-sheet-date',
      conclusion: '2025-12-31',
      remark: '2025-12-31',
    })
    const d = useG6MainDetail({
      wpId: ref('wp'),
      projectId: ref('p'),
      allResponses: ref(map),
      isReadonly: ref(false),
    })
    d.reload()
    expect(d.rows.value[0].securitiesCode).toBe('101001')
    expect(d.rows.value[0].bookQuantity).toBe(120)
  })
})

describe('useG6MainDetail 分类', () => {
  it('按到期日相对资产负债表日分类', () => {
    const map = new Map<string, ChecklistResponse>()
    map.set('G6-2-rows', {
      item_id: 'G6-2-rows',
      conclusion: JSON.stringify([
        baseRow({ id: 'a', maturityDate: '2026-06-30', investProject: '短债' }),
        baseRow({ id: 'b', maturityDate: '2030-01-01', investProject: '长债' }),
      ]),
      remark: null,
    })
    map.set('G6-2-balance-sheet-date', {
      item_id: 'G6-2-balance-sheet-date',
      conclusion: '2025-12-31',
      remark: '2025-12-31',
    })
    const d = useG6MainDetail({
      wpId: ref('wp'),
      projectId: ref('p'),
      allResponses: ref(map),
      isReadonly: ref(false),
    })
    d.reload()
    const groups = d.categoryGroups.value
    const within = groups.find((g) => g.category === '一年内到期')!
    const over = groups.find((g) => g.category === '超过一年')!
    expect(within.rows.some((r) => r.investProject === '短债')).toBe(true)
    expect(over.rows.some((r) => r.investProject === '长债')).toBe(true)
  })
})
