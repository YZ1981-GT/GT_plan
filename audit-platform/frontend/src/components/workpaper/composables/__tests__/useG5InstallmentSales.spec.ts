import { describe, it, expect } from 'vitest'
import { useG5InstallmentSales } from '../useG5InstallmentSales'

describe('useG5InstallmentSales — Excel 汇总勾稽', () => {
  it('(3)=(1)×利率，(2)=(5)−(3)，期末摊余正确', () => {
    const sales = useG5InstallmentSales()
    sales.loadData({
      groups: [{
        projectName: '测例',
        initial: {
          contractTotal: 1100,
          fairValue: 1000,
          effectiveRate: 0.1,
        },
        periods: [{
          openingReceivable: 1100,
          openingUnrealized: 100,
          periodCollection: 300,
          companyBookIncome: 100,
        }],
      }],
    })
    const g = sales.groups.value[0]
    const p = g.periods[0]
    expect(p.openingAmortizedCost).toBeCloseTo(1000, 6)
    expect(p.periodIncome).toBeCloseTo(100, 6)
    expect(p.principalCollected).toBeCloseTo(200, 6)
    expect(p.closingReceivable).toBeCloseTo(800, 6)
    expect(p.closingUnrealized).toBeCloseTo(0, 6)
    expect(p.closingAmortizedCost).toBeCloseTo(800, 6)
    expect(p.variance).toBeCloseTo(0, 6)

    const row = sales.buildReconcileRow(g)
    expect(row.unrealizedRecognized).toBeCloseTo(100, 6)
    expect(row.unrealizedEnding).toBeCloseTo(0, 6)
    expect(row.principalCollectedTotal).toBeCloseTo(200, 6)
    expect(row.carryingAmount).toBeCloseTo(800, 6)
  })

  it('新增期间自动带上期期末；连续性校验未实现', () => {
    const sales = useG5InstallmentSales()
    sales.loadData({
      groups: [{
        projectName: '连续',
        initial: { contractTotal: 1100, fairValue: 1000, effectiveRate: 0.1 },
        periods: [{
          openingReceivable: 1100,
          openingUnrealized: 100,
          periodCollection: 300,
        }],
      }],
    })
    const id = sales.groups.value[0].id
    sales.addPeriod(id)
    const g = sales.groups.value[0]
    expect(g.periods).toHaveLength(2)
    expect(g.periods[1].openingReceivable).toBeCloseTo(g.periods[0].closingReceivable, 6)
    expect(g.periods[1].openingUnrealized).toBeCloseTo(g.periods[0].closingUnrealized, 6)
    expect(sales.validateContinuity(g)).toBe(true)
  })

  it('从 G5-2 installment 行带入', () => {
    const sales = useG5InstallmentSales()
    const n = sales.importFromG5BalanceRows([
      { businessType: 'installment', debtorName: '客户甲', contractAmount: 5000, closingBalance: 4000, unrealizedIncome: 400, netAmount: 3600 },
      { businessType: 'lease', debtorName: '租赁乙', closingBalance: 100 },
    ])
    expect(n).toBe(1)
    expect(sales.groups.value[0].initial.customer).toBe('客户甲')
    expect(sales.groups.value[0].initial.contractTotal).toBe(5000)
    expect(sales.groups.value[0].periods[0].openingReceivable).toBe(4000)
  })
})
