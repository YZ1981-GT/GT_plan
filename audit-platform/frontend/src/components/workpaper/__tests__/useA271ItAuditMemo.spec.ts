/**
 * Unit Tests — useA271ItAuditMemo composable
 *
 * Spec: .kiro/specs/a27-1-it-audit-memo/
 * Task: 2.3
 *
 * Coverage:
 * - Debounce timing (2s)
 * - Team CRUD
 * - Conclusion computed properties
 * - Chapter update
 * - Flush
 * - Header auto-fill
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { useA271ItAuditMemo } from '../composables/useA271ItAuditMemo'
import type { A271RenderData } from '../composables/useA271ItAuditMemo'

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

describe('useA271ItAuditMemo', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  function setup(renderData: A271RenderData | null = null) {
    const wpId = ref('wp-a271')
    const projectId = ref('proj-001')
    const htmlData = ref<A271RenderData | null>(renderData)
    return { composable: useA271ItAuditMemo({ wpId, projectId, htmlData }), wpId, projectId, htmlData }
  }

  // ─── Debounce Save Timing ───

  describe('debounce save timing', () => {
    it('updateHeader triggers save after 2s, not before', async () => {
      const { composable } = setup()
      composable.updateHeader('date', '2026-06-01')

      expect(mockPut).not.toHaveBeenCalled()
      expect(composable.saveStatus.value).toBe('unsaved')

      vi.advanceTimersByTime(1500)
      expect(mockPut).not.toHaveBeenCalled()

      vi.advanceTimersByTime(500)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
      expect(mockPut).toHaveBeenCalledWith(
        '/api/workpapers/wp-a271/checklist-responses',
        expect.objectContaining({
          items: expect.arrayContaining([
            expect.objectContaining({ item_id: 'a271-header-date', conclusion: '2026-06-01' }),
          ]),
        }),
      )
    })

    it('batches multiple updates into single save', async () => {
      const { composable } = setup()
      composable.updateHeader('date', '2026-06-01')
      composable.updateHeader('to', '审计部')
      composable.updateChapter(1, 'content', '系统环境描述')

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
      const items = mockPut.mock.calls[0][1].items
      expect(items).toHaveLength(3)
    })

    it('save status transitions: saved → unsaved → saving → saved', async () => {
      const { composable } = setup()

      expect(composable.saveStatus.value).toBe('saved')

      composable.updateHeader('subject', 'IT审计')
      expect(composable.saveStatus.value).toBe('unsaved')

      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(composable.saveStatus.value).toBe('saved')
    })
  })

  // ─── Team CRUD ───

  describe('team CRUD', () => {
    it('addTeamMember adds a row with sequential index', () => {
      const { composable } = setup()
      composable.addTeamMember()
      composable.addTeamMember()

      expect(composable.itTeamTable.value).toHaveLength(2)
      expect(composable.itTeamTable.value[0].index).toBe(1)
      expect(composable.itTeamTable.value[1].index).toBe(2)
    })

    it('removeTeamMember removes correct row and re-indexes', () => {
      const { composable } = setup()
      composable.addTeamMember()
      composable.addTeamMember()
      composable.addTeamMember()
      composable.updateTeamMember(0, 'name', '张三')
      composable.updateTeamMember(1, 'name', '李四')
      composable.updateTeamMember(2, 'name', '王五')

      composable.removeTeamMember(1) // remove 李四

      expect(composable.itTeamTable.value).toHaveLength(2)
      expect(composable.itTeamTable.value[0].name).toBe('张三')
      expect(composable.itTeamTable.value[0].index).toBe(1)
      expect(composable.itTeamTable.value[1].name).toBe('王五')
      expect(composable.itTeamTable.value[1].index).toBe(2)
    })

    it('removeTeamMember with invalid index does nothing', () => {
      const { composable } = setup()
      composable.addTeamMember()
      composable.removeTeamMember(-1)
      composable.removeTeamMember(5)

      expect(composable.itTeamTable.value).toHaveLength(1)
    })

    it('updateTeamMember updates correct field', () => {
      const { composable } = setup()
      composable.addTeamMember()
      composable.updateTeamMember(0, 'name', '赵六')
      composable.updateTeamMember(0, 'title', '高级经理')

      expect(composable.itTeamTable.value[0].name).toBe('赵六')
      expect(composable.itTeamTable.value[0].title).toBe('高级经理')
    })

    it('team save serializes as JSON in remark', async () => {
      const { composable } = setup()
      composable.addTeamMember()
      composable.updateTeamMember(0, 'name', '张三')
      composable.updateTeamMember(0, 'title', '审计经理')

      await composable.flushPendingSaves()

      expect(mockPut).toHaveBeenCalledTimes(1)
      const items = mockPut.mock.calls[0][1].items
      const teamItem = items.find((i: any) => i.item_id === 'a271-team')
      expect(teamItem).toBeDefined()
      expect(teamItem.conclusion).toBe('1')
      const parsed = JSON.parse(teamItem.remark)
      expect(parsed[0].name).toBe('张三')
      expect(parsed[0].title).toBe('审计经理')
    })
  })

  // ─── Conclusion Computed Properties ───

  describe('conclusion computed properties', () => {
    it('showChapter4 is true by default (ch3 conclusion is null)', () => {
      const { composable } = setup()
      expect(composable.showChapter4.value).toBe(true)
    })

    it('showChapter4 is false when ch3 conclusion is "已有效"', () => {
      const { composable } = setup()
      composable.updateChapter(3, 'conclusion', '已有效')
      expect(composable.showChapter4.value).toBe(false)
    })

    it('showChapter4 is true when ch3 conclusion is "部分有效"', () => {
      const { composable } = setup()
      composable.updateChapter(3, 'conclusion', '部分有效')
      expect(composable.showChapter4.value).toBe(true)
    })

    it('showCh3Deficiency mirrors showChapter4', () => {
      const { composable } = setup()
      composable.updateChapter(3, 'conclusion', '已有效')
      expect(composable.showCh3Deficiency.value).toBe(false)
      composable.updateChapter(3, 'conclusion', '没有有效')
      expect(composable.showCh3Deficiency.value).toBe(true)
    })

    it('showCh6Deficiency is true by default', () => {
      const { composable } = setup()
      expect(composable.showCh6Deficiency.value).toBe(true)
    })

    it('showCh6Deficiency is false when ch6 conclusion is "已有效"', () => {
      const { composable } = setup()
      composable.updateChapter(6, 'conclusion', '已有效')
      expect(composable.showCh6Deficiency.value).toBe(false)
    })
  })

  // ─── Chapter Update ───

  describe('chapter update', () => {
    it('updateChapter sets content field correctly', () => {
      const { composable } = setup()
      composable.updateChapter(1, 'content', '系统使用SAP')
      expect(composable.chapters.value[0].content).toBe('系统使用SAP')
    })

    it('updateChapter with invalid chapter number does nothing', () => {
      const { composable } = setup()
      composable.updateChapter(0, 'content', 'invalid')
      composable.updateChapter(8, 'content', 'invalid')
      // No crash, chapters unchanged
      expect(composable.chapters.value[0].content).toBeNull()
    })

    it('chapter conclusion save uses conclusion field', async () => {
      const { composable } = setup()
      composable.updateChapter(3, 'conclusion', '部分有效')

      await composable.flushPendingSaves()

      const items = mockPut.mock.calls[0][1].items
      const ch3Item = items.find((i: any) => i.item_id === 'a271-ch3-conclusion')
      expect(ch3Item.conclusion).toBe('部分有效')
      expect(ch3Item.remark).toBeNull()
    })

    it('chapter content save uses remark field', async () => {
      const { composable } = setup()
      composable.updateChapter(1, 'content', '长文本内容')

      await composable.flushPendingSaves()

      const items = mockPut.mock.calls[0][1].items
      const ch1Item = items.find((i: any) => i.item_id === 'a271-ch1-content')
      expect(ch1Item.remark).toBe('长文本内容')
      expect(ch1Item.conclusion).toBeNull()
    })
  })

  // ─── Flush ───

  describe('flushPendingSaves', () => {
    it('immediately saves without waiting for debounce', async () => {
      const { composable } = setup()
      composable.updateHeader('to', '项目经理')

      await composable.flushPendingSaves()

      expect(mockPut).toHaveBeenCalledTimes(1)
    })

    it('does nothing when no pending changes', async () => {
      const { composable } = setup()
      await composable.flushPendingSaves()
      expect(mockPut).not.toHaveBeenCalled()
    })

    it('cancels pending debounce timer', async () => {
      const { composable } = setup()
      composable.updateHeader('date', '2026-06-01')

      await composable.flushPendingSaves()
      expect(mockPut).toHaveBeenCalledTimes(1)

      vi.advanceTimersByTime(3000)
      await vi.runAllTimersAsync()

      // No second save
      expect(mockPut).toHaveBeenCalledTimes(1)
    })
  })

  // ─── Header Auto-fill ───

  describe('header auto-fill', () => {
    it('hydrates header from render data', () => {
      const { composable } = setup({
        header: { date: '2026-01-01', to: 'IT部门', from_user: '审计组', subject: 'IT审计总结' },
        project_context: { client_name: '测试公司', audit_period: '2025年度', partner: '李合伙人', current_user: '张助理' },
      })

      expect(composable.header.value.date).toBe('2026-01-01')
      expect(composable.header.value.to).toBe('IT部门')
      expect(composable.header.value.from_user).toBe('审计组')
      expect(composable.header.value.subject).toBe('IT审计总结')
      expect(composable.projectContext.value.partner).toBe('李合伙人')
      expect(composable.projectContext.value.current_user).toBe('张助理')
    })

    it('hydrates chapters from render data', () => {
      const chaptersData = [
        { number: 1, title: '了解信息系统环境', content: '已有内容', conclusion: null, deficiency: null, cross_ref: 'B22A-4-3' },
        { number: 2, title: 'IT风险和一般控制', content: null, conclusion: null, deficiency: null, cross_ref: 'C22' },
        { number: 3, title: 'IT一般控制结论', content: null, conclusion: '部分有效', deficiency: '缺陷说明', cross_ref: null },
        { number: 4, title: 'IT一般控制缺陷', content: '缺陷详情', conclusion: null, deficiency: null, cross_ref: 'C21-1' },
        { number: 5, title: '信息处理控制', content: null, conclusion: null, deficiency: null, cross_ref: 'B23-15' },
        { number: 6, title: '信息处理控制结论', content: null, conclusion: '已有效', deficiency: null, cross_ref: null },
        { number: 7, title: '缺陷评估', content: '评估内容', conclusion: '无重大缺陷', deficiency: null, cross_ref: null },
      ]
      const { composable } = setup({ chapters: chaptersData })

      expect(composable.chapters.value[0].content).toBe('已有内容')
      expect(composable.chapters.value[2].conclusion).toBe('部分有效')
      expect(composable.chapters.value[2].deficiency).toBe('缺陷说明')
      expect(composable.showChapter4.value).toBe(true)
      expect(composable.showCh6Deficiency.value).toBe(false)
    })

    it('reactive htmlData watch triggers re-hydration', async () => {
      const { composable, htmlData } = setup(null)
      expect(composable.header.value.to).toBeNull()

      htmlData.value = { header: { to: '新接收人' } }
      await vi.runAllTimersAsync()

      expect(composable.header.value.to).toBe('新接收人')
    })
  })
})
