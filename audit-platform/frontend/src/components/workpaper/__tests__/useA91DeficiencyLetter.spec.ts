/**
 * Unit Tests — useA91DeficiencyLetter composable
 *
 * Spec: .kiro/specs/a9-1-deficiency-letter/
 * Task: 2.3, 4.3
 *
 * Coverage:
 * - Debounce save timing (2s, not before)
 * - Flush promise resolution
 * - Deficiency JSON serialization (add/remove correctly update arrays)
 * - B22B warning handling
 * - EventBus subscription triggers refresh, unsubscribe on unmount (4.3)
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, defineComponent, h, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { useA91DeficiencyLetter } from '../composables/useA91DeficiencyLetter'
import type { A91RenderData } from '../composables/useA91DeficiencyLetter'

// ─── Mock API ────────────────────────────────────────────────────────────────

const mockGet = vi.fn()
const mockPut = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    put: (...args: any[]) => mockPut(...args),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), error: vi.fn() },
}))

vi.mock('@vueuse/core', async (importOriginal) => {
  const actual = await importOriginal() as any
  return { ...actual }
})

// ─── Mock EventBus ───────────────────────────────────────────────────────────

const eventBusHandlers: Record<string, Function[]> = {}
const mockOn = vi.fn((event: string, handler: Function) => {
  if (!eventBusHandlers[event]) eventBusHandlers[event] = []
  eventBusHandlers[event].push(handler)
})
const mockOff = vi.fn((event: string, handler: Function) => {
  if (eventBusHandlers[event]) {
    eventBusHandlers[event] = eventBusHandlers[event].filter(h => h !== handler)
  }
})
const mockEmit = vi.fn((event: string, payload?: any) => {
  if (eventBusHandlers[event]) {
    eventBusHandlers[event].forEach(h => h(payload))
  }
})

vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    on: (event: string, handler: Function) => mockOn(event, handler),
    off: (event: string, handler: Function) => mockOff(event, handler),
    emit: (event: string, payload?: any) => mockEmit(event, payload),
  },
}))

describe('useA91DeficiencyLetter', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockGet.mockReset()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
    mockOn.mockClear()
    mockOff.mockClear()
    mockEmit.mockClear()
    // Clear tracked handlers
    Object.keys(eventBusHandlers).forEach(k => delete eventBusHandlers[k])
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  function setup(renderData: A91RenderData | null = null) {
    const wpId = ref('wp-a91')
    const projectId = ref('proj-001')
    const htmlData = ref<A91RenderData | null>(renderData)
    return { composable: useA91DeficiencyLetter({ wpId, projectId, htmlData }), wpId, projectId, htmlData }
  }

  // ─── Debounce Save Timing ───

  describe('debounce save timing', () => {
    it('updateField triggers save after 2s, not before', async () => {
      const { composable } = setup()
      composable.updateField('independence', 'team_independent', 'Y')

      expect(mockPut).not.toHaveBeenCalled()
      expect(composable.saveStatus.value).toBe('unsaved')

      // 1.5s — still not fired
      vi.advanceTimersByTime(1500)
      expect(mockPut).not.toHaveBeenCalled()

      // 2s — fires
      vi.advanceTimersByTime(500)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
      expect(mockPut).toHaveBeenCalledWith(
        '/api/workpapers/wp-a91/checklist-responses',
        expect.objectContaining({
          items: expect.arrayContaining([
            expect.objectContaining({ item_id: 'a91-independence-team_independent', conclusion: 'Y' }),
          ]),
        }),
      )
    })

    it('batches multiple updates into single save', async () => {
      const { composable } = setup()
      composable.updateField('independence', 'team_independent', 'Y')
      composable.updateField('independence', 'no_relationships', 'N')
      composable.updateField('committee', 'applicability', 'NA')

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
      const items = mockPut.mock.calls[0][1].items
      expect(items).toHaveLength(3)
    })

    it('resets debounce timer on subsequent updates', async () => {
      const { composable } = setup()
      composable.updateField('signature', 'date', '2026-01-01')

      vi.advanceTimersByTime(1500)
      composable.updateField('signature', 'date', '2026-01-15')

      vi.advanceTimersByTime(1500)
      expect(mockPut).not.toHaveBeenCalled()

      vi.advanceTimersByTime(500)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
      // Should have the latest value
      const items = mockPut.mock.calls[0][1].items
      expect(items[0].conclusion).toBe('2026-01-15')
    })

    it('save status transitions: saved → unsaved → saving → saved', async () => {
      const { composable } = setup()

      expect(composable.saveStatus.value).toBe('saved')

      composable.updateField('addressee', 'client_name', '测试公司')
      expect(composable.saveStatus.value).toBe('unsaved')

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(composable.saveStatus.value).toBe('saved')
    })
  })

  // ─── Flush Promise Resolution ───

  describe('flushPendingSaves', () => {
    it('immediately saves pending items without waiting for debounce', async () => {
      const { composable } = setup()
      composable.updateField('response', 'representative', '张三')

      // No timer advance — flush immediately
      await composable.flushPendingSaves()

      expect(mockPut).toHaveBeenCalledTimes(1)
      expect(mockPut).toHaveBeenCalledWith(
        '/api/workpapers/wp-a91/checklist-responses',
        expect.objectContaining({
          items: [expect.objectContaining({ item_id: 'a91-response-representative', conclusion: '张三' })],
        }),
      )
    })

    it('does nothing when no pending changes', async () => {
      const { composable } = setup()
      await composable.flushPendingSaves()
      expect(mockPut).not.toHaveBeenCalled()
    })

    it('cancels pending debounce timer', async () => {
      const { composable } = setup()
      composable.updateField('signature', 'date', '2026-06-01')

      // Flush before the 2s debounce
      await composable.flushPendingSaves()

      expect(mockPut).toHaveBeenCalledTimes(1)

      // Advance timer — no second save should happen
      vi.advanceTimersByTime(3000)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
    })
  })

  // ─── Deficiency JSON Serialization ───

  describe('deficiency JSON serialization', () => {
    it('addDeficiency correctly adds to severity array', () => {
      const { composable } = setup()
      composable.addDeficiency('major')
      expect(composable.deficiencyList.value.major).toHaveLength(1)
      expect(composable.deficiencyList.value.major[0].source).toBe('manual')
      expect(composable.deficiencyList.value.major[0].severity).toBe('major')
      expect(composable.deficiencyList.value.major[0].id).toBeTruthy()
    })

    it('removeDeficiency removes correct item', () => {
      const { composable } = setup()
      composable.addDeficiency('significant')
      composable.addDeficiency('significant')
      composable.updateDeficiency('significant', 0, 'description', '第一条')
      composable.updateDeficiency('significant', 1, 'description', '第二条')

      composable.removeDeficiency('significant', 0)

      expect(composable.deficiencyList.value.significant).toHaveLength(1)
      expect(composable.deficiencyList.value.significant[0].description).toBe('第二条')
    })

    it('updateDeficiency updates the correct field', () => {
      const { composable } = setup()
      composable.addDeficiency('general')
      composable.updateDeficiency('general', 0, 'description', '缺陷描述')
      composable.updateDeficiency('general', 0, 'impact', '影响说明')
      composable.updateDeficiency('general', 0, 'recommendation', '整改建议')

      const item = composable.deficiencyList.value.general[0]
      expect(item.description).toBe('缺陷描述')
      expect(item.impact).toBe('影响说明')
      expect(item.recommendation).toBe('整改建议')
    })

    it('deficiency save includes JSON-serialized remark with count as conclusion', async () => {
      const { composable } = setup()
      composable.addDeficiency('major')
      composable.updateDeficiency('major', 0, 'description', '重大缺陷1')

      await composable.flushPendingSaves()

      expect(mockPut).toHaveBeenCalledTimes(1)
      const items = mockPut.mock.calls[0][1].items
      const defItem = items.find((i: any) => i.item_id === 'a91-deficiency-major')
      expect(defItem).toBeDefined()
      expect(defItem.conclusion).toBe('1')

      const parsed = JSON.parse(defItem.remark)
      expect(parsed).toHaveLength(1)
      expect(parsed[0].description).toBe('重大缺陷1')
      expect(parsed[0].source).toBe('manual')
    })

    it('removeDeficiency on invalid index does nothing', () => {
      const { composable } = setup()
      composable.addDeficiency('general')
      composable.removeDeficiency('general', 5) // out of bounds
      composable.removeDeficiency('general', -1) // negative

      expect(composable.deficiencyList.value.general).toHaveLength(1)
    })

    it('addDeficiency to invalid severity does nothing', () => {
      const { composable } = setup()
      composable.addDeficiency('invalid' as any)
      expect(composable.deficiencyList.value.major).toHaveLength(0)
      expect(composable.deficiencyList.value.significant).toHaveLength(0)
      expect(composable.deficiencyList.value.general).toHaveLength(0)
    })
  })

  // ─── B22B Warning Handling ───

  describe('B22B warning handling', () => {
    it('reflects b22b_warning from htmlData', () => {
      const { composable } = setup({
        b22b_warning: '未找到B22B内控缺陷评价表',
        section_data: {},
        deficiency_list: { major: [], significant: [], general: [] },
      })

      expect(composable.b22bWarning.value).toBe('未找到B22B内控缺陷评价表')
    })

    it('b22bWarning is null when B22B data exists', () => {
      const { composable } = setup({
        b22b_warning: null,
        section_data: {},
        deficiency_list: { major: [], significant: [], general: [] },
      })

      expect(composable.b22bWarning.value).toBeNull()
    })

    it('refreshFromB22B updates b22bWarning', async () => {
      const { composable } = setup()

      mockGet.mockResolvedValue({
        sheets: [{
          html_data: {
            deficiency_list: { major: [], significant: [], general: [] },
            b22b_warning: '未找到B22B内控缺陷评价表',
          },
        }],
      })

      await composable.refreshFromB22B()

      expect(composable.b22bWarning.value).toBe('未找到B22B内控缺陷评价表')
      expect(composable.loading.value).toBe(false)
    })

    it('refreshFromB22B updates deficiency list from B22B', async () => {
      const { composable } = setup()

      const b22bItems = [
        { id: 'DEF-001', description: '来自B22B的缺陷', impact: '重大影响', recommendation: '建议整改', indexRef: 'B22B-001', source: 'b22b' as const, severity: 'major' as const },
      ]
      mockGet.mockResolvedValue({
        sheets: [{
          html_data: {
            deficiency_list: { major: b22bItems, significant: [], general: [] },
            b22b_warning: null,
          },
        }],
      })

      await composable.refreshFromB22B()

      expect(composable.deficiencyList.value.major).toHaveLength(1)
      expect(composable.deficiencyList.value.major[0].description).toBe('来自B22B的缺陷')
      expect(composable.deficiencyList.value.major[0].source).toBe('b22b')
    })

    it('refreshFromB22B handles API failure gracefully', async () => {
      const { composable } = setup({
        deficiency_list: { major: [{ id: 'existing', description: '已有缺陷', impact: '', recommendation: '', indexRef: null, source: 'manual', severity: 'major' }], significant: [], general: [] },
      })

      mockGet.mockRejectedValue(new Error('Network error'))

      await composable.refreshFromB22B()

      // Should preserve existing data
      expect(composable.deficiencyList.value.major).toHaveLength(1)
      expect(composable.deficiencyList.value.major[0].description).toBe('已有缺陷')
      expect(composable.loading.value).toBe(false)
    })
  })

  // ─── Data Hydration from htmlData ───

  describe('data hydration', () => {
    it('hydrates sectionData from htmlData on init', () => {
      const { composable } = setup({
        section_data: {
          addressee: { client_name: '华为技术有限公司', custom_text: null },
          independence: { team_independent: 'Y', no_relationships: 'Y', no_relationships_detail: null, safeguards_taken: 'Y', non_audit_services: 'N', non_audit_services_detail: null },
          committee: { applicability: 'N', description: null },
          signature: { date: '2026-06-26' },
          response: { opinion: '同意', conclusion: '无异议', representative: '李总', response_date: '2026-06-28' },
        },
        deficiency_list: {
          major: [{ id: 'D1', description: '重大缺陷', impact: '高', recommendation: '整改', indexRef: 'B22B-001', source: 'b22b', severity: 'major' }],
          significant: [],
          general: [],
        },
        project_context: { client_name: '华为技术有限公司', firm_name: '致同会计师事务所（特殊普通合伙）', audit_report_date: '2026-06-30' },
        b22b_warning: null,
      })

      expect(composable.sectionData.value.addressee.client_name).toBe('华为技术有限公司')
      expect(composable.sectionData.value.independence.team_independent).toBe('Y')
      expect(composable.sectionData.value.committee.applicability).toBe('N')
      expect(composable.sectionData.value.signature.date).toBe('2026-06-26')
      expect(composable.sectionData.value.response.opinion).toBe('同意')
      expect(composable.deficiencyList.value.major).toHaveLength(1)
      expect(composable.projectContext.value.audit_report_date).toBe('2026-06-30')
    })

    it('reactive htmlData watch triggers re-hydration', async () => {
      const { composable, htmlData } = setup(null)

      expect(composable.sectionData.value.addressee.client_name).toBe('')

      htmlData.value = {
        section_data: { addressee: { client_name: '新公司', custom_text: null } },
      }

      // Vue watchers are async — wait a tick
      await vi.runAllTimersAsync()

      expect(composable.sectionData.value.addressee.client_name).toBe('新公司')
    })
  })

  // ─── Section Navigation ───

  describe('scrollToSection', () => {
    it('updates activeSection ref', () => {
      const { composable } = setup()
      composable.scrollToSection('independence')
      expect(composable.activeSection.value).toBe('independence')
    })
  })

  // ─── EventBus: deficiency:severity-evaluated (Task 4.3) ───

  describe('EventBus subscription', () => {
    /** Helper: mount composable in component context for lifecycle hooks */
    function withSetup(renderData: A91RenderData | null = null) {
      let composable!: ReturnType<typeof useA91DeficiencyLetter>
      const Comp = defineComponent({
        setup() {
          const wpId = ref('wp-a91')
          const projectId = ref('proj-001')
          const htmlData = ref<A91RenderData | null>(renderData)
          composable = useA91DeficiencyLetter({ wpId, projectId, htmlData })
          return () => h('div')
        },
      })
      const wrapper = mount(Comp)
      return { composable, wrapper }
    }

    it('subscribes to deficiency:severity-evaluated on mount', () => {
      withSetup()
      expect(mockOn).toHaveBeenCalledWith('deficiency:severity-evaluated', expect.any(Function))
    })

    it('unsubscribes from deficiency:severity-evaluated on unmount', () => {
      const { wrapper } = withSetup()
      wrapper.unmount()
      expect(mockOff).toHaveBeenCalledWith('deficiency:severity-evaluated', expect.any(Function))
    })

    it('calls refreshFromB22B when deficiency:severity-evaluated event fires', async () => {
      mockGet.mockResolvedValue({
        sheets: [{
          html_data: {
            deficiency_list: {
              major: [{ id: 'NEW-1', description: '新缺陷', impact: '', recommendation: '', indexRef: null, source: 'b22b', severity: 'major' }],
              significant: [],
              general: [],
            },
            b22b_warning: null,
          },
        }],
      })

      const { composable } = withSetup()

      // Emit the event
      mockEmit('deficiency:severity-evaluated', { severities: [], overallConclusion: '存在重要缺陷' })

      // Wait for async refreshFromB22B
      await vi.runAllTimersAsync()
      await nextTick()

      expect(mockGet).toHaveBeenCalledWith(
        expect.stringContaining('/api/workpapers/wp-a91/render-config'),
        expect.anything(),
      )
      expect(composable.deficiencyList.value.major).toHaveLength(1)
      expect(composable.deficiencyList.value.major[0].description).toBe('新缺陷')
    })

    it('does not trigger refreshFromB22B after unmount', async () => {
      const { wrapper } = withSetup()
      wrapper.unmount()

      mockGet.mockClear()

      // Emit event after unmount — handler should have been removed
      mockEmit('deficiency:severity-evaluated', {})

      await vi.runAllTimersAsync()
      expect(mockGet).not.toHaveBeenCalled()
    })
  })
})
