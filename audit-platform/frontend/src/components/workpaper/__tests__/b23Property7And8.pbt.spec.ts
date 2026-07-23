/**
 * Property-Based Tests — B23 业务层面控制（14 循环重做）
 *
 * Spec: .kiro/specs/b23-business-control-rework/
 * Task: 5.4
 *
 * Property 7: 适用性幂等 — applicableCycles(applicableCycles(x)) === applicableCycles(x)
 *             不适用循环恒不计入进度分母
 *
 * Property 8: wt-* 与 ct-* 独立命名空间 — 写入互不覆盖
 *             generateItemId 对 wt 和 ct 类型产生完全独立的 item_id，
 *             即使 cycleCode、index、field 全部相同，两个命名空间也不碰撞。
 *
 * **Validates: Requirements 5.5, 9.2**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  applicableCycles,
  generateItemId,
} from '../composables/useB23ProcessControl'
import { B23_CYCLES } from '../composables/b23CycleConfig'

// ─── Arbitraries ─────────────────────────────────────────────────────────────

const ALL_CYCLE_CODES = B23_CYCLES.map((c) => c.code)

/** Arbitrary cycle-like object with applicable boolean */
const arbCycleItem = fc.record({
  code: fc.constantFrom(...ALL_CYCLE_CODES),
  name: fc.string({ minLength: 1, maxLength: 20 }),
  applicable: fc.boolean(),
})

/** Arbitrary list of cycle items (1..20 items) */
const arbCycleList = fc.array(arbCycleItem, { minLength: 0, maxLength: 20 })

/** Arbitrary cycle code */
const arbCycleCode = fc.constantFrom(...ALL_CYCLE_CODES)

/** Arbitrary control index (1..30) */
const arbIndex = fc.integer({ min: 1, max: 30 })

/** Arbitrary field name (alphanumeric, non-empty) */
const arbFieldName = fc.stringOf(
  fc.constantFrom(...'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'.split('')),
  { minLength: 1, maxLength: 20 },
)

/** WT fields from the composable */
const WT_FIELD_NAMES = ['method', 'interviewee', 'procedure', 'evidence', 'result', 'asDesigned', 'deficiencyFound'] as const
const arbWtField = fc.constantFrom(...WT_FIELD_NAMES)

/** CT fields from the composable */
const CT_FIELD_NAMES = ['riskJudgment', 'testNature', 'testTiming', 'testScope', 'operatingEffective', 'deviation', 'substantiveImpact'] as const
const arbCtField = fc.constantFrom(...CT_FIELD_NAMES)

// ═══════════════════════════════════════════════════════════════════════════════
// Property 7: 适用性幂等（Idempotence）
// applicableCycles(applicableCycles(x)) === applicableCycles(x)
// 不适用循环恒不计入进度分母
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 Rework Property 7: 适用性幂等', () => {
  it('applicableCycles 幂等 — filter(filter(x)) === filter(x)', () => {
    fc.assert(
      fc.property(arbCycleList, (cycles) => {
        const once = applicableCycles(cycles)
        const twice = applicableCycles(once)

        // Idempotent: applying the filter twice yields the same result as once
        expect(twice).toEqual(once)
      }),
      { numRuns: 100 },
    )
  })

  it('applicableCycles 结果中所有元素 applicable === true', () => {
    fc.assert(
      fc.property(arbCycleList, (cycles) => {
        const result = applicableCycles(cycles)

        // Every item in the result must be applicable
        for (const item of result) {
          expect(item.applicable).toBe(true)
        }
      }),
      { numRuns: 100 },
    )
  })

  it('applicableCycles 结果是输入的子集（保持顺序）', () => {
    fc.assert(
      fc.property(arbCycleList, (cycles) => {
        const result = applicableCycles(cycles)

        // Result length <= input length
        expect(result.length).toBeLessThanOrEqual(cycles.length)

        // Result is a subsequence of input
        let j = 0
        for (let i = 0; i < cycles.length && j < result.length; i++) {
          if (cycles[i] === result[j]) j++
        }
        expect(j).toBe(result.length)
      }),
      { numRuns: 100 },
    )
  })

  it('不适用循环恒不计入进度分母（applicableCycles 排除全部 applicable=false）', () => {
    fc.assert(
      fc.property(arbCycleList, (cycles) => {
        const result = applicableCycles(cycles)
        const inapplicable = cycles.filter((c) => !c.applicable)

        // None of the inapplicable cycles should appear in the result
        for (const item of inapplicable) {
          expect(result).not.toContain(item)
        }
      }),
      { numRuns: 100 },
    )
  })

  it('全部 applicable=true 时，applicableCycles 返回原数组', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            code: fc.constantFrom(...ALL_CYCLE_CODES),
            name: fc.string({ minLength: 1, maxLength: 10 }),
            applicable: fc.constant(true),
          }),
          { minLength: 0, maxLength: 16 },
        ),
        (cycles) => {
          const result = applicableCycles(cycles)
          expect(result).toEqual(cycles)
        },
      ),
      { numRuns: 50 },
    )
  })

  it('全部 applicable=false 时，applicableCycles 返回空数组', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            code: fc.constantFrom(...ALL_CYCLE_CODES),
            name: fc.string({ minLength: 1, maxLength: 10 }),
            applicable: fc.constant(false),
          }),
          { minLength: 1, maxLength: 16 },
        ),
        (cycles) => {
          const result = applicableCycles(cycles)
          expect(result).toHaveLength(0)
        },
      ),
      { numRuns: 50 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 8: 穿行/控制测试结论分离（wt-* 与 ct-* 独立命名空间）
// 写入 wt-* 永不覆盖 ct-*，反之亦然
// ═══════════════════════════════════════════════════════════════════════════════

describe('B23 Rework Property 8: wt-*/ct-* 命名空间分离', () => {
  it('同 cycleCode、同 index、同 field → wt 与 ct 生成的 item_id 不同', () => {
    fc.assert(
      fc.property(arbCycleCode, arbIndex, arbFieldName, (code, idx, field) => {
        const wtId = generateItemId(code, 'wt', idx, undefined, field)
        const ctId = generateItemId(code, 'ct', idx, undefined, field)

        // They must be different
        expect(wtId).not.toBe(ctId)

        // wt contains '-wt-' segment, ct contains '-ct-' segment
        expect(wtId).toContain('-wt-')
        expect(ctId).toContain('-ct-')

        // wt does not contain '-ct-' and vice versa
        expect(wtId).not.toContain('-ct-')
        expect(ctId).not.toContain('-wt-')
      }),
      { numRuns: 100 },
    )
  })

  it('wt-* 和 ct-* 全组合不碰撞（穷举真实字段）', () => {
    fc.assert(
      fc.property(arbCycleCode, arbIndex, (code, idx) => {
        const wtIds = new Set<string>()
        const ctIds = new Set<string>()

        for (const f of WT_FIELD_NAMES) {
          wtIds.add(generateItemId(code, 'wt', idx, undefined, f))
        }
        for (const f of CT_FIELD_NAMES) {
          ctIds.add(generateItemId(code, 'ct', idx, undefined, f))
        }

        // No intersection between wt and ct ID sets
        for (const id of wtIds) {
          expect(ctIds.has(id)).toBe(false)
        }
        for (const id of ctIds) {
          expect(wtIds.has(id)).toBe(false)
        }
      }),
      { numRuns: 50 },
    )
  })

  it('写入 wt-* 不影响 ct-* 存储（模拟独立写）', () => {
    fc.assert(
      fc.property(arbCycleCode, arbIndex, arbWtField, arbCtField, (code, idx, wtField, ctField) => {
        // Simulated storage (like checklist_responses Map)
        const store = new Map<string, { conclusion: string | null; remark: string | null }>()

        // Write a ct value first
        const ctId = generateItemId(code, 'ct', idx, undefined, ctField)
        store.set(ctId, { conclusion: '有效', remark: '测试数据' })

        // Write a wt value (should not touch ct)
        const wtId = generateItemId(code, 'wt', idx, undefined, wtField)
        store.set(wtId, { conclusion: '是', remark: '穿行数据' })

        // Verify ct is unchanged
        const ctStored = store.get(ctId)
        expect(ctStored).toBeDefined()
        expect(ctStored!.conclusion).toBe('有效')
        expect(ctStored!.remark).toBe('测试数据')

        // Verify wt is stored correctly
        const wtStored = store.get(wtId)
        expect(wtStored).toBeDefined()
        expect(wtStored!.conclusion).toBe('是')
        expect(wtStored!.remark).toBe('穿行数据')
      }),
      { numRuns: 100 },
    )
  })

  it('写入 ct-* 不影响 wt-* 存储（模拟独立写）', () => {
    fc.assert(
      fc.property(arbCycleCode, arbIndex, arbWtField, arbCtField, (code, idx, wtField, ctField) => {
        // Simulated storage
        const store = new Map<string, { conclusion: string | null; remark: string | null }>()

        // Write a wt value first
        const wtId = generateItemId(code, 'wt', idx, undefined, wtField)
        store.set(wtId, { conclusion: '否', remark: '穿行失败数据' })

        // Write a ct value (should not touch wt)
        const ctId = generateItemId(code, 'ct', idx, undefined, ctField)
        store.set(ctId, { conclusion: '无效', remark: '控制测试数据' })

        // Verify wt is unchanged
        const wtStored = store.get(wtId)
        expect(wtStored).toBeDefined()
        expect(wtStored!.conclusion).toBe('否')
        expect(wtStored!.remark).toBe('穿行失败数据')

        // Verify ct is stored correctly
        const ctStored = store.get(ctId)
        expect(ctStored).toBeDefined()
        expect(ctStored!.conclusion).toBe('无效')
        expect(ctStored!.remark).toBe('控制测试数据')
      }),
      { numRuns: 100 },
    )
  })

  it('wt-* 与 ct-* ID 前缀均为 B23-{code}-', () => {
    fc.assert(
      fc.property(arbCycleCode, arbIndex, arbWtField, arbCtField, (code, idx, wtField, ctField) => {
        const wtId = generateItemId(code, 'wt', idx, undefined, wtField)
        const ctId = generateItemId(code, 'ct', idx, undefined, ctField)

        const expectedPrefix = `B23-${code}-`
        expect(wtId.startsWith(expectedPrefix)).toBe(true)
        expect(ctId.startsWith(expectedPrefix)).toBe(true)
      }),
      { numRuns: 50 },
    )
  })

  it('跨所有 16 循环，wt 与 ct 全组合 item_id 集合无交集', () => {
    // Exhaustive check: all 16 cycles × indices 1..3 × all fields
    const allWtIds = new Set<string>()
    const allCtIds = new Set<string>()

    for (const code of ALL_CYCLE_CODES) {
      for (let idx = 1; idx <= 3; idx++) {
        for (const f of WT_FIELD_NAMES) {
          allWtIds.add(generateItemId(code, 'wt', idx, undefined, f))
        }
        for (const f of CT_FIELD_NAMES) {
          allCtIds.add(generateItemId(code, 'ct', idx, undefined, f))
        }
      }
    }

    // Zero intersection
    for (const id of allWtIds) {
      expect(allCtIds.has(id)).toBe(false)
    }
    // Count sanity: 16 cycles × 3 indices × 7 fields each
    expect(allWtIds.size).toBe(ALL_CYCLE_CODES.length * 3 * WT_FIELD_NAMES.length)
    expect(allCtIds.size).toBe(ALL_CYCLE_CODES.length * 3 * CT_FIELD_NAMES.length)
  })
})
