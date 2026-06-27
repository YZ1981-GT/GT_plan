/**
 * Unit Tests — useA174DisagreementRecord composable
 *
 * Spec: .kiro/specs/a17-4-disagreement-record/
 * Task: 2.3
 *
 * Tests: personnel CRUD, section update, signature auto-fill, debounce save
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { useA174DisagreementRecord } from '../composables/useA174DisagreementRecord'

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

describe('useA174DisagreementRecord', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockGet.mockReset()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  function setup(wpId = 'wp-174') {
    const wpIdRef = ref(wpId)
    return useA174DisagreementRecord(wpIdRef)
  }

  // ─── Load Data ───

  describe('loadData', () => {
    it('loads and populates personnel, sections, signature from render-config', async () => {
      mockGet.mockResolvedValue({
        sheets: [{
          html_data: {
            personnel: [
              { name: '张三', position: '审计经理', role: '项目负责人' },
            ],
            sections: {
              '1': { parties: '分歧人员' },
              '2': { cause: '事由' },
              '3': { procedures: '程序' },
              '4': { opinions: '意见' },
              '5': { considerations: '考虑' },
              '6': { conclusion: '结论' },
            },
            signature_data: { preparer: '编制人', reviewer: '复核人', date: '2026-06-20' },
            project_context: { client_name: '测试公司', current_user: '张三' },
          },
        }],
      })

      const { loadData, personnel, sections, signatureData, projectContext } = setup()
      await loadData('wp-174')

      expect(personnel.value).toHaveLength(1)
      expect(personnel.value[0].name).toBe('张三')
      expect(sections.value[1].parties).toBe('分歧人员')
      expect(sections.value[6].conclusion).toBe('结论')
      expect(signatureData.value.preparer).toBe('编制人')
      expect(projectContext.value.client_name).toBe('测试公司')
    })

    it('auto-fills preparer from current_user when empty', async () => {
      mockGet.mockResolvedValue({
        sheets: [{
          html_data: {
            personnel: [],
            sections: { '1': { parties: '' }, '2': { cause: '' }, '3': { procedures: '' }, '4': { opinions: '' }, '5': { considerations: '' }, '6': { conclusion: '' } },
            signature_data: { preparer: '', reviewer: '', date: '' },
            project_context: { client_name: '公司', current_user: '当前用户' },
          },
        }],
      })

      const { loadData, signatureData } = setup()
      await loadData('wp-174')

      expect(signatureData.value.preparer).toBe('当前用户')
    })

    it('does not override existing preparer with current_user', async () => {
      mockGet.mockResolvedValue({
        sheets: [{
          html_data: {
            personnel: [],
            sections: { '1': { parties: '' }, '2': { cause: '' }, '3': { procedures: '' }, '4': { opinions: '' }, '5': { considerations: '' }, '6': { conclusion: '' } },
            signature_data: { preparer: '已存在编制人', reviewer: '', date: '' },
            project_context: { client_name: '公司', current_user: '当前用户' },
          },
        }],
      })

      const { loadData, signatureData } = setup()
      await loadData('wp-174')

      expect(signatureData.value.preparer).toBe('已存在编制人')
    })

    it('handles API failure gracefully', async () => {
      mockGet.mockRejectedValue(new Error('Network error'))

      const { loadData, loading, personnel } = setup()
      await loadData('wp-174')

      expect(loading.value).toBe(false)
      expect(personnel.value).toEqual([])
    })
  })

  // ─── Personnel CRUD ───

  describe('personnel CRUD', () => {
    it('addPersonnel appends an empty row', () => {
      const { addPersonnel, personnel } = setup()
      expect(personnel.value).toHaveLength(0)

      addPersonnel()

      expect(personnel.value).toHaveLength(1)
      expect(personnel.value[0]).toEqual({ name: '', position: '', role: '' })
    })

    it('removePersonnel removes the specified row', () => {
      const { addPersonnel, removePersonnel, personnel } = setup()
      addPersonnel()
      addPersonnel()
      addPersonnel()

      removePersonnel(1)

      expect(personnel.value).toHaveLength(2)
    })

    it('removePersonnel with invalid index does nothing', () => {
      const { addPersonnel, removePersonnel, personnel } = setup()
      addPersonnel()

      removePersonnel(-1)
      removePersonnel(5)

      expect(personnel.value).toHaveLength(1)
    })

    it('updatePersonnel changes the specified field', () => {
      const { addPersonnel, updatePersonnel, personnel } = setup()
      addPersonnel()

      updatePersonnel(0, 'name', '王五')
      updatePersonnel(0, 'position', '审计师')
      updatePersonnel(0, 'role', '现场负责人')

      expect(personnel.value[0].name).toBe('王五')
      expect(personnel.value[0].position).toBe('审计师')
      expect(personnel.value[0].role).toBe('现场负责人')
    })

    it('updatePersonnel with invalid index does nothing', () => {
      const { updatePersonnel, personnel } = setup()
      updatePersonnel(0, 'name', '测试')
      expect(personnel.value).toHaveLength(0)
    })
  })

  // ─── Section Update ───

  describe('updateSection', () => {
    it('updates the correct section content', () => {
      const { updateSection, sections } = setup()

      updateSection(1, '新的分歧描述')
      updateSection(3, '咨询过程记录')

      expect(sections.value[1].parties).toBe('新的分歧描述')
      expect(sections.value[3].procedures).toBe('咨询过程记录')
    })

    it('sets saveStatus to unsaved', () => {
      const { updateSection, saveStatus } = setup()
      updateSection(2, '事由内容')
      expect(saveStatus.value).toBe('unsaved')
    })
  })

  // ─── Signature Update ───

  describe('updateSignature', () => {
    it('updates signature fields', () => {
      const { updateSignature, signatureData } = setup()

      updateSignature('reviewer', '复核人B')
      updateSignature('date', '2026-06-25')

      expect(signatureData.value.reviewer).toBe('复核人B')
      expect(signatureData.value.date).toBe('2026-06-25')
    })
  })

  // ─── Debounce Save ───

  describe('debounce save', () => {
    it('saves personnel after 2s debounce', async () => {
      const { addPersonnel, updatePersonnel } = setup()
      addPersonnel()
      updatePersonnel(0, 'name', '张三')

      expect(mockPut).not.toHaveBeenCalled()

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
      expect(mockPut).toHaveBeenCalledWith(
        '/api/workpapers/wp-174/checklist-responses',
        expect.objectContaining({
          items: expect.arrayContaining([
            expect.objectContaining({ item_id: 'a174-personnel' }),
          ]),
        }),
      )
    })

    it('saves sections with correct item_id format', async () => {
      const { updateSection } = setup()
      updateSection(3, '程序内容')

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledWith(
        '/api/workpapers/wp-174/checklist-responses',
        expect.objectContaining({
          items: [expect.objectContaining({ item_id: 'a174-sec3-procedures', remark: '程序内容' })],
        }),
      )
    })

    it('saves signature with correct item_id format', async () => {
      const { updateSignature } = setup()
      updateSignature('reviewer', '李四')

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledWith(
        '/api/workpapers/wp-174/checklist-responses',
        expect.objectContaining({
          items: [expect.objectContaining({ item_id: 'a174-signature-reviewer', conclusion: '李四' })],
        }),
      )
    })

    it('batches multiple updates into single save call', async () => {
      const { updateSection, updateSignature, addPersonnel } = setup()
      addPersonnel()
      updateSection(1, '分歧')
      updateSignature('date', '2026-06-20')

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
      const items = mockPut.mock.calls[0][1].items
      expect(items).toHaveLength(3)
    })

    it('resets debounce on subsequent updates', async () => {
      const { updateSection } = setup()
      updateSection(1, 'v1')

      vi.advanceTimersByTime(1500)
      updateSection(1, 'v2')

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
      updateSection(6, '结论内容')

      await flushPendingSaves()

      expect(mockPut).toHaveBeenCalledTimes(1)
      expect(mockPut).toHaveBeenCalledWith(
        '/api/workpapers/wp-174/checklist-responses',
        expect.objectContaining({
          items: [expect.objectContaining({ item_id: 'a174-sec6-conclusion', remark: '结论内容' })],
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

      updateSection(1, '内容')
      expect(saveStatus.value).toBe('unsaved')

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(saveStatus.value).toBe('saved')
    })
  })
})
