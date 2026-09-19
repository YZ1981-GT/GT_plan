/**
 * Unit Tests — useA121LegalConfirmation composable
 *
 * Spec: .kiro/specs/a12-1-legal-confirmation/
 * Task: 2.3
 *
 * Coverage:
 * - Debounce save timing (2s, not before)
 * - Litigation CRUD (add/remove/update)
 * - JSON serialization for litigation list
 * - Field update by part (send/reply)
 * - Flush pending saves
 *
 * **Validates: Requirements 4.2, 5.1-5.5, 12.1-12.3**
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { useA121LegalConfirmation } from '../composables/useA121LegalConfirmation'
import type { A121RenderData } from '../composables/useA121LegalConfirmation'

// ─── Mock API ────────────────────────────────────────────────────────────────

const mockPut = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn().mockResolvedValue({}),
    put: (...args: any[]) => mockPut(...args),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), error: vi.fn() },
}))

// ─── Setup ───────────────────────────────────────────────────────────────────

function setup(renderData: A121RenderData | null = null) {
  const wpId = ref('wp-a121')
  const projectId = ref('proj-001')
  const htmlData = ref<A121RenderData | null>(renderData)
  return { composable: useA121LegalConfirmation({ wpId, projectId, htmlData }), wpId, projectId, htmlData }
}

describe('useA121LegalConfirmation', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // ─── Debounce Timing ───

  describe('debounce save timing', () => {
    it('updateField triggers save after 2s, not before', async () => {
      const { composable } = setup()
      composable.updateField('send', 'recipient-firm', '大成律师事务所')

      expect(mockPut).not.toHaveBeenCalled()
      expect(composable.saveStatus.value).toBe('unsaved')

      vi.advanceTimersByTime(1500)
      expect(mockPut).not.toHaveBeenCalled()

      vi.advanceTimersByTime(500)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
      expect(mockPut).toHaveBeenCalledWith(
        '/api/workpapers/wp-a121/checklist-responses',
        expect.objectContaining({
          items: expect.arrayContaining([
            expect.objectContaining({ item_id: 'a121-send-recipient-firm', conclusion: '大成律师事务所' }),
          ]),
        }),
      )
    })

    it('batches multiple updates into single save', async () => {
      const { composable } = setup()
      composable.updateField('send', 'recipient-firm', '事务所A')
      composable.updateField('send', 'recipient-lawyer', '张律师')

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
      const items = mockPut.mock.calls[0][1].items
      expect(items).toHaveLength(2)
    })
  })

  // ─── Litigation CRUD ───

  describe('litigation CRUD', () => {
    it('addLitigation adds empty record', () => {
      const { composable } = setup()
      composable.addLitigation()

      const list = composable.sendSection.value.inquiry_1.litigation_list
      expect(list).toHaveLength(1)
      expect(list[0]).toEqual({ description: null, opinion: null, estimated_loss: null })
    })

    it('removeLitigation removes at index', () => {
      const { composable } = setup()
      composable.addLitigation()
      composable.addLitigation()
      composable.updateLitigation(0, 'description', '案件A')
      composable.updateLitigation(1, 'description', '案件B')

      composable.removeLitigation(0)

      const list = composable.sendSection.value.inquiry_1.litigation_list
      expect(list).toHaveLength(1)
      expect(list[0].description).toBe('案件B')
    })

    it('removeLitigation ignores invalid index', () => {
      const { composable } = setup()
      composable.addLitigation()
      composable.removeLitigation(-1)
      composable.removeLitigation(5)

      expect(composable.sendSection.value.inquiry_1.litigation_list).toHaveLength(1)
    })

    it('updateLitigation updates field correctly', () => {
      const { composable } = setup()
      composable.addLitigation()
      composable.updateLitigation(0, 'description', '合同纠纷')
      composable.updateLitigation(0, 'opinion', '可能败诉')
      composable.updateLitigation(0, 'estimated_loss', 50000)

      const row = composable.sendSection.value.inquiry_1.litigation_list[0]
      expect(row.description).toBe('合同纠纷')
      expect(row.opinion).toBe('可能败诉')
      expect(row.estimated_loss).toBe(50000)
    })
  })

  // ─── JSON Serialization ───

  describe('litigation JSON serialization', () => {
    it('litigation save includes JSON array in remark', async () => {
      const { composable } = setup()
      composable.addLitigation()
      composable.updateLitigation(0, 'description', '测试案件')
      composable.updateLitigation(0, 'estimated_loss', 100000)

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      const items = mockPut.mock.calls[0][1].items
      const litItem = items.find((i: any) => i.item_id === 'a121-send-litigation')
      expect(litItem).toBeDefined()
      expect(litItem.conclusion).toBe('1')
      const parsed = JSON.parse(litItem.remark)
      expect(parsed).toHaveLength(1)
      expect(parsed[0].description).toBe('测试案件')
      expect(parsed[0].estimated_loss).toBe(100000)
    })
  })

  // ─── Field Update by Part ───

  describe('field update by part', () => {
    it('send fields update sendSection reactive state', () => {
      const { composable } = setup()
      composable.updateField('send', 'recipient-firm', '锦天城')
      expect(composable.sendSection.value.recipient.firm_name).toBe('锦天城')

      composable.updateField('send', 'sign-date', '2026-06-01')
      expect(composable.sendSection.value.sign_info.date).toBe('2026-06-01')
    })

    it('reply fields update replySection reactive state', () => {
      const { composable } = setup()
      composable.updateField('reply', 'status', 'has_litigation')
      expect(composable.replySection.value.litigation_status).toBe('has_litigation')

      composable.updateField('reply', 'fee-amount', '50000')
      expect(composable.replySection.value.outstanding_amount).toBe(50000)
    })

    it('inquiry text saved as remark not conclusion', async () => {
      const { composable } = setup()
      composable.updateField('send', 'inquiry2-content', '长文本内容')

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      const items = mockPut.mock.calls[0][1].items
      const item = items.find((i: any) => i.item_id === 'a121-send-inquiry2-content')
      expect(item.remark).toBe('长文本内容')
      expect(item.conclusion).toBeNull()
    })
  })

  // ─── Flush ───

  describe('flush pending saves', () => {
    it('flushPendingSaves sends immediately without waiting 2s', async () => {
      const { composable } = setup()
      composable.updateField('send', 'recipient-firm', '测试')

      expect(mockPut).not.toHaveBeenCalled()
      await composable.flushPendingSaves()

      expect(mockPut).toHaveBeenCalledTimes(1)
    })

    it('flushPendingSaves is idempotent when no pending changes', async () => {
      const { composable } = setup()
      await composable.flushPendingSaves()
      expect(mockPut).not.toHaveBeenCalled()
    })
  })

  // ─── Hydration ───

  describe('hydration from render data', () => {
    it('hydrates sendSection from htmlData', () => {
      const data: A121RenderData = {
        send_section: {
          recipient: { firm_name: '国浩', lawyer_name: '李律师' },
          inquiry_1: { litigation_list: [{ description: '案件', opinion: '胜诉', estimated_loss: 10000 }] },
          inquiry_2: { content: '其他事项' },
          sign_info: { company_name: 'ABC公司', date: '2026-01-01' },
        },
      }
      const { composable } = setup(data)

      expect(composable.sendSection.value.recipient.firm_name).toBe('国浩')
      expect(composable.sendSection.value.inquiry_1.litigation_list).toHaveLength(1)
      expect(composable.sendSection.value.inquiry_2.content).toBe('其他事项')
    })

    it('hydrates replySection from htmlData', () => {
      const data: A121RenderData = {
        reply_section: {
          litigation_status: 'has_litigation',
          litigation_details: '详情',
          fee_status: 'has_outstanding',
          outstanding_amount: 25000,
          sign: { firm_name: '事务所', lawyer_name: '律师', date: '2026-02-01' },
        },
      }
      const { composable } = setup(data)

      expect(composable.replySection.value.litigation_status).toBe('has_litigation')
      expect(composable.replySection.value.outstanding_amount).toBe(25000)
      expect(composable.replySection.value.sign.firm_name).toBe('事务所')
    })
  })

  // ─── Conditional Logic ───

  describe('conditional computed', () => {
    it('showLitigationDetails true when has_litigation', () => {
      const { composable } = setup({ reply_section: { litigation_status: 'has_litigation' } })
      expect(composable.showLitigationDetails.value).toBe(true)
    })

    it('showLitigationDetails false when no_litigation', () => {
      const { composable } = setup({ reply_section: { litigation_status: 'no_litigation' } })
      expect(composable.showLitigationDetails.value).toBe(false)
    })

    it('showOutstandingAmount true when has_outstanding', () => {
      const { composable } = setup({ reply_section: { fee_status: 'has_outstanding' } })
      expect(composable.showOutstandingAmount.value).toBe(true)
    })

    it('showOutstandingAmount false when no_outstanding', () => {
      const { composable } = setup({ reply_section: { fee_status: 'no_outstanding' } })
      expect(composable.showOutstandingAmount.value).toBe(false)
    })
  })
})
