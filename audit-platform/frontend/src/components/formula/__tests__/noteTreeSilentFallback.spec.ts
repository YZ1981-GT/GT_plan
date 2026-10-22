/**
 * 公式管理中心：本项目附注未生成（后端 404「附注数据不存在」）时静默改用模板目录（spec formula-governance-coverage-closure R5 走查）。
 *
 * 原先 404 既弹全局错误（每次打开公式管理中心都弹），又因异常跳过了模板目录的降级加载。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const { get, put, post, scopeLoad, scopeGetRows, acnrListSheets, acnrListCells, getNoteTree, msg } = vi.hoisted(() => ({
  get: vi.fn(), put: vi.fn(), post: vi.fn(),
  scopeLoad: vi.fn(), scopeGetRows: vi.fn(() => []),
  acnrListSheets: vi.fn(), acnrListCells: vi.fn(), getNoteTree: vi.fn(),
  msg: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return { ...actual, ElMessage: msg }
})
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
  useAddressRegistry: () => ({ loaded: false, tbAddresses: [] }),
}))
vi.mock('@/composables/useFormulaScopeCatalog', () => ({
  useFormulaScopeCatalog: () => ({
    loadScope: scopeLoad, resolveSources: vi.fn(async () => undefined), getScopeRows: scopeGetRows,
    loadGlobal: vi.fn(async () => ({})), resolveScopeSources: vi.fn(async () => undefined),
  }),
  SCOPE_LABEL_MAP: {},
}))
vi.mock('@/services/acnr/useAcnr', () => ({
  useAcnr: () => ({
    listSheets: acnrListSheets, listCells: acnrListCells, resolve: vi.fn(), resolveFormula: vi.fn(),
    resolveUri: vi.fn(), resolveAddr: vi.fn(), resolveIndex: vi.fn(), resolveInstance: vi.fn(),
  }),
}))
vi.mock('@/services/apiPaths', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return { ...actual, linkageBus: {}, formulaAuditLog: { list: '/api/formula-audit-logs' } }
})

import FormulaManagerDialog from '@/components/formula/FormulaManagerDialog.vue'

const TEMPLATE_SECTIONS = [{ section_id: '五、1', section_title: '货币资金', tables: [] }]

function create() {
  return shallowMount(FormulaManagerDialog, {
    props: { modelValue: false, rows: [], scope: 'report', projectId: 'project-1', year: 2025, templateType: 'soe' },
    global: { plugins: [ElementPlus], renderStubDefaultSlot: false },
  })
}
const state = (w: ReturnType<typeof create>) => (w.vm as any).$.setupState

async function open() {
  const w = create()
  await w.setProps({ modelValue: true })
  for (let i = 0; i < 4; i++) await flushPromises()
  const s = state(w)
  await s.loadNoteTree()
  await flushPromises()
  return { w, s }
}

describe('附注目录：本项目附注未生成', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    get.mockImplementation(async (url: string) => {
      const u = String(url)
      if (u.endsWith('/api/note-templates/soe')) return TEMPLATE_SECTIONS
      if (u.includes('report-config/types')) return []
      return {}
    })
    scopeLoad.mockResolvedValue([])
    acnrListSheets.mockResolvedValue([])
    acnrListCells.mockResolvedValue([])
  })

  it('404：静默请求、不提示，改用模板目录', async () => {
    getNoteTree.mockRejectedValue({ response: { status: 404 } })
    const { w, s } = await open()
    expect(getNoteTree).toHaveBeenCalledWith('project-1', 2025, expect.objectContaining({ _silent: true }))
    expect(msg.warning).not.toHaveBeenCalled()
    expect(msg.error).not.toHaveBeenCalled()
    expect(s.noteTreeLoaded).toBe(true)
    expect(JSON.stringify(s.noteTreeChildren)).toContain('货币资金')
    w.unmount()
  })

  it('其他错误（500）：提示加载失败，仍用模板目录', async () => {
    getNoteTree.mockRejectedValue({ response: { status: 500 } })
    const { w, s } = await open()
    expect(msg.warning).toHaveBeenCalledWith('本项目附注目录加载失败，暂按模板目录显示')
    expect(JSON.stringify(s.noteTreeChildren)).toContain('货币资金')
    w.unmount()
  })
})
