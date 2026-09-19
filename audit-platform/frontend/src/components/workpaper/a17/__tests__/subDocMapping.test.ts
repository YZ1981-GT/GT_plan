/**
 * Property 12: 子文档导航可用性映射
 *
 * Feature: a17-summary-enhancement
 * **Validates: Requirements 6.3, 6.4, 6.5**
 */

import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import { mapSubDocAvailability, SUB_DOC_DEFINITIONS } from '../subDocMapping'

// ─── Generators ───

/** A17 子文档 wp_code 集合（KAM 实物为 A17-2-1；核对表可用 A17-5 或 A17-5-*） */
const a17SubCodes = ['A17-2-1', 'A17-3', 'A17-4', 'A17-5', 'A17-5-1', 'A17-6', 'A17-7']

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

function expectExists(
  defCode: string,
  wpIndex: Array<{ wp_code: string; wp_id: string }>,
): boolean {
  if (defCode === 'A17-5') {
    return wpIndex.some((i) => i.wp_code === 'A17-5' || i.wp_code.startsWith('A17-5-'))
  }
  return wpIndex.some((i) => i.wp_code === defCode)
}

// ─── Property Tests ───

describe('Property 12: 子文档导航可用性映射', () => {
  it('结果始终包含固定 6 个子文档条目', () => {
    fc.assert(
      fc.property(wpIndexArb, (wpIndex) => {
        const result = mapSubDocAvailability(wpIndex)
        expect(result).toHaveLength(6)
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

        for (const item of result) {
          const shouldExist = expectExists(item.wp_code, wpIndex)
          expect(item.exists).toBe(shouldExist)
          if (shouldExist) {
            expect(item.wp_id).not.toBeNull()
          } else {
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
        for (const item of result) {
          expect(item.exists).toBe(expectExists(item.wp_code, wpIndex))
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

  it('A17-5-1 存在时 A17-5 导航标记为可用', () => {
    const result = mapSubDocAvailability([
      { wp_code: 'A17-5-1', wp_id: 'wp-551' },
    ])
    const a175 = result.find((r) => r.wp_code === 'A17-5')
    expect(a175?.exists).toBe(true)
    expect(a175?.wp_id).toBe('wp-551')
  })
})
