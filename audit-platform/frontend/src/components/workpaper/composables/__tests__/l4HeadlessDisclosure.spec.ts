/** L4 真实披露 Tab 与离屏 provider 的非零恢复 / wire body 等价。 */
import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  apiGet: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn(),
  httpGet: vi.fn(), httpPost: vi.fn(), httpPut: vi.fn(),
  eventOn: vi.fn(), eventOff: vi.fn(), eventEmit: vi.fn(),
  messageSuccess: vi.fn(), messageWarning: vi.fn(), messageError: vi.fn(),
}))
vi.mock('@/services/apiProxy', () => ({
  api: { get: h.apiGet, post: h.apiPost, put: h.apiPut },
}))
vi.mock('@/utils/http', () => ({
  default: { get: h.httpGet, post: h.httpPost, put: h.httpPut },
}))
vi.mock('@/utils/eventBus', () => ({
  eventBus: { on: h.eventOn, off: h.eventOff, emit: h.eventEmit },
}))
vi.mock('element-plus', () => ({
  ElMessage: { success: h.messageSuccess, warning: h.messageWarning, error: h.messageError },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import L4TabDisclosureListed from '../../l4/core/L4TabDisclosureListed.vue'
import L4TabDisclosureSoe from '../../l4/core/L4TabDisclosureSoe.vue'
import { l4HeadlessProvider } from '../l4HeadlessDisclosure'
import { L4_LISTED_SUBTABLE, L4_SOE_SUBTABLE } from '../l4NoteSectionMap'

const PROJECT = 'p-l4'
const WP = 'wp-l4'
const URL = `/api/projects/${PROJECT}/disclosure-notes/sync-from-workpaper`
const J = JSON.stringify

type Variant = 'listed' | 'soe'
const detailRows = [{
  key: 'bond-1', bondName: '2025年度第一期公司债', issueDate: '2025-01-02', maturityDate: '2030-01-02',
  faceValue: 100_000_000, couponRate: 0.042, effectiveRate: 0.051, paymentType: 'installment',
  issuePrice: 96_000_000, transactionCost: 1_000_000, initialAmount: 95_000_000, premiumDiscount: -5_000_000,
  beginCostPrincipal: 92_000_000, beginCostInterestAdj: -4_000_000, beginCostAccrued: 300_000,
  creditIssue: 8_000_000, creditInterestAdj: 1_200_000, debitRedemption: 2_000_000,
  debitInterestAdj: 200_000, endCostPrincipal: 98_000_000, endCostInterestAdj: -3_000_000,
  endCostAccrued: 500_000, couponInterest: 4_200_000, interestExpense: 4_800_000,
  amortization: 600_000, redemptionDate: '', redemptionAmount: 300_000, isRedeemed: false,
  remark: '非零债券明细',
}]

function responses(variant: Variant) {
  return [
    { item_id: 'L4-2-rows', conclusion: null, remark: J(detailRows) },
    {
      item_id: `L4-disc-${variant}-1`, conclusion: '是',
      remark: J({ noteContent: '债券面值已核对', diffNote: '无差异' }),
    },
    { item_id: `L4-disc-${variant}-noteText`, conclusion: null, remark: `${variant} 可转换债券说明` },
    { item_id: `L4-disc-${variant}-conclusion`, conclusion: null, remark: `${variant} 核对结论` },
    { item_id: 'L5-unrelated', conclusion: null, remark: '不得读入' },
  ]
}

const STUBS = Object.fromEntries([
  'el-button', 'el-card', 'el-icon', 'el-input', 'el-option', 'el-select', 'el-table', 'el-table-column', 'el-tag',
].map((name) => [name, true]))

async function tabBody(variant: Variant) {
  const Tab = variant === 'listed' ? L4TabDisclosureListed : L4TabDisclosureSoe
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
    expect(state.disclosureItems[0]).toMatchObject({
      noteContent: '债券面值已核对', isConsistent: '是', diffNote: '无差异',
    })
    expect(state.noteText).toBe(`${variant} 可转换债券说明`)
    expect(state.conclusion).toBe(`${variant} 核对结论`)
    h.apiPost.mockClear()
    await state.syncToDisclosureNotes()
    const calls = h.apiPost.mock.calls.filter(([url]) => url === URL)
    expect(calls).toHaveLength(1)
    return calls[0][1]
  } finally {
    wrapper.unmount()
  }
}

async function providerBody(variant: Variant) {
  h.httpGet.mockImplementation(async (url: string) => {
    if (url.endsWith('/checklist-responses')) return responses(variant)
    throw new Error(`unexpected http.get ${url}`)
  })
  const add = vi.spyOn(window, 'addEventListener')
  try {
    const before = h.httpPost.mock.calls.length
    const result = await l4HeadlessProvider({
      projectId: PROJECT, wpId: WP, wpCode: 'L4', year: 2025, variant,
      applicableStandards: [`${variant}_standalone`],
    })
    const calls = h.httpPost.mock.calls.slice(before).filter(([url]) => url === URL)
    expect(calls).toHaveLength(1)
    expect(calls[0][2]).toMatchObject({ _silent: true })
    expect(h.httpPut).not.toHaveBeenCalled()
    expect(h.apiPut).not.toHaveBeenCalled()
    expect(add).not.toHaveBeenCalled()
    expect(result.sections).toEqual([{
      section: variant === 'listed' ? '五、46' : '八、50', rows: 2, kept: 0,
    }])
    return calls[0][1]
  } finally {
    add.mockRestore()
  }
}

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset()
  h.apiPost.mockResolvedValue({ rows_synced: 2 })
  h.httpPost.mockImplementation(async (_url: string, body: any) => ({
    section_id: body.section_id, rows_synced: 2, push_kept: [],
  }))
})

describe.each(['listed', 'soe'] as const)('L4 %s', (variant) => {
  it('非零已存主表 / 变动 / 说明重挂载后，真实 Tab 与 provider 请求体逐字节相同', async () => {
    const fromTab = await tabBody(variant)
    const fromProvider = await providerBody(variant)
    expect(J(fromProvider)).toBe(J(fromTab))
    const tables = fromProvider.sub_table_data
    const names = variant === 'listed' ? L4_LISTED_SUBTABLE : L4_SOE_SUBTABLE
    expect(tables[names.main]).toHaveLength(1)
    expect(tables[names.movement]).toHaveLength(1)
    expect(Object.values(tables[names.main][0]).some((value) => typeof value === 'number' && value !== 0)).toBe(true)
    expect(Object.values(tables[names.movement][0]).some((value) => typeof value === 'number' && value !== 0)).toBe(true)
    expect(tables._note_texts).toEqual([
      { section: 'l4-convertible-bond', title: '可转换公司债券', text: `${variant} 可转换债券说明` },
    ])
  })
})

it('没有 L4-2 持久化来源时不发送默认零主表或变动表', async () => {
  h.httpGet.mockResolvedValue([
    { item_id: 'L4-disc-listed-noteText', conclusion: null, remark: '仅说明' },
  ])
  const result = await l4HeadlessProvider({
    projectId: PROJECT, wpId: WP, wpCode: 'L4', year: 2025, variant: 'listed', applicableStandards: [],
  })
  expect(result.sections[0]?.error).toBeUndefined()
  const body = h.httpPost.mock.calls.at(-1)?.[1]
  expect(body.sub_table_data).not.toHaveProperty(L4_LISTED_SUBTABLE.main)
  expect(body.sub_table_data).not.toHaveProperty(L4_LISTED_SUBTABLE.movement)
  expect(body.sub_table_data._note_texts).toHaveLength(1)
})
