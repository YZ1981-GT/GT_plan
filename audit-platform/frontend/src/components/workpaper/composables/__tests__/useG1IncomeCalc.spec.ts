import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  enrichInterestRow,
  enrichDividendRow,
  enrichDisposalRow,
  useG1IncomeCalc,
  type G1InterestCalcRow,
} from '../useG1IncomeCalc'
import { calcInterestByBasis, calcAccruedDays } from '../useG1TraFinFormulaEngine'
import type { ChecklistResponse } from '../useF1FormData'

function interestBase(partial: Partial<G1InterestCalcRow> = {}): G1InterestCalcRow {
  return enrichInterestRow(
    {
      id: '1',
      seq: 1,
      securityName: '测试债',
      contractAmount: 1_000_000,
      annualRatePct: 3.65,
      startDate: '2025-01-01',
      settlementDate: '2025-07-01',
      maturityDate: '2025-12-31',
      dayCountBasis: 365,
      daysBeforeManual: null,
      daysAfterManual: null,
      daysBefore: 0,
      daysAfter: 0,
      interestBefore: 0,
      interestAfter: 0,
      interestSubtotal: 0,
      remark: '',
      ...partial,
    },
    '2025-12-31',
  )
}

describe('calcInterestByBasis / calcAccruedDays', () => {
  it('365 基数利息', () => {
    // 1e6 × 3.65% × 100 / 365 = 10000
    expect(calcInterestByBasis(1_000_000, 3.65, 100, 365)).toBeCloseTo(10_000, 6)
  })

  it('计息天数', () => {
    expect(calcAccruedDays('2025-01-01', '2025-01-31')).toBe(30)
  })
})

describe('enrichInterestRow 结息分段', () => {
  it('结息前/后天数与利息小计', () => {
    const r = interestBase()
    const beforeDays = calcAccruedDays('2025-01-01', '2025-07-01')
    const afterDays = calcAccruedDays('2025-07-01', '2025-12-31')
    expect(r.daysBefore).toBe(beforeDays)
    expect(r.daysAfter).toBe(afterDays)
    expect(r.interestSubtotal).toBeCloseTo(r.interestBefore + r.interestAfter, 6)
    expect(r.interestBefore).toBeCloseTo(
      calcInterestByBasis(1_000_000, 3.65, beforeDays, 365),
      6,
    )
  })

  it('无结息日时整段计入结息前', () => {
    const r = interestBase({ settlementDate: '', maturityDate: '2025-12-31' })
    expect(r.daysAfter).toBe(0)
    expect(r.daysBefore).toBe(calcAccruedDays('2025-01-01', '2025-12-31'))
  })

  it('手工覆盖天数', () => {
    const r = interestBase({ daysBeforeManual: 90, daysAfterManual: 10 })
    expect(r.daysBefore).toBe(90)
    expect(r.daysAfter).toBe(10)
    expect(r.interestBefore).toBeCloseTo(calcInterestByBasis(1_000_000, 3.65, 90, 365), 6)
  })

  it('截止日限制结息后区间', () => {
    const r = interestBase({ maturityDate: '2026-06-30' })
    // cutoff 2025-12-31 → 结息后至截止日
    expect(r.daysAfter).toBe(calcAccruedDays('2025-07-01', '2025-12-31'))
  })
})

describe('enrichDividendRow / enrichDisposalRow', () => {
  it('股利应收与差异', () => {
    const r = enrichDividendRow({
      id: '1',
      seq: 1,
      securityName: '股票A',
      holdingQuantity: 1000,
      dividendPerShare: 0.5,
      receivableAmount: 0,
      receivedAmount: 400,
      incomeDiff: 0,
      confirmDate: '',
      incomeSource: '',
      incomeRemark: '',
    })
    expect(r.receivableAmount).toBe(500)
    expect(r.incomeDiff).toBe(100)
  })

  it('处置成交金额自动 = 数量×单价', () => {
    const r = enrichDisposalRow({
      id: '1',
      seq: 1,
      securityName: '股票A',
      soldQuantity: 100,
      dealPrice: 10,
      dealAmount: 0,
      originalCost: 800,
      realizedGain: 0,
      fee: 5,
      netGain: 0,
      disposalRemark: '',
    })
    expect(r.dealAmount).toBe(1000)
    expect(r.realizedGain).toBe(200)
    expect(r.netGain).toBe(195)
  })
})

describe('useG1IncomeCalc 账面勾稽', () => {
  it('债息合计与账面差异', () => {
    const row = interestBase()
    const allResponses = ref(
      new Map<string, ChecklistResponse>([
        ['G1-5-interest-rows', { conclusion: JSON.stringify([row]) } as ChecklistResponse],
        [
          'G1-5-book-recon',
          {
            conclusion: JSON.stringify({
              cutoffDate: '2025-12-31',
              bookInvestmentIncome: row.interestSubtotal,
              bookAccruedInterest: 0,
              bookDividendIncome: 0,
            }),
          } as ChecklistResponse,
        ],
      ]),
    )
    const calc = useG1IncomeCalc({
      allResponses,
      debouncedSave: () => {},
      isReadonly: ref(false),
    })
    expect(calc.interestTotal.value).toBeCloseTo(row.interestSubtotal, 4)
    expect(calc.balanceOk.value).toBe(true)
    expect(calc.interestBookDiff.value).toBeCloseTo(0, 4)
  })

  it('旧版 G1-5-rows 迁移到股利区', () => {
    const allResponses = ref(
      new Map<string, ChecklistResponse>([
        [
          'G1-5-rows',
          {
            conclusion: JSON.stringify([
              {
                id: '1',
                seq: 1,
                securityName: '旧股',
                holdingQuantity: 200,
                dividendPerShare: 1,
                receivedAmount: 150,
              },
            ]),
          } as ChecklistResponse,
        ],
      ]),
    )
    const calc = useG1IncomeCalc({
      allResponses,
      debouncedSave: () => {},
      isReadonly: ref(false),
    })
    expect(calc.dividendRows.value[0].securityName).toBe('旧股')
    expect(calc.dividendRows.value[0].receivableAmount).toBe(200)
    expect(calc.dividendRows.value[0].incomeDiff).toBe(50)
  })

  it('从 G1-2 带入债息与股利', () => {
    const allResponses = ref(
      new Map<string, ChecklistResponse>([
        [
          'G1-2-rows',
          {
            conclusion: JSON.stringify([
              {
                id: '1',
                securityName: '国债A',
                investType: 'bond',
                closingCost: 500000,
                auditedClosingCost: 500000,
                dividendIncome: 1200,
              },
              {
                id: '2',
                securityName: '股票B',
                investType: 'stock',
                closingQuantity: 1000,
                dividendIncome: 300,
              },
            ]),
          } as ChecklistResponse,
        ],
      ]),
    )
    const calc = useG1IncomeCalc({
      allResponses,
      debouncedSave: () => {},
      isReadonly: ref(false),
    })
    const r = calc.syncFromDetail()
    expect(r.interest).toBe(1)
    expect(r.dividend).toBe(1)
    expect(calc.interestRows.value[0].securityName).toBe('国债A')
    expect(calc.interestRows.value[0].contractAmount).toBe(500000)
    expect(calc.dividendRows.value[0].securityName).toBe('股票B')
    expect(calc.dividendRows.value[0].holdingQuantity).toBe(1000)
  })

  it('差异推送同时覆盖债息与股利账面差异', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>())
    const calc = useG1IncomeCalc({
      allResponses,
      debouncedSave: (id, data) => {
        allResponses.value.set(id, {
          item_id: id,
          conclusion: data.conclusion ?? null,
          remark: data.remark ?? null,
        } as ChecklistResponse)
      },
      isReadonly: ref(false),
    })
    calc.interestRows.value = [interestBase({ interestSubtotal: 1000 })]
    calc.updateBookRecon({
      bookInvestmentIncome: 0,
      bookAccruedInterest: 600,
      bookDividendIncome: 50,
    })
    calc.dividendRows.value = [
      enrichDividendRow({
        id: 'd1',
        seq: 1,
        securityName: '股票B',
        holdingQuantity: 100,
        dividendPerShare: 2,
        receivableAmount: 0,
        receivedAmount: 0,
        incomeDiff: 0,
        confirmDate: '',
        incomeSource: '',
        incomeRemark: '',
      }),
    ]
    const n = calc.pushDiffToAdjustment()
    expect(n).toBeGreaterThanOrEqual(1)
    const adj = allResponses.value.get('G1-3-rows')
    const rows = JSON.parse(String(adj?.conclusion || adj?.remark || '[]'))
    const descs = rows.map((r: { description?: string }) => String(r.description || ''))
    expect(descs.some((d: string) => d.includes('债息'))).toBe(true)
    expect(descs.some((d: string) => d.includes('股利'))).toBe(true)
  })
})
