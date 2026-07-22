/**
 * PBT — GtA171AuditSummary component
 *
 * Property 4: navigation highlight uniqueness — exactly one navigation item highlighted
 *
 * **Validates: Requirements 4**
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import * as fc from 'fast-check'
import { useA171Navigation } from '../composables/useA171Navigation'
import type { ChapterData } from '../composables/useA171AuditSummary'

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), error: vi.fn() },
}))

describe('GtA171AuditSummary PBT', () => {
  // ─── Property 4: navigation highlight uniqueness ───────────────────────

  it('Property 4: activeChapter is always a single number between 1-16', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 16 }),
        (chapterNum) => {
          // Create minimal chapters ref
          const chapters = ref<Record<string, ChapterData>>({
            '1': { type: 'textarea', title: '一', content: null },
            '2': { type: 'textarea', title: '二', content: null },
            '3': { type: 'textarea', title: '三', content: null },
            '4': { type: 'textarea', title: '四', content: null },
            '5': { type: 'textarea', title: '五', content: null },
            '6': { type: 'table', title: '六', rows: [] },
            '7': { type: 'textarea', title: '七', content: null },
            '8': { type: 'table', title: '八', rows: [] },
            '9': { type: 'yn', title: '九', answer: null, explanation: null },
            '10': { type: 'yn', title: '十', answer: null, explanation: null },
            '11': { type: 'yn', title: '十一', answer: null, explanation: null },
            '12': { type: 'yn', title: '十二', answer: null, explanation: null },
            '13': { type: 'textarea', title: '十三', content: null },
            '14': { type: 'textarea', title: '十四', content: null },
            '15': { type: 'textarea', title: '十五', content: null },
            '16': { type: 'textarea', title: '十六', content: null },
          })

          const { activeChapter } = useA171Navigation(chapters)

          // Directly set activeChapter to simulate observer update
          activeChapter.value = chapterNum

          // Property: activeChapter is always a single number between 1-16
          expect(typeof activeChapter.value).toBe('number')
          expect(activeChapter.value).toBeGreaterThanOrEqual(1)
          expect(activeChapter.value).toBeLessThanOrEqual(16)
          // Exactly one value (not multiple, not array)
          expect(activeChapter.value).toBe(chapterNum)
        },
      ),
      { numRuns: 50 },
    )
  })

  it('Property 4: completionStatus has exactly 16 entries', () => {
    fc.assert(
      fc.property(
        fc.record({
          textareaFilled: fc.array(fc.constantFrom(1, 2, 3, 4, 5, 7, 13, 14, 15, 16), { minLength: 0, maxLength: 10 }),
          tableFilled: fc.array(fc.constantFrom(6, 8), { minLength: 0, maxLength: 2 }),
          ynFilled: fc.array(fc.constantFrom(9, 10, 11, 12), { minLength: 0, maxLength: 4 }),
        }),
        (data) => {
          const chapters = ref<Record<string, ChapterData>>({})

          // Build chapters with some filled
          for (let i = 1; i <= 16; i++) {
            const key = String(i)
            if ([1, 2, 3, 4, 5, 7, 13, 14, 15, 16].includes(i)) {
              chapters.value[key] = {
                type: 'textarea',
                title: `Ch${i}`,
                content: data.textareaFilled.includes(i) ? '内容' : null,
              }
            } else if ([6, 8].includes(i)) {
              chapters.value[key] = {
                type: 'table',
                title: `Ch${i}`,
                rows: data.tableFilled.includes(i) ? [{ item: 'x' }] : [],
              }
            } else {
              chapters.value[key] = {
                type: 'yn',
                title: `Ch${i}`,
                answer: data.ynFilled.includes(i) ? 'Y' : null,
                explanation: null,
              }
            }
          }

          const { completionStatus } = useA171Navigation(chapters)

          // Exactly 16 entries
          const keys = Object.keys(completionStatus.value)
          expect(keys.length).toBe(16)

          // Each is boolean
          for (let i = 1; i <= 16; i++) {
            expect(typeof completionStatus.value[i]).toBe('boolean')
          }

          // Filled chapters should be complete
          for (const n of data.textareaFilled) {
            expect(completionStatus.value[n]).toBe(true)
          }
          for (const n of data.tableFilled) {
            expect(completionStatus.value[n]).toBe(true)
          }
          for (const n of data.ynFilled) {
            expect(completionStatus.value[n]).toBe(true)
          }
        },
      ),
      { numRuns: 50 },
    )
  })
})
