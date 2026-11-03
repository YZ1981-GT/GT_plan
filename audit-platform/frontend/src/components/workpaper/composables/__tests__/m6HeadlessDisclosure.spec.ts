/** M6 模板行、真实 Tab 与离屏 provider 的非零等价。 */
import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  apiGet: vi.fn(), apiPut: vi.fn(), httpGet: vi.fn(), httpPost: vi.fn(), httpPut: vi.fn(),
  eventOn: vi.fn(), eventOff: vi.fn(), eventEmit: vi.fn(), success: vi.fn(), warning: vi.fn(), error: vi.fn(), alert: vi.fn(),
}))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet, put: h.apiPut } }))
vi.mock('@/utils/http', () => ({ default: { get: h.httpGet, post: h.httpPost, put: h.httpPut } }))
vi.mock('@/utils/eventBus', () => ({ eventBus: { on: h.eventOn, off: h.eventOff, emit: h.eventEmit } }))
vi.mock('element-plus', () => ({
  ElMessage: { success: h.success, warning: h.warning, error: h.error }, ElMessageBox: { alert: h.alert },
}))

import M6TabDisclosureListed from '../../m6/core/M6TabDisclosureListed.vue'
import M6TabDisclosureSoe from '../../m6/core/M6TabDisclosureSoe.vue'
import { m6HeadlessProvider } from '../m6HeadlessDisclosure'
import { createM6ListedRows, createM6SoeRows, m6WireRows } from '../m6DisclosureForm'
import { M6_SUBTABLE } from '../m6NoteSectionMap'

const PROJECT = 'p-m6'
const WP = 'wp-m6'
const URL = `/api/projects/${PROJECT}/disclosure-notes/sync-from-workpaper`
const J = JSON.stringify

type Variant = 'listed' | 'soe'
const listedLabels = [
  '调整前上期末未分配利润', '调整期初未分配利润合计数（调增+，调减-）', '调整后期初未分配利润',
  '加：本期归属于母公司所有者的净利润', '使用盈余公积弥补亏损', '使用资本公积弥补亏损', '其他调整',
  '减：提取法定盈余公积', '提取任意盈余公积', '提取一般风险准备', '应付普通股股利',
  '应付其他权益持有者的股利', '转作股本的普通股股利', '期末未分配利润',
]
const soeLabels = [
  '上年年末余额', '期初调整金额', '本期期初余额', '本期增加额', '其中：本期净利润转入',
  '盈余公积弥补亏损转入', '资本公积弥补亏损转入', '其他调整因素', '本期减少额',
  '其中：本期提取盈余公积数', '本期提取一般风险准备', '本期分配现金股利数', '转增资本', '其他减少', '本期期末余额',
]

function response(item_id: string, remark: unknown) {
  return { item_id, conclusion: null, remark: typeof remark === 'string' ? remark : J(remark) }
}

function responses(variant: Variant) {
  if (variant === 'listed') {
    return [
      response('M6-disclosure-listed-prior-end-before-adj-currentPeriod', 1_000),
      response('M6-disclosure-listed-prior-end-before-adj-priorPeriod', 800),
      response('M6-disclosure-listed-initial-adjustment-total-currentPeriod', 20),
      response('M6-disclosure-listed-initial-adjustment-total-priorPeriod', 10),
      response('M6-disclosure-listed-net-profit-currentPeriod', 500),
      response('M6-disclosure-listed-net-profit-priorPeriod', 450),
      response('M6-disclosure-listed-surplus-cover-loss-currentPeriod', 30),
      response('M6-disclosure-listed-capital-cover-loss-currentPeriod', 15),
      response('M6-disclosure-listed-other-adjustment-currentPeriod', 5),
      response('M6-disclosure-listed-statutory-surplus-currentPeriod', 50),
      response('M6-disclosure-listed-statutory-surplus-ratio', '10%'),
      response('M6-disclosure-listed-cash-dividend-currentPeriod', 100),
      response('M6-disclosure-listed-other-equity-dividend-currentPeriod', 20),
      response('M6-disclosure-listed-stock-dividend-currentPeriod', 10),
      response('M6-disclosure-listed-policy-change', '会计政策变更说明'),
      response('M6-disclosure-listed-distribution-plan', '利润分配说明'),
    ]
  }
  return [
    response('M6-disclosure-soe-prior-end-priorYearEnd', 1_000),
    response('M6-disclosure-soe-initial-adjustment-beginAdj', 20),
    response('M6-disclosure-soe-net-profit-increase', 500),
    response('M6-disclosure-soe-surplus-cover-loss-increase', 30),
    response('M6-disclosure-soe-capital-cover-loss-increase', 15),
    response('M6-disclosure-soe-other-adjustment-increase', 5),
    response('M6-disclosure-soe-surplus-extraction-decrease', 50),
    response('M6-disclosure-soe-general-risk-reserve-decrease', 20),
    response('M6-disclosure-soe-cash-dividend-decrease', 100),
    response('M6-disclosure-soe-capital-conversion-decrease', 10),
    response('M6-disclosure-soe-other-decrease-decrease', 5),
    response('M6-disclosure-soe-risk-reserve', '风险准备说明'),
    response('M6-disclosure-soe-distribution', '国资收益分配说明'),
  ]
}

const STUBS = Object.fromEntries(['el-button', 'el-card', 'el-icon', 'el-input', 'el-table', 'el-table-column', 'el-tag', 'WpAmountInput']
  .map((name) => [name, true]))

async function fromTab(variant: Variant) {
  const Tab = variant === 'listed' ? M6TabDisclosureListed : M6TabDisclosureSoe
  h.apiGet.mockImplementation(async (url: string) => url.endsWith('/checklist-responses') ? responses(variant) : {})
  const wrapper = shallowMount(Tab as any, {
    props: { wpId: WP, projectId: PROJECT, isReadonly: false, applicableStandards: [`${variant}_standalone`] },
    global: { stubs: STUBS },
  })
  try {
    await flushPromises()
    const state = (wrapper.vm as any).$.setupState
    const rows = state.movementRows
    expect(rows.map((row: any) => row.item)).toEqual(variant === 'listed' ? listedLabels : soeLabels)
    h.httpPost.mockClear()
    await state.syncToDisclosureNotes()
    return h.httpPost.mock.calls.find(([url]) => url === URL)?.[1]
  } finally {
    wrapper.unmount()
  }
}

async function fromProvider(variant: Variant) {
  h.httpGet.mockImplementation(async (url: string) => url.endsWith('/checklist-responses') ? responses(variant) : {})
  h.httpPost.mockClear()
  const out = await m6HeadlessProvider({
    projectId: PROJECT, wpId: WP, wpCode: 'M6', year: 2025, variant, applicableStandards: [`${variant}_standalone`],
  })
  expect(out.sections).toEqual([{
    section: variant === 'listed' ? '五、61' : '八、63', rows: variant === 'listed' ? 14 : 15, kept: 0,
  }])
  expect(h.httpPut).not.toHaveBeenCalled()
  expect(h.apiPut).not.toHaveBeenCalled()
  return h.httpPost.mock.calls.find(([url]) => url === URL)?.[1]
}

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset()
  h.httpPost.mockImplementation(async (_url: string, body: any) => ({
    section_id: body.section_id,
    rows_synced: body.section_id === '五、61' ? 14 : 15,
    push_kept: [],
  }))
})

describe.each(['listed', 'soe'] as const)('M6 %s', (variant) => {
  it('固定行逐字对齐模板，真实 Tab 与 provider 非零请求体逐字节相同', async () => {
    const tab = await fromTab(variant)
    const provider = await fromProvider(variant)
    expect(J(provider)).toBe(J(tab))
    const rows = provider.sub_table_data[M6_SUBTABLE.main]
    expect(rows.map((row: any) => row.label)).toEqual(variant === 'listed' ? listedLabels : soeLabels)
    expect(rows.flatMap((row: any) => Object.values(row)).some((value: unknown) => typeof value === 'number' && value !== 0)).toBe(true)
    if (variant === 'listed') expect(rows.find((row: any) => row.label === '减：提取法定盈余公积').ratio).toBe('10%')
  })
})

it('公式行不从 wire 快照丢失，且两版行数与模板一致', () => {
  const listed = m6WireRows('listed', createM6ListedRows())
  const soe = m6WireRows('soe', createM6SoeRows())
  expect(listed.map((row) => row.label)).toEqual(listedLabels)
  expect(soe.map((row) => row.label)).toEqual(soeLabels)
  expect(listed).toHaveLength(14)
  expect(soe).toHaveLength(15)
})
