/**
 * Unit Tests — useA173ConsultationRecord composable
 *
 * Spec: .kiro/specs/a17-3-consultation-record/
 * Task: 2.3
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { useA173ConsultationRecord } from '../composables/useA173ConsultationRecord'

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

describe('useA173ConsultationRecord', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockGet.mockReset()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  function setup(wpId = 'wp-a173') {
    const wpIdRef = ref(wpId)
    return useA173ConsultationRecord(wpIdRef)
  }

  // ─── Empty State ───

  describe('empty state initialization', () => {
    it('initializes metaInfo with empty strings', () => {
      const { metaInfo } = setup()
      expect(metaInfo.value.department).toBe('')
      expect(metaInfo.value.client_name).toBe('')
      expect(metaInfo.value.consult_type).toBe('')
      expect(metaInfo.value.period).toBe('')
    })

    it('initializes sections with empty defaults', () => {
      const { sections } = setup()
      expect(sections.value[1].overview).toBe('')
      expect(sections.value[1].background).toBe('')
      expect(sections.value[1].files).toEqual([])
      expect(sections.value[2].opinion).toBe('')
      expect(sections.value[3].standards).toBe('')
      expect(sections.value[3].reply).toBe('')
      expect(sections.value[4].opinion).toBe('')
    })

    it('initializes saveStatus as saved', () => {
      const { saveStatus } = setup()
      expect(saveStatus.value).toBe('saved')
    })
  })

  // ─── Load Data ───

  describe('loadData', () => {
    it('loads and populates all data from render-config', async () => {
      mockGet.mockResolvedValue({
        sheets: [{
          html_data: {
            meta_info: { department: '审计一部', client_name: '测试公司', consult_type: '会计处理', period: '2025年12月31日' },
            sections: {
              '1': { overview: '制造业客户', background: '收入确认', files: ['合同.pdf', '邮件.eml'] },
              '2': { opinion: '应按时点确认' },
              '3': { standards: 'CAS 14', reply: '同意' },
              '4': { opinion: '技术委员会批准' },
            },
            project_context: { client_name: '测试公司', period: '2025年12月31日', current_user: '张三' },
          },
        }],
      })

      const { loadData, metaInfo, sections, projectContext } = setup()
      await loadData('wp-a173')

      expect(metaInfo.value.department).toBe('审计一部')
      expect(metaInfo.value.consult_type).toBe('会计处理')
      expect(sections.value[1].overview).toBe('制造业客户')
      expect(sections.value[1].files).toEqual(['合同.pdf', '邮件.eml'])
      expect(sections.value[2].opinion).toBe('应按时点确认')
      expect(sections.value[3].standards).toBe('CAS 14')
      expect(sections.value[4].opinion).toBe('技术委员会批准')
      expect(projectContext.value.client_name).toBe('测试公司')
    })

    it('handles API failure gracefully', async () => {
      mockGet.mockRejectedValue(new Error('Network error'))

      const { loadData, loading, sections } = setup()
      await loadData('wp-a173')

      expect(loading.value).toBe(false)
      expect(sections.value[1].files).toEqual([])
    })
  })

  // ─── Meta Update ───

  describe('updateMeta', () => {
    it('updates meta field value', () => {
      const { updateMeta, metaInfo } = setup()
      updateMeta('department', '审计二部')
      expect(metaInfo.value.department).toBe('审计二部')
    })

    it('updates consult_type', () => {
      const { updateMeta, metaInfo } = setup()
      updateMeta('consult_type', '独立性')
      expect(metaInfo.value.consult_type).toBe('独立性')
    })

    it('sets saveStatus to unsaved', () => {
      const { updateMeta, saveStatus } = setup()
      updateMeta('department', '审计部')
      expect(saveStatus.value).toBe('unsaved')
    })
  })

  // ─── Section Update ───

  describe('updateSection', () => {
    it('updates section 1 overview', () => {
      const { updateSection, sections } = setup()
      updateSection(1, 'overview', '客户背景描述')
      expect(sections.value[1].overview).toBe('客户背景描述')
    })

    it('updates section 2 opinion', () => {
      const { updateSection, sections } = setup()
      updateSection(2, 'opinion', '初步讨论意见')
      expect(sections.value[2].opinion).toBe('初步讨论意见')
    })

    it('updates section 3 standards', () => {
      const { updateSection, sections } = setup()
      updateSection(3, 'standards', 'CAS 14第10条')
      expect(sections.value[3].standards).toBe('CAS 14第10条')
    })

    it('updates section 4 opinion', () => {
      const { updateSection, sections } = setup()
      updateSection(4, 'opinion', '技术委员会意见')
      expect(sections.value[4].opinion).toBe('技术委员会意见')
    })
  })

  // ─── File Tag Management ───

  describe('addFileTag', () => {
    it('adds a file tag to section 1', () => {
      const { addFileTag, sections } = setup()
      addFileTag('合同.pdf')
      expect(sections.value[1].files).toEqual(['合同.pdf'])
    })

    it('adds multiple file tags preserving order', () => {
      const { addFileTag, sections } = setup()
      addFileTag('文件A')
      addFileTag('文件B')
      addFileTag('文件C')
      expect(sections.value[1].files).toEqual(['文件A', '文件B', '文件C'])
    })

    it('trims whitespace from file names', () => {
      const { addFileTag, sections } = setup()
      addFileTag('  带空格.pdf  ')
      expect(sections.value[1].files).toEqual(['带空格.pdf'])
    })

    it('ignores empty file names', () => {
      const { addFileTag, sections } = setup()
      addFileTag('')
      addFileTag('   ')
      expect(sections.value[1].files).toEqual([])
    })
  })

  describe('removeFileTag', () => {
    it('removes file tag at given index', () => {
      const { addFileTag, removeFileTag, sections } = setup()
      addFileTag('A')
      addFileTag('B')
      addFileTag('C')
      removeFileTag(1)
      expect(sections.value[1].files).toEqual(['A', 'C'])
    })

    it('does nothing for invalid index', () => {
      const { addFileTag, removeFileTag, sections } = setup()
      addFileTag('X')
      removeFileTag(5)
      removeFileTag(-1)
      expect(sections.value[1].files).toEqual(['X'])
    })
  })

  // ─── File Tag JSON Serialization ───

  describe('file tag JSON serialization in save', () => {
    it('saves file tags as JSON array in remark', async () => {
      const { addFileTag, flushPendingSaves } = setup()
      addFileTag('合同.pdf')
      addFileTag('邮件记录.eml')

      await flushPendingSaves()

      expect(mockPut).toHaveBeenCalledTimes(1)
      const items = mockPut.mock.calls[0][1].items
      const fileItem = items.find((i: any) => i.item_id === 'a173-sec1-files')
      expect(fileItem).toBeDefined()
      expect(fileItem.remark).toBe('["合同.pdf","邮件记录.eml"]')
      expect(fileItem.conclusion).toBe('2')
    })
  })

  // ─── Debounce Save ───

  describe('debounce save', () => {
    it('saves after 2s debounce', async () => {
      const { updateSection } = setup()
      updateSection(2, 'opinion', '测试意见')

      expect(mockPut).not.toHaveBeenCalled()

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
      expect(mockPut).toHaveBeenCalledWith(
        '/api/workpapers/wp-a173/checklist-responses',
        expect.objectContaining({
          items: expect.arrayContaining([
            expect.objectContaining({ item_id: 'a173-sec2-opinion' }),
          ]),
        }),
      )
    })

    it('batches multiple updates into single save', async () => {
      const { updateMeta, updateSection, addFileTag } = setup()
      updateMeta('department', '部门')
      updateSection(1, 'overview', '概况')
      updateSection(3, 'reply', '回复')
      addFileTag('文件')

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
      const items = mockPut.mock.calls[0][1].items
      expect(items.length).toBe(4)
    })

    it('resets debounce on subsequent updates', async () => {
      const { updateSection } = setup()
      updateSection(2, 'opinion', 'v1')

      vi.advanceTimersByTime(1500)
      updateSection(2, 'opinion', 'v2')

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
      const { updateMeta, flushPendingSaves } = setup()
      updateMeta('department', '审计部')

      await flushPendingSaves()

      expect(mockPut).toHaveBeenCalledTimes(1)
    })

    it('does nothing when no pending changes', async () => {
      const { flushPendingSaves } = setup()
      await flushPendingSaves()
      expect(mockPut).not.toHaveBeenCalled()
    })
  })

  // ─── Auto-fill ───

  describe('auto-fill from project context', () => {
    it('metaInfo reflects loaded project values', async () => {
      mockGet.mockResolvedValue({
        sheets: [{
          html_data: {
            meta_info: { department: '', client_name: '自动公司', consult_type: '', period: '2025年12月31日' },
            sections: { '1': { overview: '', background: '', files: [] }, '2': { opinion: '' }, '3': { standards: '', reply: '' }, '4': { opinion: '' } },
            project_context: { client_name: '自动公司', period: '2025年12月31日', current_user: '编制人' },
          },
        }],
      })

      const { loadData, metaInfo, projectContext } = setup()
      await loadData('wp-a173')

      expect(metaInfo.value.client_name).toBe('自动公司')
      expect(metaInfo.value.period).toBe('2025年12月31日')
      expect(projectContext.value.current_user).toBe('编制人')
    })
  })

  // ─── Save Status ───

  describe('save status transitions', () => {
    it('transitions saved → unsaved → saving → saved', async () => {
      const { updateSection, saveStatus } = setup()

      expect(saveStatus.value).toBe('saved')

      updateSection(2, 'opinion', '意见')
      expect(saveStatus.value).toBe('unsaved')

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(saveStatus.value).toBe('saved')
    })
  })
})
