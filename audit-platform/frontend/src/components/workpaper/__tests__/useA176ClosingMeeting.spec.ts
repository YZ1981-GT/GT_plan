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
    it('loads and populates meta_info and fields from render-config', async () => {
      mockGet.mockResolvedValue({
        sheets: [{
          html_data: {
            meta_info: { client_name: '测试公司', period: '2025年12月31日', preparer: '张三', reviewer: '李四', date: '2026-01-10', index_no: 'A17-6' },
            fields: { meeting_time: '2026-01-10 14:00', attendees: '全体项目组', minutes: '会议内容', conclusion: '结论', attachments: '附件A' },
            project_context: { client_name: '测试公司', period: '2025年12月31日', current_user: '张三' },
          },
        }],
      })

      const { loadData, metaInfo, fields, projectContext } = setup()
      await loadData('wp-123')

      expect(metaInfo.value.client_name).toBe('测试公司')
      expect(metaInfo.value.preparer).toBe('张三')
      expect(fields.value.meeting_time).toBe('2026-01-10 14:00')
      expect(fields.value.minutes).toBe('会议内容')
      expect(projectContext.value.current_user).toBe('张三')
    })

    it('handles API failure gracefully without throwing', async () => {
      mockGet.mockRejectedValue(new Error('Network error'))

      const { loadData, loading, fields } = setup()
      await loadData('wp-123')

      expect(loading.value).toBe(false)
      expect(fields.value.minutes).toBe('')  // defaults preserved
    })
  })

  // ─── Update Field ───

  describe('updateField', () => {
    it('updates reactive fields value', () => {
      const { updateField, fields } = setup()
      updateField('minutes', '新的会议纪要内容')
      expect(fields.value.minutes).toBe('新的会议纪要内容')
    })

    it('sets saveStatus to unsaved', () => {
      const { updateField, saveStatus } = setup()
      updateField('attendees', '全体')
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
      const { updateField } = setup()
      updateField('minutes', '内容1')

      expect(mockPut).not.toHaveBeenCalled()

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
      expect(mockPut).toHaveBeenCalledWith(
        '/api/workpapers/wp-123/checklist-responses',
        expect.objectContaining({
          items: expect.arrayContaining([
            expect.objectContaining({ item_id: 'a176-minutes', remark: '内容1' }),
          ]),
        }),
      )
    })

    it('batches multiple updates into single save', async () => {
      const { updateField, updateMeta } = setup()
      updateField('minutes', '纪要')
      updateField('attendees', '全体')
      updateMeta('reviewer', '李四')

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
      const items = mockPut.mock.calls[0][1].items
      expect(items).toHaveLength(3)
    })

    it('resets debounce on subsequent updates', async () => {
      const { updateField } = setup()
      updateField('minutes', 'v1')

      vi.advanceTimersByTime(1500)
      updateField('minutes', 'v2')

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
      const { updateField, flushPendingSaves } = setup()
      updateField('conclusion', '同意')

      await flushPendingSaves()

      expect(mockPut).toHaveBeenCalledTimes(1)
      expect(mockPut).toHaveBeenCalledWith(
        '/api/workpapers/wp-123/checklist-responses',
        expect.objectContaining({
          items: [expect.objectContaining({ item_id: 'a176-conclusion', remark: '同意' })],
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
      const { updateField, saveStatus } = setup()

      expect(saveStatus.value).toBe('saved')

      updateField('minutes', '内容')
      expect(saveStatus.value).toBe('unsaved')

      vi.advanceTimersByTime(2000)
      // saving state is set synchronously before await
      await vi.runAllTimersAsync()

      expect(saveStatus.value).toBe('saved')
    })
  })
})
