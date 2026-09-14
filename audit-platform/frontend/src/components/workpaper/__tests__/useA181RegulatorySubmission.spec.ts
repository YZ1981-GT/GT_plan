/**
 * Unit Tests — useA181RegulatorySubmission composable
 *
 * Spec: .kiro/specs/a18-1-regulatory-submission/
 * Task: 2.3
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { useA181RegulatorySubmission } from '../composables/useA181RegulatorySubmission'

const mockGet = vi.fn()
const mockPut = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: { get: (...args: any[]) => mockGet(...args), put: (...args: any[]) => mockPut(...args) },
}))
vi.mock('element-plus', () => ({ ElMessage: { warning: vi.fn() } }))

describe('useA181RegulatorySubmission', () => {
  beforeEach(() => { vi.useFakeTimers(); mockGet.mockReset(); mockPut.mockReset(); mockPut.mockResolvedValue({}) })
  afterEach(() => { vi.useRealTimers() })

  function setup(wpId = 'wp-a181') {
    return useA181RegulatorySubmission(ref(wpId))
  }

  describe('loadData', () => {
    it('populates all sections from API', async () => {
      mockGet.mockResolvedValue({
        sheets: [{ html_data: {
          recipient: { bureau: '深圳市' },
          body: { contact_person: '张三', contact_phone: '123' },
          issuance: { partner: '李四', date: '2026-01-01' },
          project_context: { client_name: '测试', audit_year: '2025', firm_name: '致同', partner_name: '' },
        }}],
      })
      const { loadData, recipient, body, issuance } = setup()
      await loadData('wp-a181')
      expect(recipient.value.bureau).toBe('深圳市')
      expect(body.value.contact_person).toBe('张三')
      expect(issuance.value.date).toBe('2026-01-01')
    })
  })

  describe('updateField', () => {
    it('updates recipient field', () => {
      const { updateField, recipient } = setup()
      updateField('recipient', 'bureau', '北京市')
      expect(recipient.value.bureau).toBe('北京市')
    })

    it('sets saveStatus to unsaved', () => {
      const { updateField, saveStatus } = setup()
      updateField('body', 'contact_person', '王五')
      expect(saveStatus.value).toBe('unsaved')
    })
  })

  describe('debounce save', () => {
    it('saves with correct item_id format after 2s', async () => {
      const { updateField } = setup()
      updateField('recipient', 'bureau', '上海市')
      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()
      expect(mockPut).toHaveBeenCalledWith(
        '/api/workpapers/wp-a181/checklist-responses',
        expect.objectContaining({
          items: [expect.objectContaining({ item_id: 'a181-recipient-bureau', remark: '上海市' })],
        }),
      )
    })
  })

  describe('flushPendingSaves', () => {
    it('immediately saves', async () => {
      const { updateField, flushPendingSaves } = setup()
      updateField('issuance', 'partner', '赵六')
      await flushPendingSaves()
      expect(mockPut).toHaveBeenCalledTimes(1)
    })
  })
})
