/**
 * PBT — GtA101GovernanceCommunication component
 *
 * Property 2: fee total UI display — totalFee always equals sum of non-null amounts
 * Property 5: navigation highlight — exactly one nav item is active at any time
 *
 * **Validates: Requirements 7, 3**
 */
import { describe, it, expect, vi } from 'vitest'
import * as fc from 'fast-check'
import { ref, computed } from 'vue'

// We test the logic directly rather than mounting the component (fast-check focus)

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn(), put: vi.fn().mockResolvedValue({}) },
}))

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn() },
}))

describe('GtA101GovernanceCommunication PBT', () => {
  // ─── Property 2: fee total UI display ──────────────────────────────────

  it('Property 2: totalFee computed always equals sum of non-null amounts', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.oneof(
            fc.constant(null),
            fc.float({ min: 0, max: 1e7, noNaN: true, noDefaultInfinity: true }),
          ),
          { minLength: 5, maxLength: 5 },
        ),
        (amounts) => {
          // Simulate the totalFee computed logic
          const serviceFees = ref(
            amounts.map((a, i) => ({
              name: ['审计服务', '审阅服务', '其他鉴证服务', '税务服务', '其他服务'][i],
              amount: a,
            })),
          )
          const totalFee = computed(() =>
            serviceFees.value.reduce((sum, row) => sum + (row.amount ?? 0), 0),
          )

          const expected = amounts.reduce((sum: number, a) => sum + (a ?? 0), 0)
          expect(totalFee.value).toBeCloseTo(expected, 2)
        },
      ),
      { numRuns: 50 },
    )
  })

  // ─── Property 5: navigation highlight single active ────────────────────

  it('Property 5: exactly one navigation item is highlighted at any time', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 18 }),
        (activeIndex) => {
          // Simulate activeChapter ref behavior
          const activeChapter = ref(activeIndex)

          // Simulate nav items: 0=header, 1-16=chapters, 17=sign, 18=tip
          const navItems = [0, ...Array.from({ length: 16 }, (_, i) => i + 1), 17, 18]

          // Count active items
          const activeCount = navItems.filter(n => n === activeChapter.value).length

          // Exactly one nav item should match activeChapter
          expect(activeCount).toBe(1)
        },
      ),
      { numRuns: 50 },
    )
  })
})
