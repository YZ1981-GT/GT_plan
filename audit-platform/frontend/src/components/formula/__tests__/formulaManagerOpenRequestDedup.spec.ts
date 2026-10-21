/**
 * formulaManagerOpenRequestDedup.spec.ts — 公式管理弹窗打开时的重复请求守卫
 *
 * spec: frontend-test-network-isolation-and-load-dedup（R3.4；design §3、§4）
 *
 * 打开链路里同一个加载函数会被两处同时调用（watch 里直接预加载 + 定位函数 await 等它）：
 *   - loadAcnrTree：附注 / 合并工作底稿 scope → 两次 GET /api/acnr/entries（合并下沉在 useAcnr）
 *   - loadConsolNoteTree：合并附注 scope → 两次 GET 合并附注章节（弹窗内单飞）
 *   - loadNoteUserFormulas：附注 scope 带章节 → 预取 + 定位到章节叶子后再调一次，
 *     两次 GET 本章节用户编辑集（弹窗内单飞）
 * 生产上第二发相同 GET 会被 http 去重取消先发那一发，被取消方当成失败（打告警、先写空树）。
 *
 * 用真实 useAcnr（只 mock 它的 http），ACNR / 用户编辑集响应挂起到断言之后才放行 ⇒ 两路调用
 * 必然重叠，不靠 mock 立即返回的时序碰运气（noteListFormulasWiring 的「1 次」断言就是靠
 * mock 立即返回才成立的：浏览器里第一发还在飞，实测 2 次、先发那次被取消）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import FormulaManagerDialog from '@/components/formula/FormulaManagerDialog.vue'
import { invalidateModuleCache } from '@/services/acnr/useAcnr'

const { get, httpGet, getNoteTree, scopeLoad, addressState } = vi.hoisted(() => ({
  get: vi.fn(),
  httpGet: vi.fn(),
  getNoteTree: vi.fn(),
  scopeLoad: vi.fn(),
  addressState: { loaded: false, tbAddresses: [] },
}))

vi.mock('@/utils/http', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return { ...actual, default: { get: httpGet } }
})
vi.mock('@/services/apiProxy', () => ({ api: { get } }))
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
    getScopeRows: vi.fn(() => []),
    loadGlobal: vi.fn(async () => ({})),
    resolveScopeSources: vi.fn(async () => undefined),
  }),
  SCOPE_LABEL_MAP: {},
}))
vi.mock('@/services/apiPaths', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return { ...actual, linkageBus: {}, formulaAuditLog: { list: '/api/formula-audit-logs' } }
})

const SECTION = '五、1'
const NOTE_TREE = [{ section_id: SECTION, note_section: SECTION, section_title: '货币资金', title: '货币资金' }]
const CONSOL_SECTIONS = [{ label: '五、报表科目', children: [{ section_id: '五-1-1', title: '货币资金' }] }]

/** ACNR 目录响应：挂起直到 releaseAcnr()，保证两路 listSheets 调用重叠。 */
let releaseAcnr: () => void = () => undefined

function create(props: Record<string, unknown>) {
  return shallowMount(FormulaManagerDialog, {
    props: { modelValue: false, rows: [], projectId: 'project-1', year: 2025, templateType: 'soe', ...props },
    global: { plugins: [ElementPlus], renderStubDefaultSlot: false },
  })
}

async function openWhileAcnrPending(props: Record<string, unknown>) {
  const w = create(props)
  await w.setProps({ modelValue: true })
  for (let i = 0; i < 4; i++) await flushPromises()
  return w
}

const acnrEntryCalls = () => httpGet.mock.calls.filter((c) => String(c[0]) === '/api/acnr/entries').length
const consolSectionCalls = () => get.mock.calls.filter((c) => String(c[0]).includes('consol-note-sections')).length
const isNoteUserFormulasUrl = (u: string) => u.includes('/disclosure-notes/project-1/2025/') && u.endsWith('/formulas')
const noteUserFormulaCalls = () => get.mock.calls.filter((c) => isNoteUserFormulasUrl(String(c[0]))).length
const state = (w: ReturnType<typeof create>) => (w.vm as any).$.setupState

beforeEach(() => {
  // useAcnr 的目录缓存是模块级的：上一例放行的响应已写进缓存，不清会让本例一次都不请求
  invalidateModuleCache()
  get.mockReset()
  get.mockImplementation(async (url: string) => {
    const u = String(url)
    if (u.includes('consol-note-sections')) return CONSOL_SECTIONS
    if (u.includes('report-config/types')) return []
    return {}
  })
  httpGet.mockReset()
  httpGet.mockImplementation((url: string) => {
    if (String(url) === '/api/acnr/entries') {
      return new Promise((resolve) => { releaseAcnr = () => resolve({ data: [] }) })
    }
    return Promise.resolve({ data: {} })
  })
  getNoteTree.mockReset()
  getNoteTree.mockResolvedValue(NOTE_TREE)
  scopeLoad.mockReset()
  scopeLoad.mockResolvedValue([])
})

describe('公式管理弹窗打开：同一份目录只请求一次', () => {
  it('附注 scope（带页面章节）：ACNR 目录 1 次', async () => {
    const w = await openWhileAcnrPending({ scope: 'note', noteSection: SECTION, noteSectionTitle: '货币资金' })
    expect(acnrEntryCalls()).toBe(1)
    releaseAcnr()
    await flushPromises()
    expect(acnrEntryCalls()).toBe(1)
    w.unmount()
  })

  it('合并工作底稿 scope：ACNR 目录 1 次', async () => {
    const w = await openWhileAcnrPending({ scope: 'consol_worksheet', sheetName: 'elimination' })
    expect(acnrEntryCalls()).toBe(1)
    releaseAcnr()
    await flushPromises()
    w.unmount()
  })

  it('附注 scope（带页面章节）：本章节用户编辑集公式 1 次', async () => {
    // 用户编辑集响应也挂起：预取那一发还在飞时，定位到章节叶子后的 onTreeNodeClick 会再调一次
    let releaseFormulas: () => void = () => undefined
    get.mockImplementation(async (url: string) => {
      const u = String(url)
      if (isNoteUserFormulasUrl(u)) {
        return new Promise((resolve) => { releaseFormulas = () => resolve({ formulas: [] }) })
      }
      if (u.includes('report-config/types')) return []
      return {}
    })
    const w = await openWhileAcnrPending({ scope: 'note', noteSection: SECTION, noteSectionTitle: '货币资金' })
    releaseAcnr()
    for (let i = 0; i < 4; i++) await flushPromises()
    // 已定位到章节叶子 ⇒ 第二路调用确实发生过（否则本例测不到并发）
    expect(state(w).selectedNodeKey).toBe('note_五_1')
    expect(noteUserFormulaCalls()).toBe(1)
    releaseFormulas()
    await flushPromises()
    expect(noteUserFormulaCalls()).toBe(1)
    expect(state(w).noteUserFormulasSection).toBe(SECTION)
    w.unmount()
  })

  it('合并附注 scope：合并附注章节 1 次', async () => {
    const w = await openWhileAcnrPending({ scope: 'consol_note', noteSection: '五-1-1', noteSectionTitle: '货币资金' })
    releaseAcnr()
    for (let i = 0; i < 3; i++) await flushPromises()
    expect(consolSectionCalls()).toBe(1)
    w.unmount()
  })
})
