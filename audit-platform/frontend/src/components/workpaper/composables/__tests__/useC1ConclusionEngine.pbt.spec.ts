/**
 * useC1ConclusionEngine.pbt.spec.ts — C1 整体结论点选/自动建议/回写事件 属性测试（Task 7.3）
 *
 * Spec: .kiro/specs/c1-entity-level-control/  Task 7.3
 *
 * 覆盖 design 补充 Correctness Properties：
 *   - Property P7 点选值合法性：任意点选字段保存值必属于该字段选项枚举（无自由文本注入）。
 *       **Validates: Requirements 9.1, 11.3**
 *   - Property P9 结论回写事件正确性：整体结论变更仅在新旧值不同时发布事件。
 *       **Validates: Requirements 11.1, 11.4**
 *
 * Property P8（OCR merge 非破坏性）已在 __tests__/useC1SampleEngineOcr.pbt.spec.ts 覆盖，本文件不重复。
 *
 * 纯函数 PBT：直接验证 useC1ConclusionEngine，无组件挂载、无网络。每 property 跑 25 runs。
 */
import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import {
  FREQ_OPTIONS,
  TEST_METHOD_OPTIONS,
  CONCLUSION_OPTIONS,
  sanitizeEnumValue,
  sanitizeMultiEnum,
  isValidConclusion,
  suggestOverallConclusion,
  normalizeConclusion,
  shouldPublishConclusion,
} from '../useC1ConclusionEngine'

// 所有点选枚举集合（P7 覆盖：频率/测试方法/结论）+ 任意"自由文本"噪声
const ALL_OPTION_SETS: readonly (readonly string[])[] = [
  FREQ_OPTIONS,
  TEST_METHOD_OPTIONS,
  CONCLUSION_OPTIONS,
]

/** 生成器：合法枚举值 ∪ 自由文本噪声 ∪ 非字符串 */
const noisyValueArb = fc.oneof(
  fc.constantFrom(...FREQ_OPTIONS, ...TEST_METHOD_OPTIONS, ...CONCLUSION_OPTIONS),
  fc.string(),
  fc.constantFrom('有效 ', ' 无效', 'DROP TABLE', '<script>', '有效x', '', '   '),
  fc.constant(null),
  fc.constant(undefined),
  fc.integer(),
  fc.boolean(),
)

// ══════════════════════════════════════════════════════════════════════════════
// Property P7: 点选值合法性（无自由文本注入）
// ══════════════════════════════════════════════════════════════════════════════

describe('Feature: c1-entity-level-control, Property P7: 点选值合法性', () => {
  it('sanitizeEnumValue 对任意输入返回「枚举值 或 null」，绝不产出非法/自由文本', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...ALL_OPTION_SETS),
        noisyValueArb,
        (options, value) => {
          const out = sanitizeEnumValue(options, value)
          if (out !== null) {
            // 非 null 时必属于该字段枚举
            expect(options).toContain(out)
            // 且原样等于输入（未被篡改）
            expect(out).toBe(value)
          } else {
            // null 当且仅当输入不是该枚举内的字符串
            const legal = typeof value === 'string' && options.includes(value)
            expect(legal).toBe(false)
          }
        },
      ),
      { numRuns: 25 },
    )
  })

  it('sanitizeMultiEnum 结果恒为枚举子集、去重、且不含自由文本', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...ALL_OPTION_SETS),
        fc.array(noisyValueArb, { maxLength: 12 }),
        (options, arr) => {
          const out = sanitizeMultiEnum(options, arr)
          // 子集
          for (const v of out) expect(options).toContain(v)
          // 去重
          expect(new Set(out).size).toBe(out.length)
          // 输入中所有合法成员都被保留（无遗漏）
          const legalInput = new Set(
            arr.filter((v): v is string => typeof v === 'string' && options.includes(v)),
          )
          expect(new Set(out)).toEqual(legalInput)
        },
      ),
      { numRuns: 25 },
    )
  })

  it('非数组输入 sanitizeMultiEnum 一律返回空数组', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...ALL_OPTION_SETS),
        fc.oneof(fc.string(), fc.integer(), fc.constant(null), fc.constant(undefined), fc.boolean()),
        (options, notArr) => {
          expect(sanitizeMultiEnum(options, notArr)).toEqual([])
        },
      ),
      { numRuns: 25 },
    )
  })

  it('自动建议的整体结论恒为合法结论枚举或 null（建议值本身也满足 P7 合法性）', () => {
    fc.assert(
      fc.property(
        fc.array(noisyValueArb, { maxLength: 10 }),
        (raw) => {
          const s = suggestOverallConclusion(raw as (string | null | undefined)[])
          if (s !== null) {
            expect(CONCLUSION_OPTIONS).toContain(s)
            expect(isValidConclusion(s)).toBe(true)
          }
        },
      ),
      { numRuns: 25 },
    )
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// 自动建议就低聚合口径（Requirement 11.3）
// ══════════════════════════════════════════════════════════════════════════════

describe('Feature: c1-entity-level-control, suggestOverallConclusion 就低聚合', () => {
  it('存在「无效」→ 建议「无效」（一票否决，忽略其他）', () => {
    fc.assert(
      fc.property(
        fc.array(fc.constantFrom<string>('有效', '部分有效', '无效'), { minLength: 1, maxLength: 9 }),
        (arr) => {
          const s = suggestOverallConclusion(arr)
          if (arr.includes('无效')) expect(s).toBe('无效')
          else if (arr.includes('部分有效')) expect(s).toBe('部分有效')
          else expect(s).toBe('有效')
        },
      ),
      { numRuns: 25 },
    )
  })

  it('全空 / 全非法输入 → 返回 null（无可建议）', () => {
    fc.assert(
      fc.property(
        fc.array(fc.oneof(fc.constant(null), fc.constant(''), fc.constant('  '), fc.string().filter((s) => !CONCLUSION_OPTIONS.includes(s))), { maxLength: 8 }),
        (arr) => {
          expect(suggestOverallConclusion(arr as (string | null)[])).toBeNull()
        },
      ),
      { numRuns: 25 },
    )
  })

  it('空白/非法项被忽略，不影响合法项聚合结果', () => {
    const s = suggestOverallConclusion(['有效', '', null, 'xxx', '部分有效', '   '])
    expect(s).toBe('部分有效')
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// Property P9: 结论回写事件正确性（仅在新旧值不同时发布）
// ══════════════════════════════════════════════════════════════════════════════

describe('Feature: c1-entity-level-control, Property P9: 结论回写事件正确性', () => {
  const conclusionOrEmptyArb = fc.oneof(
    fc.constantFrom<string>('有效', '部分有效', '无效'),
    fc.constant(''),
    fc.constant('   '),
    fc.constant(null),
    fc.constant(undefined),
  )

  it('shouldPublishConclusion ⟺ 归一化后新旧值不等', () => {
    fc.assert(
      fc.property(conclusionOrEmptyArb, conclusionOrEmptyArb, (oldV, newV) => {
        const expected = normalizeConclusion(oldV) !== normalizeConclusion(newV)
        expect(shouldPublishConclusion(oldV, newV)).toBe(expected)
      }),
      { numRuns: 25 },
    )
  })

  it('新旧归一化相等（含 null/空白互等）时绝不发布', () => {
    fc.assert(
      fc.property(
        fc.oneof(fc.constant(null), fc.constant(undefined), fc.constant(''), fc.constant('  ')),
        fc.oneof(fc.constant(null), fc.constant(undefined), fc.constant(''), fc.constant('   ')),
        (oldV, newV) => {
          // 两者归一化后都为空串 → 相等 → 不发布
          expect(shouldPublishConclusion(oldV, newV)).toBe(false)
        },
      ),
      { numRuns: 25 },
    )
  })

  it('归一化幂等：normalize(normalize(x)) == normalize(x)', () => {
    fc.assert(
      fc.property(conclusionOrEmptyArb, (v) => {
        const once = normalizeConclusion(v)
        expect(normalizeConclusion(once)).toBe(once)
      }),
      { numRuns: 25 },
    )
  })

  it('模拟连续 set：发布次数 == 实际值变更次数（无重复事件）', () => {
    fc.assert(
      fc.property(
        fc.array(conclusionOrEmptyArb, { maxLength: 30 }),
        (seq) => {
          let current = ''
          let publishes = 0
          let expectedChanges = 0
          for (const next of seq) {
            const nextNorm = normalizeConclusion(next)
            if (nextNorm !== current) expectedChanges++
            if (shouldPublishConclusion(current, next)) publishes++
            current = nextNorm
          }
          expect(publishes).toBe(expectedChanges)
        },
      ),
      { numRuns: 25 },
    )
  })
})
