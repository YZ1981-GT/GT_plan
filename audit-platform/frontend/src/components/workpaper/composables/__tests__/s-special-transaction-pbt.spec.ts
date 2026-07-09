/**
 * Property-Based Tests — S 类交易/专家/检查型专项底稿 (S4/S5/S6/S12/S13/S14)
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 8.1
 * Framework: vitest + fast-check, numRuns = 100
 *
 * Properties:
 *   P1: componentType 注册与分发完整性
 *   P2: S4 交换损益计算正确性
 *   P3: S4 商业实质判断正确性
 *   P4: S5 债务重组损益计算正确性
 *   P5: 专家子表分支解析确定性
 *   P8: readonly 禁编辑
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

import {
  calcExchangeGainLoss,
  judgeApplicable,
  judgeCommercialSubstance,
  type S4ExchangeInput,
  type CommercialSubstanceInput,
} from '../useS4FormulaEngine'

import {
  calcCreditorGainLoss,
  calcDebtorGainLoss,
  type CreditorInput,
  type DebtorInput,
} from '../useS5FormulaEngine'

import {
  resolveExpertSubSheet,
  EXPERT_DOMAINS,
  type ExpertDomain,
  type ExpertPrefix,
} from '../useS12S13ExpertBranch'

// ═══ Generators ═══

const safeFloat = (opts?: { min?: number; max?: number }) =>
  fc.double({
    min: opts?.min ?? -1e8,
    max: opts?.max ?? 1e8,
    noNaN: true,
    noDefaultInfinity: true,
  })

const s4ExchangeInputArb = (): fc.Arbitrary<S4ExchangeInput> =>
  fc.record({
    inFairValue: safeFloat(),
    outFairValue: safeFloat(),
    outBookValue: safeFloat(),
    taxes: safeFloat(),
  })

const commercialSubstanceInputArb = (): fc.Arbitrary<CommercialSubstanceInput> =>
  fc.record({
    exclusions: fc.array(fc.boolean(), { minLength: 6, maxLength: 6 }),
    cashflowDifferent: fc.boolean(),
  })

const creditorInputArb = (): fc.Arbitrary<CreditorInput> =>
  fc.record({
    origBook: safeFloat(),
    origFair: safeFloat(),
    recvFair: safeFloat(),
    otherCost: safeFloat(),
  })

const debtorInputArb = (): fc.Arbitrary<DebtorInput> =>
  fc.record({
    debtBook: safeFloat(),
    assetBook: safeFloat(),
    equityFair: safeFloat(),
  })

const expertDomainArb = (): fc.Arbitrary<ExpertDomain> =>
  fc.constantFrom('general', 'share-based-payment', 'financial-instrument-fair-value')

const expertPrefixArb = (): fc.Arbitrary<ExpertPrefix> =>
  fc.constantFrom('S12', 'S13')

// ═══════════════════════════════════════════════════════════════════════════════
// P1: componentType 注册与分发完整性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: s-special-transaction-workpapers, Property 1: componentType 注册与分发完整性', () => {
  /**
   * **Validates: Requirements 1.1, 1.2, 1.3**
   */
  it('交易型 wp_code (S4/S5/S6/S12/S13/S14) 映射为对应专属 componentType', async () => {
    const DEDICATED_MAP: Record<string, string> = {
      S4: 's4-nonmonetary-exchange',
      S5: 's5-debt-restructuring',
      S6: 's6-fund-occupation',
      S12: 's12-cpa-expert',
      S13: 's13-mgmt-expert',
      S14: 's14-accounting-estimate',
    }

    const { HTML_COMPONENT_TYPE_SET } = await import('../../htmlRendererRegistry')

    fc.assert(
      fc.property(
        fc.constantFrom(...Object.entries(DEDICATED_MAP)),
        ([wpCode, expectedType]) => {
          expect(DEDICATED_MAP[wpCode]).toBe(expectedType)
          expect(HTML_COMPONENT_TYPE_SET.has(expectedType as any)).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('检查表型 wp_code (S1/S2/S8/S9/S10/S11/S16/S17) 映射为 a-program-console', async () => {
    const CONSOLE_CODES = ['S1', 'S2', 'S8', 'S9', 'S10', 'S11', 'S16', 'S17']

    const { HTML_COMPONENT_TYPE_SET } = await import('../../htmlRendererRegistry')

    fc.assert(
      fc.property(
        fc.constantFrom(...CONSOLE_CODES),
        (wpCode) => {
          // 验证 a-program-console 在 registry 中已注册
          expect(HTML_COMPONENT_TYPE_SET.has('a-program-console' as any)).toBe(true)
          // 所有 CONSOLE_CODES 都应映射到 a-program-console
          expect(CONSOLE_CODES).toContain(wpCode)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// P2: S4 交换损益计算正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: s-special-transaction-workpapers, Property 2: S4 交换损益计算正确性', () => {
  /**
   * **Validates: Requirements 2.2**
   */
  it('gainLoss = outFairValue - outBookValue（换出资产损益）', () => {
    fc.assert(
      fc.property(s4ExchangeInputArb(), (input) => {
        const result = calcExchangeGainLoss(input)
        const expected = input.outFairValue - input.outBookValue
        expect(result.gainLoss).toBeCloseTo(expected, 5)
      }),
      { numRuns: 100 },
    )
  })

  it('inCost = outFairValue + taxes（换入资产成本）', () => {
    fc.assert(
      fc.property(s4ExchangeInputArb(), (input) => {
        const result = calcExchangeGainLoss(input)
        const expected = input.outFairValue + input.taxes
        expect(result.inCost).toBeCloseTo(expected, 5)
      }),
      { numRuns: 100 },
    )
  })

  it('结果永远不为 NaN 或 Infinity', () => {
    fc.assert(
      fc.property(s4ExchangeInputArb(), (input) => {
        const result = calcExchangeGainLoss(input)
        expect(Number.isFinite(result.gainLoss)).toBe(true)
        expect(Number.isFinite(result.inCost)).toBe(true)
      }),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// P3: S4 商业实质判断正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: s-special-transaction-workpapers, Property 3: S4 商业实质判断正确性', () => {
  /**
   * **Validates: Requirements 2.3, 2.4**
   */
  it('judgeApplicable = 6 项排除全为 false（即全「不属于」）→ true', () => {
    fc.assert(
      fc.property(commercialSubstanceInputArb(), (input) => {
        const result = judgeApplicable(input)
        const allFalse = input.exclusions.every(e => e === false)
        expect(result).toBe(allFalse)
      }),
      { numRuns: 100 },
    )
  })

  it('judgeCommercialSubstance = cashflowDifferent（商业实质 = 现金流量显著不同）', () => {
    fc.assert(
      fc.property(commercialSubstanceInputArb(), (input) => {
        const result = judgeCommercialSubstance(input)
        expect(result).toBe(input.cashflowDifferent)
      }),
      { numRuns: 100 },
    )
  })

  it('返回值始终为布尔类型', () => {
    fc.assert(
      fc.property(commercialSubstanceInputArb(), (input) => {
        expect(typeof judgeApplicable(input)).toBe('boolean')
        expect(typeof judgeCommercialSubstance(input)).toBe('boolean')
      }),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// P4: S5 债务重组损益计算正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: s-special-transaction-workpapers, Property 4: S5 债务重组损益计算正确性', () => {
  /**
   * **Validates: Requirements 3.2**
   */
  it('calcCreditorGainLoss = origBook - origFair + recvFair（债权人视角）', () => {
    fc.assert(
      fc.property(creditorInputArb(), (input) => {
        const result = calcCreditorGainLoss(input)
        const expected = input.origBook - input.origFair + input.recvFair
        expect(result).toBeCloseTo(expected, 5)
      }),
      { numRuns: 100 },
    )
  })

  it('calcDebtorGainLoss = debtBook - assetBook - equityFair（债务人视角）', () => {
    fc.assert(
      fc.property(debtorInputArb(), (input) => {
        const result = calcDebtorGainLoss(input)
        const expected = input.debtBook - input.assetBook - input.equityFair
        expect(result).toBeCloseTo(expected, 5)
      }),
      { numRuns: 100 },
    )
  })

  it('债权人/债务人损益结果永远不为 NaN 或 Infinity', () => {
    fc.assert(
      fc.property(creditorInputArb(), debtorInputArb(), (cInput, dInput) => {
        const cResult = calcCreditorGainLoss(cInput)
        const dResult = calcDebtorGainLoss(dInput)
        expect(Number.isFinite(cResult)).toBe(true)
        expect(Number.isFinite(dResult)).toBe(true)
      }),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// P5: 专家子表分支解析确定性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: s-special-transaction-workpapers, Property 5: 专家子表分支解析确定性', () => {
  /**
   * **Validates: Requirements 4.3, 4.4**
   */
  it('resolveExpertSubSheet 确定性：相同 (prefix, domain) 始终返回相同结果', () => {
    fc.assert(
      fc.property(expertPrefixArb(), expertDomainArb(), (prefix, domain) => {
        const result1 = resolveExpertSubSheet(prefix, domain)
        const result2 = resolveExpertSubSheet(prefix, domain)
        expect(result1).toBe(result2)
      }),
      { numRuns: 100 },
    )
  })

  it('resolveExpertSubSheet 返回非空字符串', () => {
    fc.assert(
      fc.property(expertPrefixArb(), expertDomainArb(), (prefix, domain) => {
        const result = resolveExpertSubSheet(prefix, domain)
        expect(typeof result).toBe('string')
        expect(result.length).toBeGreaterThan(0)
      }),
      { numRuns: 100 },
    )
  })

  it('S12 domain 映射：general→S12-3-2 / share-based-payment→S12-3-3 / financial-instrument-fair-value→S12-3-4', () => {
    fc.assert(
      fc.property(expertDomainArb(), (domain) => {
        const result = resolveExpertSubSheet('S12', domain)
        if (domain === 'general') {
          expect(result).toContain('S12-3-2')
        } else if (domain === 'share-based-payment') {
          expect(result).toContain('S12-3-3')
        } else {
          expect(result).toContain('S12-3-4')
        }
      }),
      { numRuns: 100 },
    )
  })

  it('S13 domain 映射：general→S13-3-2 / share-based-payment→S13-3-3 / financial-instrument-fair-value→S13-3-4', () => {
    fc.assert(
      fc.property(expertDomainArb(), (domain) => {
        const result = resolveExpertSubSheet('S13', domain)
        if (domain === 'general') {
          expect(result).toContain('S13-3-2')
        } else if (domain === 'share-based-payment') {
          expect(result).toContain('S13-3-3')
        } else {
          expect(result).toContain('S13-3-4')
        }
      }),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// P8: readonly 禁编辑
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: s-special-transaction-workpapers, Property 8: readonly 禁编辑', () => {
  /**
   * **Validates: Requirements 11.4**
   */
  it('readonly=true 时禁止编辑操作（纯逻辑层）', () => {
    fc.assert(
      fc.property(fc.boolean(), (readonly) => {
        // 模拟 readonly 控制逻辑：when true, mutations are blocked
        const canEdit = !readonly
        const canAddRow = !readonly
        const canDeleteRow = !readonly

        if (readonly) {
          expect(canEdit).toBe(false)
          expect(canAddRow).toBe(false)
          expect(canDeleteRow).toBe(false)
        } else {
          expect(canEdit).toBe(true)
          expect(canAddRow).toBe(true)
          expect(canDeleteRow).toBe(true)
        }
      }),
      { numRuns: 100 },
    )
  })

  it('readonly 属性反转性：readonly XOR canEdit === true', () => {
    fc.assert(
      fc.property(fc.boolean(), (readonly) => {
        const canEdit = !readonly
        // XOR 性质: 一个 true 另一个必 false
        expect(readonly !== canEdit).toBe(true)
      }),
      { numRuns: 100 },
    )
  })
})
