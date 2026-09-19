/**
 * useF3CrossSheet — F3-2→F3-1 现代字段映射回归
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  useF3CrossSheet,
  rowPeriodCredit,
  rowPeriodDebit,
  rowClosingAdjusted,
} from '../useF3CrossSheet'
import type { ChecklistResponse, ProjectContext } from '../useF3FormData'

describe('row helpers', () => {
  it('优先现代字段 currentIssued / currentAccepted', () => {
    expect(rowPeriodCredit({ currentIssued: 100, increase: 9 })).toBe(100)
    expect(rowPeriodDebit({ currentAccepted: 40, decrease: 1 })).toBe(40)
  })

  it('无现代字段时回退 increase / decrease', () => {
    expect(rowPeriodCredit({ increase: 120 })).toBe(120)
    expect(rowPeriodDebit({ decrease: 80 })).toBe(80)
  })

  it('closingAdjusted：无显式审定数时按 期初+开票-承兑+调整 重算', () => {
    // 期初100 + 开票50 - 承兑20 = 130；+aje10 +rje0 = 140
    expect(rowClosingAdjusted({
      openingBalance: 100,
      currentIssued: 50,
      currentAccepted: 20,
      aje: 10,
      rje: 0,
    })).toBe(140)
  })

  it('closingAdjusted：显式字段优先', () => {
    expect(rowClosingAdjusted({
      openingBalance: 100,
      currentIssued: 50,
      currentAccepted: 20,
      closingAdjusted: 999,
    })).toBe(999)
  })
})

describe('useF3CrossSheet with modern F3-2 JSON', () => {
  function setup(rows: unknown[]) {
    const map = new Map<string, ChecklistResponse>()
    map.set('F3-2-rows', {
      item_id: 'F3-2-rows',
      conclusion: null,
      remark: JSON.stringify(rows),
    })
    return useF3CrossSheet({
      allResponses: ref(map),
      projectContext: ref({} as ProjectContext),
    })
  }

  it('按 noteType 汇总本期开票/承兑与期末审定', () => {
    const cs = setup([
      {
        noteType: '银行承兑汇票',
        openingBalance: 1000,
        currentIssued: 500,
        currentAccepted: 200,
        aje: 0,
        rje: 0,
      },
      {
        noteType: '商业承兑汇票',
        openingBalance: 300,
        currentIssued: 100,
        currentAccepted: 50,
        aje: 0,
        rje: 0,
      },
    ])
    // 银行期末未审 = 1000+500-200=1300
    expect(cs.bankPeriodCredit.value).toBe(500)
    expect(cs.bankPeriodDebit.value).toBe(200)
    expect(cs.detailBankTotal.value).toBe(1300)
    // 商业期末 = 300+100-50=350
    expect(cs.commercialPeriodCredit.value).toBe(100)
    expect(cs.commercialPeriodDebit.value).toBe(50)
    expect(cs.detailCommercialTotal.value).toBe(350)
    expect(cs.detailGrandTotal.value).toBe(1650)
    expect(cs.hasDetailData.value).toBe(true)
  })

  it('旧字段 increase/decrease/adjustedBalance 仍可用', () => {
    const cs = setup([
      { noteType: '银行承兑汇票', increase: 80, decrease: 30, adjustedBalance: 700 },
    ])
    expect(cs.bankPeriodCredit.value).toBe(80)
    expect(cs.bankPeriodDebit.value).toBe(30)
    expect(cs.detailBankTotal.value).toBe(700)
  })
})
