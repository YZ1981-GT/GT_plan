/** K3 owner 状态读回、真实 Tab 与离屏 provider 的非零等价。 */
import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), put: vi.fn(),
  eventOn: vi.fn(), eventOff: vi.fn(), eventEmit: vi.fn(),
  success: vi.fn(), warning: vi.fn(), error: vi.fn(), alert: vi.fn(),
}))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/utils/eventBus', () => ({ eventBus: { on: h.eventOn, off: h.eventOff, emit: h.eventEmit } }))
vi.mock('@/composables/useAgingConfig', async () => {
  const { ref } = await import('vue')
  return { useAgingConfig: () => ({ segments: ref([]), bands: ref([]) }) }
})
vi.mock('element-plus', () => ({
  ElMessage: { success: h.success, warning: h.warning, error: h.error },
  ElMessageBox: { alert: h.alert },
}))

import K3TabDisclosureListed from '../../k3/core/K3TabDisclosureListed.vue'
import K3TabDisclosureSoe from '../../k3/core/K3TabDisclosureSoe.vue'
import { k3HeadlessProvider } from '../k3HeadlessDisclosure'
import { K3_LISTED_SUBTABLE, K3_SOE_SUBTABLE, K3_TABLE_SCOPE } from '../k3NoteSectionMap'

const PROJECT = 'p-k3'
const WP = 'wp-k3'
const URL = `/api/projects/${PROJECT}/disclosure-notes/sync-from-workpaper`
type Variant = 'listed' | 'soe'
const J = JSON.stringify

function saved(item_id: string, value: unknown) {
  return { item_id, conclusion: null, remark: typeof value === 'string' ? value : J(value) }
}

function responses(variant: Variant) {
  const nature = variant === 'listed'
    ? { id: 'nature', title: '（五）其他应付款（按款项性质列示）', rows: [
        { item: '押金', endBalance: 123, beginBalance: 45, isFormula: false },
        { item: '合计', endBalance: 123, beginBalance: 45, isFormula: true },
      ], textContent: '上市按性质说明' }
    : { id: 'nature', title: '四、其他应付款（按款项性质列示）', rows: [
        { item: '应付往来款', endBalance: 234, beginBalance: 56, isFormula: false },
        { item: '合计', endBalance: 234, beginBalance: 56, isFormula: true },
      ], textContent: '国企按性质说明' }
  const longTerm = {
    id: 'long-term',
    title: variant === 'listed'
      ? '（六）其中，账龄超过1年的重要其他应付款'
      : '五、账龄超过1年的重要其他应付款项',
    rows: [{ item: '长期供应商', endBalance: 78, beginBalance: 0, remark: '尚未结算', isFormula: false }],
    textContent: variant === 'listed' ? '上市长期挂账说明' : '国企长期挂账说明',
  }
  return [
    saved(`K3-disc-${variant}-nature`, nature),
    saved(`K3-disc-${variant}-long-term`, longTerm),
    saved(`K3-disc-${variant}-interest`, {
      rows: [{ item: '不应由K3发送的利息', endBalance: 999, beginBalance: 999 }],
      textContent: '不应进入K3叙述',
    }),
  ]
}

const STUBS = Object.fromEntries([
  'el-button', 'el-card', 'el-col', 'el-descriptions', 'el-descriptions-item', 'el-divider', 'el-icon',
  'el-input', 'el-row', 'el-table', 'el-table-column', 'el-tag', 'el-tooltip', 'WpAmountInput',
].map((name) => [name, true]))

async function fromTab(variant: Variant) {
  const map = new Map(responses(variant).map((item) => [item.item_id, item]))
  const Tab = variant === 'listed' ? K3TabDisclosureListed : K3TabDisclosureSoe
  const wrapper = shallowMount(Tab as any, {
    props: { wpId: WP, projectId: PROJECT, allResponses: map, isReadonly: false, applicableStandards: [] },
    global: { stubs: STUBS },
  })
  try {
    await flushPromises()
    h.post.mockClear()
    await (wrapper.vm as any).$.setupState.syncToDisclosureNotes()
    return h.post.mock.calls.find(([url]) => url === URL)?.[1]
  } finally {
    wrapper.unmount()
  }
}

async function fromProvider(variant: Variant) {
  h.get.mockImplementation(async (url: string) => url.endsWith('/checklist-responses') ? responses(variant) : {})
  h.post.mockClear()
  const result = await k3HeadlessProvider({
    projectId: PROJECT, wpId: WP, wpCode: 'K3', year: 2025, variant, applicableStandards: [],
  })
  expect(result.sections[0].section).toBe(variant === 'listed' ? '五、42' : '八、42')
  expect(h.put).not.toHaveBeenCalled()
  return h.post.mock.calls.find(([url]) => url === URL)?.[1]
}
beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset()
  h.post.mockImplementation(async (_url: string, body: any) => ({
    section_id: body.section_id,
    rows_synced: Object.values(body.sub_table_data)
      .filter(Array.isArray).reduce((sum: number, rows: any) => sum + rows.length, 0),
    push_kept: [],
  }))
})

describe.each(['listed', 'soe'] as const)('K3 %s', (variant) => {
  it('真实 Tab 与 provider 非零请求体逐字节相同，且只发送 K3 owner 表和文字', async () => {
    const tab = await fromTab(variant)
    const provider = await fromProvider(variant)
    expect(J(provider)).toBe(J(tab))
    const dataKeys = Object.keys(provider.sub_table_data).filter((key) => !key.startsWith('_')).sort()
    expect(dataKeys).toEqual([...K3_TABLE_SCOPE[variant]].sort())
    const T = variant === 'listed' ? K3_LISTED_SUBTABLE : K3_SOE_SUBTABLE
    expect(provider.sub_table_data[T.byNature][0]).toMatchObject({
      end_amount: variant === 'listed' ? 123 : 234,
    })
    expect(provider.sub_table_data[T.agingOver1y][0]).toMatchObject({
      label: '长期供应商', end_amount: 78, unpaid_reason: '尚未结算',
    })
    const text = provider.sub_table_data._note_texts[0].text
    expect(text).toContain(variant === 'listed' ? '上市按性质说明' : '国企按性质说明')
    expect(text).not.toContain('不应进入K3叙述')
  })
})

it('没有 K3 owner 保存状态时离屏同步 no-op，不用默认零表覆盖附注', async () => {
  h.get.mockResolvedValue([])
  const result = await k3HeadlessProvider({
    projectId: PROJECT, wpId: WP, wpCode: 'K3', year: 2025, variant: 'listed', applicableStandards: [],
  })
  expect(result.sections).toEqual([])
  expect(h.post).not.toHaveBeenCalled()
})
