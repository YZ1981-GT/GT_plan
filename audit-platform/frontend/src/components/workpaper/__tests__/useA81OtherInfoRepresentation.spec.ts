/**
 * Unit Tests — useA81OtherInfoRepresentation composable
 *
 * Spec: .kiro/specs/a8-1-other-info-representation/
 * Task: 2.3
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { useA81OtherInfoRepresentation } from '../composables/useA81OtherInfoRepresentation'

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

describe('useA81OtherInfoRepresentation', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockGet.mockReset()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  function setup(wpId = 'wp-a81') {
    const wpIdRef = ref(wpId)
    return useA81OtherInfoRepresentation(wpIdRef)
  }

  // ─── Empty State Initialization ───

  describe('empty state initialization', () => {
    it('initializes statements with default empty values', () => {
      const { statements } = setup()
      expect(statements.value[1].files).toEqual([])
      expect(statements.value[2].date).toBeNull()
      expect(statements.value[3].consistency).toBeNull()
      expect(statements.value[3].explanation).toBeNull()
      expect(statements.value[4].files).toEqual([])
      expect(statements.value[5].files).toEqual([])
      expect(statements.value[6].other).toBeNull()
    })

    it('initializes signatureData with null values', () => {
      const { signatureData } = setup()
      expect(signatureData.value.representative).toBeNull()
      expect(signatureData.value.signatureDate).toBeNull()
    })

    it('initializes projectContext with empty defaults', () => {
      const { projectContext } = setup()
      expect(projectContext.value.clientName).toBe('')
      expect(projectContext.value.auditReportDate).toBeNull()
      expect(projectContext.value.cpaNames).toEqual([])
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
            statements: {
              '1': { files: ['年报', '财务报表'] },
              '2': { date: '2026-04-30' },
              '3': { consistency: 'Y', explanation: null },
              '4': { files: ['审计报告'] },
              '5': { files: [] },
              '6': { other: '无' },
            },
            signature_data: { representative: '张三', signature_date: '2026-03-31' },
            project_context: { client_name: '测试公司', audit_report_date: '2026-03-31', cpa_names: ['王五'] },
          },
        }],
      })

      const { loadData, statements, signatureData, projectContext } = setup()
      await loadData('wp-a81')

      expect(statements.value[1].files).toEqual(['年报', '财务报表'])
      expect(statements.value[2].date).toBe('2026-04-30')
      expect(statements.value[3].consistency).toBe('Y')
      expect(statements.value[4].files).toEqual(['审计报告'])
      expect(statements.value[6].other).toBe('无')
      expect(signatureData.value.representative).toBe('张三')
      expect(signatureData.value.signatureDate).toBe('2026-03-31')
      expect(projectContext.value.clientName).toBe('测试公司')
      expect(projectContext.value.cpaNames).toEqual(['王五'])
    })

    it('defaults signature date to audit_report_date when not set', async () => {
      mockGet.mockResolvedValue({
        sheets: [{
          html_data: {
            statements: { '1': { files: [] }, '2': { date: null }, '3': { consistency: null, explanation: null }, '4': { files: [] }, '5': { files: [] }, '6': { other: null } },
            signature_data: { representative: null, signature_date: null },
            project_context: { client_name: '公司', audit_report_date: '2026-06-30', cpa_names: [] },
          },
        }],
      })

      const { loadData, signatureData } = setup()
      await loadData('wp-a81')

      expect(signatureData.value.signatureDate).toBe('2026-06-30')
    })

    it('handles API failure gracefully', async () => {
      mockGet.mockRejectedValue(new Error('Network error'))

      const { loadData, loading, statements } = setup()
      await loadData('wp-a81')

      expect(loading.value).toBe(false)
      expect(statements.value[1].files).toEqual([])
    })
  })

  // ─── File List Add/Remove ───

  describe('addFile', () => {
    it('adds a file to statement 1 list', () => {
      const { addFile, statements } = setup()
      addFile(1, '董事会报告')
      expect(statements.value[1].files).toEqual(['董事会报告'])
    })

    it('adds multiple files preserving order', () => {
      const { addFile, statements } = setup()
      addFile(1, '文件A')
      addFile(1, '文件B')
      addFile(1, '文件C')
      expect(statements.value[1].files).toEqual(['文件A', '文件B', '文件C'])
    })

    it('trims whitespace from file names', () => {
      const { addFile, statements } = setup()
      addFile(4, '  带空格文件  ')
      expect(statements.value[4].files).toEqual(['带空格文件'])
    })

    it('ignores empty file names', () => {
      const { addFile, statements } = setup()
      addFile(5, '')
      addFile(5, '   ')
      expect(statements.value[5].files).toEqual([])
    })

    it('sets saveStatus to unsaved', () => {
      const { addFile, saveStatus } = setup()
      addFile(1, '文件')
      expect(saveStatus.value).toBe('unsaved')
    })
  })

  describe('removeFile', () => {
    it('removes file at given index', () => {
      const { addFile, removeFile, statements } = setup()
      addFile(1, 'A')
      addFile(1, 'B')
      addFile(1, 'C')
      removeFile(1, 1)
      expect(statements.value[1].files).toEqual(['A', 'C'])
    })

    it('does nothing for invalid index', () => {
      const { addFile, removeFile, statements } = setup()
      addFile(4, 'X')
      removeFile(4, 5)
      expect(statements.value[4].files).toEqual(['X'])
    })
  })

  // ─── File List JSON Serialization ───

  describe('file list JSON serialization in save', () => {
    it('saves file list as JSON array in remark', async () => {
      const { addFile, flushPendingSaves } = setup()
      addFile(1, '年报')
      addFile(1, '财务报告')

      await flushPendingSaves()

      expect(mockPut).toHaveBeenCalledTimes(1)
      const items = mockPut.mock.calls[0][1].items
      const fileItem = items.find((i: any) => i.item_id === 'a81-statement-1-files')
      expect(fileItem).toBeDefined()
      expect(fileItem.remark).toBe('["年报","财务报告"]')
      expect(fileItem.conclusion).toBe('2')
    })
  })

  // ─── Statement Updates ───

  describe('updateStatement', () => {
    it('updates statement 2 date', () => {
      const { updateStatement, statements } = setup()
      updateStatement(2, 'date', '2026-05-01')
      expect(statements.value[2].date).toBe('2026-05-01')
    })

    it('updates statement 3 consistency', () => {
      const { updateStatement, statements } = setup()
      updateStatement(3, 'consistency', 'N')
      expect(statements.value[3].consistency).toBe('N')
    })

    it('updates statement 3 explanation', () => {
      const { updateStatement, statements } = setup()
      updateStatement(3, 'explanation', '存在差异')
      expect(statements.value[3].explanation).toBe('存在差异')
    })

    it('updates statement 6 other', () => {
      const { updateStatement, statements } = setup()
      updateStatement(6, 'other', '补充内容')
      expect(statements.value[6].other).toBe('补充内容')
    })
  })

  // ─── Signature Updates ───

  describe('updateSignature', () => {
    it('updates representative', () => {
      const { updateSignature, signatureData } = setup()
      updateSignature('representative', '李四')
      expect(signatureData.value.representative).toBe('李四')
    })

    it('updates date', () => {
      const { updateSignature, signatureData } = setup()
      updateSignature('date', '2026-06-30')
      expect(signatureData.value.signatureDate).toBe('2026-06-30')
    })
  })

  // ─── Debounce Save ───

  describe('debounce save', () => {
    it('saves after 2s debounce', async () => {
      const { updateStatement } = setup()
      updateStatement(2, 'date', '2026-04-30')

      expect(mockPut).not.toHaveBeenCalled()

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
      expect(mockPut).toHaveBeenCalledWith(
        '/api/workpapers/wp-a81/checklist-responses',
        expect.objectContaining({
          items: expect.arrayContaining([
            expect.objectContaining({ item_id: 'a81-statement-2-date' }),
          ]),
        }),
      )
    })

    it('batches multiple updates into single save', async () => {
      const { updateStatement, updateSignature, addFile } = setup()
      updateStatement(2, 'date', '2026-04-30')
      updateStatement(3, 'consistency', 'Y')
      updateSignature('representative', '张三')
      addFile(1, '文件')

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
      const items = mockPut.mock.calls[0][1].items
      expect(items.length).toBe(4)
    })

    it('resets debounce on subsequent updates', async () => {
      const { updateStatement } = setup()
      updateStatement(6, 'other', 'v1')

      vi.advanceTimersByTime(1500)
      updateStatement(6, 'other', 'v2')

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
      const { updateSignature, flushPendingSaves } = setup()
      updateSignature('representative', '王五')

      await flushPendingSaves()

      expect(mockPut).toHaveBeenCalledTimes(1)
      expect(mockPut).toHaveBeenCalledWith(
        '/api/workpapers/wp-a81/checklist-responses',
        expect.objectContaining({
          items: [expect.objectContaining({ item_id: 'a81-signature-representative', remark: '王五' })],
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
      const { updateStatement, saveStatus } = setup()

      expect(saveStatus.value).toBe('saved')

      updateStatement(2, 'date', '2026-01-01')
      expect(saveStatus.value).toBe('unsaved')

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(saveStatus.value).toBe('saved')
    })
  })
})
