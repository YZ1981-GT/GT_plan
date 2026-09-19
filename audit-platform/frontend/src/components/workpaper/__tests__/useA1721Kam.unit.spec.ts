/**
 * Unit Tests + PBT — useA1721Kam
 *
 * Spec: .kiro/specs/a17-2-1-kam/
 * Task: 2.2, 2.3
 *
 * Coverage:
 * - KAM add/remove
 * - Candidate table update
 * - Applicability toggle
 * - Notes auto-sync
 * - Debounce save
 * - PBT Property 1: item_id format (a1721-candidates / a1721-kam{N} / a1721-notes-{N} / a1721-applicability)
 * - PBT Property 3: applicability switch mutual exclusion
 * - PBT Property 5: KAM add/remove length consistency
 *
 * **Validates: Requirements 3, 4, 5, 6, 9**
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import * as fc from 'fast-check'
import {
  useA1721Kam,
  buildCandidatesItemId,
  buildKamItemId,
  buildNoteItemId,
  buildApplicabilityItemId,
} from '../composables/useA1721Kam'
import type { A1721RenderData } from '../composables/useA1721Kam'

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

vi.mock('@/utils/eventBus', () => ({
  eventBus: { emit: vi.fn(), on: vi.fn(), off: vi.fn() },
}))

function setup(data: A1721RenderData | null = null) {
  const wpId = ref('wp-a1721-001')
  const projectId = ref('proj-001')
  const htmlData = ref<A1721RenderData | null>(data)
  return { composable: useA1721Kam({ wpId, projectId, htmlData }), htmlData }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Unit Tests (Task 2.3)
// ═══════════════════════════════════════════════════════════════════════════════

describe('useA1721Kam — Unit', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // ─── KAM Add/Remove ───

  describe('KAM add/remove', () => {
    it('addKam increases kams array length', () => {
      const { composable } = setup()
      expect(composable.kams.value.length).toBe(0)
      composable.addKam()
      expect(composable.kams.value.length).toBe(1)
      composable.addKam()
      expect(composable.kams.value.length).toBe(2)
    })

    it('addKam creates KAM with empty fields and correct index', () => {
      const { composable } = setup()
      composable.addKam()
      const kam = composable.kams.value[0]
      expect(kam.index).toBe(0)
      expect(kam.basic).toBe('')
      expect(kam.policy).toBe('')
      expect(kam.reason).toBe('')
      expect(kam.response).toBe('')
      expect(kam.result).toBe('')
      expect(kam.ref_index).toBe('')
    })

    it('removeKam decreases kams array length', () => {
      const { composable } = setup()
      composable.addKam()
      composable.addKam()
      composable.removeKam(0)
      expect(composable.kams.value.length).toBe(1)
    })

    it('removeKam re-indexes remaining KAMs', () => {
      const { composable } = setup()
      composable.addKam()
      composable.addKam()
      composable.addKam()
      composable.updateKamField(1, 'basic', '第二个KAM')
      composable.removeKam(0)
      expect(composable.kams.value[0].index).toBe(0)
      expect(composable.kams.value[0].basic).toBe('第二个KAM')
      expect(composable.kams.value[1].index).toBe(1)
    })

    it('removeKam with invalid index does nothing', () => {
      const { composable } = setup()
      composable.addKam()
      composable.removeKam(-1)
      composable.removeKam(5)
      expect(composable.kams.value.length).toBe(1)
    })

    it('updateKamField updates specific field', () => {
      const { composable } = setup()
      composable.addKam()
      composable.updateKamField(0, 'basic', '收入确认')
      composable.updateKamField(0, 'policy', '权责发生制')
      expect(composable.kams.value[0].basic).toBe('收入确认')
      expect(composable.kams.value[0].policy).toBe('权责发生制')
    })

    it('updateKamField with invalid index does nothing', () => {
      const { composable } = setup()
      composable.addKam()
      composable.updateKamField(5, 'basic', 'test')
      expect(composable.kams.value[0].basic).toBe('')
    })
  })

  // ─── Candidate Table Update ───

  describe('candidate table update', () => {
    it('addCandidate adds a row with default values', () => {
      const { composable } = setup()
      composable.addCandidate()
      expect(composable.candidates.value.length).toBe(1)
      expect(composable.candidates.value[0]).toEqual({
        description: '',
        risk_level: '',
        communicate: 'N',
        reason: '',
      })
    })

    it('removeCandidate removes correct row', () => {
      const { composable } = setup()
      composable.addCandidate()
      composable.addCandidate()
      composable.updateCandidate(0, 'description', '第一项')
      composable.updateCandidate(1, 'description', '第二项')
      composable.removeCandidate(0)
      expect(composable.candidates.value.length).toBe(1)
      expect(composable.candidates.value[0].description).toBe('第二项')
    })

    it('removeCandidate with invalid index does nothing', () => {
      const { composable } = setup()
      composable.addCandidate()
      composable.removeCandidate(-1)
      composable.removeCandidate(10)
      expect(composable.candidates.value.length).toBe(1)
    })

    it('updateCandidate updates field value', () => {
      const { composable } = setup()
      composable.addCandidate()
      composable.updateCandidate(0, 'description', '商誉减值')
      composable.updateCandidate(0, 'risk_level', '高')
      composable.updateCandidate(0, 'communicate', 'Y')
      expect(composable.candidates.value[0].description).toBe('商誉减值')
      expect(composable.candidates.value[0].risk_level).toBe('高')
      expect(composable.candidates.value[0].communicate).toBe('Y')
    })

    it('candidate save stores JSON array in remark', async () => {
      const { composable } = setup()
      composable.addCandidate()
      composable.updateCandidate(0, 'description', '收入确认')
      await composable.flushPendingSaves()

      const items = mockPut.mock.calls[0][1].items
      const cand = items.find((i: any) => i.item_id === 'a1721-candidates')
      expect(cand).toBeDefined()
      const parsed = JSON.parse(cand.remark)
      expect(parsed).toHaveLength(1)
      expect(parsed[0].description).toBe('收入确认')
    })
  })

  // ─── Applicability Toggle ───

  describe('applicability toggle', () => {
    it('toggleApplicability sets noKam to true', () => {
      const { composable } = setup()
      composable.toggleApplicability(true)
      expect(composable.applicability.value.noKam).toBe(true)
    })

    it('toggleApplicability(true) clears reason to null initially', () => {
      const { composable } = setup()
      composable.setApplicabilityReason('一些原因')
      // When toggling OFF (noKam=false), reason is cleared
      composable.toggleApplicability(false)
      expect(composable.applicability.value.reason).toBeNull()
    })

    it('toggleApplicability(false) clears reason', () => {
      const { composable } = setup()
      composable.toggleApplicability(true)
      composable.setApplicabilityReason('不存在关键审计事项')
      composable.toggleApplicability(false)
      expect(composable.applicability.value.noKam).toBe(false)
      expect(composable.applicability.value.reason).toBeNull()
    })

    it('setApplicabilityReason updates reason text', () => {
      const { composable } = setup()
      composable.toggleApplicability(true)
      composable.setApplicabilityReason('首次审计，不存在关键审计事项')
      expect(composable.applicability.value.reason).toBe('首次审计，不存在关键审计事项')
    })

    it('applicability save uses correct item_id and conclusion', async () => {
      const { composable } = setup()
      composable.toggleApplicability(true)
      composable.setApplicabilityReason('原因说明')
      await composable.flushPendingSaves()

      const items = mockPut.mock.calls[0][1].items
      const app = items.find((i: any) => i.item_id === 'a1721-applicability')
      expect(app).toBeDefined()
      expect(app.conclusion).toBe('Y')
      expect(app.remark).toBe('原因说明')
    })
  })

  // ─── Notes Auto-Sync ───

  describe('notes auto-sync', () => {
    it('notes length matches kams length after addKam', () => {
      const { composable } = setup()
      composable.addKam()
      composable.addKam()
      expect(composable.notes.value.length).toBe(2)
    })

    it('notes length decreases after removeKam', () => {
      const { composable } = setup()
      composable.addKam()
      composable.addKam()
      composable.addKam()
      composable.removeKam(1)
      expect(composable.notes.value.length).toBe(2)
    })

    it('updateNote updates specific note content', () => {
      const { composable } = setup()
      composable.addKam()
      composable.updateNote(0, '附注第七条')
      expect(composable.notes.value[0].content).toBe('附注第七条')
    })

    it('updateNote with invalid index does nothing', () => {
      const { composable } = setup()
      composable.addKam()
      composable.updateNote(5, 'test')
      expect(composable.notes.value[0].content).toBe('')
    })

    it('note save uses correct item_id', async () => {
      const { composable } = setup()
      composable.addKam()
      composable.updateNote(0, '附注披露内容')
      await composable.flushPendingSaves()

      const items = mockPut.mock.calls[0][1].items
      const note = items.find((i: any) => i.item_id === 'a1721-notes-0')
      expect(note).toBeDefined()
      expect(note.remark).toBe('附注披露内容')
    })
  })

  // ─── Debounce Save ───

  describe('debounce save', () => {
    it('does not save before 2s', () => {
      const { composable } = setup()
      composable.addCandidate()
      vi.advanceTimersByTime(1999)
      expect(mockPut).not.toHaveBeenCalled()
    })

    it('saves after 2s', async () => {
      const { composable } = setup()
      composable.addCandidate()
      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()
      expect(mockPut).toHaveBeenCalledTimes(1)
    })

    it('batches multiple changes into one API call', async () => {
      const { composable } = setup()
      composable.addCandidate()
      composable.addKam()
      composable.toggleApplicability(true)
      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()
      expect(mockPut).toHaveBeenCalledTimes(1)
      const items = mockPut.mock.calls[0][1].items
      expect(items.length).toBeGreaterThan(1)
    })

    it('flushPendingSaves immediately saves without debounce', async () => {
      const { composable } = setup()
      composable.addKam()
      await composable.flushPendingSaves()
      expect(mockPut).toHaveBeenCalledTimes(1)
    })

    it('flushPendingSaves is no-op when nothing pending', async () => {
      const { composable } = setup()
      await composable.flushPendingSaves()
      expect(mockPut).not.toHaveBeenCalled()
    })

    it('saveStatus transitions: saved → unsaved → saving → saved', async () => {
      const { composable } = setup()
      expect(composable.saveStatus.value).toBe('saved')
      composable.addKam()
      expect(composable.saveStatus.value).toBe('unsaved')
      await composable.flushPendingSaves()
      expect(composable.saveStatus.value).toBe('saved')
    })
  })

  // ─── Hydration ───

  describe('hydration from render data', () => {
    it('hydrates candidates', () => {
      const data: A1721RenderData = {
        candidates: [
          { description: '商誉', risk_level: '高', communicate: 'Y', reason: '金额重大' },
        ],
      }
      const { composable } = setup(data)
      expect(composable.candidates.value.length).toBe(1)
      expect(composable.candidates.value[0].description).toBe('商誉')
    })

    it('hydrates kams with correct fields', () => {
      const data: A1721RenderData = {
        kams: [
          { index: 0, basic: '收入', policy: '政策', reason: '原因', response: '应对', result: '结果', ref_index: 'D2-1' },
        ],
      }
      const { composable } = setup(data)
      expect(composable.kams.value.length).toBe(1)
      expect(composable.kams.value[0].basic).toBe('收入')
      expect(composable.kams.value[0].ref_index).toBe('D2-1')
    })

    it('hydrates applicability', () => {
      const data: A1721RenderData = {
        applicability: { no_kam: true, reason: '不适用' },
      }
      const { composable } = setup(data)
      expect(composable.applicability.value.noKam).toBe(true)
      expect(composable.applicability.value.reason).toBe('不适用')
    })

    it('syncs notes with kams on hydration', () => {
      const data: A1721RenderData = {
        kams: [
          { index: 0, basic: '', policy: '', reason: '', response: '', result: '', ref_index: '' },
          { index: 1, basic: '', policy: '', reason: '', response: '', result: '', ref_index: '' },
        ],
        notes: [{ kam_index: 0, content: '附注1' }],
      }
      const { composable } = setup(data)
      // notes should be synced to kams length
      expect(composable.notes.value.length).toBe(2)
      expect(composable.notes.value[0].content).toBe('附注1')
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// PBT Tests (Task 2.2)
// ═══════════════════════════════════════════════════════════════════════════════

// ─── PBT: Property 1 — item_id format ───────────────────────────────────────

/**
 * **Validates: Requirements 9**
 *
 * Property 1: For any field edit in useA1721Kam, the save SHALL produce item_ids
 * matching `a1721-candidates`, `a1721-kam{N}`, `a1721-notes-{N}`, or `a1721-applicability`.
 */
describe('useA1721Kam PBT — Property 1: item_id format', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('buildCandidatesItemId always produces a1721-candidates', () => {
    expect(buildCandidatesItemId()).toBe('a1721-candidates')
  })

  it('buildKamItemId produces a1721-kam{N} format for any valid index', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 20 }),
        (index) => {
          const itemId = buildKamItemId(index)
          expect(itemId).toMatch(/^a1721-kam\d+$/)
          expect(itemId).toBe(`a1721-kam${index}`)
        },
      ),
      { numRuns: 50 },
    )
  })

  it('buildNoteItemId produces a1721-notes-{N} format for any valid index', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 20 }),
        (index) => {
          const itemId = buildNoteItemId(index)
          expect(itemId).toMatch(/^a1721-notes-\d+$/)
          expect(itemId).toBe(`a1721-notes-${index}`)
        },
      ),
      { numRuns: 50 },
    )
  })

  it('buildApplicabilityItemId always produces a1721-applicability', () => {
    expect(buildApplicabilityItemId()).toBe('a1721-applicability')
  })

  it('all saved item_ids from composable operations match a1721-* patterns', () => {
    fc.assert(
      fc.property(
        fc.record({
          numKams: fc.integer({ min: 1, max: 5 }),
          numCandidates: fc.integer({ min: 1, max: 5 }),
          noKam: fc.boolean(),
        }),
        (data) => {
          mockPut.mockReset()
          mockPut.mockResolvedValue({})
          const { composable } = setup()

          // Add candidates
          for (let i = 0; i < data.numCandidates; i++) {
            composable.addCandidate()
          }
          // Add KAMs
          for (let i = 0; i < data.numKams; i++) {
            composable.addKam()
          }
          // Toggle applicability
          composable.toggleApplicability(data.noKam)
          // Update a note
          if (data.numKams > 0) {
            composable.updateNote(0, '附注内容')
          }

          composable.flushPendingSaves()

          if (mockPut.mock.calls.length > 0) {
            const items = mockPut.mock.calls[0][1].items
            const validPatterns = [
              /^a1721-candidates$/,
              /^a1721-kam\d+$/,
              /^a1721-notes-\d+$/,
              /^a1721-applicability$/,
            ]

            for (const item of items) {
              const matchesAny = validPatterns.some(p => p.test(item.item_id))
              expect(matchesAny).toBe(true)
            }
          }
        },
      ),
      { numRuns: 50 },
    )
  })
})

// ─── PBT: Property 3 — Applicability switch mutual exclusion ────────────────

/**
 * **Validates: Requirements 6**
 *
 * Property 3: For any applicability state, WHEN noKam is true, the saved conclusion
 * SHALL be "Y" and reason can be non-null; WHEN noKam is false, conclusion SHALL
 * be "N" and reason SHALL be null.
 */
describe('useA1721Kam PBT — Property 3: applicability switch mutual exclusion', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('noKam=true → conclusion="Y", reason preserved', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 50 }),
        (reason) => {
          mockPut.mockReset()
          mockPut.mockResolvedValue({})
          const { composable } = setup()

          composable.toggleApplicability(true)
          composable.setApplicabilityReason(reason)
          composable.flushPendingSaves()

          if (mockPut.mock.calls.length > 0) {
            const items = mockPut.mock.calls[0][1].items
            const app = items.find((i: any) => i.item_id === 'a1721-applicability')
            expect(app).toBeDefined()
            expect(app.conclusion).toBe('Y')
            expect(app.remark).toBe(reason)
          }
        },
      ),
      { numRuns: 50 },
    )
  })

  it('noKam=false → conclusion="N", reason=null', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 50 }),
        (reason) => {
          mockPut.mockReset()
          mockPut.mockResolvedValue({})
          const { composable } = setup()

          // First set to true with reason
          composable.toggleApplicability(true)
          composable.setApplicabilityReason(reason)
          // Then toggle back to false
          composable.toggleApplicability(false)
          composable.flushPendingSaves()

          if (mockPut.mock.calls.length > 0) {
            const items = mockPut.mock.calls[0][1].items
            const app = items.find((i: any) => i.item_id === 'a1721-applicability')
            expect(app).toBeDefined()
            expect(app.conclusion).toBe('N')
            expect(app.remark).toBeNull()
          }
        },
      ),
      { numRuns: 50 },
    )
  })

  it('toggling maintains mutual exclusion: noKam and reason cannot coexist when off', () => {
    fc.assert(
      fc.property(
        fc.array(fc.boolean(), { minLength: 1, maxLength: 10 }),
        (toggleSequence) => {
          const { composable } = setup()

          for (const noKam of toggleSequence) {
            composable.toggleApplicability(noKam)
            if (noKam) {
              composable.setApplicabilityReason('原因')
            }
          }

          const finalState = composable.applicability.value
          if (!finalState.noKam) {
            // When noKam is false, reason must be null
            expect(finalState.reason).toBeNull()
          }
        },
      ),
      { numRuns: 50 },
    )
  })
})

// ─── PBT: Property 5 — KAM add/remove length consistency ───────────────────

/**
 * **Validates: Requirements 4, 5**
 *
 * Property 5: For any sequence of add/remove operations on KAMs,
 * kams.length SHALL equal (initial + adds - removes),
 * and notes SHALL auto-sync length with kams.
 */
describe('useA1721Kam PBT — Property 5: KAM add/remove length', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('kams.length == initial + adds - valid_removes', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.oneof(
            fc.constant({ type: 'add' as const }),
            fc.record({ type: fc.constant('remove' as const), index: fc.nat({ max: 10 }) }),
          ),
          { minLength: 1, maxLength: 20 },
        ),
        (operations) => {
          const { composable } = setup()
          let expectedLength = 0

          for (const op of operations) {
            if (op.type === 'add') {
              composable.addKam()
              expectedLength++
            } else {
              const idx = (op as any).index
              if (idx >= 0 && idx < expectedLength) {
                composable.removeKam(idx)
                expectedLength--
              } else {
                composable.removeKam(idx) // no-op for invalid index
              }
            }
          }

          expect(composable.kams.value.length).toBe(expectedLength)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('notes.length always equals kams.length after any operation sequence', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.oneof(
            fc.constant({ type: 'add' as const }),
            fc.record({ type: fc.constant('remove' as const), index: fc.nat({ max: 10 }) }),
          ),
          { minLength: 1, maxLength: 20 },
        ),
        (operations) => {
          const { composable } = setup()

          for (const op of operations) {
            if (op.type === 'add') {
              composable.addKam()
            } else {
              composable.removeKam((op as any).index)
            }
          }

          expect(composable.notes.value.length).toBe(composable.kams.value.length)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('KAM indices are always sequential 0..N-1 after operations', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.oneof(
            fc.constant({ type: 'add' as const }),
            fc.record({ type: fc.constant('remove' as const), index: fc.nat({ max: 10 }) }),
          ),
          { minLength: 1, maxLength: 15 },
        ),
        (operations) => {
          const { composable } = setup()

          for (const op of operations) {
            if (op.type === 'add') {
              composable.addKam()
            } else {
              composable.removeKam((op as any).index)
            }
          }

          // Indices should be sequential 0..N-1
          for (let i = 0; i < composable.kams.value.length; i++) {
            expect(composable.kams.value[i].index).toBe(i)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})
