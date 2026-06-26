/**
 * Property 5: Ref_Chip 可用性由 wp_index 决定
 *
 * Feature: a17-summary-enhancement
 * **Validates: Requirements 2.3, 6.3, 6.4**
 *
 * For any parsed wp_code and any project wp_index set, the Ref_Chip SHALL be
 * in disabled state if and only if the wp_code is NOT present in the project's
 * wp_index. Conversely, if the wp_code IS in the wp_index, the chip SHALL be
 * enabled with navigation capability.
 */

import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import { resolveWpCodeState } from '@/composables/useA17Navigation'
import type { WpIndexItem } from '@/services/workpaperApi'

// ─── Generators ───

/** 生成有效的 wp_code (A-S + 1~2位数字 + 可选-数字 + 可选大写字母) */
const wpCodeArb = fc.tuple(
  fc.constantFrom(...'ABCDEFGHIJKLMNOPQRS'.split('')),
  fc.integer({ min: 1, max: 50 }),
  fc.option(fc.integer({ min: 1, max: 9 }), { nil: undefined }),
  fc.option(fc.constantFrom(...'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('')), { nil: undefined }),
).map(([letter, num, sub, suffix]) => {
  let code = `${letter}${num}`
  if (sub !== undefined) code += `-${sub}`
  if (suffix !== undefined) code += suffix
  return code
})

/** 生成一个 WpIndexItem */
const wpIndexItemArb = (wpCode: string): fc.Arbitrary<WpIndexItem> =>
  fc.record({
    id: fc.uuid(),
    wp_code: fc.constant(wpCode),
    wp_name: fc.string({ minLength: 1, maxLength: 20 }),
    audit_cycle: fc.constantFrom('A', 'B', 'C', 'D', null),
    status: fc.constantFrom('draft', 'reviewed', null),
    assigned_to: fc.option(fc.uuid(), { nil: null }),
    reviewer: fc.option(fc.uuid(), { nil: null }),
  })

/** 生成 wp_index 列表（包含若干随机 wp_code 项） */
const wpIndexArb = fc.array(wpCodeArb, { minLength: 0, maxLength: 10 })
  .chain((codes) => {
    const uniqueCodes = [...new Set(codes)]
    return fc.tuple(
      ...uniqueCodes.map((code) => wpIndexItemArb(code))
    ).map((items) => items as WpIndexItem[])
  })

// ─── Property Test ───

describe('Property 5: Ref_Chip 可用性由 wp_index 决定', () => {
  it('wp_code 在 wp_index 中 → enabled; 不在 → disabled', () => {
    fc.assert(
      fc.property(
        wpCodeArb,
        wpIndexArb,
        (targetCode, wpIndex) => {
          const state = resolveWpCodeState(targetCode, wpIndex)
          const existsInIndex = wpIndex.some((item) => item.wp_code === targetCode)

          if (existsInIndex) {
            // wp_code 存在于 wp_index → enabled, 有 wpId
            expect(state.exists).toBe(true)
            expect(state.disabled).toBe(false)
            expect(state.wpId).not.toBeNull()
          } else {
            // wp_code 不存在 → disabled
            expect(state.exists).toBe(false)
            expect(state.disabled).toBe(true)
            expect(state.wpId).toBeNull()
            expect(state.tooltip).toBe('该底稿在当前项目中不存在')
          }
        }
      ),
      { numRuns: 100 }
    )
  })
})
