import { describe, it, expect } from 'vitest'
import { useG5LeaseAmortization } from '../useG5LeaseAmortization'

describe('useG5LeaseAmortization — Excel 汇总勾稽', () => {
  it('最低租赁收款额 = 租金 + 承租人担保 + 第三方担保', () => {
    const lease = useG5LeaseAmortization()
    lease.loadData({
      groups: [{
        id: 'g1',
        projectName: '测例A',
        basic: {
          rentalInstallments: 1000,
          residualLessee: 100,
          residualThirdParty: 50,
          unguaranteedResidual: 80,
          initialDirectCosts: 20,
          implicitRate: 0.1,
        },
        periods: [{
          periodNo: 1,
          openingReceivable: 1230,
          openingUnrealized: 200,
          periodCollection: 300,
          companyBookIncome: 100,
        }],
      }],
    })
    const g = lease.groups.value[0]
    lease.syncMinimumLeasePayment(g.basic)
    expect(g.basic.minimumLeasePayment).toBe(1150)

    const row = lease.buildReconcileRow(g)
    expect(row.grossInvestment).toBe(1150 + 80 + 20)
    expect(row.unrealizedRecognized).toBeCloseTo(g.periods[0].periodIncome, 6)
    expect(row.unrealizedEnding).toBeCloseTo(g.periods[0].closingUnrealized, 6)
    // 增加 = 期末 − 期初 + 确认
    expect(row.unrealizedAddition).toBeCloseTo(
      row.unrealizedEnding - row.unrealizedOpening + row.unrealizedRecognized,
      6,
    )
    expect(row.carryingAmount).toBeCloseTo(row.netEnding, 6)
  })

  it('旧数据仅有 minimumLeasePayment 时可兼容加载', () => {
    const lease = useG5LeaseAmortization()
    lease.loadData({
      groups: [{
        projectName: '旧项目',
        basic: {
          lessee: '甲',
          minimumLeasePayment: 5000,
          unguaranteedResidual: 200,
          implicitRate: 0.05,
        },
        periods: [{
          openingReceivable: 5200,
          openingUnrealized: 800,
          periodCollection: 1000,
          companyBookIncome: 0,
        }],
      }],
    })
    const g = lease.groups.value[0]
    expect(g.basic.minimumLeasePayment).toBe(5000)
    expect(g.basic.rentalInstallments).toBe(5000)
    expect(lease.validateContinuity(g)).toBe(true)
  })

  it('从 G5-2 lease 行带入不覆盖已有同名项目', () => {
    const lease = useG5LeaseAmortization()
    lease.loadData({
      groups: [{ projectName: '债务人A', basic: {}, periods: [{}] }],
    })
    const n = lease.importFromG5BalanceRows([
      { businessType: 'lease', debtorName: '债务人A', closingBalance: 100, unrealizedIncome: 10 },
      { businessType: 'lease', debtorName: '债务人B', closingBalance: 200, unrealizedIncome: 20, netAmount: 180 },
      { businessType: 'other', debtorName: '其他', closingBalance: 50 },
    ])
    expect(n).toBe(1)
    expect(lease.groups.value.map(g => g.projectName)).toEqual(['债务人A', '债务人B'])
    expect(lease.groups.value[1].basic.bookClosingUnrealized).toBe(20)
  })
})
