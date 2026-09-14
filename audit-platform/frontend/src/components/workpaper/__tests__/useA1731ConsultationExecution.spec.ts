/**
 * Unit Tests — useA1731ConsultationExecution composable
 *
 * Spec: .kiro/specs/a17-3-1-consultation-execution/
 * Task: 2.3
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { useA1731ConsultationExecution } from '../composables/useA1731ConsultationExecution'

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

describe('useA1731ConsultationExecution', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockGet.mockReset()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  function setup(wpId = 'wp-123') {
    const wpIdRef = ref(wpId)
    return useA1731ConsultationExecution(wpIdRef)
  }

  // ─── Load Data ───

  describe('loadData', () => {
    it('loads and populates metaInfo, sections, a173Reference from render-config', async () => {
      mockGet.mockResolvedValue({
        sheets: [{
          html_data: {
            meta_info: { executor: '张三', execution_date: '2026-06-20', review_date: '2026-06-25', reviewer: '李四' },
            sections: {
              '1': { supplementary: '补充说明' },
              '2': { execution_details: '执行详情' },
              '3': { results: '结果' },
              '4': { follow_up: '跟进' },
            },
            a173_reference: { overview: '客户从事制造业', background: '收入确认问题' },
            project_context: { client_name: '测试公司', period: '2025年12月31日' },
          },
        }],
      })

      const { loadData, metaInfo, sections, a173Reference, projectContext } = setup()
      await loadData('wp-123')

      expect(metaInfo.value.executor).toBe('张三')
      expect(metaInfo.value.reviewer).toBe('李四')
      expect(sections.value[1].supplementary).toBe('补充说明')
      expect(sections.value[2].execution_details).toBe('执行详情')
      expect(sections.value[3].results).toBe('结果')
      expect(sections.value[4].follow_up).toBe('跟进')
      expect(a173Reference.value.overview).toBe('客户从事制造业')
      expect(a173Reference.value.background).toBe('收入确认问题')
      expect(projectContext.value.client_name).toBe('测试公司')
    })

    it('handles API failure gracefully without throwing', async () => {
      mockGet.mockRejectedValue(new Error('Network error'))

      const { loadData, loading, sections } = setup()
      await loadData('wp-123')

      expect(loading.value).toBe(false)
      expect(sections.value[1].supplementary).toBe('')  // defaults preserved
    })

    it('handles missing a173_reference gracefully', async () => {
      mockGet.mockResolvedValue({
        sheets: [{
          html_data: {
            meta_info: { executor: '', execution_date: '', review_date: '', reviewer: '' },
            sections: { '1': { supplementary: '' }, '2': { execution_details: '' }, '3': { results: '' }, '4': { follow_up: '' } },
            project_context: { client_name: '', period: '' },
          },
        }],
      })

      const { loadData, a173Reference } = setup()
      await loadData('wp-123')

      expect(a173Reference.value.overview).toBe('')
      expect(a173Reference.value.background).toBe('')
    })
  })

  // ─── Update Meta ───

  describe('updateMeta', () => {
    it('updates meta info value', () => {
      const { updateMeta, metaInfo } = setup()
      updateMeta('executor', '王五')
      expect(metaInfo.value.executor).toBe('王五')
    })

    it('sets saveStatus to unsaved', () => {
      const { updateMeta, saveStatus } = setup()
      updateMeta('reviewer', '赵六')
      expect(saveStatus.value).toBe('unsaved')
    })
  })

  // ─── Update Section ───

  describe('updateSection', () => {
    it('updates section field value', () => {
      const { updateSection, sections } = setup()
      updateSection(1, 'supplementary', '新的补充说明')
      expect(sections.value[1].supplementary).toBe('新的补充说明')
    })

    it('updates section 2 execution_details', () => {
      const { updateSection, sections } = setup()
      updateSection(2, 'execution_details', '执行详细内容')
      expect(sections.value[2].execution_details).toBe('执行详细内容')
    })
  })

  // ─── Debounce Save ───

  describe('debounce save', () => {
    it('saves after 2s debounce', async () => {
      const { updateSection } = setup()
      updateSection(1, 'supplementary', '内容1')

      expect(mockPut).not.toHaveBeenCalled()

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
      expect(mockPut).toHaveBeenCalledWith(
        '/api/workpapers/wp-123/checklist-responses',
        expect.objectContaining({
          items: expect.arrayContaining([
            expect.objectContaining({ item_id: 'a1731-sec1-supplementary', remark: '内容1' }),
          ]),
        }),
      )
    })

    it('batches multiple updates into single save', async () => {
      const { updateSection, updateMeta } = setup()
      updateSection(1, 'supplementary', '补充')
      updateSection(2, 'execution_details', '执行')
      updateMeta('executor', '张三')

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
      const items = mockPut.mock.calls[0][1].items
      expect(items).toHaveLength(3)
    })

    it('resets debounce on subsequent updates', async () => {
      const { updateSection } = setup()
      updateSection(1, 'supplementary', 'v1')

      vi.advanceTimersByTime(1500)
      updateSection(1, 'supplementary', 'v2')

      vi.advanceTimersByTime(1500)
      expect(mockPut).not.toHaveBeenCalled()

      vi.advanceTimersByTime(500)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
    })
  })

  // ─── Flush ───

  describe('flushPendingSaves', () => {
    it('immediately saves pending items', async () => {
      const { updateSection, flushPendingSaves } = setup()
      updateSection(3, 'results', '已完成')

      await flushPendingSaves()

      expect(mockPut).toHaveBeenCalledTimes(1)
      expect(mockPut).toHaveBeenCalledWith(
        '/api/workpapers/wp-123/checklist-responses',
        expect.objectContaining({
          items: [expect.objectContaining({ item_id: 'a1731-sec3-results', remark: '已完成' })],
        }),
      )
    })

    it('does nothing when no pending changes', async () => {
      const { flushPendingSaves } = setup()
      await flushPendingSaves()
      expect(mockPut).not.toHaveBeenCalled()
    })
  })

  // ─── Save Status ───

  describe('save status', () => {
    it('transitions saved → unsaved → saving → saved', async () => {
      const { updateSection, saveStatus } = setup()

      expect(saveStatus.value).toBe('saved')

      updateSection(1, 'supplementary', '内容')
      expect(saveStatus.value).toBe('unsaved')

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(saveStatus.value).toBe('saved')
    })
  })

  // ─── A17-3 Reference (read-only) ───

  describe('a173Reference', () => {
    it('is populated from render-config and is read-only (no save methods)', async () => {
      mockGet.mockResolvedValue({
        sheets: [{
          html_data: {
            meta_info: { executor: '', execution_date: '', review_date: '', reviewer: '' },
            sections: { '1': { supplementary: '' }, '2': { execution_details: '' }, '3': { results: '' }, '4': { follow_up: '' } },
            a173_reference: { overview: 'A17-3概述', background: 'A17-3背景' },
            project_context: { client_name: '', period: '' },
          },
        }],
      })

      const { loadData, a173Reference } = setup()
      await loadData('wp-123')

      expect(a173Reference.value.overview).toBe('A17-3概述')
      expect(a173Reference.value.background).toBe('A17-3背景')
    })
  })
})
