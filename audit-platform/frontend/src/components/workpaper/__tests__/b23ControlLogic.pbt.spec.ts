/**
 * Property-Based Tests — B23 关键控制驱动测试 / 穿行前置 / 缺陷触发
 *
 * Spec: .kiro/specs/b23-business-control-rework/
 * Task: 5.3
 *
 * Property 4: 关键控制驱动测试对象
 *   - eligibleForTest(cp) = cp.isKeyControl === '是'
 *   - 测试对象集 ⊆ 关键控制集 ⊆ 全集
 *   **Validates: Requirements 4.3, 5.3**
 *
 * Property 5: 穿行有效是控制测试前置
 *   - isKeyControl 且 wt.asDesigned === '是' → 建议控制测试
 *   - asDesigned === '否' → 不建议控制测试
 *   **Validates: Requirements 5.3, 5.4, 7.1**
 *
 * Property 6: 缺陷触发一致
 *   - designEffective === '否' 或 wt.asDesigned === '否' → 必有缺陷提示
 *   - 即使缺陷记录数为 0
 *   **Validates: Requirements 4.4, 6.4**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  eligibleForTest,
  suggestControlTest,
  deficiencyHints,
  type B23ControlPoint,
  type B23WalkthroughTest,
} from '../composables/useB23ProcessControl'

// ─── Arbitraries ─────────────────────────────────────────────────────────────

const arbYesNo = fc.constantFrom('是', '否') as fc.Arbitrary<'是' | '否'>
const arbYesNoNull = fc.constantFrom('是', '否', null) as fc.Arbitrary<'是' | '否' | null>
const arbFrequency = fc.constantFrom('每笔', '每日', '每周', '每月', '每季', '每年', '不定期', '定期', null)
const arbPreventDetect = fc.constantFrom('预防性', '检查性', null)
const arbCtrlTypeL1 = fc.constantFrom('授权和审批', '监督控制', '信息处理', '实物控制', '职责分离', '绩效评价复核', null)
const arbAssertions = fc.subarray(
  ['存在', '发生', '完整性', '准确性', '计价分摊', '权利义务', '列报'],
  { minLength: 0 },
)

/** Generator for B23ControlPoint with controlled isKeyControl/designEffective */
function arbControlPoint(overrides?: Partial<B23ControlPoint>): fc.Arbitrary<B23ControlPoint> {
  return fc.record({
    index: fc.integer({ min: 1, max: 30 }),
    subProcess: fc.string({ minLength: 0, maxLength: 15 }),
    ctrlNo: fc.string({ minLength: 1, maxLength: 10 }),
    ctrlName: fc.string({ minLength: 1, maxLength: 20 }),
    ctrlDesc: fc.string({ minLength: 0, maxLength: 30 }),
    affectedItems: fc.string({ minLength: 0, maxLength: 20 }),
    assertion: arbAssertions,
    wcgwRef: fc.string({ minLength: 0, maxLength: 10 }),
    wcgwDetail: fc.string({ minLength: 0, maxLength: 20 }),
    ctrlAttr: fc.string({ minLength: 0, maxLength: 10 }),
    frequency: arbFrequency as fc.Arbitrary<B23ControlPoint['frequency']>,
    itApp: fc.string({ minLength: 0, maxLength: 10 }),
    preventDetect: arbPreventDetect as fc.Arbitrary<B23ControlPoint['preventDetect']>,
    designEffective: arbYesNoNull as fc.Arbitrary<B23ControlPoint['designEffective']>,
    ctrlTypeL1: arbCtrlTypeL1 as fc.Arbitrary<B23ControlPoint['ctrlTypeL1']>,
    ctrlTypeL2: fc.oneof(fc.constant(null), fc.string({ minLength: 1, maxLength: 8 })),
    executor: fc.string({ minLength: 0, maxLength: 8 }),
    executorOrg: fc.string({ minLength: 0, maxLength: 10 }),
    hasDoc: arbYesNoNull as fc.Arbitrary<B23ControlPoint['hasDoc']>,
    isKeyControl: arbYesNoNull as fc.Arbitrary<B23ControlPoint['isKeyControl']>,
    doControlTest: arbYesNoNull as fc.Arbitrary<B23ControlPoint['doControlTest']>,
  }).map((cp) => ({ ...cp, ...overrides }))
}

/** Generator for B23WalkthroughTest */
function arbWalkthrough(overrides?: Partial<B23WalkthroughTest>): fc.Arbitrary<B23WalkthroughTest> {
  return fc.record({
    ctrlIndex: fc.integer({ min: 1, max: 30 }),
    method: fc.subarray(['询问', '观察', '检查文件', '穿行测试', '重新执行'], { minLength: 0 }),
    interviewee: fc.string({ minLength: 0, maxLength: 10 }),
    procedure: fc.string({ minLength: 0, maxLength: 20 }),
    evidence: fc.string({ minLength: 0, maxLength: 20 }),
    result: fc.string({ minLength: 0, maxLength: 20 }),
    asDesigned: arbYesNoNull as fc.Arbitrary<B23WalkthroughTest['asDesigned']>,
    deficiencyFound: fc.string({ minLength: 0, maxLength: 20 }),
  }).map((wt) => ({ ...wt, ...overrides }))
}

// ═══════════════════════════════════════════════════════════════════════════════
// Property 4: 关键控制驱动测试对象
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 Property 4: 关键控制驱动测试对象', () => {
  /**
   * **Validates: Requirements 4.3, 5.3**
   */
  it('isKeyControl === "是" ⟺ eligibleForTest returns true', () => {
    fc.assert(
      fc.property(arbControlPoint(), (cp) => {
        const eligible = eligibleForTest(cp)
        if (cp.isKeyControl === '是') {
          expect(eligible).toBe(true)
        } else {
          expect(eligible).toBe(false)
        }
      }),
      { numRuns: 20 },
    )
  })

  it('测试对象集 ⊆ 关键控制集 ⊆ 全集', () => {
    fc.assert(
      fc.property(
        fc.array(arbControlPoint(), { minLength: 1, maxLength: 10 }),
        (controlPoints) => {
          const allSet = new Set(controlPoints.map((_, i) => i))
          const keyControlSet = new Set(
            controlPoints
              .map((cp, i) => (cp.isKeyControl === '是' ? i : -1))
              .filter((i) => i >= 0),
          )
          const testObjectSet = new Set(
            controlPoints
              .map((cp, i) => (eligibleForTest(cp) ? i : -1))
              .filter((i) => i >= 0),
          )

          // testObjectSet ⊆ keyControlSet
          for (const idx of testObjectSet) {
            expect(keyControlSet.has(idx)).toBe(true)
          }
          // keyControlSet ⊆ allSet
          for (const idx of keyControlSet) {
            expect(allSet.has(idx)).toBe(true)
          }
          // Since eligibleForTest ⟺ isKeyControl === '是', sets are equal
          expect(testObjectSet.size).toBe(keyControlSet.size)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('非关键控制(isKeyControl !== "是") 永远不进入测试对象集', () => {
    fc.assert(
      fc.property(
        arbControlPoint({ isKeyControl: '否' }),
        (cp) => {
          expect(eligibleForTest(cp)).toBe(false)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('isKeyControl === null 时不可进入测试', () => {
    fc.assert(
      fc.property(
        arbControlPoint({ isKeyControl: null }),
        (cp) => {
          expect(eligibleForTest(cp)).toBe(false)
        },
      ),
      { numRuns: 20 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 5: 穿行有效是控制测试前置
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 Property 5: 穿行有效是控制测试前置', () => {
  /**
   * **Validates: Requirements 5.3, 5.4, 7.1**
   */
  it('关键控制 ∧ asDesigned === "是" → suggestControlTest 返回 true', () => {
    fc.assert(
      fc.property(
        arbControlPoint({ isKeyControl: '是' }),
        arbWalkthrough({ asDesigned: '是' }),
        (cp, wt) => {
          expect(suggestControlTest(cp, wt)).toBe(true)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('关键控制 ∧ asDesigned === "否" → suggestControlTest 返回 false', () => {
    fc.assert(
      fc.property(
        arbControlPoint({ isKeyControl: '是' }),
        arbWalkthrough({ asDesigned: '否' }),
        (cp, wt) => {
          expect(suggestControlTest(cp, wt)).toBe(false)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('非关键控制 → suggestControlTest 返回 false（无论 asDesigned 如何）', () => {
    fc.assert(
      fc.property(
        arbControlPoint({ isKeyControl: '否' }),
        arbWalkthrough(),
        (cp, wt) => {
          expect(suggestControlTest(cp, wt)).toBe(false)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('穿行记录为 undefined → suggestControlTest 返回 false（无论是否关键控制）', () => {
    fc.assert(
      fc.property(arbControlPoint(), (cp) => {
        expect(suggestControlTest(cp, undefined)).toBe(false)
      }),
      { numRuns: 20 },
    )
  })

  it('asDesigned === null → suggestControlTest 返回 false（关键控制也不建议）', () => {
    fc.assert(
      fc.property(
        arbControlPoint({ isKeyControl: '是' }),
        arbWalkthrough({ asDesigned: null }),
        (cp, wt) => {
          expect(suggestControlTest(cp, wt)).toBe(false)
        },
      ),
      { numRuns: 20 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 6: 缺陷触发一致
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 Property 6: 缺陷触发一致', () => {
  /**
   * **Validates: Requirements 4.4, 6.4**
   */
  it('designEffective === "否" → deficiencyHints 必有至少一条提示', () => {
    fc.assert(
      fc.property(
        arbControlPoint({ designEffective: '否' }),
        arbWalkthrough(),
        (cp, wt) => {
          const hints = deficiencyHints(cp, wt)
          expect(hints.length).toBeGreaterThanOrEqual(1)
          expect(hints.some((h) => h.includes('控制设计无效'))).toBe(true)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('asDesigned === "否" → deficiencyHints 必有至少一条提示', () => {
    fc.assert(
      fc.property(
        arbControlPoint(),
        arbWalkthrough({ asDesigned: '否' }),
        (cp, wt) => {
          const hints = deficiencyHints(cp, wt)
          expect(hints.length).toBeGreaterThanOrEqual(1)
          expect(hints.some((h) => h.includes('穿行测试未按设计执行'))).toBe(true)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('designEffective === "否" ∧ asDesigned === "否" → deficiencyHints 至少两条', () => {
    fc.assert(
      fc.property(
        arbControlPoint({ designEffective: '否' }),
        arbWalkthrough({ asDesigned: '否' }),
        (cp, wt) => {
          const hints = deficiencyHints(cp, wt)
          expect(hints.length).toBeGreaterThanOrEqual(2)
          expect(hints.some((h) => h.includes('控制设计无效'))).toBe(true)
          expect(hints.some((h) => h.includes('穿行测试未按设计执行'))).toBe(true)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('designEffective !== "否" ∧ asDesigned !== "否" → deficiencyHints 为空', () => {
    fc.assert(
      fc.property(
        arbControlPoint({ designEffective: '是' }),
        arbWalkthrough({ asDesigned: '是' }),
        (cp, wt) => {
          const hints = deficiencyHints(cp, wt)
          expect(hints).toHaveLength(0)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('穿行记录 undefined 且 designEffective === "否" → 仍触发缺陷提示', () => {
    fc.assert(
      fc.property(
        arbControlPoint({ designEffective: '否' }),
        (cp) => {
          const hints = deficiencyHints(cp, undefined)
          expect(hints.length).toBeGreaterThanOrEqual(1)
          expect(hints.some((h) => h.includes('控制设计无效'))).toBe(true)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('穿行记录 undefined 且 designEffective !== "否" → deficiencyHints 为空', () => {
    fc.assert(
      fc.property(
        arbControlPoint({ designEffective: '是' }),
        (cp) => {
          const hints = deficiencyHints(cp, undefined)
          expect(hints).toHaveLength(0)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('缺陷提示包含控制点标识信息（ctrlNo 或 index）', () => {
    fc.assert(
      fc.property(
        arbControlPoint({ designEffective: '否' }),
        (cp) => {
          const hints = deficiencyHints(cp, undefined)
          // Each hint should reference the control point identifier
          for (const hint of hints) {
            const hasCtrlNo = cp.ctrlNo && hint.includes(cp.ctrlNo)
            const hasIndex = hint.includes(String(cp.index))
            expect(hasCtrlNo || hasIndex).toBe(true)
          }
        },
      ),
      { numRuns: 20 },
    )
  })
})
