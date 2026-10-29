/**
 * F1 离屏同步接入门：真实 listed / soe Tab 与 provider 在同一非零底稿、账龄配置和
 * render 上下文下逐章节请求体逐字节相同；配置失败时也必须走同一兜底。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h as vueH, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

const net = vi.hoisted(() => ({
  httpGet: vi.fn(), httpPost: vi.fn(), httpPut: vi.fn(),
  apiGet: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn(),
  routerPush: vi.fn(), messageSuccess: vi.fn(), messageWarning: vi.fn(),
  messageError: vi.fn(), messageInfo: vi.fn(), confirm: vi.fn(),
}))

vi.mock('@/utils/http', () => ({
  default: { get: net.httpGet, post: net.httpPost, put: net.httpPut },
}))
vi.mock('@/services/apiProxy', () => ({
  api: { get: net.apiGet, post: net.apiPost, put: net.apiPut },
}))
vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRouter: () => ({ push: net.routerPush }),
  useRoute: () => ({ params: {}, query: {} }),
}))
vi.mock('element-plus', async (importOriginal) => ({
  ...(await importOriginal<typeof import('element-plus')>()),
  ElMessage: {
    success: net.messageSuccess, warning: net.messageWarning,
    error: net.messageError, info: net.messageInfo,
  },
  ElMessageBox: { confirm: net.confirm },
}))
import F1TabDisclosureListed from '../../f1/F1TabDisclosureListed.vue'
import F1TabDisclosureSoe from '../../f1/F1TabDisclosureSoe.vue'
import { clearAgingConfigCache, PRESET_SEGMENTS, type AgingPreset } from '@/composables/useAgingConfig'
import { f1HeadlessProvider } from '../f1HeadlessDisclosure'
import { f1ClientNameOf, f1ImpairmentPrefillOf } from '../f1HostRenderContext'
import { F1_LISTED_SUBTABLE, F1_SOE_SUBTABLE } from '../f1DisclosureSyncPayload'
import { useF1AgingScope } from '../useF1AgingScope'
import { useF1CrossSheet } from '../useF1CrossSheet'
import type { ChecklistResponse } from '../useF1FormData'

const PROJECT_ID = 'p-f1'
const WP_ID = 'wp-f1'
const YEAR = 2025
const SYNC_URL = `/api/projects/${PROJECT_ID}/disclosure-notes/sync-from-workpaper`
const J = JSON.stringify

type Variant = 'listed' | 'soe'
type Resp = { item_id: string; conclusion: string | null; remark: string | null }

const response = (itemId: string, value: unknown): Resp => ({
  item_id: itemId,
  conclusion: null,
  remark: typeof value === 'string' ? value : J(value),
})

function detailRows(preset: AgingPreset) {
  const segments = PRESET_SEGMENTS[preset]
  const names = ['甲供应商', '乙供应商', '丙供应商', '丁供应商', '戊供应商', '己供应商']
  const endAmounts = [600, 500, 400, 300, 200, 100]
  const priorAmounts = [300, 250, 200, 150, 100, 50]
  return names.map((customerName, index) => {
    const amount = endAmounts[index]
    const priorAmount = priorAmounts[index]
    const segment = segments[index % segments.length]
    return {
      rowId: `detail-${index + 1}`,
      customerName,
      nature: index % 2 ? '工程款' : '货款',
      relationType: '非关联方',
      endAudited: amount,
      priorAudited: priorAmount,
      agingAudited: Object.fromEntries(segments.map((s) => [s.key, s.key === segment.key ? amount : 0])),
      agingPrior: Object.fromEntries(segments.map((s) => [s.key, s.key === segment.key ? priorAmount : 0])),
    }
  })
}
function responsesFor(preset: AgingPreset): Resp[] {
  const segments = PRESET_SEGMENTS[preset]
  const badDebt = Object.fromEntries(segments.map((s, i) => [s.key, { end: i + 1, prior: i + 0.5 }]))
  return [
    response('F1-det-rows', detailRows(preset)),
    response('F1-lt-rows', [{
      rowId: 'long-1', customerName: '长期供应商', endBalance: 900,
      badDebtProvision: 90, aging: '3年以上', reason: '合同尚未结算',
    }]),
    response('F1-note-listed-over1-rows', [{
      rowId: 'listed-manual-1', debtorName: '手工上市供应商', endBalance: 75,
      impairment: 3, reason: '验收未完成',
    }]),
    response('F1-note-listed-over1-reasons', { 乙供应商: '等待发票' }),
    response('F1-note-listed-over1-impairments', { 乙供应商: 8 }),
    response('F1-note-listed-top5-mode', 'separate'),
    response('F1-note-listed-note-1', '上市账龄说明'),
    response('F1-note-listed-note-2', '上市长期款项说明'),
    response('F1-note-listed-note-3', '上市前五名说明'),
    response('F1-note-soe-aging-bad-debt', badDebt),
    response('F1-note-soe-top5-bad-debt', {
      甲供应商: 12, 乙供应商: 10, 丙供应商: 8, 丁供应商: 6, 戊供应商: 4,
    }),
    response('F1-note-soe-over1-meta', { 长期供应商: { agingLabel: '3年以上', reason: '管理层已说明' } }),
    response('F1-note-soe-over1-rows', [{
      rowId: 'soe-manual-1', creditorUnit: '', debtorUnit: '手工国企供应商',
      endBalance: 66, agingLabel: '1至2年', reason: '合同执行中',
    }]),
    response('F1-note-soe-note-1', '国企账龄说明'),
    response('F1-note-soe-note-2', '国企长期款项说明'),
    response('F1-note-soe-note-3', '国企前五名说明'),
    response('K1-unrelated', '不得进入 F1'),
  ]
}

const RENDER_HTML = {
  impairment_prefill: { end: 37, prior: 19 },
  project_context: { client_name: '被审计单位甲公司' },
}

const RENDER_CONFIG = {
  sheets: [
    { sheet_name: '附注披露信息（上市公司）', html_data: RENDER_HTML },
    // 主入口认“国企/国有企业”同义；用带科目前缀的真实变体卡住 provider 的定位口径。
    { sheet_name: '预付款项附注披露信息（国有企业）', html_data: RENDER_HTML },
  ],
}
interface CaseState {
  responses: Resp[]
  agingConfig: {
    preset: AgingPreset
    effective_segments: typeof PRESET_SEGMENTS.THREE_YEAR
    subject_overrides: Record<string, AgingPreset>
  }
  renderConfig: typeof RENDER_CONFIG
  failAging: boolean
  failRender: boolean
}

let state: CaseState

function configureCase(
  preset: AgingPreset,
  failures: Partial<Pick<CaseState, 'failAging' | 'failRender'>> = {},
): void {
  state = {
    responses: responsesFor(preset),
    agingConfig: {
      preset,
      effective_segments: PRESET_SEGMENTS[preset],
      subject_overrides: { F1: preset },
    },
    renderConfig: RENDER_CONFIG,
    failAging: failures.failAging ?? false,
    failRender: failures.failRender ?? false,
  }
}

const EL_STUBS = Object.fromEntries([
  'el-alert', 'el-button', 'el-input', 'el-option', 'el-popconfirm',
  'el-radio-button', 'el-radio-group', 'el-select', 'el-table',
  'el-table-column', 'el-tag', 'el-tooltip',
].map((name) => [name, true]))

const TAB_STUBS = {
  ...EL_STUBS,
  F1DisclosureUsageGuide: true,
  F1FourTableSourcePanel: true,
  F1DisclosureConsistencyPanel: true,
  GtIndexChip: true,
  WpAmountInput: true,
}

function ownResponseMap(): Map<string, ChecklistResponse> {
  return new Map(
    state.responses
      .filter((item) => item.item_id.startsWith('F1-'))
      .map((item) => [item.item_id, item as ChecklistResponse]),
  )
}
function htmlDataForTab(variant: Variant): Record<string, unknown> | undefined {
  if (state.failRender) return undefined
  const marker = variant === 'listed' ? '上市' : '国有企业'
  return state.renderConfig.sheets.find((sheet) => sheet.sheet_name.includes(marker))?.html_data
}

function makeTabHarness(variant: Variant) {
  const Tab = variant === 'listed' ? F1TabDisclosureListed : F1TabDisclosureSoe
  const htmlData = htmlDataForTab(variant)
  const standards = [`${variant}_standalone`]
  return defineComponent({
    name: `F1${variant}ParityHarness`,
    setup() {
      const allResponses = ref(ownResponseMap())
      const projectId = ref(PROJECT_ID)
      const isReadonly = ref(false)
      const agingScope = useF1AgingScope({
        allResponses,
        projectId,
        debouncedSave: () => {},
        isReadonly,
      })
      const crossSheet = useF1CrossSheet({ allResponses, segments: agingScope.segments })
      return () => vueH(Tab as any, {
        allResponses: allResponses.value,
        wpId: WP_ID,
        projectId: PROJECT_ID,
        year: YEAR,
        isReadonly: false,
        saveImmediate: async () => {},
        debouncedSave: () => {},
        crossSheet,
        applicableStandards: standards,
        agingSegments: agingScope.segments.value,
        impairmentPrefill: f1ImpairmentPrefillOf(htmlData),
        clientName: f1ClientNameOf(htmlData),
      })
    },
  })
}

async function captureTabBodies(variant: Variant): Promise<unknown[]> {
  clearAgingConfigCache()
  const Tab = variant === 'listed' ? F1TabDisclosureListed : F1TabDisclosureSoe
  const wrapper = mount(makeTabHarness(variant), { global: { stubs: TAB_STUBS } })
  try {
    await flushPromises()
    const child = wrapper.findComponent(Tab as any)
    expect(child.exists(), `${variant} 真实 Tab 未挂载`).toBe(true)
    const sync = (child.vm as any).$?.setupState?.syncToDisclosureNotes
    expect(typeof sync).toBe('function')
    const before = net.apiPost.mock.calls.length
    await sync()
    await flushPromises()
    return net.apiPost.mock.calls.slice(before)
      .filter(([url]) => url === SYNC_URL)
      .map(([, body]) => body)
  } finally {
    wrapper.unmount()
  }
}
async function captureProviderBodies(variant: Variant): Promise<{ bodies: unknown[]; out: unknown }> {
  clearAgingConfigCache()
  net.httpPut.mockClear()
  net.apiPut.mockClear()
  net.messageSuccess.mockClear()
  net.messageWarning.mockClear()
  net.messageError.mockClear()
  net.messageInfo.mockClear()
  net.confirm.mockClear()

  const domBefore = document.body.innerHTML
  const apiPostBefore = net.apiPost.mock.calls.length
  const postBefore = net.httpPost.mock.calls.length
  const addListener = vi.spyOn(window, 'addEventListener')
  const dispatch = vi.spyOn(window, 'dispatchEvent')
  try {
    const out = await f1HeadlessProvider({
      projectId: PROJECT_ID,
      wpId: WP_ID,
      wpCode: 'F1',
      year: YEAR,
      variant,
      applicableStandards: [`${variant}_standalone`],
    })
    const providerPosts = net.httpPost.mock.calls.slice(postBefore)
    const bodies = providerPosts
      .filter(([url]) => url === SYNC_URL)
      .map(([, body]) => body)
    expect(providerPosts.every(([url]) => url === SYNC_URL)).toBe(true)
    expect(addListener).not.toHaveBeenCalled()
    expect(dispatch).not.toHaveBeenCalled()
    expect(document.body.innerHTML).toBe(domBefore)
    expect(net.httpPut).not.toHaveBeenCalled()
    expect(net.apiPut).not.toHaveBeenCalled()
    expect(net.apiPost.mock.calls).toHaveLength(apiPostBefore)
    expect(net.messageSuccess).not.toHaveBeenCalled()
    expect(net.messageWarning).not.toHaveBeenCalled()
    expect(net.messageError).not.toHaveBeenCalled()
    expect(net.messageInfo).not.toHaveBeenCalled()
    expect(net.confirm).not.toHaveBeenCalled()
    return { bodies, out }
  } finally {
    addListener.mockRestore()
    dispatch.mockRestore()
  }
}

beforeEach(() => {
  for (const fn of Object.values(net)) fn.mockReset()
  configureCase('THREE_YEAR')
  net.apiGet.mockImplementation(async (url: string) => {
    if (url === `/api/projects/${PROJECT_ID}/aging/config`) {
      if (state.failAging) throw new Error('账龄配置不可用')
      return state.agingConfig
    }
    throw new Error(`未预期的 api.get: ${url}`)
  })
  net.httpGet.mockImplementation(async (url: string) => {
    if (url === '/api/ai/health') return { data: { status: 'offline' } }
    if (url === `/api/workpapers/${WP_ID}/checklist-responses`) return state.responses
    if (url === `/api/workpapers/${WP_ID}/render-config`) {
      if (state.failRender) throw new Error('render-config 不可用')
      return state.renderConfig
    }
    throw new Error(`未预期的 http.get: ${url}`)
  })
  net.apiPost.mockResolvedValue({ rows_synced: 17 })
  net.httpPost.mockImplementation(async (_url: string, body: any) => ({
    section_id: body.section_id,
    rows_synced: 17,
  }))
})

afterEach(() => {
  clearAgingConfigCache()
  vi.useRealTimers()
})
function agingTable(body: any, variant: Variant): any[] {
  const key = variant === 'listed' ? F1_LISTED_SUBTABLE.AGING : F1_SOE_SUBTABLE.AGING
  return body.sub_table_data[key]
}

function over1Table(body: any, variant: Variant): any[] {
  const key = variant === 'listed' ? F1_LISTED_SUBTABLE.OVER1 : F1_SOE_SUBTABLE.OVER1
  return body.sub_table_data[key]
}

async function expectParity(variant: Variant): Promise<any> {
  const tabBodies = await captureTabBodies(variant)
  const { bodies: providerBodies, out } = await captureProviderBodies(variant)
  expect(tabBodies).toHaveLength(1)
  expect(providerBodies).toHaveLength(1)
  expect(providerBodies.map((body) => J(body))).toEqual(tabBodies.map((body) => J(body)))
  expect(out).toEqual({
    sections: [{ section: variant === 'listed' ? '五、7' : '八、7', rows: 17, kept: 0 }],
  })
  return providerBodies[0]
}

describe('f1HeadlessProvider 与真实 F1 披露 Tab', () => {
  it.each([
    ['listed', 'THREE_YEAR'],
    ['listed', 'FIVE_YEAR'],
    ['soe', 'THREE_YEAR'],
    ['soe', 'FIVE_YEAR'],
  ] as const)('%s / %s：同一非零 responses 与 render 上下文逐字节等价', async (variant, preset) => {
    configureCase(preset)
    const sent = await expectParity(variant)
    const expectedSegments = PRESET_SEGMENTS[preset].length
    const rows = agingTable(sent, variant)
    expect(rows).toHaveLength(expectedSegments + 3)
    expect(rows.slice(0, expectedSegments).every((row) => row.end_amount > 0)).toBe(true)
    expect(sent).toMatchObject({
      wp_id: WP_ID,
      section_id: variant === 'listed' ? '五、7' : '八、7',
      current_standard: `${variant}_standalone`,
      year: YEAR,
    })

    if (variant === 'listed') {
      expect(rows.at(-2)).toMatchObject({ label: '减：减值准备', end_amount: 37, prior_amount: 19 })
    } else {
      expect(over1Table(sent, variant)[0]).toMatchObject({
        creditor_unit: '被审计单位甲公司',
        debtor_unit: '长期供应商',
        end_balance: 810,
      })
    }
  })
  it.each(['listed', 'soe'] as const)('%s：账龄配置读取失败时，两路都回退 F1 三年段且保留 render 上下文', async (variant) => {
    configureCase('THREE_YEAR', { failAging: true })
    const sent = await expectParity(variant)
    expect(agingTable(sent, variant)).toHaveLength(PRESET_SEGMENTS.THREE_YEAR.length + 3)
    if (variant === 'listed') {
      expect(agingTable(sent, variant).at(-2)).toMatchObject({ end_amount: 37, prior_amount: 19 })
    } else {
      expect(over1Table(sent, variant)[0].creditor_unit).toBe('被审计单位甲公司')
    }
  })

  it.each(['listed', 'soe'] as const)('%s：render-config 读取失败时，两路都保留五年段并按空上下文兜底', async (variant) => {
    configureCase('FIVE_YEAR', { failRender: true })
    const sent = await expectParity(variant)
    expect(agingTable(sent, variant)).toHaveLength(PRESET_SEGMENTS.FIVE_YEAR.length + 3)
    if (variant === 'listed') {
      expect(agingTable(sent, variant).at(-2)).toMatchObject({ end_amount: 0, prior_amount: 0 })
    } else {
      expect(over1Table(sent, variant)[0].creditor_unit).toBe('')
    }
  })
})
