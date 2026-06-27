/**
 * Unit Tests — useA111SubsequentEvents composable
 *
 * Spec: .kiro/specs/a11-1-subsequent-events-inquiry/
 * Task: 2.3
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { useA111SubsequentEvents } from '../composables/useA111SubsequentEvents'

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

describe('useA111SubsequentEvents', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockGet.mockReset()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  function setup(wpId = 'wp-a111') {
    const wpIdRef = ref(wpId)
    return useA111SubsequentEvents(wpIdRef)
  }

  // ─── Empty State Initialization ───

  describe('empty state initialization', () => {
    it('initializes qaList with 10 items', () => {
      const { qaList } = setup()
      expect(qaList.value).toHaveLength(10)
      for (let i = 0; i < 10; i++) {
        expect(qaList.value[i].number).toBe(i + 1)
        expect(qaList.value[i].answer).toBe('')
      }
    })

    it('initializes metaData with null values', () => {
      const { metaData } = setup()
      expect(metaData.value.inquiryDate).toBeNull()
      expect(metaData.value.interviewee).toBeNull()
      expect(metaData.value.location).toBeNull()
      expect(metaData.value.teamSignature).toBeNull()
    })

    it('initializes evidence as empty string', () => {
      const { evidence } = setup()
      expect(evidence.value).toBe('')
    })

    it('initializes saveStatus as saved', () => {
      const { saveStatus } = setup()
      expect(saveStatus.value).toBe('saved')
    })

    it('initializes projectContext with defaults', () => {
      const { projectContext } = setup()
      expect(projectContext.value.clientName).toBe('')
      expect(projectContext.value.balanceSheetDate).toBeNull()
    })
  })

  // ─── Load Data ───

  describe('loadData', () => {
    it('loads and populates all data from render-config', async () => {
      mockGet.mockResolvedValue({
        sheets: [{
          html_data: {
            meta_data: {
              inquiry_date: '2026-03-20',
              interviewee: '张三',
              location: '会议室',
              team_signature: '李四',
            },
            qa_list: Array.from({ length: 10 }, (_, i) => ({ number: i + 1, answer: `答复${i + 1}` })),
            evidence: '银行对账单',
            project_context: { client_name: '测试公司', balance_sheet_date: '2025-12-31' },
            questions_config: Array.from({ length: 10 }, (_, i) => ({
              number: i + 1,
              title: `问题${i + 1}`,
              text: `文本${i + 1}`,
              has_guidance: i === 4,
              guidance_text: i === 4 ? '指导内容' : null,
            })),
          },
        }],
      })

      const { loadData, metaData, qaList, evidence, projectContext } = setup()
      await loadData('wp-a111')

      expect(metaData.value.inquiryDate).toBe('2026-03-20')
      expect(metaData.value.interviewee).toBe('张三')
      expect(metaData.value.location).toBe('会议室')
      expect(metaData.value.teamSignature).toBe('李四')

      expect(qaList.value).toHaveLength(10)
      expect(qaList.value[0].answer).toBe('答复1')
      expect(qaList.value[4].hasGuidance).toBe(true)
      expect(qaList.value[4].guidanceText).toBe('指导内容')

      expect(evidence.value).toBe('银行对账单')
      expect(projectContext.value.clientName).toBe('测试公司')
      expect(projectContext.value.balanceSheetDate).toBe('2025-12-31')
    })

    it('handles API failure gracefully', async () => {
      mockGet.mockRejectedValue(new Error('Network error'))

      const { loadData, loading, qaList } = setup()
      await loadData('wp-a111')

      expect(loading.value).toBe(false)
      expect(qaList.value).toHaveLength(10)
    })
  })

  // ─── Meta Updates ───

  describe('updateMeta', () => {
    it('updates inquiryDate', () => {
      const { updateMeta, metaData } = setup()
      updateMeta('inquiryDate', '2026-03-15')
      expect(metaData.value.inquiryDate).toBe('2026-03-15')
    })

    it('updates interviewee', () => {
      const { updateMeta, metaData } = setup()
      updateMeta('interviewee', '王五（CFO）')
      expect(metaData.value.interviewee).toBe('王五（CFO）')
    })

    it('updates location', () => {
      const { updateMeta, metaData } = setup()
      updateMeta('location', '总部大楼3层')
      expect(metaData.value.location).toBe('总部大楼3层')
    })

    it('updates teamSignature', () => {
      const { updateMeta, metaData } = setup()
      updateMeta('teamSignature', '审计员A')
      expect(metaData.value.teamSignature).toBe('审计员A')
    })

    it('sets saveStatus to unsaved', () => {
      const { updateMeta, saveStatus } = setup()
      updateMeta('interviewee', '张三')
      expect(saveStatus.value).toBe('unsaved')
    })
  })

  // ─── Answer Updates ───

  describe('updateAnswer', () => {
    it('updates answer for given question number', () => {
      const { updateAnswer, qaList } = setup()
      updateAnswer(1, '无新承诺')
      expect(qaList.value[0].answer).toBe('无新承诺')
    })

    it('updates answer for Q10', () => {
      const { updateAnswer, qaList } = setup()
      updateAnswer(10, '无其他事项')
      expect(qaList.value[9].answer).toBe('无其他事项')
    })

    it('sets saveStatus to unsaved', () => {
      const { updateAnswer, saveStatus } = setup()
      updateAnswer(5, '诉讼已结案')
      expect(saveStatus.value).toBe('unsaved')
    })
  })

  // ─── Evidence Updates ───

  describe('updateEvidence', () => {
    it('updates evidence value', () => {
      const { updateEvidence, evidence } = setup()
      updateEvidence('已提供银行对账单')
      expect(evidence.value).toBe('已提供银行对账单')
    })

    it('sets saveStatus to unsaved', () => {
      const { updateEvidence, saveStatus } = setup()
      updateEvidence('证据文本')
      expect(saveStatus.value).toBe('unsaved')
    })
  })

  // ─── Debounce Save ───

  describe('debounce save', () => {
    it('saves after 2s debounce', async () => {
      const { updateAnswer } = setup()
      updateAnswer(1, '答案1')

      expect(mockPut).not.toHaveBeenCalled()

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
      expect(mockPut).toHaveBeenCalledWith(
        '/api/workpapers/wp-a111/checklist-responses',
        expect.objectContaining({
          items: expect.arrayContaining([
            expect.objectContaining({ item_id: 'a111-qa-1', remark: '答案1' }),
          ]),
        }),
      )
    })

    it('batches multiple updates into single save', async () => {
      const { updateMeta, updateAnswer, updateEvidence } = setup()
      updateMeta('interviewee', '张三')
      updateAnswer(3, '无资本发行')
      updateEvidence('已提供证据')

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
      const items = mockPut.mock.calls[0][1].items
      expect(items.length).toBe(3)
    })

    it('resets debounce on subsequent updates', async () => {
      const { updateAnswer } = setup()
      updateAnswer(1, 'v1')

      vi.advanceTimersByTime(1500)
      updateAnswer(1, 'v2')

      vi.advanceTimersByTime(1500)
      expect(mockPut).not.toHaveBeenCalled()

      vi.advanceTimersByTime(500)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
      // Latest value wins
      const items = mockPut.mock.calls[0][1].items
      expect(items[0].remark).toBe('v2')
    })
  })

  // ─── Flush ───

  describe('flushPendingSaves', () => {
    it('immediately saves pending items', async () => {
      const { updateAnswer, flushPendingSaves } = setup()
      updateAnswer(5, '诉讼答复')

      await flushPendingSaves()

      expect(mockPut).toHaveBeenCalledTimes(1)
      expect(mockPut).toHaveBeenCalledWith(
        '/api/workpapers/wp-a111/checklist-responses',
        expect.objectContaining({
          items: [expect.objectContaining({ item_id: 'a111-qa-5', remark: '诉讼答复' })],
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
      const { updateAnswer, saveStatus } = setup()

      expect(saveStatus.value).toBe('saved')

      updateAnswer(1, '测试')
      expect(saveStatus.value).toBe('unsaved')

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(saveStatus.value).toBe('saved')
    })
  })

  // ─── Meta item_id format ───

  describe('meta field save item_id format', () => {
    it('inquiryDate saves as a111-meta-inquiry_date', async () => {
      const { updateMeta, flushPendingSaves } = setup()
      updateMeta('inquiryDate', '2026-03-15')
      await flushPendingSaves()

      const items = mockPut.mock.calls[0][1].items
      expect(items[0].item_id).toBe('a111-meta-inquiry_date')
    })

    it('teamSignature saves as a111-meta-team_signature', async () => {
      const { updateMeta, flushPendingSaves } = setup()
      updateMeta('teamSignature', '审计员')
      await flushPendingSaves()

      const items = mockPut.mock.calls[0][1].items
      expect(items[0].item_id).toBe('a111-meta-team_signature')
    })
  })
})
