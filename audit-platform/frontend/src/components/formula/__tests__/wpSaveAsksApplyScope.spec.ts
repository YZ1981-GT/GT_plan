/**
 * 底稿新公式保存后按回执问「应用范围」（spec formula-management-repair-closure R4）
 *
 * 公式管理在底稿里新增一条公式：落库成功后，回执带 `changed_slot_keys`（执行定义真的变了）⇒ 调顶栏
 * `askApplyScope('wp', 公式位)` 弹应用范围；回执不带（只改了说明等不影响计算的字段）⇒ 不弹。保存后刷新联动状态。
 * 变异「askWpApplyScope 不再调顶栏」原先没有任何用例能发现（工具栏 / 应用范围弹窗的用例都直接调 askApplyScope），本文件补上。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import FormulaManagerDialog from '@/components/formula/FormulaManagerDialog.vue'
import { GC0_CONTRACT_VERSION, type CanonicalWorkpaperLocation } from '@/shared/contracts/gc0'
import type { WorkpaperCapabilitySnapshot } from '@/shell/formula/workpaperCapabilitySnapshot'
import { openSessionFromCommand } from '@/shell/formula/openFormulaManagerCommand'

const SHEET = '应收账款审定表D2-1'
const { get, put, askApplyScope, refreshPropagation, acnrListSheets } = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
  askApplyScope: vi.fn(),
  refreshPropagation: vi.fn(),
  acnrListSheets: vi.fn(),
}))

vi.mock('@/services/apiProxy', () => ({ api: { get, put, post: vi.fn(async () => ({})) } }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/components/formula/FormulaEditDialog.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/formula/FormulaHistoryTab.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/shared/SharedTemplatePicker.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/import/UnifiedImportDialog.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/services/auditPlatformApi', () => ({ getDisclosureNoteTree: vi.fn(async () => []) }))
vi.mock('@/stores/displayPrefs', () => ({
  useDisplayPrefsStore: () => ({ fmtAmount: (v: unknown) => String(v ?? ''), fmt: (v: unknown) => String(v ?? '') }),
}))
vi.mock('@/stores/addressRegistry', () => ({ useAddressRegistry: () => ({ loaded: false, tbAddresses: [] }) }))
vi.mock('@/composables/useFormulaScopeCatalog', () => ({
  useFormulaScopeCatalog: () => ({
    loadScope: vi.fn(async () => []), resolveSources: vi.fn(async () => undefined), getScopeRows: vi.fn(() => []),
    loadGlobal: vi.fn(async () => ({})), resolveScopeSources: vi.fn(async () => undefined),
    // 弹窗正文渲染时公式看板 / 全局总览读这三项
    allRows: { value: [] }, totalCount: { value: 0 }, globalGrouped: { value: {} },
  }),
  SCOPE_LABEL_MAP: {},
}))
vi.mock('@/services/acnr/useAcnr', () => ({
  useAcnr: () => ({
    listSheets: acnrListSheets, listCells: vi.fn(), resolve: vi.fn(), resolveFormula: vi.fn(),
    resolveUri: vi.fn(), resolveAddr: vi.fn(), resolveIndex: vi.fn(), resolveInstance: vi.fn(),
  }),
}))
vi.mock('@/services/apiPaths', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return { ...actual, linkageBus: {}, formulaAuditLog: { list: '/api/formula-audit-logs' } }
})

/** 顶栏替身：只暴露公式管理会调用的两个方法 */
const ToolbarStub = { name: 'FormulaSettingsToolbar', template: '<div />', methods: { askApplyScope, refreshPropagation } }

const LOCATION: CanonicalWorkpaperLocation = {
  contractVersion: GC0_CONTRACT_VERSION, organizationId: 'org', projectId: 'project-1', fiscalYear: 2025,
  wpId: 'wp-1', wpCode: 'D2', entryId: null, host: 'html',
  anchor: { kind: 'sheet', sheetUid: 's-1', sheetCode: 'D2-1' },
  display: { sheetName: SHEET, sectionLabel: null }, ownerEpoch: 1, contextRevision: 1,
}
const YES = { allowed: true, reasonCode: null, owner: null, nextAction: null, zhMessage: null }
const CAPABILITY = {
  snapshotVersion: '1.0', subjectDigest: 'd', ownerEpoch: 1, expiresAt: '2099-01-01T00:00:00Z',
  formulaView: YES, formulaEditUser: YES, formulaHistory: YES, aiReviewPage: YES, aiReviewBatch: YES,
  aiAssistChat: YES, humanReviewRead: YES, humanReviewWrite: YES, guidanceRead: YES,
} as WorkpaperCapabilitySnapshot

async function openDialog() {
  const w = shallowMount(FormulaManagerDialog, {
    props: {
      modelValue: false, rows: [], scope: 'workpaper', wpId: 'wp-1', wpCode: 'D2', projectId: 'project-1', year: 2025,
      sheetName: SHEET, canonicalLocation: LOCATION, capabilitySnapshot: CAPABILITY,
      formulaSession: openSessionFromCommand({
        commandVersion: '2.0', location: LOCATION, capabilitySnapshotVersion: '1.0', ownerEpoch: 1, contextRevision: 1,
      }),
    },
    // 顶栏在弹窗默认插槽里：替身弹窗要渲染默认插槽，模板 ref 才挂得上顶栏（其余替身仍不渲染插槽）
    global: {
      plugins: [ElementPlus], renderStubDefaultSlot: false,
      stubs: { FormulaSettingsToolbar: ToolbarStub, ElDialog: { template: '<div><slot /></div>' } },
    },
  })
  await w.setProps({ modelValue: true })
  await flushPromises()
  await flushPromises()
  return w
}

const state = (w: Awaited<ReturnType<typeof openDialog>>) => (w.vm as any).$.setupState

async function addAndSave(w: Awaited<ReturnType<typeof openDialog>>) {
  state(w).onAddFormulaRow()
  expect(state(w).editingRow?._isNew, '新增公式应打开编辑弹窗').toBe(true)
  await state(w).onFormulaEditSave({ formula: '100+23', category: 'auto_calc', description: '', target_cell: 'B7' })
  await flushPromises()
}

describe('公式管理：底稿新公式保存后问应用范围', () => {
  beforeEach(() => {
    get.mockReset()
    get.mockImplementation(async (url: string) => {
      if (String(url).includes('/formulas')) return { items: [], surfaced: [], extraction: { tierA: [], tierB: [] } }
      if (String(url).includes('report-config/types')) return []
      return {}
    })
    put.mockReset()
    askApplyScope.mockReset()
    refreshPropagation.mockReset()
    acnrListSheets.mockReset()
    acnrListSheets.mockResolvedValue([{
      addr_id: 'D2/D2-1', domain: 'wp', cycle: 'D', parent_wp_code: 'D2', sheet_code: 'D2-1', sheet_name: SHEET,
    }])
  })

  it('回执带变化的公式位：按这些公式位弹应用范围，并刷新联动状态', async () => {
    const slots = [`D2|${SHEET}|B7`]
    put.mockResolvedValue({ saved: { id: 'f-new', definition_version: 1 }, changed_slot_keys: slots })
    const w = await openDialog()
    expect(typeof state(w).settingsToolbarRef?.askApplyScope, '顶栏替身没挂上，判据会空转').toBe('function')
    await addAndSave(w)

    expect(put).toHaveBeenCalledTimes(1)
    expect(put.mock.calls[0][0]).toBe('/api/workpapers/wp-1/formulas')
    expect(put.mock.calls[0][1]).toMatchObject({ target_cell: 'B7', expression: '100+23', sheet_name: SHEET })
    expect(askApplyScope).toHaveBeenCalledTimes(1)
    expect(askApplyScope).toHaveBeenCalledWith('wp', slots)
    expect(refreshPropagation).toHaveBeenCalled()
    w.unmount()
  })

  it('回执不带变化的公式位（执行定义没变）：不弹', async () => {
    put.mockResolvedValue({ saved: { id: 'f-new', definition_version: 2 } })
    const w = await openDialog()
    await addAndSave(w)

    expect(put).toHaveBeenCalledTimes(1)
    expect(askApplyScope).not.toHaveBeenCalled()
    w.unmount()
  })
})
