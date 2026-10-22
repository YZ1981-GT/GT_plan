/**
 * noteListFormulasWiring.spec.ts — Task 4.1 / ADR-FMC-04 弹窗附注节点调 list_note_formulas 守卫
 *
 * 真挂载 FormulaManagerDialog（铁律㉕：接线须真 mount，不只测纯函数）：
 *   - 附注页打开（scope='note' + noteSection）→ 弹窗调 list_note_formulas
 *     （GET /api/disclosure-notes/{pid}/{year}/{section}/formulas），拿用户编辑集。
 *   - 用户编辑集公式并入右栏显示（currentRows 含 _userTarget 行）。
 *   - 变异反证：若 noteUserFormulas 未被加载/未并入，右栏无用户行（覆盖样本打红锚）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import FormulaManagerDialog from '@/components/formula/FormulaManagerDialog.vue'

const SECTION = '五、1'
const SECTION_TITLE = '货币资金'

const { get, put, post, scopeLoad, scopeGetRows, acnrListSheets, acnrListCells, addressState, getNoteTree } = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
  post: vi.fn(),
  scopeLoad: vi.fn(),
  scopeGetRows: vi.fn(() => []),
  acnrListSheets: vi.fn(),
  acnrListCells: vi.fn(),
  addressState: { loaded: false, tbAddresses: [] },
  getNoteTree: vi.fn(),
}))

vi.mock('@/services/apiProxy', () => ({ api: { get, put, post } }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/components/formula/FormulaEditDialog.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/formula/FormulaHistoryTab.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/shared/SharedTemplatePicker.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/import/UnifiedImportDialog.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/services/auditPlatformApi', () => ({ getDisclosureNoteTree: getNoteTree }))
vi.mock('@/stores/displayPrefs', () => ({
  useDisplayPrefsStore: () => ({ fmtAmount: (v: unknown) => String(v ?? '') }),
}))
vi.mock('@/stores/addressRegistry', () => ({
  useAddressRegistry: () => ({
    get loaded() { return addressState.loaded },
    get tbAddresses() { return addressState.tbAddresses },
  }),
}))
vi.mock('@/composables/useFormulaScopeCatalog', () => ({
  useFormulaScopeCatalog: () => ({
    loadScope: scopeLoad,
    resolveSources: vi.fn(async () => undefined),
    getScopeRows: scopeGetRows,
    loadGlobal: vi.fn(async () => ({})),
    resolveScopeSources: vi.fn(async () => undefined),
  }),
  SCOPE_LABEL_MAP: {},
}))
vi.mock('@/services/acnr/useAcnr', () => ({
  useAcnr: () => ({
    listSheets: acnrListSheets,
    listCells: acnrListCells,
    resolve: vi.fn(),
    resolveFormula: vi.fn(),
    resolveUri: vi.fn(),
    resolveAddr: vi.fn(),
    resolveIndex: vi.fn(),
    resolveInstance: vi.fn(),
  }),
}))
vi.mock('@/services/apiPaths', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return { ...actual, linkageBus: {}, formulaAuditLog: { list: '/api/formula-audit-logs' } }
})

/** 项目附注树：含本章节节点（_sectionId / _sectionTitle）。 */
const NOTE_TREE = [
  { section_id: SECTION, note_section: SECTION, section_title: SECTION_TITLE, title: SECTION_TITLE },
]

/** 模板级预设公式（note-templates/preset-formulas）。 */
const PRESET_FORMULAS = [
  { note_section: SECTION, section_title: SECTION_TITLE, formula: "TB('1001','期末')", category: 'auto_calc', description: '库存现金' },
]

/** list_note_formulas 返回的用户编辑集。 */
const USER_FORMULAS = {
  formulas: [
    { target: '2:0', formula: 'SUM(0:1, 0)', description: '用户合计', category: 'auto_calc', source: 'user', type: 'vertical_sum' },
  ],
}

function create(props: Record<string, unknown> = {}) {
  return shallowMount(FormulaManagerDialog, {
    props: {
      modelValue: false,
      rows: [{ row_code: '五、1-R1' }],
      scope: 'note',
      noteSection: SECTION,
      noteSectionTitle: SECTION_TITLE,
      projectId: 'project-1',
      year: 2025,
      templateType: 'soe',
      ...props,
    },
    global: { plugins: [ElementPlus], renderStubDefaultSlot: false },
  })
}

const state = (w: ReturnType<typeof create>) => (w.vm as any).$.setupState

async function open(props: Record<string, unknown> = {}) {
  const w = create(props)
  await w.setProps({ modelValue: true })
  await flushPromises()
  await flushPromises()
  await flushPromises()
  return w
}

describe('弹窗附注节点调 list_note_formulas（Task 4.1 / ADR-FMC-04）', () => {
  beforeEach(() => {
    get.mockReset()
    get.mockImplementation(async (url: string) => {
      const u = String(url)
      // list_note_formulas: GET /api/disclosure-notes/{pid}/{year}/{section}/formulas
      if (u.includes('/disclosure-notes/') && u.endsWith('/formulas')) return USER_FORMULAS
      if (u.includes('note-templates/preset-formulas')) return PRESET_FORMULAS
      if (u.includes('report-config/types')) return []
      return {}
    })
    scopeLoad.mockReset(); scopeLoad.mockResolvedValue([])
    scopeGetRows.mockReset(); scopeGetRows.mockReturnValue([])
    acnrListSheets.mockReset(); acnrListSheets.mockResolvedValue([])
    acnrListCells.mockReset(); acnrListCells.mockResolvedValue([])
    getNoteTree.mockReset(); getNoteTree.mockResolvedValue(NOTE_TREE)
    addressState.loaded = false
    addressState.tbAddresses = []
  })

  it('带页面章节打开：打开链路即按精确章节取用户集，附注树只取一次且在打开内落定', async () => {
    // 打开链路会从 watch 与 applyNoteScopeTarget 两处同时加载附注树。没有单飞合并时第二路
    // 并发动态 import 会绕过 vi.mock 去打真实接口，打开链路要等一次真实网络往返才走完——
    // 这里固定 3 次 flush 后章节、选中节点都还停在初始值（本例即打红）。
    const w = await open()
    const noteFormulaCalls = get.mock.calls
      .map((c) => String(c[0]))
      .filter((u) => u.includes('/disclosure-notes/project-1/2025/') && u.endsWith('/formulas'))
    expect(noteFormulaCalls).toHaveLength(1)
    expect(noteFormulaCalls[0]).toContain(SECTION)
    expect(getNoteTree).toHaveBeenCalledTimes(1)
    expect(state(w).noteUserFormulasSection).toBe(SECTION)
    expect(state(w).selectedNodeKey).toBe('note_五_1')
    w.unmount()
  })

  it('点选附注章节节点 → 调 list_note_formulas（精确 pid/year/section）', async () => {
    // 不带页面章节打开：打开链路不预取任何章节的用户集，下面的请求只可能来自点选。
    const w = await open({ noteSection: '', noteSectionTitle: '' })
    get.mockClear()
    // 用户点选具体附注章节节点（onTreeNodeClick 是主交互路径）。
    state(w).onTreeNodeClick({ key: 'note_五_1', _sectionId: SECTION, _sectionTitle: SECTION_TITLE, label: SECTION_TITLE })
    await flushPromises()
    const calls = get.mock.calls.map((c) => String(c[0]))
    const noteFormulaCall = calls.find(
      (u) => u.includes('/disclosure-notes/project-1/2025/') && u.endsWith('/formulas'),
    )
    expect(noteFormulaCall).toBeTruthy()
    expect(noteFormulaCall).toContain(SECTION)
    expect(state(w).noteUserFormulasSection).toBe(SECTION)
    w.unmount()
  })

  it('用户编辑集并入右栏显示（currentRows 含 _userTarget 行）', async () => {
    const w = await open()
    state(w).onTreeNodeClick({ key: 'note_五_1', _sectionId: SECTION, _sectionTitle: SECTION_TITLE, label: SECTION_TITLE })
    await flushPromises()
    expect(state(w).selectedNodeKey).toBe('note_五_1')
    expect(state(w).noteUserFormulasSection).toBe(SECTION)
    const rows = state(w).currentRows as any[]
    expect(rows.some((r) => r._userTarget === '2:0')).toBe(true)
    w.unmount()
  })

  it('变异反证：清空已加载用户集后右栏无用户行（覆盖样本打红锚）', async () => {
    const w = await open()
    state(w).onTreeNodeClick({ key: 'note_五_1', _sectionId: SECTION, _sectionTitle: SECTION_TITLE, label: SECTION_TITLE })
    await flushPromises()
    expect((state(w).currentRows as any[]).some((r) => r._userTarget === '2:0')).toBe(true)
    // 模拟「未并入用户集」：清空 noteUserFormulas → 右栏应退回仅预设行。
    state(w).noteUserFormulas = []
    await flushPromises()
    expect((state(w).currentRows as any[]).some((r) => r._userTarget === '2:0')).toBe(false)
    w.unmount()
  })
})

// spec formula-governance-coverage-closure R4：附注行原先按「其余 → report」保存，编辑后发 report-config 必失败；
// 现交给附注公式弹窗（附注章节公式集接口，整套 + 载入令牌）。
describe('附注章节公式的编辑 / 新增 / 保存交给附注公式弹窗', () => {
  beforeEach(() => {
    get.mockReset()
    get.mockImplementation(async (url: string) => {
      const u = String(url)
      if (u.includes('/disclosure-notes/') && u.endsWith('/formulas')) return USER_FORMULAS
      if (u.includes('note-templates/preset-formulas')) return PRESET_FORMULAS
      if (u.includes('report-config/types')) return []
      return {}
    })
    put.mockReset(); post.mockReset()
    scopeLoad.mockReset(); scopeLoad.mockResolvedValue([])
    scopeGetRows.mockReset(); scopeGetRows.mockReturnValue([])
    acnrListSheets.mockReset(); acnrListSheets.mockResolvedValue([])
    acnrListCells.mockReset(); acnrListCells.mockResolvedValue([])
    getNoteTree.mockReset(); getNoteTree.mockResolvedValue(NOTE_TREE)
  })

  const pick = async (w: ReturnType<typeof create>) => {
    state(w).onTreeNodeClick({ key: 'note_五_1', _sectionId: SECTION, _sectionTitle: SECTION_TITLE, label: SECTION_TITLE })
    await flushPromises()
  }

  it('点附注行「编辑」：打开附注公式弹窗定位本章节，不进通用编辑框、不发任何写请求', async () => {
    const w = await open()
    await pick(w)
    const row = (state(w).currentRows as any[]).find((r) => r._userTarget === '2:0')
    state(w).startEdit(row)
    await flushPromises()
    expect(state(w).showNoteFormulaDialog).toBe(true)
    expect(state(w).showFormulaEdit).toBe(false)
    expect(state(w).noteEditTarget).toEqual({ note_section: SECTION, section_title: SECTION_TITLE, content_type: '' })
    expect(put).not.toHaveBeenCalled()
    expect(post).not.toHaveBeenCalled()
    w.unmount()
  })

  it('附注节点的「+ 新增公式」「💾 保存」同样交给附注公式弹窗（原先保存报「已保存 0 个」）', async () => {
    const w = await open()
    await pick(w)
    state(w).onAddFormulaRow()
    expect(state(w).showNoteFormulaDialog).toBe(true)
    expect(state(w).showFormulaEdit).toBe(false)
    state(w).showNoteFormulaDialog = false
    await state(w).onSaveAllFormulas()
    expect(state(w).showNoteFormulaDialog).toBe(true)
    expect(put).not.toHaveBeenCalled()
    expect(post).not.toHaveBeenCalled()
    w.unmount()
  })

  it('附注公式弹窗保存后：强制重取本章节用户集（不用已加载缓存）并通知宿主', async () => {
    const w = await open()
    await pick(w)
    state(w).openNoteFormulaEditor()
    expect(state(w).noteDialogTarget).toEqual({ note_section: SECTION, section_title: SECTION_TITLE, content_type: '' })
    const before = get.mock.calls.filter((c) => String(c[0]).endsWith('/formulas')).length
    await state(w).onNoteFormulasSaved()
    const after = get.mock.calls.filter((c) => String(c[0]).endsWith('/formulas')).length
    expect(after).toBe(before + 1)
    expect(w.emitted('saved')).toHaveLength(1)
    w.unmount()
  })

  it('附注根节点列着全部章节：点某行「编辑」打开该行所属的本项目章节；模板章节号本项目没有则不打开', async () => {
    const w = await open({ noteSection: '', noteSectionTitle: '' })
    state(w).selectedNodeKey = 'note'
    await flushPromises()
    expect(state(w).noteEditTarget).toBeNull()
    // 预设章节号来自模板（国企 / 上市编号不同）：本项目附注里没有 ⇒ 不打开空弹窗
    state(w).startEdit({ id: 'note_preset_7', row_code: '五、3', row_name: '应收账款' })
    expect(state(w).showNoteFormulaDialog).toBe(false)
    state(w).startEdit({ id: 'note_preset_0', row_code: SECTION, row_name: SECTION_TITLE })
    expect(state(w).showNoteFormulaDialog).toBe(true)
    expect(state(w).noteDialogTarget).toEqual({ note_section: SECTION, section_title: SECTION_TITLE, content_type: '' })
    // 右栏列的是预设全集，不是该章节的用户集 ⇒ 保存后不重取，只通知宿主
    const before = get.mock.calls.length
    await state(w).onNoteFormulasSaved()
    expect(get.mock.calls.length).toBe(before)
    expect(w.emitted('saved')).toHaveLength(1)
    w.unmount()
  })

  it('没有章节编号（附注未生成的静态树 / 章级节点）：不打开弹窗', async () => {
    const w = await open({ noteSection: '', noteSectionTitle: '' })
    state(w).selectedNodeKey = 'note_chapter_x'
    await flushPromises()
    expect(state(w).noteEditTarget).toBeNull()
    state(w).openNoteFormulaEditor()
    expect(state(w).showNoteFormulaDialog).toBe(false)
    w.unmount()
  })

  it('模板挂载附注公式弹窗并绑定当前章节', async () => {
    const { readFileSync } = await import('node:fs')
    const { resolve } = await import('node:path')
    const src = readFileSync(resolve(__dirname, '../FormulaManagerDialog.vue'), 'utf-8')
    expect(src).toMatch(/<NoteFormulaDialog[^>]*v-model="showNoteFormulaDialog"[^>]*:current-note="noteDialogTarget"/)
    // 工具栏按钮：没有具体章节时禁用（不是点了才提示）
    expect(src).toMatch(/data-testid="fm-note-edit" :disabled="!noteEditTarget"/)
    expect(src).toContain('@saved="onNoteFormulasSaved"')
  })
})
