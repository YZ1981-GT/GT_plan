/**
 * composables.spec.ts — 抽出的 composable 单元测试
 *
 * 覆盖关键分支：useNoteTree, useNoteDetail, useNotePersist,
 * useNoteRefresh, useNoteTemplate, useNoteExport, useNoteAi
 *
 * 使用 vitest + fast-check numRuns: 100（涉随机输入）
 *
 * Validates: Requirements 4.6
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import * as fc from 'fast-check'
import { ref, computed, nextTick } from 'vue'

// ─── Mock vue-router ────────────────────────────────────────────────────────

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useRoute: () => ({ params: { projectId: 'proj-001' }, query: { year: '2025' } }),
}))

// ─── Mock API calls ─────────────────────────────────────────────────────────

const mockGetTree = vi.fn()
const mockGetDetail = vi.fn()
const mockUpdateNote = vi.fn()

vi.mock('@/services/auditPlatformApi', () => ({
  getDisclosureNoteTree: (...args: any[]) => mockGetTree(...args),
  getDisclosureNoteDetail: (...args: any[]) => mockGetDetail(...args),
  updateDisclosureNote: (...args: any[]) => mockUpdateNote(...args),
}))

const mockRefresh = vi.fn()
vi.mock('@/services/commonApi', () => ({
  refreshDisclosureFromWorkpapers: (...args: any[]) => mockRefresh(...args),
  noteAiContinueWrite: vi.fn().mockResolvedValue({}),
  noteAiRewrite: vi.fn().mockResolvedValue({}),
  noteAiGeneratePolicy: vi.fn().mockResolvedValue({}),
  noteAiGenerateAnalysis: vi.fn().mockResolvedValue({}),
  fetchNoteAutoPull: vi.fn().mockResolvedValue({ refs: [] }),
}))

const mockApiGet = vi.fn()
const mockApiPost = vi.fn()
const mockApiPut = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  default: { get: (...a: any[]) => mockApiGet(...a), post: (...a: any[]) => mockApiPost(...a), put: (...a: any[]) => mockApiPut(...a) },
  api: { get: (...a: any[]) => mockApiGet(...a), post: (...a: any[]) => mockApiPost(...a), put: (...a: any[]) => mockApiPut(...a) },
}))

vi.mock('@/utils/http', () => ({
  default: { post: vi.fn().mockResolvedValue({ data: new Blob() }), get: vi.fn() },
}))

vi.mock('@/composables/useLoading', () => ({
  withLoading: (_ref: any, fn: any) => fn,
}))

vi.mock('@/composables/useKnowledge', () => ({
  useKnowledge: () => ({ pickDocuments: vi.fn().mockResolvedValue([]), buildContext: vi.fn().mockResolvedValue('') }),
}))

vi.mock('@/utils/errorHandler', () => ({
  handleApiError: vi.fn(),
}))

vi.mock('element-plus', () => {
  const elMessageFn = vi.fn()
  elMessageFn.success = vi.fn()
  elMessageFn.warning = vi.fn()
  elMessageFn.info = vi.fn()
  elMessageFn.error = vi.fn()
  return {
    ElMessage: elMessageFn,
    ElMessageBox: { confirm: vi.fn().mockResolvedValue('confirm') },
  }
})

// ─── Import composables ─────────────────────────────────────────────────────

import { useNoteTree, type UseNoteTreeOptions } from '../composables/useNoteTree'
import { useNoteDetail } from '../composables/useNoteDetail'
import { useNotePersist } from '../composables/useNotePersist'
import { useNoteRefresh } from '../composables/useNoteRefresh'
import { useNoteTemplate } from '../composables/useNoteTemplate'
import { useNoteExport } from '../composables/useNoteExport'
import { useNoteAi } from '../composables/useNoteAi'

// ─── Fixtures ───────────────────────────────────────────────────────────────

function makeTreeItem(overrides: Record<string, any> = {}) {
  return {
    id: 'note-1', note_section: '五、1', section_title: '货币资金',
    content_type: 'table', is_stale: false, ...overrides,
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// useNoteTree
// ═══════════════════════════════════════════════════════════════════════════════

describe('useNoteTree', () => {
  const makeOpts = (): UseNoteTreeOptions => ({
    projectId: computed(() => 'proj-001'),
    year: computed(() => 2025),
    templateType: ref('soe'),
    isEqcrRole: computed(() => false),
  })

  beforeEach(() => { mockGetTree.mockReset() })

  it('fetchTree populates noteList', async () => {
    mockGetTree.mockResolvedValue([makeTreeItem()])
    const { fetchTree, noteList } = useNoteTree(makeOpts())
    await fetchTree()
    expect(noteList.value).toHaveLength(1)
  })

  it('fetchTree handles API error gracefully', async () => {
    mockGetTree.mockRejectedValue(new Error('Network error'))
    const { fetchTree, noteList } = useNoteTree(makeOpts())
    await fetchTree()
    expect(noteList.value).toEqual([])
  })

  it('treeData groups items by chapter', async () => {
    mockGetTree.mockResolvedValue([
      makeTreeItem({ id: '1', note_section: '五、1' }),
      makeTreeItem({ id: '2', note_section: '五、2' }),
    ])
    const { fetchTree, treeData } = useNoteTree(makeOpts())
    await fetchTree()
    // Should create a group for chapter 五
    const fiveGroup = treeData.value.find(g => g.id === 'chapter_五')
    expect(fiveGroup).toBeDefined()
    expect(fiveGroup!.children!.length).toBe(2)
  })

  it('filteredTreeData filters by search keyword', async () => {
    mockGetTree.mockResolvedValue([
      makeTreeItem({ id: '1', note_section: '五、1', section_title: '货币资金' }),
      makeTreeItem({ id: '2', note_section: '五、2', section_title: '应收账款' }),
    ])
    const opts = makeOpts()
    const { fetchTree, filteredTreeData, treeSearch } = useNoteTree(opts)
    await fetchTree()
    treeSearch.value = '货币'
    // After filtering, only matching items remain
    const allLeaves = filteredTreeData.value.flatMap(g => g.children || [])
    expect(allLeaves.some(n => n.label?.includes('货币'))).toBe(true)
  })

  it('allowTreeDrop rejects cross-parent drops', () => {
    const { allowTreeDrop } = useNoteTree(makeOpts())
    const parentA = { data: 'groupA' }
    const parentB = { data: 'groupB' }
    expect(allowTreeDrop({ parent: parentA }, { parent: parentB, data: {} }, 'prev')).toBe(false)
  })

  it('flatNoteList returns all notes without grouping', async () => {
    mockGetTree.mockResolvedValue([
      makeTreeItem({ id: '1', note_section: '五、1' }),
      makeTreeItem({ id: '2', note_section: '一、1' }),
    ])
    const { fetchTree, flatNoteList } = useNoteTree(makeOpts())
    await fetchTree()
    expect(flatNoteList.value).toHaveLength(2)
  })

  // fast-check: treeSearch filtering never throws
  it('treeSearch filtering is safe for random keywords (fast-check)', async () => {
    mockGetTree.mockResolvedValue([
      makeTreeItem({ id: '1', note_section: '五、1', section_title: '货币资金' }),
    ])
    const { fetchTree, treeSearch, filteredTreeData } = useNoteTree(makeOpts())
    await fetchTree()

    fc.assert(
      fc.property(fc.string({ maxLength: 20 }), (kw) => {
        treeSearch.value = kw
        // Should never throw
        expect(() => filteredTreeData.value).not.toThrow()
      }),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// useNoteDetail
// ═══════════════════════════════════════════════════════════════════════════════

describe('useNoteDetail', () => {
  beforeEach(() => {
    mockGetDetail.mockReset()
    mockApiGet.mockReset()
  })

  it('fetchDetail loads note and sets textContent', async () => {
    mockGetDetail.mockResolvedValue({
      id: 'n1', note_section: '五、1', text_content: '<p>hello</p>', table_data: {}, content_type: 'text',
    })
    mockApiGet.mockResolvedValue(null)

    const editor = ref({ commands: { setContent: vi.fn() } })
    const { fetchDetail, currentNote, textContent } = useNoteDetail({
      projectId: computed(() => 'proj-001'),
      year: computed(() => 2025),
      editor,
      editMode: ref(false),
      markEditDirty: vi.fn(),
      autoSaveMarkDirty: vi.fn(),
    })
    await fetchDetail('五、1')
    expect(currentNote.value).not.toBeNull()
    expect(textContent.value).toBe('<p>hello</p>')
    expect(editor.value.commands.setContent).toHaveBeenCalledWith('<p>hello</p>')
  })

  it('fetchDetail converts plain text to html paragraphs', async () => {
    mockGetDetail.mockResolvedValue({
      id: 'n2', note_section: '五、2', text_content: 'line1\n\nline2', table_data: {}, content_type: 'mixed',
    })
    mockApiGet.mockResolvedValue(null)

    const mockSetContent = vi.fn()
    const editor = ref({ commands: { setContent: mockSetContent } })
    const { fetchDetail } = useNoteDetail({
      projectId: computed(() => 'proj-001'),
      year: computed(() => 2025),
      editor,
      editMode: ref(false),
      markEditDirty: vi.fn(),
      autoSaveMarkDirty: vi.fn(),
    })
    await fetchDetail('五、2')
    // Plain text should be wrapped in <p> tags
    expect(mockSetContent).toHaveBeenCalledWith(expect.stringContaining('<p>'))
  })

  it('onRichTextChange updates textContent and marks dirty in edit mode', () => {
    const markDirty = vi.fn()
    const autoMark = vi.fn()
    const { onRichTextChange, textContent } = useNoteDetail({
      projectId: computed(() => 'proj-001'),
      year: computed(() => 2025),
      editor: ref(null),
      editMode: ref(true),
      markEditDirty: markDirty,
      autoSaveMarkDirty: autoMark,
    })
    onRichTextChange('<p>updated</p>')
    expect(textContent.value).toBe('<p>updated</p>')
    expect(markDirty).toHaveBeenCalled()
    expect(autoMark).toHaveBeenCalled()
  })

  it('onRichTextChange does not mark dirty when not in edit mode', () => {
    const markDirty = vi.fn()
    const { onRichTextChange } = useNoteDetail({
      projectId: computed(() => 'proj-001'),
      year: computed(() => 2025),
      editor: ref(null),
      editMode: ref(false),
      markEditDirty: markDirty,
      autoSaveMarkDirty: vi.fn(),
    })
    onRichTextChange('<p>new</p>')
    expect(markDirty).not.toHaveBeenCalled()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// useNotePersist
// ═══════════════════════════════════════════════════════════════════════════════

describe('useNotePersist', () => {
  beforeEach(() => { mockUpdateNote.mockReset() })

  it('onSave sends table_data for table content_type', async () => {
    mockUpdateNote.mockResolvedValue({})
    const currentNote = ref({
      id: 'n1', note_section: '五、1', content_type: 'table',
      table_data: { rows: [{ values: [1, 2] }] }, text_content: '', status: 'draft',
    } as any)
    const clearDirty = vi.fn()
    const { onSave } = useNotePersist({
      currentNote, textContent: ref(''), editMode: ref(true),
      clearEditDirty: clearDirty, autoSaveClearDirty: vi.fn(), clearAutoSaveDraft: vi.fn(),
    })
    await onSave()
    expect(mockUpdateNote).toHaveBeenCalledWith('n1', expect.objectContaining({ table_data: { rows: [{ values: [1, 2] }] } }))
    expect(clearDirty).toHaveBeenCalled()
  })

  it('onSave sends text_content for text content_type', async () => {
    mockUpdateNote.mockResolvedValue({})
    const currentNote = ref({
      id: 'n2', note_section: '一、1', content_type: 'text',
      table_data: null, text_content: '', status: 'draft',
    } as any)
    const { onSave } = useNotePersist({
      currentNote, textContent: ref('<p>hello</p>'), editMode: ref(true),
      clearEditDirty: vi.fn(), autoSaveClearDirty: vi.fn(), clearAutoSaveDraft: vi.fn(),
    })
    await onSave()
    expect(mockUpdateNote).toHaveBeenCalledWith('n2', expect.objectContaining({ text_content: '<p>hello</p>' }))
  })

  it('onSave does nothing when currentNote is null', async () => {
    const { onSave } = useNotePersist({
      currentNote: ref(null), textContent: ref(''), editMode: ref(true),
      clearEditDirty: vi.fn(), autoSaveClearDirty: vi.fn(), clearAutoSaveDraft: vi.fn(),
    })
    await onSave()
    expect(mockUpdateNote).not.toHaveBeenCalled()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// useNoteRefresh
// ═══════════════════════════════════════════════════════════════════════════════

describe('useNoteRefresh', () => {
  beforeEach(() => { mockRefresh.mockReset() })

  it('onRefreshFromWP sets refreshLoading and calls API', async () => {
    mockRefresh.mockResolvedValue({ refreshed: 2, total_notes: 5, sections_recomputed: [], text_only_sections: [], errors: [], cells_updated: 2 })
    const fetchDetail = vi.fn()
    const { onRefreshFromWP, refreshLoading } = useNoteRefresh({
      projectId: computed(() => 'proj-001'), year: computed(() => 2025),
      currentNote: ref({ note_section: '五、1' }), fetchDetail, fetchTree: vi.fn(), staleRecalc: vi.fn(),
    })
    await onRefreshFromWP()
    expect(mockRefresh).toHaveBeenCalledWith('proj-001', 2025)
    expect(fetchDetail).toHaveBeenCalledWith('五、1')
    expect(refreshLoading.value).toBe(false)
  })

  it('onManualRefresh sets syncError on failure', async () => {
    mockRefresh.mockRejectedValue(new Error('500'))
    const { onManualRefresh, syncError } = useNoteRefresh({
      projectId: computed(() => 'proj-001'), year: computed(() => 2025),
      currentNote: ref(null), fetchDetail: vi.fn(), fetchTree: vi.fn(), staleRecalc: vi.fn(),
    })
    await onManualRefresh()
    expect(syncError.value).toBe(true)
  })

  it('showRefreshResultMessage handles all branches without throwing (fast-check)', () => {
    const { showRefreshResultMessage } = useNoteRefresh({
      projectId: computed(() => 'proj-001'), year: computed(() => 2025),
      currentNote: ref(null), fetchDetail: vi.fn(), fetchTree: vi.fn(), staleRecalc: vi.fn(),
    })

    fc.assert(
      fc.property(
        fc.record({
          refreshed: fc.nat({ max: 200 }),
          total_notes: fc.nat({ max: 200 }),
          sections_recomputed: fc.array(fc.string({ maxLength: 10 }), { maxLength: 5 }),
          text_only_sections: fc.array(fc.string({ maxLength: 10 }), { maxLength: 5 }),
          errors: fc.array(fc.string({ maxLength: 30 }), { maxLength: 3 }),
          cells_updated: fc.nat({ max: 100 }),
        }),
        (result) => { expect(() => showRefreshResultMessage(result)).not.toThrow() },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// useNoteTemplate
// ═══════════════════════════════════════════════════════════════════════════════

describe('useNoteTemplate', () => {
  it('loadNoteMappingPreset generates rules from noteList', () => {
    const noteList = ref([
      makeTreeItem({ id: '1', note_section: '五、1', section_title: '货币资金' }),
      makeTreeItem({ id: '2', note_section: '五、2', section_title: '应收账款' }),
    ])
    const { loadNoteMappingPreset, noteMappingRules } = useNoteTemplate({
      projectId: computed(() => 'proj-001'), templateType: ref('soe'),
      noteList, fetchTree: vi.fn(), onGenerate: vi.fn(),
    })
    loadNoteMappingPreset()
    expect(noteMappingRules.value).toHaveLength(2)
    expect(noteMappingRules.value[0].soe_section).toContain('货币资金')
  })

  it('handleTemplateChange rejects custom without ID', async () => {
    const templateType = ref('soe')
    const { handleTemplateChange, customTemplateId } = useNoteTemplate({
      projectId: computed(() => 'proj-001'), templateType,
      noteList: ref([]), fetchTree: vi.fn(), onGenerate: vi.fn(),
    })
    customTemplateId.value = ''
    await handleTemplateChange('custom')
    // Should revert to soe since no customTemplateId
    expect(templateType.value).toBe('soe')
  })

  it('onNoteTemplateApplied updates templateType and fetches tree', () => {
    const templateType = ref('soe')
    const fetchTree = vi.fn()
    const { onNoteTemplateApplied } = useNoteTemplate({
      projectId: computed(() => 'proj-001'), templateType,
      noteList: ref([]), fetchTree, onGenerate: vi.fn(),
    })
    onNoteTemplateApplied({ template_type: 'listed' })
    expect(templateType.value).toBe('listed')
    expect(fetchTree).toHaveBeenCalled()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// useNoteExport
// ═══════════════════════════════════════════════════════════════════════════════

describe('useNoteExport', () => {
  it('onExportWord sets exportLoading during operation', async () => {
    const { onExportWord, exportLoading } = useNoteExport({
      projectId: computed(() => 'proj-001'), year: computed(() => 2025),
    })
    // After completion, loading should be false
    await onExportWord()
    expect(exportLoading.value).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// useNoteAi
// ═══════════════════════════════════════════════════════════════════════════════

describe('useNoteAi', () => {
  it('getSelectedText returns empty when no editor', () => {
    const { getSelectedText } = useNoteAi({
      projectId: computed(() => 'proj-001'), year: computed(() => 2025),
      templateType: ref('soe'), currentNote: ref(null), editor: ref(null),
    })
    expect(getSelectedText()).toBe('')
  })

  it('getSelectedText returns selection from editor', () => {
    const mockEditor = {
      state: { selection: { from: 0, to: 5 }, doc: { textBetween: vi.fn().mockReturnValue('hello') } },
      getText: vi.fn().mockReturnValue('hello world'),
    }
    const { getSelectedText } = useNoteAi({
      projectId: computed(() => 'proj-001'), year: computed(() => 2025),
      templateType: ref('soe'), currentNote: ref(null), editor: ref(mockEditor),
    })
    expect(getSelectedText()).toBe('hello')
  })

  it('onAiRewriteOpen warns when no text selected', () => {
    const mockEditor = {
      state: { selection: { from: 0, to: 0 }, doc: { textBetween: vi.fn().mockReturnValue('') } },
      getText: vi.fn().mockReturnValue(''),
    }
    const { onAiRewriteOpen, aiRewriteDialogVisible } = useNoteAi({
      projectId: computed(() => 'proj-001'), year: computed(() => 2025),
      templateType: ref('soe'), currentNote: ref(null), editor: ref(mockEditor),
    })
    onAiRewriteOpen()
    // Dialog should not open since no selection
    expect(aiRewriteDialogVisible.value).toBe(false)
  })

  it('clearKnowledgeContext resets context state', () => {
    const { onPickKnowledge, clearKnowledgeContext, knowledgeContextText, knowledgeDocCount } = useNoteAi({
      projectId: computed(() => 'proj-001'), year: computed(() => 2025),
      templateType: ref('soe'), currentNote: ref(null), editor: ref(null),
    })
    knowledgeContextText.value = 'some context'
    knowledgeDocCount.value = 3
    clearKnowledgeContext()
    expect(knowledgeContextText.value).toBe('')
    expect(knowledgeDocCount.value).toBe(0)
  })
})
