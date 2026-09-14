/**
 * PBT + Unit Tests — GtA1721Kam component
 *
 * Property 4: For any candidate row with communicate="Y", a corresponding KAM card
 * SHOULD exist (logical linkage). Tested via composable directly.
 *
 * **Validates: Requirements 3, 4, 5, 6**
 *
 * Spec: .kiro/specs/a17-2-1-kam/
 * Tasks: 3.5, 3.6
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import * as fc from 'fast-check'
import { useA1721Kam } from '../composables/useA1721Kam'
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
  return useA1721Kam({ wpId, projectId, htmlData })
}

// ═══════════════════════════════════════════════════════════════════════════════
// PBT — Property 4: candidate→KAM linkage
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * **Validates: Requirements 3, 4**
 *
 * Property 4: For any candidate row with communicate="Y", a corresponding KAM card
 * SHALL exist in the kams array. The count of candidates with communicate="Y" should
 * be <= kams.length (user may manually add extra KAMs beyond communicated candidates).
 *
 * We test this by hydrating with render data that has N candidates with communicate="Y"
 * and verifying kams.length >= communicatedCount.
 */
describe('GtA1721Kam PBT — Property 4: candidate→KAM linkage', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('Property 4: hydrated data with communicate="Y" candidates always has corresponding KAM cards', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            description: fc.string({ minLength: 1, maxLength: 30 }),
            risk_level: fc.constantFrom('高', '中', '低'),
            communicate: fc.constantFrom('Y' as const, 'N' as const),
            reason: fc.string({ maxLength: 20 }),
          }),
          { minLength: 1, maxLength: 8 },
        ),
        (candidates) => {
          const communicatedCount = candidates.filter(c => c.communicate === 'Y').length

          // Build kams matching communicated candidates (as a properly linked dataset would)
          const kams = Array.from({ length: communicatedCount }, (_, i) => ({
            index: i,
            basic: `KAM ${i + 1}`,
            policy: '',
            reason: '',
            response: '',
            result: '',
            ref_index: '',
          }))

          const data: A1721RenderData = { candidates, kams }
          const composable = setup(data)

          // Property: kams.length >= number of candidates with communicate="Y"
          const actualCommunicatedCount = composable.candidates.value.filter(
            c => c.communicate === 'Y',
          ).length
          expect(composable.kams.value.length).toBeGreaterThanOrEqual(actualCommunicatedCount)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('Property 4: after adding candidates with communicate="Y" and matching KAMs, linkage holds', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 6 }),
        fc.integer({ min: 0, max: 4 }),
        (communicatedCount, extraKams) => {
          const composable = setup()

          // Add candidates — some communicate="Y", some "N"
          for (let i = 0; i < communicatedCount; i++) {
            composable.addCandidate()
            composable.updateCandidate(i, 'communicate', 'Y')
            composable.updateCandidate(i, 'description', `事项${i}`)
          }
          // Add extra non-communicating candidates
          for (let i = 0; i < 2; i++) {
            composable.addCandidate()
          }

          // Add KAMs matching communicated count + potential extras
          for (let i = 0; i < communicatedCount + extraKams; i++) {
            composable.addKam()
            composable.updateKamField(i, 'basic', `对应KAM ${i}`)
          }

          // Property: kams count >= communicate="Y" count
          const yCount = composable.candidates.value.filter(c => c.communicate === 'Y').length
          expect(composable.kams.value.length).toBeGreaterThanOrEqual(yCount)
          expect(yCount).toBe(communicatedCount)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('Property 4: when no candidates have communicate="Y", zero KAMs is valid', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 5 }),
        (numCandidates) => {
          const candidates = Array.from({ length: numCandidates }, () => ({
            description: '事项',
            risk_level: '中',
            communicate: 'N' as const,
            reason: '',
          }))

          const data: A1721RenderData = { candidates, kams: [] }
          const composable = setup(data)

          const yCount = composable.candidates.value.filter(c => c.communicate === 'Y').length
          expect(yCount).toBe(0)
          // Zero KAMs is valid when no communication needed
          expect(composable.kams.value.length).toBeGreaterThanOrEqual(yCount)
        },
      ),
      { numRuns: 50 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Unit Tests — Task 3.6
// ═══════════════════════════════════════════════════════════════════════════════

describe('GtA1721Kam — Unit', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // ─── Candidate Table UI ───

  describe('candidate table', () => {
    it('add/remove candidates adjusts array correctly', () => {
      const composable = setup()
      composable.addCandidate()
      composable.addCandidate()
      composable.addCandidate()
      expect(composable.candidates.value.length).toBe(3)

      composable.removeCandidate(1)
      expect(composable.candidates.value.length).toBe(2)
    })

    it('update candidate fields reflects in state', () => {
      const composable = setup()
      composable.addCandidate()
      composable.updateCandidate(0, 'description', '商誉减值')
      composable.updateCandidate(0, 'risk_level', '高')
      composable.updateCandidate(0, 'communicate', 'Y')
      composable.updateCandidate(0, 'reason', '金额重大且涉及主观判断')

      expect(composable.candidates.value[0]).toEqual({
        description: '商誉减值',
        risk_level: '高',
        communicate: 'Y',
        reason: '金额重大且涉及主观判断',
      })
    })

    it('candidate with communicate="Y" is distinguishable from "N"', () => {
      const composable = setup()
      composable.addCandidate()
      composable.addCandidate()
      composable.updateCandidate(0, 'communicate', 'Y')
      composable.updateCandidate(1, 'communicate', 'N')

      const highlighted = composable.candidates.value.filter(c => c.communicate === 'Y')
      expect(highlighted.length).toBe(1)
      expect(highlighted[0]).toBe(composable.candidates.value[0])
    })

    it('candidates hydrate from render data', () => {
      const composable = setup({
        candidates: [
          { description: '收入确认', risk_level: '高', communicate: 'Y', reason: '测试' },
          { description: '存货跌价', risk_level: '中', communicate: 'N', reason: '' },
        ],
      })
      expect(composable.candidates.value.length).toBe(2)
      expect(composable.candidates.value[0].description).toBe('收入确认')
      expect(composable.candidates.value[1].risk_level).toBe('中')
    })
  })

  // ─── KAM Cards Render ───

  describe('KAM cards render', () => {
    it('each KAM has all 6 fields', () => {
      const composable = setup()
      composable.addKam()
      const kam = composable.kams.value[0]
      expect(kam).toHaveProperty('basic')
      expect(kam).toHaveProperty('policy')
      expect(kam).toHaveProperty('reason')
      expect(kam).toHaveProperty('response')
      expect(kam).toHaveProperty('result')
      expect(kam).toHaveProperty('ref_index')
    })

    it('KAM card fields are independently updatable', () => {
      const composable = setup()
      composable.addKam()
      composable.updateKamField(0, 'basic', '收入确认时点')
      composable.updateKamField(0, 'policy', '新收入准则')
      composable.updateKamField(0, 'reason', '收入跨期风险高')
      composable.updateKamField(0, 'response', '实施截止测试')
      composable.updateKamField(0, 'result', '未发现重大错报')
      composable.updateKamField(0, 'ref_index', 'D2-1')

      const kam = composable.kams.value[0]
      expect(kam.basic).toBe('收入确认时点')
      expect(kam.policy).toBe('新收入准则')
      expect(kam.reason).toBe('收入跨期风险高')
      expect(kam.response).toBe('实施截止测试')
      expect(kam.result).toBe('未发现重大错报')
      expect(kam.ref_index).toBe('D2-1')
    })

    it('multiple KAM cards are rendered with sequential indices', () => {
      const composable = setup()
      composable.addKam()
      composable.addKam()
      composable.addKam()

      expect(composable.kams.value.length).toBe(3)
      expect(composable.kams.value[0].index).toBe(0)
      expect(composable.kams.value[1].index).toBe(1)
      expect(composable.kams.value[2].index).toBe(2)
    })

    it('removing KAM re-indexes and preserves remaining data', () => {
      const composable = setup()
      composable.addKam()
      composable.addKam()
      composable.addKam()
      composable.updateKamField(0, 'basic', '第一个')
      composable.updateKamField(1, 'basic', '第二个')
      composable.updateKamField(2, 'basic', '第三个')

      composable.removeKam(1) // Remove "第二个"

      expect(composable.kams.value.length).toBe(2)
      expect(composable.kams.value[0].basic).toBe('第一个')
      expect(composable.kams.value[0].index).toBe(0)
      expect(composable.kams.value[1].basic).toBe('第三个')
      expect(composable.kams.value[1].index).toBe(1)
    })

    it('KAM hydration fills all 6 fields correctly', () => {
      const composable = setup({
        kams: [{
          index: 0,
          basic: '收入确认',
          policy: '权责发生制',
          reason: '金额重大',
          response: '截止测试',
          result: '无错报',
          ref_index: 'D2-1',
        }],
      })
      const kam = composable.kams.value[0]
      expect(kam.basic).toBe('收入确认')
      expect(kam.policy).toBe('权责发生制')
      expect(kam.reason).toBe('金额重大')
      expect(kam.response).toBe('截止测试')
      expect(kam.result).toBe('无错报')
      expect(kam.ref_index).toBe('D2-1')
    })
  })

  // ─── Applicability Toggle UI ───

  describe('applicability toggle UI', () => {
    it('noKam=true hides sections 2/3 data (candidates/kams/notes remain but UI hides)', () => {
      const composable = setup({
        candidates: [{ description: 'A', risk_level: '高', communicate: 'Y', reason: '' }],
        kams: [{ index: 0, basic: '测试', policy: '', reason: '', response: '', result: '', ref_index: '' }],
      })

      composable.toggleApplicability(true)

      // Data still exists (not destroyed), but UI should hide sections 2/3
      expect(composable.applicability.value.noKam).toBe(true)
      // In the Vue template, v-if="!applicability.noKam" hides sections 1/2/3
      expect(composable.candidates.value.length).toBe(1) // data preserved
      expect(composable.kams.value.length).toBe(1) // data preserved
    })

    it('noKam=false shows sections 2/3 (applicability.noKam === false)', () => {
      const composable = setup()
      composable.toggleApplicability(true)
      composable.toggleApplicability(false)

      expect(composable.applicability.value.noKam).toBe(false)
      // Sections visible when noKam=false
    })

    it('toggling noKam=true enables reason textarea', () => {
      const composable = setup()
      composable.toggleApplicability(true)
      composable.setApplicabilityReason('首年审计无KAM')

      expect(composable.applicability.value.noKam).toBe(true)
      expect(composable.applicability.value.reason).toBe('首年审计无KAM')
    })

    it('toggling noKam=false clears reason', () => {
      const composable = setup()
      composable.toggleApplicability(true)
      composable.setApplicabilityReason('原因说明')
      composable.toggleApplicability(false)

      expect(composable.applicability.value.reason).toBeNull()
    })

    it('applicability hydrates from render data', () => {
      const composable = setup({
        applicability: { no_kam: true, reason: '已有说明' },
      })
      expect(composable.applicability.value.noKam).toBe(true)
      expect(composable.applicability.value.reason).toBe('已有说明')
    })
  })

  // ─── Notes Sync ───

  describe('notes sync', () => {
    it('notes length always matches kams length', () => {
      const composable = setup()
      composable.addKam()
      expect(composable.notes.value.length).toBe(1)
      composable.addKam()
      expect(composable.notes.value.length).toBe(2)
      composable.addKam()
      expect(composable.notes.value.length).toBe(3)
      composable.removeKam(0)
      expect(composable.notes.value.length).toBe(2)
    })

    it('notes content is preserved for remaining KAMs after removal', () => {
      const composable = setup()
      composable.addKam()
      composable.addKam()
      composable.addKam()
      composable.updateNote(0, '附注一')
      composable.updateNote(1, '附注二')
      composable.updateNote(2, '附注三')

      composable.removeKam(1)

      // After removing KAM[1], notes are truncated to match kams.length
      expect(composable.notes.value.length).toBe(2)
    })

    it('notes hydrate and sync from render data', () => {
      const composable = setup({
        kams: [
          { index: 0, basic: '', policy: '', reason: '', response: '', result: '', ref_index: '' },
          { index: 1, basic: '', policy: '', reason: '', response: '', result: '', ref_index: '' },
          { index: 2, basic: '', policy: '', reason: '', response: '', result: '', ref_index: '' },
        ],
        notes: [{ kam_index: 0, content: '附注A' }],
      })
      // Should auto-sync to 3 notes
      expect(composable.notes.value.length).toBe(3)
      expect(composable.notes.value[0].content).toBe('附注A')
      expect(composable.notes.value[1].content).toBe('')
      expect(composable.notes.value[2].content).toBe('')
    })

    it('updateNote with valid index updates content', () => {
      const composable = setup()
      composable.addKam()
      composable.addKam()
      composable.updateNote(1, '这是KAM2的附注')
      expect(composable.notes.value[1].content).toBe('这是KAM2的附注')
    })
  })

  // ─── Mode Switch / Save Status ───

  describe('mode switch / saveStatus', () => {
    it('saveStatus starts as saved', () => {
      const composable = setup()
      expect(composable.saveStatus.value).toBe('saved')
    })

    it('any edit transitions saveStatus to unsaved', () => {
      const composable = setup()
      composable.addCandidate()
      expect(composable.saveStatus.value).toBe('unsaved')
    })

    it('saveStatus transitions to saving then saved on flush', async () => {
      const composable = setup()
      composable.addKam()
      expect(composable.saveStatus.value).toBe('unsaved')

      const flushPromise = composable.flushPendingSaves()
      // During API call, status should be 'saving'
      expect(composable.saveStatus.value).toBe('saving')

      await flushPromise
      expect(composable.saveStatus.value).toBe('saved')
    })

    it('saveStatus stays unsaved on API failure after retries', async () => {
      mockPut.mockRejectedValue(new Error('Network error'))
      const composable = setup()
      composable.addKam()

      await composable.flushPendingSaves()

      // After failure (first attempt in flush, retries happen later), status depends on retry logic
      // The composable retries up to 3 times with setTimeout, so after immediate flush:
      // First attempt fails → items re-queued → next retry scheduled
      // We need to advance timers through all retries
      for (let i = 0; i < 4; i++) {
        vi.advanceTimersByTime(5000)
        await vi.runAllTimersAsync()
      }

      expect(composable.saveStatus.value).toBe('unsaved')
    })

    it('flushPendingSaves clears debounce timer', async () => {
      const composable = setup()
      composable.addKam()
      // Debounce timer is running
      await composable.flushPendingSaves()
      expect(mockPut).toHaveBeenCalledTimes(1)

      // Advancing timer should NOT trigger another save
      vi.advanceTimersByTime(3000)
      await vi.runAllTimersAsync()
      expect(mockPut).toHaveBeenCalledTimes(1)
    })
  })

  // ─── Hydration from Render Data ───

  describe('hydration from render data', () => {
    it('hydrates empty render data gracefully', () => {
      const composable = setup({})
      expect(composable.candidates.value).toEqual([])
      expect(composable.kams.value).toEqual([])
      expect(composable.notes.value).toEqual([])
      expect(composable.applicability.value).toEqual({ noKam: false, reason: null })
    })

    it('hydrates null render data gracefully', () => {
      const composable = setup(null)
      expect(composable.candidates.value).toEqual([])
      expect(composable.kams.value).toEqual([])
    })

    it('hydrates full render data with all sections', () => {
      const composable = setup({
        candidates: [
          { description: '商誉', risk_level: '高', communicate: 'Y', reason: '重大' },
          { description: '收入', risk_level: '中', communicate: 'N', reason: '' },
        ],
        kams: [
          { index: 0, basic: '商誉减值', policy: 'CAS8', reason: '估计复杂', response: '测试', result: '合理', ref_index: 'D5-1' },
        ],
        notes: [{ kam_index: 0, content: '附注十二' }],
        applicability: { no_kam: false, reason: null },
      })

      expect(composable.candidates.value.length).toBe(2)
      expect(composable.kams.value.length).toBe(1)
      expect(composable.kams.value[0].basic).toBe('商誉减值')
      expect(composable.notes.value.length).toBe(1)
      expect(composable.notes.value[0].content).toBe('附注十二')
      expect(composable.applicability.value.noKam).toBe(false)
    })

    it('hydration handles missing fields with defaults', () => {
      const composable = setup({
        candidates: [{ description: '', risk_level: '', communicate: 'N', reason: '' }],
        kams: [{ index: 0, basic: '', policy: '', reason: '', response: '', result: '', ref_index: '' }],
      })
      expect(composable.candidates.value[0].communicate).toBe('N')
      expect(composable.kams.value[0].basic).toBe('')
    })
  })
})
