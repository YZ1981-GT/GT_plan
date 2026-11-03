/** M10 数量/账面价值所有权、真实 Tab 与离屏 provider 非零等价。 */
import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  apiGet: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn(),
  httpGet: vi.fn(), httpPost: vi.fn(), httpPut: vi.fn(),
  eventOn: vi.fn(), eventOff: vi.fn(), eventEmit: vi.fn(),
  success: vi.fn(), warning: vi.fn(), error: vi.fn(), alert: vi.fn(),
}))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet, post: h.apiPost, put: h.apiPut } }))
vi.mock('@/utils/http', () => ({ default: { get: h.httpGet, post: h.httpPost, put: h.httpPut } }))
vi.mock('@/utils/eventBus', () => ({ eventBus: { on: h.eventOn, off: h.eventOff, emit: h.eventEmit } }))
vi.mock('element-plus', () => ({
  ElMessage: { success: h.success, warning: h.warning, error: h.error },
  ElMessageBox: { alert: h.alert },
}))

import M10TabDisclosureListed from '../../m10/core/M10TabDisclosureListed.vue'
import M10TabDisclosureSoe from '../../m10/core/M10TabDisclosureSoe.vue'
import {
  buildM10DisclosurePayload,
  createM10Rows,
  restoreM10Rows,
} from '../m10DisclosureForm'
import { m10HeadlessProvider } from '../m10HeadlessDisclosure'
import { M10_LISTED_SUBTABLE, M10_SOE_SUBTABLE } from '../m10NoteSectionMap'

const PROJECT = 'p-m10'
const WP = 'wp-m10'
const URL = `/api/projects/${PROJECT}/disclosure-notes/sync-from-workpaper`
const J = JSON.stringify
type Variant = 'listed' | 'soe'

function response(item_id: string, remark: string | number) {
  return { item_id, conclusion: null, remark: String(remark) }
}

function movement(variant: Variant, row: string, values: readonly number[]) {
  const fields = ['beginQty', 'beginBalance', 'increaseQty', 'issuance', 'decreaseQty', 'redemption'] as const
  return fields.map((field, index) => response(
    `M10-disclosure-${variant}-movement-${row}-${field}`,
    values[index],
  ))
}
function responses(variant: Variant) {
  if (variant === 'listed') return [
    ...movement('listed', 'perpetual-1', [10, 1_000, 3, 360, 2, 210]),
    ...movement('listed', 'preferred-a', [20, 2_000, 5, 550, 4, 440]),
    response('M10-disclosure-listed-movement-perpetual-1-interestDividend', 88),
    response('M10-disclosure-listed-terms-summary', '主要条款说明'),
    response('M10-disclosure-listed-distribution-note', '股息分配说明'),
    response('M10-disclosure-listed-other-disclosure', '其他事项说明'),
  ]
  return [
    ...movement('soe', 'perpetual', [30, 3_000, 7, 770, 6, 660]),
    ...movement('soe', 'preferred', [40, 4_000, 9, 990, 8, 880]),
    response('M10-disclosure-soe-classification-basis', '分类依据说明'),
    response('M10-disclosure-soe-special-note', '国企专项说明'),
  ]
}

const STUBS = Object.fromEntries([
  'el-button', 'el-card', 'el-icon', 'el-input', 'el-input-number', 'el-table',
  'el-table-column', 'el-tag', 'el-tooltip', 'WpAmountInput',
].map((name) => [name, true]))

async function fromTab(variant: Variant) {
  h.apiGet.mockImplementation(async (url: string) => url.endsWith('/checklist-responses') ? responses(variant) : {})
  const Tab = variant === 'listed' ? M10TabDisclosureListed : M10TabDisclosureSoe
  const wrapper = shallowMount(Tab as any, {
    props: { wpId: WP, projectId: PROJECT, isReadonly: false, applicableStandards: [`${variant}_standalone`] },
    global: { stubs: STUBS },
  })
  try {
    await flushPromises()
    expect(h.httpPost).not.toHaveBeenCalled()
    h.httpPost.mockClear()
    await (wrapper.vm as any).$.setupState.syncToDisclosureNotes()
    return h.httpPost.mock.calls.find(([url]) => url === URL)?.[1]
  } finally {
    wrapper.unmount()
  }
}

async function fromProvider(variant: Variant) {
  h.httpGet.mockImplementation(async (url: string) => url.endsWith('/checklist-responses') ? responses(variant) : {})
  h.httpPost.mockClear()
  const result = await m10HeadlessProvider({
    projectId: PROJECT, wpId: WP, wpCode: 'M10', year: 2025, variant,
    applicableStandards: [`${variant}_standalone`],
  })
  expect(result.sections[0].section).toBe(variant === 'listed' ? '五、54' : '八、59')
  expect(h.httpPut).not.toHaveBeenCalled()
  expect(h.apiPut).not.toHaveBeenCalled()
  return h.httpPost.mock.calls.find(([url]) => url === URL)?.[1]
}

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset()
  h.apiPut.mockResolvedValue({})
  h.httpPost.mockImplementation(async (_url: string, body: any) => ({
    section_id: body.section_id,
    rows_synced: Object.values(body.sub_table_data)
      .filter(Array.isArray).reduce((sum: number, rows: any) => sum + rows.length, 0),
    push_kept: [],
  }))
})

describe.each(['listed', 'soe'] as const)('M10 %s', (variant) => {
  it('真实 Tab 与 provider 的非零请求体逐字节相同，数量和账面价值均有真实来源', async () => {
    const tab = await fromTab(variant)
    const provider = await fromProvider(variant)
    expect(J(provider)).toBe(J(tab))
    const expectedTable = variant === 'listed' ? M10_LISTED_SUBTABLE.movement : M10_SOE_SUBTABLE.main
    const dataKeys = Object.keys(provider.sub_table_data).filter((key) => !key.startsWith('_'))
    expect(dataKeys).toEqual([expectedTable])
    expect(Object.keys(provider.columns)).toEqual([expectedTable])
    expect(provider.sub_table_data[expectedTable][0]).toMatchObject({
      begin_qty: variant === 'listed' ? 10 : 30,
      begin_value: variant === 'listed' ? 1_000 : 3_000,
    })
    expect(provider.sub_table_data[expectedTable].at(-1)).toMatchObject({ label: '合计', is_total: true })
    if (variant === 'listed') {
      expect(provider.sub_table_data).not.toHaveProperty(M10_LISTED_SUBTABLE.basic)
      expect(provider.sub_table_data).not.toHaveProperty(M10_LISTED_SUBTABLE.holders)
      expect(provider.columns).not.toHaveProperty(M10_LISTED_SUBTABLE.basic)
      expect(provider.columns).not.toHaveProperty(M10_LISTED_SUBTABLE.holders)
    }
  })
})

it('无任何变动来源和说明时不构造载荷，不能用默认零覆盖附注', () => {
  expect(buildM10DisclosurePayload({ wpId: WP, variant: 'listed', rows: createM10Rows('listed') })).toBeNull()
  expect(buildM10DisclosurePayload({ wpId: WP, variant: 'soe', rows: createM10Rows('soe') })).toBeNull()
  const oldAmountsOnly = restoreM10Rows(new Map([
    ['M10-disclosure-listed-0-beginBalance', response('legacy', 1_000)],
    ['M10-disclosure-listed-0-issuance', response('legacy', 100)],
  ]), 'listed')
  expect(buildM10DisclosurePayload({ wpId: WP, variant: 'listed', rows: oldAmountsOnly })).toBeNull()
})
it('只有说明时只发送说明，不创建空表或列元数据', () => {
  const payload = buildM10DisclosurePayload({
    wpId: WP, variant: 'listed', rows: createM10Rows('listed'), noteText: '仅有条款说明',
  })!
  expect(Object.keys(payload.sub_table_data)).toEqual(['_note_texts'])
  expect(payload.columns).toEqual({})
})

it('稳定键优先于旧位置键，明确零可读回，非法数值保持无来源', () => {
  const map = new Map([
    ['M10-disclosure-listed-0-beginBalance', response('legacy', 11)],
    ['M10-disclosure-listed-movement-perpetual-1-beginBalance', response('stable', 22)],
    ['M10-disclosure-listed-movement-perpetual-1-beginQty', response('zero', 0)],
    ['M10-disclosure-listed-movement-perpetual-1-increaseQty', response('invalid', '不是数字')],
  ])
  const row = restoreM10Rows(map, 'listed')[0]
  expect(row.beginBalance).toBe(22)
  expect(row.beginQty).toBe(0)
  expect(row.increaseQty).toBeNull()
})

it('每次恢复都从新状态开始，后端删除的字段不会残留上一次非零值', () => {
  const first = restoreM10Rows(new Map([
    ['M10-disclosure-soe-movement-perpetual-beginBalance', response('first', 99)],
  ]), 'soe')
  expect(first[0].beginBalance).toBe(99)
  const second = restoreM10Rows(new Map(), 'soe')
  expect(second[0].beginBalance).toBeNull()
})
