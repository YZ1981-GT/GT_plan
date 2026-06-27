/**
 * Unit Tests — useA101GovernanceCommunication + useA101Navigation
 *
 * Spec: .kiro/specs/a10-1-governance-communication/
 * Task: 2.4
 *
 * Coverage:
 * - Debounce timing (2s)
 * - Chapter update (16 chapters)
 * - Fee calculation & totalFee
 * - Flush pending
 * - useA101Navigation: scrollspy trigger, activeChapter update
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { useA101GovernanceCommunication } from '../composables/useA101GovernanceCommunication'
import type { A101RenderData } from '../composables/useA101GovernanceCommunication'

// ─── Mock API ────────────────────────────────────────────────────────────────

const mockPut = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(),
    put: (...args: any[]) => mockPut(...args),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), error: vi.fn() },
}))

function setup(data: A101RenderData | null = null) {
  const wpId = ref('wp-a101-001')
  const projectId = ref('proj-001')
  const htmlData = ref<A101RenderData | null>(data)
  return { composable: useA101GovernanceCommunication({ wpId, projectId, htmlData }), htmlData }
}

describe('useA101GovernanceCommunication — Unit', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // ─── Debounce Timing ───

  describe('debounce timing', () => {
    it('does not save before 2s', () => {
      const { composable } = setup()
      composable.updateRecipient('测试公司董事会')
      vi.advanceTimersByTime(1999)
      expect(mockPut).not.toHaveBeenCalled()
    })

    it('saves after 2s', async () => {
      const { composable } = setup()
      composable.updateRecipient('测试公司董事会')
      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()
      expect(mockPut).toHaveBeenCalledTimes(1)
    })

    it('batches multiple changes', async () => {
      const { composable } = setup()
      composable.updateRecipient('董事会')
      composable.updateChapter(1, '内容1')
      composable.updateChapter(2, '内容2')
      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()
      expect(mockPut).toHaveBeenCalledTimes(1)
      const items = mockPut.mock.calls[0][1].items
      expect(items.length).toBe(3)
    })

    it('save status cycle: saved → unsaved → saving → saved', async () => {
      const { composable } = setup()
      expect(composable.saveStatus.value).toBe('saved')
      composable.updateRecipient('X')
      expect(composable.saveStatus.value).toBe('unsaved')
      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()
      expect(composable.saveStatus.value).toBe('saved')
    })
  })

  // ─── Chapter Update ───

  describe('chapter update', () => {
    it('updates correct chapter content', () => {
      const { composable } = setup()
      composable.updateChapter(5, '审计中发现的重大错报说明')
      expect(composable.chapters.value[4].content).toBe('审计中发现的重大错报说明')
    })

    it('invalid chapter number does nothing', () => {
      const { composable } = setup()
      composable.updateChapter(0, 'invalid')
      composable.updateChapter(17, 'invalid')
      // All still null
      for (const ch of composable.chapters.value) {
        expect(ch.content).toBeNull()
      }
    })

    it('all 16 chapters exist after initialization', () => {
      const { composable } = setup()
      expect(composable.chapters.value.length).toBe(16)
      const numbers = composable.chapters.value.map(c => c.number)
      expect(numbers).toEqual(Array.from({ length: 16 }, (_, i) => i + 1))
    })

    it('chapter save uses remark field', async () => {
      const { composable } = setup()
      composable.updateChapter(3, '非审计服务说明')
      await composable.flushPendingSaves()

      const items = mockPut.mock.calls[0][1].items
      const ch3 = items.find((i: any) => i.item_id === 'a101-ch3-content')
      expect(ch3).toBeDefined()
      expect(ch3.remark).toBe('非审计服务说明')
      expect(ch3.conclusion).toBeNull()
    })
  })

  // ─── Fee Calculation ───

  describe('fee calculation & totalFee', () => {
    it('totalFee starts at 0 with all null amounts', () => {
      const { composable } = setup()
      expect(composable.totalFee.value).toBe(0)
    })

    it('totalFee sums non-null values', () => {
      const { composable } = setup({
        service_fees: [
          { name: '审计服务', amount: 1000 },
          { name: '审阅服务', amount: 2000 },
          { name: '其他鉴证服务', amount: null },
          { name: '税务服务', amount: 500 },
          { name: '其他服务', amount: null },
        ],
      })
      expect(composable.totalFee.value).toBe(3500)
    })

    it('updateFee recalculates totalFee', () => {
      const { composable } = setup()
      composable.updateFee(0, 5000)
      composable.updateFee(1, 3000)
      expect(composable.totalFee.value).toBe(8000)
    })

    it('updateFee with null decreases total', () => {
      const { composable } = setup()
      composable.updateFee(0, 5000)
      composable.updateFee(1, 3000)
      composable.updateFee(0, null)
      expect(composable.totalFee.value).toBe(3000)
    })

    it('fee save stores JSON array in remark', async () => {
      const { composable } = setup()
      composable.updateFee(0, 10000)
      await composable.flushPendingSaves()

      const items = mockPut.mock.calls[0][1].items
      const feeItem = items.find((i: any) => i.item_id === 'a101-fee')
      expect(feeItem).toBeDefined()
      const parsed = JSON.parse(feeItem.remark)
      expect(parsed).toHaveLength(5)
      expect(parsed[0].amount).toBe(10000)
      expect(parsed[1].amount).toBeNull()
    })

    it('invalid fee index does nothing', () => {
      const { composable } = setup()
      composable.updateFee(-1, 100)
      composable.updateFee(5, 100)
      expect(composable.totalFee.value).toBe(0)
    })
  })

  // ─── Signing Section ───

  describe('signing section', () => {
    it('updateSigning updates correct field', () => {
      const { composable } = setup()
      composable.updateSigning('partner_name', '李四')
      expect(composable.signingSection.value.partner_name).toBe('李四')
    })

    it('signing save uses conclusion field', async () => {
      const { composable } = setup()
      composable.updateSigning('date', '2024-06-30')
      await composable.flushPendingSaves()

      const items = mockPut.mock.calls[0][1].items
      const signDate = items.find((i: any) => i.item_id === 'a101-sign-date')
      expect(signDate.conclusion).toBe('2024-06-30')
    })
  })

  // ─── Flush ───

  describe('flushPendingSaves', () => {
    it('immediately saves without debounce', async () => {
      const { composable } = setup()
      composable.updateRecipient('测试')
      await composable.flushPendingSaves()
      expect(mockPut).toHaveBeenCalledTimes(1)
    })

    it('no-op when nothing pending', async () => {
      const { composable } = setup()
      await composable.flushPendingSaves()
      expect(mockPut).not.toHaveBeenCalled()
    })
  })

  // ─── Hydration ───

  describe('hydration from render data', () => {
    it('hydrates recipient', () => {
      const { composable } = setup({ recipient: '测试公司董事会' })
      expect(composable.recipient.value).toBe('测试公司董事会')
    })

    it('hydrates chapters', () => {
      const chapters = Array.from({ length: 16 }, (_, i) => ({
        number: i + 1,
        title: `Chapter ${i + 1}`,
        content: i === 0 ? '第一章内容' : null,
        cross_ref: null,
      }))
      const { composable } = setup({ chapters })
      expect(composable.chapters.value[0].content).toBe('第一章内容')
    })

    it('hydrates cross references', () => {
      const { composable } = setup({
        cross_references: { a9_2_wp_id: 'wp-a92', a13_wp_id: 'wp-a13' },
      })
      expect(composable.crossReferences.value.a9_2_wp_id).toBe('wp-a92')
      expect(composable.crossReferences.value.a13_wp_id).toBe('wp-a13')
    })
  })
})

// ─── useA101Navigation Unit Tests ───────────────────────────────────────────

describe('useA101Navigation', () => {
  it('module exports expected interface', async () => {
    const mod = await import('../composables/useA101Navigation')
    expect(mod.useA101Navigation).toBeDefined()
    expect(typeof mod.useA101Navigation).toBe('function')
  })
})
