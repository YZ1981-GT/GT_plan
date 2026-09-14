/**
 * Unit Tests — useA176ClosingMeeting composable
 *
 * Spec: .kiro/specs/a17-6-closing-meeting/
 * Task: 2.3
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { useA176ClosingMeeting } from '../composables/useA176ClosingMeeting'

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

describe('useA176ClosingMeeting', () => {
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
    return useA176ClosingMeeting(wpIdRef)
  }

  // ─── Load Data ───

  describe('loadData', () => {
    it('loads and populates meta_info and agenda from render-config', async () => {
      mockGet.mockResolvedValue({
        sheets: [{
          html_data: {
            meta_info: {
              client_name: '测试公司',
              period: '2025年12月31日',
              preparer: '张三',
              reviewer: '李四',
              index_no: 'A17-6',
              meeting_time: '2026-01-10 14:00',
              attendees: '全体项目组',
            },
            agenda: { 1: '总体审计意见内容', 2: '计划执行评估' },
            project_context: { client_name: '测试公司', period: '2025年12月31日', current_user: '张三' },
          },
        }],
      })

      const { loadData, metaInfo, agenda, projectContext } = setup()
      await loadData('wp-123')

      expect(metaInfo.value.client_name).toBe('测试公司')
      expect(metaInfo.value.preparer).toBe('张三')
      expect(agenda.value[1]).toBe('总体审计意见内容')
      expect(agenda.value[2]).toBe('计划执行评估')
      expect(projectContext.value.current_user).toBe('张三')
    })

    it('handles API failure gracefully without throwing', async () => {
      mockGet.mockRejectedValue(new Error('Network error'))

      const { loadData, loading, agenda } = setup()
      await loadData('wp-123')

      expect(loading.value).toBe(false)
      expect(agenda.value[1]).toBe('')
    })
  })

  // ─── Update Agenda ───

  describe('updateAgenda', () => {
    it('updates reactive agenda value', () => {
      const { updateAgenda, agenda } = setup()
      updateAgenda(5, '已发现错报汇总内容')
      expect(agenda.value[5]).toBe('已发现错报汇总内容')
    })

    it('sets saveStatus to unsaved', () => {
      const { updateAgenda, saveStatus } = setup()
      updateAgenda(3, '特别风险讨论')
      expect(saveStatus.value).toBe('unsaved')
    })
  })

  // ─── Update Meta ───

  describe('updateMeta', () => {
    it('updates meta info value', () => {
      const { updateMeta, metaInfo } = setup()
      updateMeta('reviewer', '王五')
      expect(metaInfo.value.reviewer).toBe('王五')
    })
  })

  // ─── Debounce Save ───

  describe('debounce save', () => {
    it('saves after 2s debounce', async () => {
      const { updateAgenda } = setup()
      updateAgenda(1, '内容1')

      expect(mockPut).not.toHaveBeenCalled()

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
      expect(mockPut).toHaveBeenCalledWith(
        '/api/workpapers/wp-123/checklist-responses',
        expect.objectContaining({
          items: expect.arrayContaining([
            expect.objectContaining({ item_id: 'a176-agenda-1', remark: '内容1' }),
          ]),
        }),
      )
    })

    it('batches multiple updates into single save', async () => {
      const { updateAgenda, updateMeta } = setup()
      updateAgenda(1, '议题1')
      updateAgenda(2, '议题2')
      updateMeta('reviewer', '李四')

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
      const items = mockPut.mock.calls[0][1].items
      expect(items).toHaveLength(3)
    })

    it('resets debounce on subsequent updates', async () => {
      const { updateAgenda } = setup()
      updateAgenda(1, 'v1')

      vi.advanceTimersByTime(1500)
      updateAgenda(1, 'v2')

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
      const { updateAgenda, flushPendingSaves } = setup()
      updateAgenda(8, '拟发表审计意见')

      await flushPendingSaves()

      expect(mockPut).toHaveBeenCalledTimes(1)
      expect(mockPut).toHaveBeenCalledWith(
        '/api/workpapers/wp-123/checklist-responses',
        expect.objectContaining({
          items: [expect.objectContaining({ item_id: 'a176-agenda-8', remark: '拟发表审计意见' })],
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
      const { updateAgenda, saveStatus } = setup()

      expect(saveStatus.value).toBe('saved')

      updateAgenda(1, '内容')
      expect(saveStatus.value).toBe('unsaved')

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(saveStatus.value).toBe('saved')
    })
  })
})
