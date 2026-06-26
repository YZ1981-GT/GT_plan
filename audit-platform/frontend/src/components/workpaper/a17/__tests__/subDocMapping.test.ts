/**
 * Property 12: 子文档导航可用性映射
 *
 * Feature: a17-summary-enhancement
 * **Validates: Requirements 6.3, 6.4, 6.5**
 *
 * For any project wp_index containing a subset of A17-series wp_codes (A17-2 through A17-7),
 * the Sub_Doc_Navigator SHALL mark each sub-document as "已创建" (exists=true, navigable) if
 * its wp_code appears in wp_index, and "不适用/未创建" (exists=false, disabled) otherwise.
 */

import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import { mapSubDocAvailability, SUB_DOC_DEFINITIONS } from '../subDocMapping'

// ─── Generators ───

/** A17 子文档 wp_code 集合 */
const a17SubCodes = ['A17-2', 'A17-3', 'A17-4', 'A17-5', 'A17-6', 'A17-7']

/** 生成随机子集的 A17-x wp_codes 作为 wp_index */
const wpIndexArb = fc.subarray(a17SubCodes).chain((codes) =>
  fc.tuple(
    ...codes.map((code) =>
      fc.uuid().map((id) => ({ wp_code: code, wp_id: id }))
    )
  ).map((items) => items as Array<{ wp_code: string; wp_id: string }>)
)

/** 生成含有非 A17 项目的混合 wp_index */
const mixedWpIndexArb = fc.tuple(
  wpIndexArb,
  fc.array(
    fc.tuple(
      fc.constantFrom('A1', 'B50', 'D2-1', 'F3A', 'A17-1'),
      fc.uuid(),
    ).map(([code, id]) => ({ wp_code: code, wp_id: id })),
    { minLength: 0, maxLength: 5 }
  ),
).map(([a17Items, otherItems]) => [...a17Items, ...otherItems])

// ─── Property Tests ───

describe('Property 12: 子文档导航可用性映射', () => {
  it('结果始终包含固定 6 个子文档条目', () => {
    fc.assert(
      fc.property(wpIndexArb, (wpIndex) => {
        const result = mapSubDocAvailability(wpIndex)
        expect(result).toHaveLength(6)
        // 验证顺序和 wp_code
        for (let i = 0; i < 6; i++) {
          expect(result[i].wp_code).toBe(SUB_DOC_DEFINITIONS[i].wp_code)
          expect(result[i].label).toBe(SUB_DOC_DEFINITIONS[i].label)
        }
      }),
      { numRuns: 100 }
    )
  })

  it('wp_code 在 wp_index 中 → exists=true + wp_id 非空', () => {
    fc.assert(
      fc.property(wpIndexArb, (wpIndex) => {
        const result = mapSubDocAvailability(wpIndex)
        const existingCodes = new Set(wpIndex.map((item) => item.wp_code))

        for (const item of result) {
          if (existingCodes.has(item.wp_code)) {
            expect(item.exists).toBe(true)
            expect(item.wp_id).not.toBeNull()
          } else {
            expect(item.exists).toBe(false)
            expect(item.wp_id).toBeNull()
          }
        }
      }),
      { numRuns: 100 }
    )
  })

  it('非 A17 子文档的 wp_index 条目不影响结果', () => {
    fc.assert(
      fc.property(mixedWpIndexArb, (wpIndex) => {
        const result = mapSubDocAvailability(wpIndex)

        // 只有 A17-2~A17-7 的条目影响 exists
        const a17Codes = new Set(
          wpIndex
            .filter((item) => a17SubCodes.includes(item.wp_code))
            .map((item) => item.wp_code)
        )

        for (const item of result) {
          expect(item.exists).toBe(a17Codes.has(item.wp_code))
        }
      }),
      { numRuns: 100 }
    )
  })

  it('空 wp_index → 所有子文档 exists=false', () => {
    const result = mapSubDocAvailability([])
    for (const item of result) {
      expect(item.exists).toBe(false)
      expect(item.wp_id).toBeNull()
    }
  })
})
