/**
 * H3 离屏 provider 与真实 listed / soe 披露 Tab 的逐字节等价测试。
 * 四种口径都从同一宿主 responses Map 恢复计量模式、业务行、文字与 FV 层次。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h as vueH, isRef, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

const net = vi.hoisted(() => ({
  httpGet: vi.fn(), httpPost: vi.fn(), httpPut: vi.fn(),
  apiGet: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn(),
  routerPush: vi.fn(), messageSuccess: vi.fn(), messageWarning: vi.fn(),
  messageError: vi.fn(), messageInfo: vi.fn(), messageAlert: vi.fn(),
  eventOn: vi.fn(), eventOff: vi.fn(), eventEmit: vi.fn(),
}))

vi.mock('@/utils/http', () => ({
  default: { get: net.httpGet, post: net.httpPost, put: net.httpPut },
}))
vi.mock('@/services/apiProxy', () => {
  const api = { get: net.apiGet, post: net.apiPost, put: net.apiPut }
  return { api, apiProxy: api, default: api }
})
vi.mock('@/utils/eventBus', () => ({
  eventBus: { on: net.eventOn, off: net.eventOff, emit: net.eventEmit },
}))
vi.mock('@/composables/useAuditContext', () => ({
  useAuditContext: () => ({ year: { value: 2025 } }),
}))
vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRouter: () => ({ push: net.routerPush }),
  useRoute: () => ({ params: {}, query: {}, path: '/', name: 'wp' }),
}))
vi.mock('element-plus', () => ({
  ElMessage: {
    success: net.messageSuccess, warning: net.messageWarning,
    error: net.messageError, info: net.messageInfo,
  },
  ElMessageBox: { alert: net.messageAlert },
}))

import H3TabDisclosureListed from '../../h3/core/H3TabDisclosureListed.vue'
import H3TabDisclosureSoe from '../../h3/core/H3TabDisclosureSoe.vue'
import { h3HeadlessProvider } from '../h3HeadlessDisclosure'
import { useH3FormData, type ChecklistItem } from '../useH3FormData'
import { useH3MeasurementModel, type MeasurementModelType } from '../useH3MeasurementModel'
import {
  H3_LISTED_SUBTABLE,
  H3_SOE_SUBTABLE,
  type H3DisclosureVariant,
} from '../h3NoteSectionMap'

const PROJECT_ID = 'p-h3'
const WP_ID = 'wp-h3'
const YEAR = 2025
const SYNC_URL = `/api/projects/${PROJECT_ID}/disclosure-notes/sync-from-workpaper`
const J = JSON.stringify

type Resp = ChecklistItem
type Variant = H3DisclosureVariant
interface ParityCase {
  name: string
  variant: Variant
  model: MeasurementModelType
  responses: Resp[]
  mainTable: string
  rowCount: number
  text: string
  hierarchyValue: number
}

const response = (itemId: string, value: unknown): Resp => ({
  item_id: itemId,
  conclusion: null,
  remark: typeof value === 'string' ? value : J(value),
})

const hierarchy = (variant: Variant, fairValue: number): Resp => response(
  `H3-disc-${variant}-fv-hierarchy`,
  [{
    rowId: `${variant}-fv`, category: `${variant}层次资产`, level: '3', fairValue,
    valuationTechnique: '收益法', keyInputs: '市场租金与折现率', isObservable: '否', remark: '非零层次',
  }],
)

const measurement = (model: MeasurementModelType): Resp =>
  response('H3-measurement-model', model)

const CASES: ParityCase[] = [
  {
    name: '上市 / 成本', variant: 'listed', model: 'cost',
    mainTable: H3_LISTED_SUBTABLE.cost, rowCount: 32,
    text: '上市成本：本期外购写字楼。', hierarchyValue: 910,
    responses: [
      measurement('cost'),
      response('H3-disc-listed-rows-cost-original', [
        { rowId: 'lc-o', category: '房屋、建筑物', beginBalance: 1000, increase: 210, decrease: 30 },
      ]),
      response('H3-disc-listed-rows-cost-dep', [
        { rowId: 'lc-d', category: '房屋、建筑物', beginBalance: 180, increase: 45, decrease: 6 },
      ]),
      response('H3-disc-listed-rows-cost-impair', [
        { rowId: 'lc-i', category: '房屋、建筑物', beginBalance: 20, increase: 7, decrease: 2 },
      ]),
      response('H3-disc-listed-rows-title-cert', [
        { rowId: 'lc-t', category: '研发楼', beginBalance: 321, usage: '产权证办理中' },
      ]),
      response('H3-disc-listed-text-cost-original', '上市成本：本期外购写字楼。'),
      hierarchy('listed', 910),
    ],
  },
  {
    name: '上市 / 公允价值', variant: 'listed', model: 'fair_value',
    mainTable: H3_LISTED_SUBTABLE.fair, rowCount: 9,
    text: '上市公允：采用收益法估值。', hierarchyValue: 1435,
    responses: [
      measurement('fair_value'),
      response('H3-disc-listed-rows-fair-change', [
        { rowId: 'lf', category: '土地使用权', beginBalance: 1200, increase: 160, decrease: 25, fairChange: 100 },
      ]),
      response('H3-disc-listed-rows-title-cert', [
        { rowId: 'lf-t', category: '商业楼', bookValue: 432, reason: '换证中' },
      ]),
      response('H3-disc-listed-text-fair-change', '上市公允：采用收益法估值。'),
      hierarchy('listed', 1435),
    ],
  },
  {
    name: '国企 / 成本', variant: 'soe', model: 'cost',
    mainTable: H3_SOE_SUBTABLE.cost, rowCount: 15,
    text: '国企成本：增加额按两级列拆分。', hierarchyValue: 1750,
    responses: [
      measurement('cost'),
      response('H3-disc-soe-rows-soe-cost', [{
        rowId: 'sc-o', category: '房屋、建筑物', beginBalance: 1500,
        buyOrProvision: 180, transferIn: 70, disposal: 35, transferOut: 15,
        increase: 250, decrease: 50, usage: '出租',
      }]),
      response('H3-disc-soe-rows-soe-cost-dep', [{
        rowId: 'sc-d', category: '房屋、建筑物', beginBalance: 260,
        buyOrProvision: 55, transferIn: 5, disposal: 8, transferOut: 2,
        increase: 60, decrease: 10,
      }]),
      response('H3-disc-soe-rows-soe-impair', [{
        rowId: 'sc-i', category: '房屋、建筑物', beginBalance: 30,
        buyOrProvision: 9, transferIn: 1, disposal: 2, transferOut: 1,
        increase: 10, decrease: 3,
      }]),
      response('H3-disc-soe-rows-soe-unlicensed', [
        { rowId: 'sc-t', category: '出租厂房', bookValue: 654, reason: '资料补正中' },
      ]),
      response('H3-disc-soe-text-soe-cost', '国企成本：增加额按两级列拆分。'),
      hierarchy('soe', 1750),
    ],
  },
  {
    name: '国企 / 公允价值', variant: 'soe', model: 'fair_value',
    mainTable: H3_SOE_SUBTABLE.fair, rowCount: 9,
    text: '国企公允：第三层次输入值已复核。', hierarchyValue: 2374,
    responses: [
      measurement('fair_value'),
      response('H3-disc-soe-rows-soe-fair-change', [{
        rowId: 'sf', category: '土地使用权', beginBalance: 2100,
        buyOrProvision: 140, transferIn: 60, fairChange: 120,
        disposal: 30, transferOut: 16, increase: 200, decrease: 46,
      }]),
      // 历史汇总块同时存在时仍应优先细分列块，和真实 Tab 完全一致。
      response('H3-disc-soe-rows-soe-fair-value', [
        { rowId: 'sf-old', category: '房屋、建筑物', beginBalance: 9999, fairChange: 999 },
      ]),
      response('H3-disc-soe-rows-soe-unlicensed', [
        { rowId: 'sf-t', category: '增值物业', beginBalance: 765, usage: '尚待验收' },
      ]),
      response('H3-disc-soe-text-soe-fair-change', '国企公允：第三层次输入值已复核。'),
      hierarchy('soe', 2374),
    ],
  },
]

let activeCase = CASES[0]

const TAB_STUBS = Object.fromEntries([
  'el-alert', 'el-button', 'el-input', 'el-option', 'el-select',
].map((name) => [name, true]))
Object.assign(TAB_STUBS, { GtGridTable: true })

function ownResponseMap(testCase: ParityCase): Map<string, ChecklistItem> {
  return new Map(
    [...testCase.responses, response('H4-unrelated', 999)]
      .filter((item) => item.item_id.startsWith('H3-') || item.item_id.startsWith('H3A-'))
      .map((item) => [item.item_id, { ...item }]),
  )
}

function makeTabHarness(testCase: ParityCase) {
  const Tab = testCase.variant === 'listed' ? H3TabDisclosureListed : H3TabDisclosureSoe
  return defineComponent({
    name: `H3${testCase.variant}ParityHarness`,
    setup() {
      const allResponses = ref(ownResponseMap(testCase))
      const bootstrapModel = ref<MeasurementModelType>('cost')
      const form = useH3FormData({
        wpId: ref(WP_ID), projectId: ref(PROJECT_ID),
        measurementModel: bootstrapModel, allResponses,
      })
      const { measurementModel } = useH3MeasurementModel({
        getValue: form.getValue,
        saveImmediate: async () => {},
      })
      return () => vueH(Tab as any, {
        wpId: WP_ID,
        projectId: PROJECT_ID,
        allResponses: allResponses.value,
        measurementModel: measurementModel.value,
        isReadonly: false,
        applicableStandards: [`${testCase.variant}_standalone`],
      })
    },
  })
}

function setupValue<T>(value: T | { value: T }): T {
  return isRef<T>(value) ? value.value : value as T
}

async function captureTabBody(testCase: ParityCase): Promise<any> {
  const Tab = testCase.variant === 'listed' ? H3TabDisclosureListed : H3TabDisclosureSoe
  const wrapper = mount(makeTabHarness(testCase), { global: { stubs: TAB_STUBS } })
  try {
    await flushPromises()
    const child = wrapper.findComponent(Tab as any)
    expect(child.exists(), `${testCase.name} 真实 Tab 未挂载`).toBe(true)
    expect(child.props('measurementModel')).toBe(testCase.model)
    const setup = (child.vm as any).$?.setupState
    const hierarchyRows = setupValue<any[]>(setup.fvHierarchyRows)
    expect(hierarchyRows[0]).toMatchObject({
      fairValue: testCase.hierarchyValue,
      valuationTechnique: '收益法',
    })
    const sync = setup.syncToDisclosureNotes
    expect(typeof sync).toBe('function')
    const before = net.httpPost.mock.calls.length
    await sync()
    await flushPromises()
    const calls = net.httpPost.mock.calls.slice(before).filter(([url]) => url === SYNC_URL)
    expect(calls).toHaveLength(1)
    return calls[0][1]
  } finally {
    wrapper.unmount()
  }
}

async function captureProviderBody(testCase: ParityCase): Promise<{ body: any; out: unknown }> {
  activeCase = testCase
  for (const fn of [
    net.httpPut, net.apiGet, net.apiPost, net.apiPut,
    net.messageSuccess, net.messageWarning, net.messageError, net.messageInfo, net.messageAlert,
    net.eventOn, net.eventOff, net.eventEmit,
  ]) fn.mockClear()
  const domBefore = document.body.innerHTML
  const postBefore = net.httpPost.mock.calls.length
  const addListener = vi.spyOn(window, 'addEventListener')
  const dispatch = vi.spyOn(window, 'dispatchEvent')
  try {
    const out = await h3HeadlessProvider({
      projectId: PROJECT_ID,
      wpId: WP_ID,
      wpCode: 'H3',
      year: YEAR,
      variant: testCase.variant,
      applicableStandards: [`${testCase.variant}_standalone`],
    })
    const posts = net.httpPost.mock.calls.slice(postBefore)
      .filter(([url]) => url === SYNC_URL)
    expect(posts).toHaveLength(1)
    expect(posts[0][2]).toMatchObject({ _silent: true })
    expect(net.httpPut).not.toHaveBeenCalled()
    expect(net.apiGet).not.toHaveBeenCalled()
    expect(net.apiPost).not.toHaveBeenCalled()
    expect(net.apiPut).not.toHaveBeenCalled()
    expect(net.messageSuccess).not.toHaveBeenCalled()
    expect(net.messageWarning).not.toHaveBeenCalled()
    expect(net.messageError).not.toHaveBeenCalled()
    expect(net.messageInfo).not.toHaveBeenCalled()
    expect(net.messageAlert).not.toHaveBeenCalled()
    expect(net.eventOn).not.toHaveBeenCalled()
    expect(net.eventOff).not.toHaveBeenCalled()
    expect(net.eventEmit).not.toHaveBeenCalled()
    expect(addListener).not.toHaveBeenCalled()
    expect(dispatch).not.toHaveBeenCalled()
    expect(document.body.innerHTML).toBe(domBefore)
    return { body: posts[0][1], out }
  } finally {
    addListener.mockRestore()
    dispatch.mockRestore()
  }
}

beforeEach(() => {
  for (const fn of Object.values(net)) fn.mockReset()
  activeCase = CASES[0]
  net.httpGet.mockImplementation(async (url: string) => {
    if (url === `/api/workpapers/${WP_ID}/checklist-responses`) {
      return [...activeCase.responses, response('H4-unrelated', 999)]
    }
    throw new Error(`未预期的 http.get: ${url}`)
  })
  net.httpPost.mockImplementation(async (_url: string, body: any) => ({
    section_id: body.section_id,
    rows_synced: 13,
    push_kept: [],
  }))
})

afterEach(() => {
  vi.useRealTimers()
})

describe('h3HeadlessProvider 与真实 H3 披露 Tab', () => {
  it.each(CASES)('$name：非零行、文字与 FV 层次从持久化 Map 恢复，POST body 逐字节相同', async (testCase) => {
    activeCase = testCase
    const tabBody = await captureTabBody(testCase)
    const { body: providerBody, out } = await captureProviderBody(testCase)

    expect(J(providerBody)).toBe(J(tabBody))
    expect(providerBody).toMatchObject({
      wp_id: WP_ID,
      section_id: testCase.variant === 'listed' ? '五、21' : '八、21',
      current_standard: `${testCase.variant}_standalone`,
      year: YEAR,
    })
    const mainRows = providerBody.sub_table_data[testCase.mainTable] as Array<Record<string, unknown>>
    expect(mainRows).toHaveLength(testCase.rowCount)
    expect(mainRows.flatMap((row) => Object.values(row)).some((value) => typeof value === 'number' && value !== 0)).toBe(true)
    expect(providerBody.sub_table_data._note_texts).toEqual(expect.arrayContaining([
      expect.objectContaining({ text: testCase.text }),
    ]))
    expect(out).toEqual({
      sections: [{
        section: testCase.variant === 'listed' ? '五、21' : '八、21',
        rows: 13,
        kept: 0,
      }],
    })
  })

  it.each(CASES)('$name：只有模式、文字与 FV 层次而没有行来源时，不推默认零主表', async (testCase) => {
    const noRows: ParityCase = {
      ...testCase,
      responses: [
        measurement(testCase.model),
        response(`H3-disc-${testCase.variant}-text-${testCase.variant === 'listed' ? 'measurement-basis' : 'soe-policy'}`, '仅更新说明'),
        hierarchy(testCase.variant, testCase.hierarchyValue),
      ],
    }
    const { body } = await captureProviderBody(noRows)
    const names = testCase.variant === 'listed' ? H3_LISTED_SUBTABLE : H3_SOE_SUBTABLE
    expect(body.sub_table_data).not.toHaveProperty(names.cost)
    expect(body.sub_table_data).not.toHaveProperty(names.fair)
    expect(body.sub_table_data._removed_table_keys).not.toContain(names.cost)
    expect(body.sub_table_data._removed_table_keys).not.toContain(names.fair)
  })

  it('静态接线只复用 H3 生产 composable / builder，不引入 UI、Tab 或全局监听', () => {
    const provider = readFileSync(resolve(__dirname, '../h3HeadlessDisclosure.ts'), 'utf-8')
    const model = readFileSync(resolve(__dirname, '../useH3MeasurementModel.ts'), 'utf-8')
    expect(model).toContain("const ITEM_ID = 'H3-measurement-model'")
    expect(provider).toContain("prefix: ['H3-', 'H3A-']")
    expect(provider).toContain('useH3FormData(')
    expect(provider).toContain('useH3MeasurementModel(')
    expect(provider).toContain('useH3Disclosure(')
    expect(provider).toContain('getSectionRowsForSync(')
    expect(provider).toContain('buildH3SyncPayload(')
    expect(provider).not.toMatch(/from\s+['"]element-plus['"]|from\s+['"][^'"]+\.vue['"]|\beventBus\b/)
    expect(provider).not.toMatch(/\b(?:api|http)\.(?:put|post)\s*\(|addEventListener\s*\(/)
  })
})
