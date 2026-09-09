/**
 * Task 8 FE — function/category split guard.
 */

import { describe, expect, it } from 'vitest'

import { assertFunctionCategorySplit } from '@/shell/formula/userFormulaV2'
import { wpUserFormula } from '@/services/apiPaths/formula'

describe('Task 8: user formula v2 FE contract', () => {
  it('registers v2 paths distinct from legacy dict API', () => {
    expect(wpUserFormula.list('w1')).toBe('/api/workpapers/w1/user-formulas')
    expect(wpUserFormula.v2.list('w1')).toBe('/api/workpapers/w1/user-formulas/v2')
    expect(wpUserFormula.v2.batchMutate('w1')).toContain('v2:batchMutate')
    expect(wpUserFormula.v2.history('w1', 'f1')).toContain('/v2/f1/history')
  })

  it('rejects collapsed formulaFunction/ruleCategory and legacy formula_type', () => {
    expect(
      assertFunctionCategorySplit({
        formulaFunction: 'TB',
        ruleCategory: 'auto_calc',
      }).ok,
    ).toBe(true)
    expect(
      assertFunctionCategorySplit({
        formulaFunction: 'auto_calc',
        ruleCategory: 'auto_calc',
      }).ok,
    ).toBe(false)
    expect(
      assertFunctionCategorySplit({
        formulaFunction: 'TB',
        ruleCategory: 'auto_calc',
        formula_type: 'TB',
      }).ok,
    ).toBe(false)
  })
})
