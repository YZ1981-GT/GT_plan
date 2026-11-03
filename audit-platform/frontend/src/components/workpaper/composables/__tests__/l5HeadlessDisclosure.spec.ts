/** L5 真实 Tab 与离屏 provider 的非零恢复、多章节和 L6 隔离契约。 */
import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  apiGet: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn(),
  httpGet: vi.fn(), httpPost: vi.fn(), httpPut: vi.fn(),
  eventOn: vi.fn(), eventOff: vi.fn(), eventEmit: vi.fn(), routerPush: vi.fn(),
  success: vi.fn(), warning: vi.fn(), error: vi.fn(),
}))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet, post: h.apiPost, put: h.apiPut } }))
vi.mock('@/utils/http', () => ({ default: { get: h.httpGet, post: h.httpPost, put: h.httpPut } }))
vi.mock('@/utils/eventBus', () => ({ eventBus: { on: h.eventOn, off: h.eventOff, emit: h.eventEmit } }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: h.routerPush }) }))
vi.mock('element-plus', () => ({
  ElMessage: { success: h.success, warning: h.warning, error: h.error },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import L5TabDisclosureListed from '../../l5/core/L5TabDisclosureListed.vue'
import L5TabDisclosureSoe from '../../l5/core/L5TabDisclosureSoe.vue'
import { l5HeadlessProvider } from '../l5HeadlessDisclosure'
import {
  L5_LISTED_SUBTABLE, L5_SOE_SUBTABLE, L5_WITHIN1Y_SUBTABLE,
  L6_LISTED_SUBTABLE, L6_SOE_SUBTABLE,
} from '../l5NoteSectionMap'

const PROJECT = 'p-l5'
const WP = 'wp-l5'
const URL = `/api/projects/${PROJECT}/disclosure-notes/sync-from-workpaper`
const J = JSON.stringify

type Variant = 'listed' | 'soe'

const detailRows = [
  {
    key: 'l52-a', section: 'saleLeaseback', payableName: '融资租赁甲', category: '融资租赁款',
    beginning: 1_000, periodRepayment: 100, periodIncrease: 300,
    priorAdjustment: 0, priorReclass: 0, ajeDebit: 0, ajeCredit: 0, rjeDebit: 0, rjeCredit: 0,
    minusPriorDue: 80, minusEndDue: 120, maturityDate: '2026-08-01',
  },
  {
    key: 'l52-b', section: 'installment', payableName: '分期付款乙', category: '分期付款购入资产款',
    beginning: 700, periodRepayment: 50, periodIncrease: 150,
    priorAdjustment: 0, priorReclass: 0, ajeDebit: 0, ajeCredit: 0, rjeDebit: 0, rjeCredit: 0,
    minusPriorDue: 40, minusEndDue: 60, maturityDate: '2027-08-01',
  },
]

const unrecognizedRows = [
  {
    key: 'u-a', payableName: '融资租赁甲', beginning: 120, initialUnrecognized: 180,
    cumulativeAmortization: 40, unrecognizedBalance: 140, periodAmortization: 20,
  },
  {
    key: 'u-b', payableName: '分期付款乙', beginning: 60, initialUnrecognized: 100,
    cumulativeAmortization: 30, unrecognizedBalance: 70, periodAmortization: 10,
  },
]

function response(item_id: string, remark: unknown, conclusion: string | null = null) {
  return { item_id, conclusion, remark: typeof remark === 'string' ? remark : J(remark) }
}

function responses(variant: Variant) {
  const labels = variant === 'listed'
    ? ['融资租赁款', '分期付款购入资产款', '其他长期应付款', '合计']
    : ['融资租赁款', '分期付款购入资产款', '国有资本融资安排', '其他长期应付款', '合计']
  const endValues = variant === 'listed' ? [1_500, 900, 0, 2_400] : [1_500, 900, 0, 321, 2_721]
  const beginValues = variant === 'listed' ? [1_000, 700, 0, 1_700] : [1_000, 700, 0, 123, 1_823]
  const rows = labels.flatMap((_, index) => [
    response(`L5-disclosure-${variant}-cat-${index}-endBalance`, endValues[index]),
    response(`L5-disclosure-${variant}-cat-${index}-beginBalance`, beginValues[index]),
  ])
  return [
    response('L5-L5-2-rows', detailRows),
    response('L5-L5-3-rows', unrecognizedRows),
    response(`L5-disclosure-${variant}-unrecognized-end`, 210),
    response(`L5-disclosure-${variant}-unrecognized-begin`, 180),
    response(`L5-disclosure-${variant}-amortization`, 30),
    response(`L5-disc-${variant}-conclusion`, `${variant} 结论`),
    ...(variant === 'soe' ? [
      response('L5-disclosure-soe-special', '国资专项说明'),
      response('L5-disclosure-soe-related', '关联方公允说明'),
    ] : [response('L5-disclosure-listed-maturity-0', 180)]),
    ...rows,
  ]
}

const STUBS = Object.fromEntries([
  'el-button', 'el-card', 'el-descriptions', 'el-descriptions-item', 'el-icon', 'el-input', 'el-input-number',
  'el-table', 'el-table-column', 'el-tag',
].map((name) => [name, true]))

async function tabBodies(variant: Variant) {
  const Tab = variant === 'listed' ? L5TabDisclosureListed : L5TabDisclosureSoe
  h.apiGet.mockImplementation(async (url: string) => {
    if (url.includes('render-config')) return {}
    if (url.endsWith('/checklist-responses')) return responses(variant)
    throw new Error(`unexpected api.get ${url}`)
  })
  const wrapper = shallowMount(Tab as any, {
    props: { wpId: WP, projectId: PROJECT, isReadonly: false, applicableStandards: [`${variant}_standalone`] },
    global: { stubs: STUBS },
  })
  try {
    await flushPromises()
    const state = (wrapper.vm as any).$.setupState
    const expectedTotal = variant === 'listed'
      ? { endBalance: 2_400, beginBalance: 1_700 }
      : { endBalance: 2_721, beginBalance: 1_823 }
    expect(state.categoryRows.at(-1)).toMatchObject(expectedTotal)
    expect(state.unrecognizedEnd).toBe(210)
    expect(state.unrecognizedBegin).toBe(180)
    expect(state.periodAmortizationAmount).toBe(30)
    if (variant === 'soe') {
      expect(state.soeSpecialNote).toBe('国资专项说明')
      expect(state.relatedPartyNote).toBe('关联方公允说明')
    }
    h.httpPost.mockClear()
    await state.syncToDisclosureNotes()
    return h.httpPost.mock.calls.filter(([url]) => url === URL).map(([, body]) => body)
  } finally {
    wrapper.unmount()
  }
}

async function providerBodies(variant: Variant) {
  h.httpGet.mockImplementation(async (url: string) => {
    if (url.endsWith('/checklist-responses')) return responses(variant)
    throw new Error(`unexpected http.get ${url}`)
  })
  const add = vi.spyOn(window, 'addEventListener')
  try {
    h.httpPost.mockClear()
    const result = await l5HeadlessProvider({
      projectId: PROJECT, wpId: WP, wpCode: 'L5', year: 2025, variant,
      applicableStandards: [`${variant}_standalone`],
    })
    const calls = h.httpPost.mock.calls.filter(([url]) => url === URL)
    expect(calls.every((call) => (call[2] as any)?._silent === true)).toBe(true)
    expect(h.httpPut).not.toHaveBeenCalled()
    expect(h.apiPut).not.toHaveBeenCalled()
    expect(add).not.toHaveBeenCalled()
    expect(result.sections).toHaveLength(2)
    return calls.map(([, body]) => body)
  } finally {
    add.mockRestore()
  }
}

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset()
  h.httpPost.mockImplementation(async (_url: string, body: any) => ({
    section_id: body.section_id, rows_synced: 3, push_kept: [],
  }))
})

describe.each(['listed', 'soe'] as const)('L5 %s', (variant) => {
  it('非零持久化状态恢复后，主章节和一年内到期章节与 provider 逐字节相同', async () => {
    const tab = await tabBodies(variant)
    const provider = await providerBodies(variant)
    expect(provider.map((body) => J(body))).toEqual(tab.map((body) => J(body)))
    expect(provider.map((body) => body.section_id)).toEqual(variant === 'listed' ? ['五、48', '五、43'] : ['八、53', '八、47'])

    const mainName = variant === 'listed' ? L5_LISTED_SUBTABLE.main : L5_SOE_SUBTABLE.main
    const expectedMain = variant === 'listed'
      ? { label: '长期应付款', end_amount: 2_190, prior_amount: 1_520 }
      : { label: '长期应付款', end_amount: 2_511, prior_amount: 1_643 }
    expect(provider[0].sub_table_data[mainName][0]).toMatchObject(expectedMain)
    if (variant === 'soe') {
      const top5Rows = provider[0].sub_table_data[L5_SOE_SUBTABLE.top5] as Array<Record<string, unknown>>
      expect(top5Rows.find((row) => row.label === '其他')).toMatchObject({
        end_amount: 321,
        prior_amount: 123,
      })
      expect(top5Rows.find((row) => row.label === '小计')).toMatchObject({
        end_amount: 2_721,
        prior_amount: 1_823,
      })
    }
    const withinName = L5_WITHIN1Y_SUBTABLE[variant]
    expect(provider[1].sub_table_data[withinName].at(-1)).toMatchObject({ label: '合计', end_amount: 180, prior_amount: 120 })

    const l6Name = variant === 'listed' ? L6_LISTED_SUBTABLE.special : L6_SOE_SUBTABLE.special
    for (const body of provider) {
      expect(body.sub_table_data).not.toHaveProperty(l6Name)
      expect(body.sub_table_data._removed_table_keys ?? []).not.toContain(l6Name)
    }
  })
})

it('没有任何 L5 持久化来源时不发送默认零载荷', async () => {
  h.httpGet.mockResolvedValue([])
  const result = await l5HeadlessProvider({
    projectId: PROJECT, wpId: WP, wpCode: 'L5', year: 2025, variant: 'listed', applicableStandards: [],
  })
  expect(result).toEqual({ sections: [] })
  expect(h.httpPost).not.toHaveBeenCalled()
})
