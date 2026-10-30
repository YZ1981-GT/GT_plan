/**
 * useNoteRefresh — disclosure:note-text-updated 匹配逻辑
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { refreshDisclosureFromWorkpapers, refreshDisclosureSection } from '@/services/commonApi'
import { useNoteRefresh } from '../useNoteRefresh'
import { pullFromWorkpapers, type NotePullResult } from '../noteWorkpaperPull'
import { runHeadlessDisclosure } from '../noteHeadlessDisclosure'

vi.mock('@/services/commonApi', () => ({
  refreshDisclosureFromWorkpapers: vi.fn(async () => ({ cells_updated: 0 })),
  refreshDisclosureSection: vi.fn(async () => ({ cells_updated: 0 })),
}))
vi.mock('@/utils/errorHandler', () => ({
  handleApiError: vi.fn(),
}))
vi.mock('element-plus', () => ({ ElMessage: vi.fn() }))
// 提示文案用真实 describeWorkpaperPull，只替换请求
vi.mock('../noteWorkpaperPull', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../noteWorkpaperPull')>()),
  pullFromWorkpapers: vi.fn(),
}))
vi.mock('../noteHeadlessDisclosure', () => ({
  runHeadlessDisclosure: vi.fn(async () => ({ outcomes: [], pending: [] })),
}))

function pullResult(overrides: Partial<NotePullResult> = {}): NotePullResult {
  return {
    synced: 1,
    skipped: 0,
    skipped_never_synced: 0,
    variant: 'soe',
    applicable_standards: ['soe_standalone', 'soe', 'standalone'],
    push: { ran: true, error: null, wp_codes: ['D2'], written: 3, kept: 1, skipped: 0, run_id: 'r1', warnings: [] },
    sections: [{
      section: '八、5', wp_codes: ['D2'], wp_ids: { D2: 'wp-d2' }, push_wp_codes: ['D2'], unsupported_wp_codes: [],
      exists: true, synced_before: true, manual_values: 0, written: 3, unchanged: 0, kept: 1, skipped: 0, reasons: [],
    }],
    ...overrides,
  }
}

describe('useNoteRefresh 刷新先从底稿取数（spec note-pull-header-formula-closure R2）', () => {
  beforeEach(() => {
    vi.mocked(pullFromWorkpapers).mockReset()
    vi.mocked(runHeadlessDisclosure).mockReset()
    vi.mocked(runHeadlessDisclosure).mockResolvedValue({ outcomes: [], pending: [] })
    vi.mocked(refreshDisclosureSection).mockReset()
    vi.mocked(refreshDisclosureSection).mockResolvedValue({ cells_updated: 0 } as any)
    vi.mocked(refreshDisclosureFromWorkpapers).mockReset()
    vi.mocked(refreshDisclosureFromWorkpapers).mockResolvedValue({ cells_updated: 0 } as any)
    vi.mocked(ElMessage).mockReset()
  })

  function setup(section = '八、5') {
    const order: string[] = []
    const fetchDetail = vi.fn(async (s: string) => { order.push(`detail:${s}`) })
    const fetchTree = vi.fn(async () => { order.push('tree') })
    const api = useNoteRefresh({
      projectId: ref('p1'),
      year: ref(2025),
      currentNote: ref<{ note_section: string } | null>({ note_section: section }),
      fetchDetail,
      fetchTree,
      staleRecalc: vi.fn(async () => undefined),
    })
    return { api, order, fetchDetail, fetchTree }
  }

  it('当前章节刷新：prepare → 离屏同步 → push → 按模板与表内公式重算 → 重载目录和详情', async () => {
    const { api, order } = setup()
    const pulled = pullResult()
    vi.mocked(pullFromWorkpapers).mockImplementation(async (...args) => { order.push(`pull:${args[3]}:${args[2]}`); return { result: pulled, error: null } })
    vi.mocked(runHeadlessDisclosure).mockImplementation(async (pull) => {
      order.push('headless')
      expect(pull).toBe(pulled)
      return { outcomes: [{ wpCode: 'D2', section: '八、5', status: 'synced', rows: 6 }], pending: [] }
    })
    vi.mocked(refreshDisclosureSection).mockImplementation(async (...args: any[]) => { order.push(`section:${args[2]}`); return { cells_updated: 0 } as any })

    await api.onRefreshFromWP()

    expect(pullFromWorkpapers).toHaveBeenNthCalledWith(1, 'p1', 2025, '八、5', 'prepare')
    expect(pullFromWorkpapers).toHaveBeenNthCalledWith(2, 'p1', 2025, '八、5', 'push')
    // 单章节刷新：底稿写的其他章节不在本次范围（spec note-pull-followup-closure R1）
    expect(runHeadlessDisclosure).toHaveBeenCalledWith(pulled, { projectId: 'p1', year: 2025, allSections: false })
    expect(order).toEqual(['pull:prepare:八、5', 'headless', 'pull:push:八、5', 'section:八、5', 'tree', 'detail:八、5'])
    const msg = vi.mocked(ElMessage).mock.calls.at(-1)?.[0] as any
    expect(msg.type).toBe('success')
    expect(msg.message).toContain('公式推送按审定数写入 3 格（八、5）')
    expect(msg.message).toContain('保留人工 / 锁定 1 格')
    expect(msg.message).toContain('已从底稿披露表同步：D2→八、5（6 行）')
    expect(api.refreshLoading.value).toBe(false)
  })

  it('取数失败不阻断按模板重算，提示为警告并写明原因', async () => {
    const { api } = setup()
    vi.mocked(pullFromWorkpapers).mockResolvedValue({ result: null, error: '从底稿取数失败：权限不足' })

    await api.onRefreshFromWP()

    expect(runHeadlessDisclosure).not.toHaveBeenCalled()
    expect(refreshDisclosureSection).toHaveBeenCalledWith('p1', 2025, '八、5')
    const msg = vi.mocked(ElMessage).mock.calls.at(-1)?.[0] as any
    expect(msg.type).toBe('warning')
    expect(msg.message).toContain('从底稿取数失败：权限不足')
  })

  it('预设公式与底稿值不一致：提示为警告并写明保留底稿值的格数（spec note-chain-followup-optimizations ADR-2）', async () => {
    const { api } = setup()
    vi.mocked(pullFromWorkpapers).mockResolvedValue({ result: pullResult(), error: null })
    vi.mocked(refreshDisclosureSection).mockResolvedValue({ cells_updated: 0, formula_differs: 2 } as any)

    await api.onRefreshFromWP()

    const msg = vi.mocked(ElMessage).mock.calls.at(-1)?.[0] as any
    expect(msg.type).toBe('warning')
    expect(msg.message).toContain('2 个单元格的底稿披露表数值与预设公式结果不一致，已保留底稿值')
    // 差异提示与取数结果并入同一条
    expect(msg.message).toContain('公式推送按审定数写入 3 格（八、5）')
    expect(msg.duration).toBeGreaterThanOrEqual(6000)
  })

  it('无差异时不出现差异提示，取数成功按成功提示', async () => {
    const { api } = setup()
    vi.mocked(pullFromWorkpapers).mockResolvedValue({ result: pullResult(), error: null })
    vi.mocked(refreshDisclosureSection).mockResolvedValue({ cells_updated: 0, formula_differs: 0 } as any)

    await api.onRefreshFromWP()

    const msg = vi.mocked(ElMessage).mock.calls.at(-1)?.[0] as any
    expect(msg.type).toBe('success')
    expect(msg.message).not.toContain('预设公式结果不一致')
  })

  it('离屏同步抛错按失败记入提示，后续刷新照常', async () => {
    const { api } = setup()
    vi.mocked(pullFromWorkpapers).mockResolvedValue({ result: pullResult({ push: { ran: true, error: null, wp_codes: ['D2'], written: 0, kept: 0, skipped: 0, run_id: 'r1', warnings: [] } }), error: null })
    vi.mocked(runHeadlessDisclosure).mockRejectedValue(new Error('账龄配置读取失败'))

    await api.onRefreshFromWP()

    expect(refreshDisclosureSection).toHaveBeenCalledTimes(1)
    const msg = vi.mocked(ElMessage).mock.calls.at(-1)?.[0] as any
    expect(msg.type).toBe('warning')
    expect(msg.message).toContain('底稿披露表同步失败')
    expect(msg.message).toContain('账龄配置读取失败')
  })

  it('全部刷新：prepare → 全部 headless → push → 项目级重算，未接入 provider 的底稿写进提示', async () => {
    const { api, order } = setup()
    vi.mocked(pullFromWorkpapers).mockImplementation(async (...args) => { order.push(`pull:${args[3]}:${args[2]}`); return { result: pullResult(), error: null } })
    vi.mocked(runHeadlessDisclosure).mockResolvedValue({ outcomes: [], pending: ['E1', 'F2'] })
    vi.mocked(refreshDisclosureFromWorkpapers).mockImplementation(async () => { order.push('all'); return { cells_updated: 0 } as any })

    await api.onRefreshAll()

    expect(pullFromWorkpapers).toHaveBeenNthCalledWith(1, 'p1', 2025, null, 'prepare')
    expect(pullFromWorkpapers).toHaveBeenNthCalledWith(2, 'p1', 2025, null, 'push')
    expect(vi.mocked(runHeadlessDisclosure).mock.calls[0][1]).toEqual({ projectId: 'p1', year: 2025, allSections: true })
    expect(order).toEqual(['pull:prepare:null', 'pull:push:null', 'all', 'tree', 'detail:八、5'])
    const msg = vi.mocked(ElMessage).mock.calls.at(-1)?.[0] as any
    expect(msg.message).toContain('底稿 E1、F2 的明细表需在底稿附注披露页保存一次后同步')
    expect(api.refreshAllLoading.value).toBe(false)
  })

  it('未选章节时不发任何请求', async () => {
    const api = useNoteRefresh({
      projectId: ref('p1'),
      year: ref(2025),
      currentNote: ref(null),
      fetchDetail: vi.fn(async () => undefined),
      fetchTree: vi.fn(async () => undefined),
      staleRecalc: vi.fn(async () => undefined),
    })
    await api.onRefreshFromWP()
    expect(pullFromWorkpapers).not.toHaveBeenCalled()
    expect(refreshDisclosureSection).not.toHaveBeenCalled()
  })
})

describe('useNoteRefresh disclosure:note-text-updated', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('refreshes current note when listed sectionId matches', async () => {
    const fetchDetail = vi.fn(async () => undefined)
    const currentNote = ref<{ note_section: string } | null>({ note_section: '五、18' })
    const api = useNoteRefresh({
      projectId: ref('p1'),
      year: ref(2024),
      currentNote,
      fetchDetail,
      fetchTree: vi.fn(async () => undefined),
      staleRecalc: vi.fn(async () => undefined),
    })

    api.onDisclosureNoteTextUpdated({
      projectId: 'p1',
      accountCode: '1511',
      sectionId: '五、18',
    })
    await vi.advanceTimersByTimeAsync(500)
    expect(fetchDetail).toHaveBeenCalledWith('五、18')
  })

  it('refreshes when SOE payload noteSectionId matches current chapter', async () => {
    const fetchDetail = vi.fn(async () => undefined)
    const currentNote = ref<{ note_section: string } | null>({ note_section: '八、18' })
    const api = useNoteRefresh({
      projectId: ref('p1'),
      year: ref(2024),
      currentNote,
      fetchDetail,
      fetchTree: vi.fn(async () => undefined),
      staleRecalc: vi.fn(async () => undefined),
    })

    api.onDisclosureNoteTextUpdated({
      projectId: 'p1',
      accountCode: '1511',
      section: 'soe',
      payloads: [{ noteSectionId: '八、18' }, { noteSectionId: '七、本期纳入合并报表范围的子公司基本情况' }],
    })
    await vi.advanceTimersByTimeAsync(500)
    expect(fetchDetail).toHaveBeenCalledWith('八、18')
  })

  it('refreshes newly-covered families (H1/H9) when payload carries an accountCode', async () => {
    // 修复前 useNoteRefresh 仅硬编码 6 个 accountCode 特例，H1 固定资产/H9 租赁负债等
    // 底稿改叙述后当前节不会自动刷新；现复用 noteDisclosureJump 判定兜底覆盖。
    for (const section of ['五、22', '五、47']) {
      const fetchDetail = vi.fn(async () => undefined)
      const currentNote = ref<{ note_section: string } | null>({ note_section: section })
      const api = useNoteRefresh({
        projectId: ref('p1'),
        year: ref(2024),
        currentNote,
        fetchDetail,
        fetchTree: vi.fn(async () => undefined),
        staleRecalc: vi.fn(async () => undefined),
      })
      api.onDisclosureNoteTextUpdated({
        projectId: 'p1',
        accountCode: '1601', // 任一 accountCode 均代表某底稿披露已变更
      })
      await vi.advanceTimersByTimeAsync(500)
      expect(fetchDetail).toHaveBeenCalledWith(section)
    }
  })

  it.each([
    // 2026-10-16 上市损益类按 Word 从「三」章改挂到第五章：现行编号不含科目关键词，按科目号的刷新须认新编号
    ['6101', '五、75'],
    ['6701', '五、77'],
    ['6711', '五、80'],
    ['6115', '五、78'],
    ['6702', '五、76'],
  ])('accountCode %s 刷新上市现行编号 %s（载荷不带 sectionId）', async (accountCode, section) => {
    const fetchDetail = vi.fn(async () => undefined)
    const currentNote = ref<{ note_section: string } | null>({ note_section: section })
    const api = useNoteRefresh({
      projectId: ref('p1'),
      year: ref(2024),
      currentNote,
      fetchDetail,
      fetchTree: vi.fn(async () => undefined),
      staleRecalc: vi.fn(async () => undefined),
    })
    api.onDisclosureNoteTextUpdated({ projectId: 'p1', accountCode })
    await vi.advanceTimersByTimeAsync(500)
    expect(fetchDetail).toHaveBeenCalledWith(section)
  })

  it('does not refresh disclosure-family section when payload lacks accountCode and no sectionId match', async () => {
    const fetchDetail = vi.fn(async () => undefined)
    const currentNote = ref<{ note_section: string } | null>({ note_section: '五、22' })
    const api = useNoteRefresh({
      projectId: ref('p1'),
      year: ref(2024),
      currentNote,
      fetchDetail,
      fetchTree: vi.fn(async () => undefined),
      staleRecalc: vi.fn(async () => undefined),
    })
    api.onDisclosureNoteTextUpdated({ projectId: 'p1' }) // 无 accountCode 且无 sectionId
    await vi.advanceTimersByTimeAsync(500)
    expect(fetchDetail).not.toHaveBeenCalled()
  })

  it('ignores other projects and unrelated sections', async () => {
    const fetchDetail = vi.fn(async () => undefined)
    const currentNote = ref<{ note_section: string } | null>({ note_section: '四、货币资金' })
    const api = useNoteRefresh({
      projectId: ref('p1'),
      year: ref(2024),
      currentNote,
      fetchDetail,
      fetchTree: vi.fn(async () => undefined),
      staleRecalc: vi.fn(async () => undefined),
    })

    api.onDisclosureNoteTextUpdated({
      projectId: 'other',
      accountCode: '1511',
      sectionId: '五、18',
    })
    api.onDisclosureNoteTextUpdated({
      projectId: 'p1',
      accountCode: '1001',
      sectionId: '一、货币资金',
    })
    await vi.advanceTimersByTimeAsync(500)
    expect(fetchDetail).not.toHaveBeenCalled()
  })
})
