/**
 * Property 6: source_label 分割正确性
 *
 * For any source_label string containing + delimiters (e.g., "A15+A15-1+B50"),
 * splitting on + SHALL produce exactly N segments where N equals the count of +
 * characters plus one, and each segment SHALL be a non-empty string that can be
 * independently parsed for wp_code patterns.
 *
 * **Validates: Requirements 2.4**
 *
 * Feature: a17-summary-enhancement, Property 6: source_label 分割正确性
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { parseSourceLabel } from '@/composables/useWpCodeParser'

// ─── 生成器 ──────────────────────────────────────────────────────────────────────

/** 生成单个非空 segment（不含 + 字符） */
const SEG_CHARS = 'ABCDEFGHIJKLMNOPQRS0123456789-'.split('')
const segmentArb = fc.array(fc.constantFrom(...SEG_CHARS), { minLength: 1, maxLength: 10 })
  .map((chars) => chars.join(''))

/** 生成由 + 分隔的 source_label */
const sourceLabelArb = fc.array(segmentArb, { minLength: 1, maxLength: 6 })
  .map((segments) => ({
    label: segments.join('+'),
    segments,
    plusCount: segments.length - 1,
  }))

// ─── Property Tests ──────────────────────────────────────────────────────────

describe('parseSourceLabel — Property 6: source_label 分割正确性', () => {
  it('P6-a: 分割后段数等于 + 数量加一', () => {
    fc.assert(
      fc.property(sourceLabelArb, ({ label, plusCount }) => {
        const result = parseSourceLabel(label)
        expect(result).toHaveLength(plusCount + 1)
      }),
      { numRuns: 100 },
    )
  })

  it('P6-b: 每个分割后的 segment 都是非空字符串', () => {
    fc.assert(
      fc.property(sourceLabelArb, ({ label }) => {
        const result = parseSourceLabel(label)
        for (const seg of result) {
          expect(seg.length).toBeGreaterThan(0)
        }
      }),
      { numRuns: 100 },
    )
  })

  it('P6-c: 分割结果与原始 segments 一致', () => {
    fc.assert(
      fc.property(sourceLabelArb, ({ label, segments }) => {
        const result = parseSourceLabel(label)
        expect(result).toEqual(segments)
      }),
      { numRuns: 100 },
    )
  })

  it('P6-d: 重新用 + 拼接分割结果等于原始 label', () => {
    fc.assert(
      fc.property(sourceLabelArb, ({ label }) => {
        const result = parseSourceLabel(label)
        expect(result.join('+')).toBe(label)
      }),
      { numRuns: 100 },
    )
  })

  it('P6-e: 空输入返回空数组', () => {
    expect(parseSourceLabel('')).toEqual([])
  })

  it('P6-f: 无 + 分隔符时返回单元素数组', () => {
    fc.assert(
      fc.property(segmentArb, (seg) => {
        const result = parseSourceLabel(seg)
        expect(result).toEqual([seg])
      }),
      { numRuns: 50 },
    )
  })
})
