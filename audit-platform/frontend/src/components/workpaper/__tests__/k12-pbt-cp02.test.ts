/**
 * K12 营业外收入 — CP-K12-02 Property-Based Test
 *
 * 收入类发生额 = 贷方发生 - 借方发生（红冲）
 * 科目：6301营业外收入（**损益类/贷方科目**，取发生额非余额）
 *   - 贷方=收入增加（营业外收入确认：政府补助/债务重组利得/资产盘盈/罚款收入/捐赠利得等）
 *   - 借方=收入冲回/红冲（期末结转损益或错误冲销）
 *
 * ⚠️ 方向注意：K12是贷方科目(credit - debit)，与K8/K11(debit - credit)相反！
 *
 * Spec: .kiro/specs/k12-non-operating-income/design.md → Correctness Properties CP-K12-02
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { calcIncomeStatementOccurrence } from '../composables/useK12FormulaEngine'

fc.configureGlobal({ numRuns: 100 })

const EPSILON = 1e-4

describe('K12 PBT — CP-K12-02 损益类发生额', () => {
  // ═══ CP-K12-02: 收入类发生额=贷方发生-借方发生 ═══
  // **Validates: Requirements 2.4**
  describe('Feature: k12-non-operating-income, Property CP-K12-02: 收入类发生额=贷方发生-借方发生', () => {
    it('CP-K12-02: calcIncomeStatementOccurrence(cr, dr) === cr - dr (creditOcc≥0, debitOcc≥0)', () => {
      fc.assert(
        fc.property(
          fc.float({ min: 0, max: Math.fround(1e9), noNaN: true, noDefaultInfinity: true }),
          fc.float({ min: 0, max: Math.fround(1e9), noNaN: true, noDefaultInfinity: true }),
          (cr, dr) => {
            const result = calcIncomeStatementOccurrence(cr, dr)
            const expected = cr - dr
            expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
          },
        ),
      )
    })
  })
})
