/**
 * D4 IPO 表内计算公式引擎行为判据。
 *
 * spec: d4-ipo-checklist-dual-mode-writeback-and-formula · Wave 3 · Task 8
 * Property 15/21/26/29/33。
 */
import { describe, it, expect } from 'vitest'
import { evaluateExpression, recalcDerivedColumns } from '../ipoChecklistFormulaEngine'

describe('evaluateExpression — 占比（分母为 0/空 → null）', () => {
  const rows = [
    { rowId: 'r1', seq: 1, salesAmount: 300 },
    { rowId: 'r2', seq: 2, salesAmount: 700 },
  ]
  it('$salesAmount / SUM($salesAmount) 正常求值', () => {
    const v = evaluateExpression('$salesAmount / SUM($salesAmount)', rows[0], rows)
    expect(v).toBeCloseTo(0.3, 4)
  })
  it('分母为 0（全部行销售为 0）→ null（不显示 0%、Property 21/33）', () => {
    const zero = [
      { rowId: 'r1', seq: 1, salesAmount: 0 },
      { rowId: 'r2', seq: 2, salesAmount: 0 },
    ]
    expect(evaluateExpression('$salesAmount / SUM($salesAmount)', zero[0], zero)).toBeNull()
  })
})

describe('evaluateExpression — 差异（任一为空 → null，Property 26）', () => {
  it('确认金额 − 本期金额，两者齐全', () => {
    const row = { rowId: 'r1', seq: 1, confirmedSalesAmount: 120, salesAmount: 100 }
    expect(evaluateExpression('$confirmedSalesAmount - $salesAmount', row, [row])).toBeCloseTo(20, 4)
  })
  it('本期金额为空 → 差异 null（不误判为 120）', () => {
    const row = { rowId: 'r1', seq: 1, confirmedSalesAmount: 120, salesAmount: '' }
    expect(evaluateExpression('$confirmedSalesAmount - $salesAmount', row, [row])).toBeNull()
  })
})

describe('evaluateExpression — D4-27 总计 = 10 checkbox 之和（Property 29）', () => {
  const expr =
    '$isPersonalCustomer + $isCustomerLegal + $isContractSigner + $isExecRelative + $isFinanceDept + $isMgmtDept + $isTechDept + $isProductionDept + $isMarketingDept + $isOther'
  it('勾选 3 个 → 3', () => {
    const row = {
      rowId: 'r1', seq: 1,
      isPersonalCustomer: true, isCustomerLegal: false, isContractSigner: true,
      isExecRelative: false, isFinanceDept: true, isMgmtDept: false, isTechDept: false,
      isProductionDept: false, isMarketingDept: false, isOther: false,
    }
    expect(evaluateExpression(expr, row, [row])).toBe(3)
  })
  it('全不勾 → 0', () => {
    const row = { rowId: 'r1', seq: 1 }
    expect(evaluateExpression(expr, row, [row])).toBe(0)
  })
})

describe('recalcDerivedColumns — 手填锁定不重算（Property 15）', () => {
  it('派生列写回；被 manualLock 的行不重算', () => {
    const rows = [
      { rowId: 'r1', seq: 1, salesAmount: 300 },
      { rowId: 'r2', seq: 2, salesAmount: 700 },
    ] as any
    recalcDerivedColumns('D4-25', rows)
    // D4-25 派生列 proportion = salesAmount / SUM
    expect(rows[0].proportion).toBeCloseTo(0.3, 4)
    // 手填锁定 r1
    rows[0].proportion = 0.99
    recalcDerivedColumns('D4-25', rows, new Set(['r1:proportion']))
    expect(rows[0].proportion).toBe(0.99) // 锁定不被覆盖
    expect(rows[1].proportion).toBeCloseTo(0.7, 4) // r2 仍重算
  })
})
