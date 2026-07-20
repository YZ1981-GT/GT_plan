/**
 * useNoteRefresh — disclosure:note-text-updated 匹配逻辑
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { useNoteRefresh } from '../useNoteRefresh'

vi.mock('@/services/commonApi', () => ({
  refreshDisclosureFromWorkpapers: vi.fn(async () => ({ cells_updated: 0 })),
}))
vi.mock('@/utils/errorHandler', () => ({
  handleApiError: vi.fn(),
}))

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
      payloads: [{ noteSectionId: '八、18' }, { noteSectionId: '七、本期纳入合并报表' }],
    })
    await vi.advanceTimersByTimeAsync(500)
    expect(fetchDetail).toHaveBeenCalledWith('八、18')
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
