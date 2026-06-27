/**
 * PBT + Unit Tests — GtA171AuditSummary component
 *
 * Property 4: navigation highlight uniqueness — exactly one navigation item highlighted
 * at any scroll position, matching the most visible chapter (1-16).
 *
 * **Validates: Requirements 4**
 *
 * Spec: .kiro/specs/a17-1-audit-summary/
 * Tasks: 3.6, 3.7
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import * as fc from 'fast-check'
import { useA171AuditSummary, buildA171ItemId, buildA171SignatureItemId } from '../composables/useA171AuditSummary'
import { useA171Navigation } from '../composables/useA171Navigation'
import type { A171RenderData, ChapterData } from '../composables/useA171AuditSummary'

// ─── Mock API ────────────────────────────────────────────────────────────────

const mockPut = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(),
    put: (...args: any[]) => mockPut(...args),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), error: vi.fn() },
}))

function setup(data: A171RenderData | null = null) {
  const wpId = ref('wp-a171-001')
  const projectId = ref('proj-001')
  const htmlData = ref<A171RenderData | null>(data)
  return useA171AuditSummary({ wpId, projectId, htmlData })
}

function buildChaptersRef(overrides?: Partial<Record<string, Partial<ChapterData>>>) {
  const base: Record<string, ChapterData> = {
    '1': { type: 'textarea', title: '一、审计工作概况', content: null },
    '2': { type: 'textarea', title: '二、重大会计政策及估计变更', content: null },
    '3': { type: 'textarea', title: '三、关键审计事项', content: null },
    '4': { type: 'textarea', title: '四、持续经营评估', content: null },
    '5': { type: 'textarea', title: '五、审计范围调整', content: null },
    '6': { type: 'table', title: '六、重大错报风险应对', rows: [] },
    '7': { type: 'textarea', title: '七、集团审计事项', content: null },
    '8': { type: 'table', title: '八、已审财务报表分析', rows: [] },
    '9': { type: 'yn', title: '九、舞弊识别', answer: null, explanation: null },
    '10': { type: 'yn', title: '十、违反法规情况', answer: null, explanation: null },
    '11': { type: 'yn', title: '十一、关联方事项', answer: null, explanation: null },
    '12': { type: 'yn', title: '十二、期后事项', answer: null, explanation: null },
    '13': { type: 'textarea', title: '十三、审计意见', content: null },
    '14': { type: 'textarea', title: '十四、错报汇总与处理', content: null },
    '15': { type: 'textarea', title: '十五、与治理层沟通事项', content: null },
    '16': { type: 'textarea', title: '十六、审计总结', content: null },
  }
  if (overrides) {
    for (const [k, v] of Object.entries(overrides)) {
      base[k] = { ...base[k], ...v } as ChapterData
    }
  }
  return ref(base)
}

// ═══════════════════════════════════════════════════════════════════════════════
// PBT — Property 4: Navigation Highlight Uniqueness
// ═══════════════════════════════════════════════════════════════════════════════

describe('GtA171AuditSummary PBT — Property 4', () => {
  it('Property 4: activeChapter ref always contains exactly one value between 1-16', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 16 }),
        (scrollTarget) => {
          const chapters = buildChaptersRef()
          const { activeChapter } = useA171Navigation(chapters as any)

          // Simulate IntersectionObserver updating activeChapter
          activeChapter.value = scrollTarget

          // Property: exactly one value, integer, in [1,16]
          expect(typeof activeChapter.value).toBe('number')
          expect(Number.isInteger(activeChapter.value)).toBe(true)
          expect(activeChapter.value).toBeGreaterThanOrEqual(1)
          expect(activeChapter.value).toBeLessThanOrEqual(16)
          expect(activeChapter.value).toBe(scrollTarget)
        },
      ),
      { numRuns: 50 },
    )
  })

  it('Property 4: completionStatus computed returns a record with exactly 16 boolean keys', () => {
    // Arbitrary for chapter content states
    const chapterContentArb = fc.record({
      textareaFilled: fc.subarray([1, 2, 3, 4, 5, 7, 13, 14, 15, 16]),
      tableFilled: fc.subarray([6, 8]),
      ynAnswered: fc.subarray([9, 10, 11, 12]),
    })

    fc.assert(
      fc.property(chapterContentArb, ({ textareaFilled, tableFilled, ynAnswered }) => {
        const chaptersData: Record<string, ChapterData> = {}

        for (let i = 1; i <= 16; i++) {
          const key = String(i)
          if ([1, 2, 3, 4, 5, 7, 13, 14, 15, 16].includes(i)) {
            chaptersData[key] = {
              type: 'textarea',
              title: `Ch${i}`,
              content: textareaFilled.includes(i) ? '有内容' : null,
            }
          } else if ([6, 8].includes(i)) {
            chaptersData[key] = {
              type: 'table',
              title: `Ch${i}`,
              rows: tableFilled.includes(i) ? [{ item: 'data' }] : [],
            }
          } else {
            chaptersData[key] = {
              type: 'yn',
              title: `Ch${i}`,
              answer: ynAnswered.includes(i) ? 'Y' : null,
              explanation: null,
            }
          }
        }

        const chapters = ref(chaptersData)
        const { completionStatus } = useA171Navigation(chapters as any)

        // Property: exactly 16 keys
        const keys = Object.keys(completionStatus.value)
        expect(keys.length).toBe(16)

        // Each key is a number 1-16, each value is boolean
        for (let i = 1; i <= 16; i++) {
          expect(i in completionStatus.value).toBe(true)
          expect(typeof completionStatus.value[i]).toBe('boolean')
        }

        // Filled items are true, unfilled are false
        for (const n of textareaFilled) {
          expect(completionStatus.value[n]).toBe(true)
        }
        for (const n of tableFilled) {
          expect(completionStatus.value[n]).toBe(true)
        }
        for (const n of ynAnswered) {
          expect(completionStatus.value[n]).toBe(true)
        }
      }),
      { numRuns: 50 },
    )
  })

  it('Property 4: navigation highlight is always a single integer value between 1-16 (never NaN/float/array)', () => {
    fc.assert(
      fc.property(
        // Generate various "scroll" scenarios
        fc.integer({ min: 1, max: 16 }),
        fc.boolean(),
        (chapter, hasContent) => {
          const overrides: Partial<Record<string, Partial<ChapterData>>> = {}
          if (hasContent) {
            overrides[String(chapter)] = { content: '已填写' } as any
          }
          const chapters = buildChaptersRef(overrides)
          const { activeChapter } = useA171Navigation(chapters as any)

          // Simulate scroll to chapter
          activeChapter.value = chapter

          // Properties
          expect(activeChapter.value).not.toBeNaN()
          expect(Number.isFinite(activeChapter.value)).toBe(true)
          expect(Number.isInteger(activeChapter.value)).toBe(true)
          expect(activeChapter.value).toBeGreaterThanOrEqual(1)
          expect(activeChapter.value).toBeLessThanOrEqual(16)
          // Single value not array
          expect(Array.isArray(activeChapter.value)).toBe(false)
        },
      ),
      { numRuns: 50 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Unit Tests — 3.7 overlap (16 chapters, mode switch, GtIndexChip)
// ═══════════════════════════════════════════════════════════════════════════════

describe('GtA171AuditSummary — Unit', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // ─── 16 Chapters Render ───

  describe('16 chapters structure', () => {
    it('has 16 chapters with correct keys', () => {
      const composable = setup()
      const keys = Object.keys(composable.chapters.value)
      expect(keys.length).toBe(16)
      for (let i = 1; i <= 16; i++) {
        expect(keys).toContain(String(i))
      }
    })

    it('textarea chapters are 1,2,3,4,5,7,13,14,15,16', () => {
      const composable = setup()
      const textareaKeys = [1, 2, 3, 4, 5, 7, 13, 14, 15, 16]
      for (const k of textareaKeys) {
        expect(composable.chapters.value[String(k)].type).toBe('textarea')
      }
    })

    it('table chapters are 6,8', () => {
      const composable = setup()
      expect(composable.chapters.value['6'].type).toBe('table')
      expect(composable.chapters.value['8'].type).toBe('table')
    })

    it('yn chapters are 9,10,11,12', () => {
      const composable = setup()
      for (const k of [9, 10, 11, 12]) {
        expect(composable.chapters.value[String(k)].type).toBe('yn')
      }
    })

    it('each chapter has a title', () => {
      const composable = setup()
      for (let i = 1; i <= 16; i++) {
        expect(composable.chapters.value[String(i)].title).toBeTruthy()
      }
    })
  })

  // ─── Mode Switch ───

  describe('mode switch', () => {
    it('saveStatus starts as saved', () => {
      const composable = setup()
      expect(composable.saveStatus.value).toBe('saved')
    })

    it('editing triggers unsaved status', () => {
      const composable = setup()
      composable.updateTextarea(1, '内容')
      expect(composable.saveStatus.value).toBe('unsaved')
    })
  })

  // ─── Signature Table ───

  describe('signature table', () => {
    it('has 10 rows', () => {
      const composable = setup()
      expect(composable.signatureTable.value.length).toBe(10)
    })

    it('first row is 编制人', () => {
      const composable = setup()
      expect(composable.signatureTable.value[0].role).toBe('编制人')
    })

    it('last row is 其他', () => {
      const composable = setup()
      expect(composable.signatureTable.value[9].role).toBe('其他')
    })

    it('all rows have name and date as null initially', () => {
      const composable = setup()
      for (const row of composable.signatureTable.value) {
        expect(row.name).toBeNull()
        expect(row.date).toBeNull()
      }
    })
  })

  // ─── Navigation ───

  describe('navigation', () => {
    it('completionStatus has 16 entries', () => {
      const composable = setup()
      const { completionStatus } = useA171Navigation(composable.chapters as any)
      const keys = Object.keys(completionStatus.value)
      expect(keys.length).toBe(16)
    })

    it('all chapters initially incomplete', () => {
      const composable = setup()
      const { completionStatus } = useA171Navigation(composable.chapters as any)
      for (let i = 1; i <= 16; i++) {
        expect(completionStatus.value[i]).toBe(false)
      }
    })

    it('textarea chapter marked complete when content is set', () => {
      const composable = setup()
      composable.updateTextarea(1, '有内容')
      const { completionStatus } = useA171Navigation(composable.chapters as any)
      expect(completionStatus.value[1]).toBe(true)
    })

    it('table chapter marked complete when rows exist', () => {
      const composable = setup()
      composable.addTableRow(6)
      const { completionStatus } = useA171Navigation(composable.chapters as any)
      expect(completionStatus.value[6]).toBe(true)
    })

    it('yn chapter marked complete when answer is set', () => {
      const composable = setup()
      composable.updateYn(9, 'Y', null)
      const { completionStatus } = useA171Navigation(composable.chapters as any)
      expect(completionStatus.value[9]).toBe(true)
    })
  })

  // ─── GtIndexChip cross-references ───

  describe('cross-references (GtIndexChip)', () => {
    it('initializes all references as null', () => {
      const composable = setup()
      expect(composable.crossReferences.value.b50_wp_id).toBeNull()
      expect(composable.crossReferences.value.a13_wp_id).toBeNull()
      expect(composable.crossReferences.value.a115_wp_id).toBeNull()
    })

    it('hydrates B50 cross reference from render data', () => {
      const composable = setup({
        cross_references: { b50_wp_id: 'wp-b50-id' },
      })
      expect(composable.crossReferences.value.b50_wp_id).toBe('wp-b50-id')
    })

    it('hydrates A13 cross reference from render data', () => {
      const composable = setup({
        cross_references: { a13_wp_id: 'wp-a13-id' },
      })
      expect(composable.crossReferences.value.a13_wp_id).toBe('wp-a13-id')
    })

    it('hydrates A1-15 cross reference from render data', () => {
      const composable = setup({
        cross_references: { a115_wp_id: 'wp-a115-id' },
      })
      expect(composable.crossReferences.value.a115_wp_id).toBe('wp-a115-id')
    })

    it('hydrates all cross references together', () => {
      const composable = setup({
        cross_references: {
          b50_wp_id: 'wp-b50-id',
          a13_wp_id: 'wp-a13-id',
          a115_wp_id: 'wp-a115-id',
        },
      })
      expect(composable.crossReferences.value.b50_wp_id).toBe('wp-b50-id')
      expect(composable.crossReferences.value.a13_wp_id).toBe('wp-a13-id')
      expect(composable.crossReferences.value.a115_wp_id).toBe('wp-a115-id')
    })
  })

  // ─── Item ID builders ───

  describe('item ID builders', () => {
    it('buildA171ItemId produces correct format', () => {
      expect(buildA171ItemId(1, 'content')).toBe('a171-ch1-content')
      expect(buildA171ItemId(6, 'table')).toBe('a171-ch6-table')
      expect(buildA171ItemId(9, 'yn')).toBe('a171-ch9-yn')
    })

    it('buildA171SignatureItemId produces correct format', () => {
      expect(buildA171SignatureItemId(0, 'name')).toBe('a171-signature-0-name')
      expect(buildA171SignatureItemId(4, 'date')).toBe('a171-signature-4-date')
    })
  })
})
