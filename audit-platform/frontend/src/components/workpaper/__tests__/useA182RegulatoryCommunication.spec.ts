/**
 * Unit Tests — useA182RegulatoryCommunication composable
 *
 * Spec: .kiro/specs/a18-2-regulatory-communication/
 * Task: 2.3
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { useA182RegulatoryCommunication } from '../composables/useA182RegulatoryCommunication'

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

describe('useA182RegulatoryCommunication', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockGet.mockReset()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  function setup(wpId = 'wp-182') {
    const wpIdRef = ref(wpId)
    return useA182RegulatoryCommunication(wpIdRef)
  }

  // ─── Load Data ───

  describe('loadData', () => {
    it('loads and populates recipient, matters, issuance from render-config', async () => {
      mockGet.mockResolvedValue({
        sheets: [{
          html_data: {
            recipient: { authority: '中国证券监督管理委员会', custom: '' },
            matters: [
              { id: 1, title: '舞弊', applicability: 'Y', content: '发现舞弊' },
              { id: 2, title: '重大违反法律法规行为', applicability: 'N', content: '' },
              { id: 3, title: '年度报告中信息不一致或错报', applicability: 'NA', content: '' },
              { id: 4, title: '其他事项', applicability: null, content: '' },
            ],
            issuance: { cpa1: '张三', cpa2: '李四', date: '2026-03-15' },
            project_context: { client_name: '测试公司', audit_year: '2025', firm_name: '致同会计师事务所（特殊普通合伙）' },
          },
        }],
      })

      const { loadData, recipient, matters, issuance, projectContext } = setup()
      await loadData('wp-182')

      expect(recipient.value.authority).toBe('中国证券监督管理委员会')
      expect(matters.value[0].applicability).toBe('Y')
      expect(matters.value[0].content).toBe('发现舞弊')
      expect(matters.value[1].applicability).toBe('N')
      expect(issuance.value.cpa1).toBe('张三')
      expect(issuance.value.cpa2).toBe('李四')
      expect(projectContext.value.client_name).toBe('测试公司')
    })

    it('handles API failure gracefully', async () => {
      mockGet.mockRejectedValue(new Error('Network error'))

      const { loadData, loading, matters } = setup()
      await loadData('wp-182')

      expect(loading.value).toBe(false)
      expect(matters.value).toHaveLength(4)
      expect(matters.value[0].applicability).toBeNull()
    })
  })

  // ─── Recipient ───

  describe('updateRecipient', () => {
    it('updates recipient authority', () => {
      const { updateRecipient, recipient } = setup()
      updateRecipient('authority', '其他')
      expect(recipient.value.authority).toBe('其他')
    })

    it('updates recipient custom name', () => {
      const { updateRecipient, recipient } = setup()
      updateRecipient('custom', '某省财政厅')
      expect(recipient.value.custom).toBe('某省财政厅')
    })

    it('sets saveStatus to unsaved', () => {
      const { updateRecipient, saveStatus } = setup()
      updateRecipient('authority', '其他')
      expect(saveStatus.value).toBe('unsaved')
    })
  })

  // ─── Matter Applicability ───

  describe('updateMatter — applicability toggle', () => {
    it('sets matter applicability to Y', () => {
      const { updateMatter, matters } = setup()
      updateMatter(1, 'applicability', 'Y')
      expect(matters.value[0].applicability).toBe('Y')
    })

    it('sets matter applicability to N', () => {
      const { updateMatter, matters } = setup()
      updateMatter(2, 'applicability', 'N')
      expect(matters.value[1].applicability).toBe('N')
    })

    it('sets matter applicability to NA', () => {
      const { updateMatter, matters } = setup()
      updateMatter(3, 'applicability', 'NA')
      expect(matters.value[2].applicability).toBe('NA')
    })

    it('updates matter content', () => {
      const { updateMatter, matters } = setup()
      updateMatter(1, 'content', '发现重大舞弊')
      expect(matters.value[0].content).toBe('发现重大舞弊')
    })
  })

  // ─── Textarea Visibility (pure logic) ───

  describe('textarea visibility', () => {
    it('Y → textarea should be shown (content editable)', () => {
      const { updateMatter, matters } = setup()
      updateMatter(1, 'applicability', 'Y')
      expect(matters.value[0].applicability).toBe('Y')
    })

    it('N → textarea should be hidden', () => {
      const { updateMatter, matters } = setup()
      updateMatter(1, 'applicability', 'N')
      expect(matters.value[0].applicability).toBe('N')
    })

    it('NA → textarea should be hidden', () => {
      const { updateMatter, matters } = setup()
      updateMatter(1, 'applicability', 'NA')
      expect(matters.value[0].applicability).toBe('NA')
    })
  })

  // ─── Dual-Sign Fields ───

  describe('updateIssuance — dual sign', () => {
    it('updates cpa1 independently', () => {
      const { updateIssuance, issuance } = setup()
      updateIssuance('cpa1', '王五')
      expect(issuance.value.cpa1).toBe('王五')
      expect(issuance.value.cpa2).toBe('')
    })

    it('updates cpa2 independently', () => {
      const { updateIssuance, issuance } = setup()
      updateIssuance('cpa2', '赵六')
      expect(issuance.value.cpa2).toBe('赵六')
      expect(issuance.value.cpa1).toBe('')
    })

    it('updates date', () => {
      const { updateIssuance, issuance } = setup()
      updateIssuance('date', '2026-06-01')
      expect(issuance.value.date).toBe('2026-06-01')
    })
  })

  // ─── Debounce Save ───

  describe('debounce save', () => {
    it('saves after 2s debounce', async () => {
      const { updateRecipient } = setup()
      updateRecipient('authority', '中国证券监督管理委员会')

      expect(mockPut).not.toHaveBeenCalled()

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
      expect(mockPut).toHaveBeenCalledWith(
        '/api/workpapers/wp-182/checklist-responses',
        expect.objectContaining({
          items: expect.arrayContaining([
            expect.objectContaining({ item_id: 'a182-recipient-authority', remark: '中国证券监督管理委员会' }),
          ]),
        }),
      )
    })

    it('batches multiple updates into single save', async () => {
      const { updateRecipient, updateMatter, updateIssuance } = setup()
      updateRecipient('authority', '其他')
      updateMatter(1, 'applicability', 'Y')
      updateIssuance('cpa1', '张三')

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
      const items = mockPut.mock.calls[0][1].items
      expect(items).toHaveLength(3)
    })

    it('resets debounce on subsequent updates', async () => {
      const { updateMatter } = setup()
      updateMatter(1, 'content', 'v1')

      vi.advanceTimersByTime(1500)
      updateMatter(1, 'content', 'v2')

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
      const { updateIssuance, flushPendingSaves } = setup()
      updateIssuance('cpa1', '签字人')

      await flushPendingSaves()

      expect(mockPut).toHaveBeenCalledTimes(1)
      expect(mockPut).toHaveBeenCalledWith(
        '/api/workpapers/wp-182/checklist-responses',
        expect.objectContaining({
          items: [expect.objectContaining({ item_id: 'a182-sign-cpa1', remark: '签字人' })],
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
      const { updateMatter, saveStatus } = setup()

      expect(saveStatus.value).toBe('saved')

      updateMatter(1, 'applicability', 'Y')
      expect(saveStatus.value).toBe('unsaved')

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(saveStatus.value).toBe('saved')
    })
  })
})
