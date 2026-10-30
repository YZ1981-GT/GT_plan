/** H1 项目口径、状态恢复、主章节与受限资产段的真实 Tab/provider 等价。 */
import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  httpGet: vi.fn(), httpPost: vi.fn(), httpPut: vi.fn(),
  apiGet: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn(),
  eventOn: vi.fn(), eventOff: vi.fn(), eventEmit: vi.fn(),
  success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn(), confirm: vi.fn(),
}))
vi.mock('@/utils/http', () => ({ default: { get: h.httpGet, post: h.httpPost, put: h.httpPut } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet, post: h.apiPost, put: h.apiPut } }))
vi.mock('@/utils/eventBus', () => ({ eventBus: { on: h.eventOn, off: h.eventOff, emit: h.eventEmit } }))
vi.mock('vue-router', async () => ({
  ...(await vi.importActual<Record<string, unknown>>('vue-router')),
  useRouter: () => ({ push: vi.fn(() => Promise.resolve()) }),
}))
vi.mock('element-plus', async () => ({
  ...(await vi.importActual<Record<string, unknown>>('element-plus')),
  ElMessage: { success: h.success, warning: h.warning, error: h.error, info: h.info },
  ElMessageBox: { confirm: h.confirm },
}))

import H1TabDisclosureListed from '../../h1/core/H1TabDisclosureListed.vue'
import H1TabDisclosureSoe from '../../h1/core/H1TabDisclosureSoe.vue'
import { h1HeadlessProvider } from '../h1HeadlessDisclosure'
import { resolveH1ProjectContext } from '../h1ProjectContext'
import {
  H1_LISTED_DEFAULT_CATEGORIES,
  H1_LISTED_ITEM,
} from '../h1ListedDisclosureModel'
import {
  H1_SOE_KEYS,
  createH1SoeDisclosureState,
  recomputeSoeLayers,
} from '../h1SoeDisclosureModel'

const PROJECT = 'p-h1'
const WP = 'wp-h1'
const SYNC_URL = `/api/projects/${PROJECT}/disclosure-notes/sync-from-workpaper`
const J = JSON.stringify
type Variant = 'listed' | 'soe'
type Resp = { item_id: string; remark: string | null; conclusion: string | null }
const resp = (item_id: string, value: unknown): Resp => ({
  item_id, conclusion: null, remark: typeof value === 'string' ? value : J(value),
})
const LISTED: Resp[] = [
  resp(H1_LISTED_ITEM.summary, [
    { key: 'fixed_assets', label: '固定资产', endBalance: 920, priorBalance: 690 },
    { key: 'clearing', label: '固定资产清理', endBalance: 30, priorBalance: 20 },
  ]),
  resp(H1_LISTED_ITEM.categories, H1_LISTED_DEFAULT_CATEGORIES.map((item) => ({ ...item }))),
  resp(H1_LISTED_ITEM.movement, {
    cost_begin: { buildings: 1_000 }, cost_inc_purchase: { buildings: 200 }, cost_dec_dispose: { buildings: 100 },
    dep_begin: { buildings: 300 }, dep_inc_provision: { buildings: 50 }, dep_dec_dispose: { buildings: 20 },
    imp_begin: { buildings: 10 }, imp_inc_provision: { buildings: 5 }, imp_dec_dispose: { buildings: 5 },
  }),
  resp(H1_LISTED_ITEM.idle, [{ rowId: 'idle-1', name: '闲置仓库', cost: 100, dep: 20, impairment: 5, bookValue: 75, remark: '待处置' }]),
  resp(H1_LISTED_ITEM.leaseOut, [{ rowId: 'lease-1', name: '出租厂房', bookValue: 88 }]),
  resp(H1_LISTED_ITEM.titleCert, [{ rowId: 'title-1', name: '办公楼', bookValue: 66, reason: '办理中' }]),
  resp(H1_LISTED_ITEM.clearing, [{ rowId: 'clr-1', name: '报废设备', endBalance: 30, priorBalance: 20, reason: '清理中' }]),
  resp(H1_LISTED_ITEM.govSubsidy, { amount: 12, text: '本期政府补助冲减固定资产12元。' }),
  resp(H1_LISTED_ITEM.noteImpairment, '减值测试说明'),
  resp(H1_LISTED_ITEM.noteMortgage, '抵押事项说明'),
  resp(H1_LISTED_ITEM.noteSale, '处置事项说明'),
  resp(H1_LISTED_ITEM.noteClearing, '清理事项说明'),
  resp(H1_LISTED_ITEM.mortgageRows, [{ rowId: 'mort-1', name: '抵押厂房', amount: 321, mortgageNature: '借款担保', description: '', remark: '' }]),
]

function soeResponses(): Resp[] {
  const state = createH1SoeDisclosureState()
  const set = (layer: string, key: string, begin: number, increase: number, decrease: number) => {
    const block = state.layers.find((item) => item.layer === layer)!
    const category = block.categories.find((item) => item.key === key)!
    Object.assign(category, { begin, increase, decrease })
  }
  set('cost', 'building', 5_000, 500, 200)
  set('dep', 'building', 1_000, 250, 60)
  set('impair', 'building', 100, 30, 10)
  recomputeSoeLayers(state.layers)
  state.summary = { clearingEnd: 80, clearingBegin: 50 }
  state.idleRows = [{ rowId: 'idle-s', name: '闲置车间', originalCost: 200, accumDep: 50, impairment: 10, carrying: 140, remark: '' }]
  state.titleRows = [{ rowId: 'title-s', name: '无证房产', carrying: 99, reason: '办理中' }]
  state.clearingRows = [{ rowId: 'clr-s', name: '待清理设备', endCarrying: 80, beginCarrying: 50, reason: '报废' }]
  state.clearingNote = '国企固定资产清理说明'
  return [
    resp(H1_SOE_KEYS.summary, state.summary),
    resp(H1_SOE_KEYS.movement, state.layers),
    resp(H1_SOE_KEYS.idle, state.idleRows),
    resp(H1_SOE_KEYS.title, state.titleRows),
    resp(H1_SOE_KEYS.clearing, state.clearingRows),
    resp(H1_SOE_KEYS.clearingNote, state.clearingNote),
    resp('H1-soe-restricted-rows', [{ name: '抵押厂房', amount: 432, mortgageNature: '借款担保' }]),
  ]
}

const fixture = (variant: Variant) => variant === 'listed' ? LISTED : soeResponses()
const renderConfig = (variant: Variant, scope = 'standalone') => ({
  html_data: { project_context: { template_type: variant, report_scope: scope } },
})

const STUBS = Object.fromEntries([
  'el-alert', 'el-button', 'el-card', 'el-checkbox', 'el-col', 'el-descriptions',
  'el-descriptions-item', 'el-divider', 'el-dropdown', 'el-dropdown-item', 'el-dropdown-menu',
  'el-icon', 'el-input', 'el-input-number', 'el-popover', 'el-row', 'el-select', 'el-option',
  'el-table', 'el-table-column', 'el-tag', 'el-tooltip', 'GtIndexChip', 'GtReviewTrigger',
  'WpAmountInput', 'WpNoteTextArea', 'WpDisclosureConsistencyPanel',
].map((name) => [name, true]))

function responseMap(variant: Variant) {
  return new Map(fixture(variant).map((item) => [item.item_id, { ...item }]))
}

async function tabPayloads(variant: Variant): Promise<any[]> {
  const Tab = variant === 'listed' ? H1TabDisclosureListed : H1TabDisclosureSoe
  const wrapper = shallowMount(Tab as any, {
    props: {
      wpId: WP, projectId: PROJECT, allResponses: responseMap(variant), isReadonly: false,
      applicableStandards: [`${variant}_standalone`], templateType: variant, reportScope: 'standalone',
    },
    global: { stubs: STUBS },
  })
  try {
    await flushPromises()
    h.apiPost.mockClear()
    h.httpPost.mockClear()
    await (wrapper.vm as any).$.setupState.syncToNotes()
    return [
      ...h.apiPost.mock.calls.filter(([url]) => url === SYNC_URL).map((call) => call[1]),
      ...h.httpPost.mock.calls.filter(([url]) => url === SYNC_URL).map((call) => call[1]),
    ]
  } finally {
    wrapper.unmount()
  }
}
async function providerPayloads(variant: Variant, scope = 'standalone') {
  h.httpGet.mockImplementation(async (url: string) => {
    if (url.endsWith('/checklist-responses')) return fixture(variant)
    if (url.endsWith('/render-config')) return renderConfig(variant, scope)
    throw new Error(`意外 GET ${url}`)
  })
  h.httpPost.mockClear()
  const result = await h1HeadlessProvider({
    projectId: PROJECT, wpId: WP, wpCode: 'H1', year: 2025, variant,
    applicableStandards: [`${variant}_${scope}`],
  })
  return {
    result,
    payloads: h.httpPost.mock.calls.filter(([url]) => url === SYNC_URL).map((call) => call[1]),
  }
}

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset()
  h.confirm.mockResolvedValue(true)
  const success = async (_url: string, body: any) => ({
    success: true, section_id: body.section_id, rows_synced: 7, push_kept: [],
    row_scope_unresolved: [], row_scope_unresolved_reasons: {},
  })
  h.apiPost.mockImplementation(success)
  h.httpPost.mockImplementation(success)
})

it('宿主 htmlData 与 render-config 读取同一项目口径，并识别 consolidated', () => {
  expect(resolveH1ProjectContext(renderConfig('listed', 'consolidated'))).toEqual({
    templateType: 'listed', reportScope: 'consolidated',
  })
  expect(resolveH1ProjectContext({ data: renderConfig('soe') })).toEqual({
    templateType: 'soe', reportScope: 'standalone',
  })
})

describe.each(['listed', 'soe'] as const)('H1 %s', (variant) => {
  it('主章节+受限资产段与真实 Tab 非零请求体逐字节相同，且 provider 零 PUT', async () => {
    const tab = await tabPayloads(variant)
    const { result, payloads } = await providerPayloads(variant)
    expect(J(payloads)).toBe(J(tab))
    expect(payloads[0].section_id).toBe(variant === 'listed' ? '五、22' : '八、22')
    expect(payloads.some((payload) => payload.section_id === (variant === 'listed' ? '五、32' : '八、93'))).toBe(true)
    expect(payloads.flatMap((payload) => Object.values(payload.sub_table_data ?? {}))
      .flatMap((rows: any) => Array.isArray(rows) ? rows : [])
      .some((row: any) => Object.values(row).some((value) => typeof value === 'number' && value !== 0))).toBe(true)
    expect(result.sections.every((item) => !item.error)).toBe(true)
    expect(h.httpPut).not.toHaveBeenCalled()
    expect(h.apiPut).not.toHaveBeenCalled()
  })
})
it('render-config 项目口径与请求变体不一致时不发送任何载荷', async () => {
  h.httpGet.mockImplementation(async (url: string) => url.endsWith('/checklist-responses')
    ? LISTED
    : renderConfig('soe'))
  const result = await h1HeadlessProvider({
    projectId: PROJECT, wpId: WP, wpCode: 'H1', year: 2025,
    variant: 'listed', applicableStandards: ['listed_standalone'],
  })
  expect(result.sections).toEqual([])
  expect(h.httpPost).not.toHaveBeenCalled()
})

it('受限资产 row_scope_unresolved 在离屏结果中按失败回报，不能静默算成功', async () => {
  h.httpPost.mockImplementation(async (_url: string, body: any) => body.section_id === '五、32'
    ? {
        section_id: body.section_id,
        row_scope_unresolved: ['受限资产及短期投资'],
        row_scope_unresolved_reasons: { 受限资产及短期投资: 'owner_row_code_not_in_template' },
      }
    : { success: true, section_id: body.section_id, rows_synced: 7, push_kept: [] })
  const { result } = await providerPayloads('listed')
  const failed = result.sections.find((item) => item.section === '五、32')
  expect(failed?.error).toContain('owner_row_code_not_in_template')
  expect(failed?.rows).toBe(0)
})

it('主章节与受限资产均无来源时 no-op，不用默认零覆盖附注', async () => {
  h.httpGet.mockImplementation(async (url: string) => url.endsWith('/checklist-responses')
    ? []
    : renderConfig('listed'))
  const result = await h1HeadlessProvider({
    projectId: PROJECT,
    wpId: WP,
    wpCode: 'H1',
    year: 2025,
    variant: 'listed',
    applicableStandards: ['listed_standalone'],
  })
  expect(result.sections).toEqual([])
  expect(h.httpPost).not.toHaveBeenCalled()
})

it('render-config 的 consolidated 口径进入主章节和受限资产载荷', async () => {
  const { payloads } = await providerPayloads('listed', 'consolidated')
  expect(payloads.length).toBeGreaterThan(1)
  expect(payloads.every((payload) => payload.current_standard === 'listed_consolidated')).toBe(true)
})
