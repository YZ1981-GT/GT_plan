/**
 * M1/M2/M3/M8 披露 Tab 自动同步消费者契约。
 *
 * 挂载真实 Tab 并调用真实编辑入口，验证 useDisclosureAutoSync 的两层契约：
 * 连续编辑只同步一次、只读不发请求、卸载取消待执行同步。
 */
import { flushPromises, shallowMount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), put: vi.fn(),
  apiGet: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn(),
}))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet, post: h.apiPost, put: h.apiPut } }))
vi.mock('element-plus', async (importOriginal) => ({
  ...(await importOriginal<typeof import('element-plus')>()),
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), alert: vi.fn() },
}))

import M1TabDisclosureListed from '../../m1/core/M1TabDisclosureListed.vue'
import M1TabDisclosureSoe from '../../m1/core/M1TabDisclosureSoe.vue'
import M2TabDisclosureListed from '../../m2/core/M2TabDisclosureListed.vue'
import M2TabDisclosureSoe from '../../m2/core/M2TabDisclosureSoe.vue'
import M3TabDisclosureListed from '../../m3/core/M3TabDisclosureListed.vue'
import M8TabDisclosureListed from '../../m8/core/M8TabDisclosureListed.vue'
import M8TabDisclosureSoe from '../../m8/core/M8TabDisclosureSoe.vue'
import M10TabDisclosureListed from '../../m10/core/M10TabDisclosureListed.vue'
import M10TabDisclosureSoe from '../../m10/core/M10TabDisclosureSoe.vue'
import { M_SYNC_URL, M_TAB_STUBS } from './_mDisclosureTabHarness'

type SetupState = Record<string, (...args: any[]) => unknown>
type Case = {
  name: string
  component: unknown
  edit: (setup: SetupState, value: number) => void
}
const CASES: Case[] = [
  {
    name: 'M1 上市', component: M1TabDisclosureListed,
    edit: (s, value) => s.updateDetailRow(0, 'endAmount', value),
  },
  {
    name: 'M1 国企', component: M1TabDisclosureSoe,
    edit: (s, value) => s.updateDetailRow(0, 'beginBalance', value),
  },
  {
    name: 'M2 上市', component: M2TabDisclosureListed,
    edit: (s, value) => s.updateCapitalRow(0, 'beginShares', value),
  },
  {
    name: 'M2 国企', component: M2TabDisclosureSoe,
    edit: (s, value) => s.updateCapitalRow(0, 'beginAmount', value),
  },
  {
    name: 'M3 上市', component: M3TabDisclosureListed,
    edit: (s, value) => s.updateTreasuryRow(0, 'beginAmount', value),
  },
  {
    name: 'M8 上市', component: M8TabDisclosureListed,
    edit: (s, value) => s.updateDataRow(0, 'beginBalance', value),
  },
  {
    name: 'M8 国企', component: M8TabDisclosureSoe,
    edit: (s, value) => s.updateDataRow(0, 'beginBalance', value),
  },
  {
    name: 'M10 上市', component: M10TabDisclosureListed,
    edit: (s, value) => {
      for (const field of ['beginQty', 'beginBalance', 'increaseQty', 'issuance', 'decreaseQty', 'redemption']) {
        s.updateInstrumentRow(0, field, value)
      }
    },
  },
  {
    name: 'M10 国企', component: M10TabDisclosureSoe,
    edit: (s, value) => {
      for (const field of ['beginQty', 'beginBalance', 'increaseQty', 'issuance', 'decreaseQty', 'redemption']) {
        s.updateRow(0, field, value)
      }
    },
  },
]

function syncCalls(): unknown[][] {
  return h.post.mock.calls.filter(([url]) => url === M_SYNC_URL)
}

async function mountTab(testCase: Case, isReadonly: boolean): Promise<VueWrapper> {
  h.apiGet.mockResolvedValue([])
  const wrapper = shallowMount(testCase.component as any, {
    props: { wpId: 'wp-m', projectId: 'p1', isReadonly, applicableStandards: [] },
    global: { stubs: M_TAB_STUBS },
  })
  await flushPromises()
  h.post.mockClear()
  return wrapper
}

beforeEach(() => {
  vi.useFakeTimers()
  for (const mock of Object.values(h)) mock.mockReset()
  h.get.mockResolvedValue([])
  h.post.mockResolvedValue({ rows_synced: 1 })
  h.put.mockResolvedValue({})
  h.apiGet.mockResolvedValue([])
  h.apiPost.mockResolvedValue({})
  h.apiPut.mockResolvedValue({})
})

afterEach(() => {
  vi.clearAllTimers()
  vi.useRealTimers()
})

describe.each(CASES)('$name 自动同步', (testCase) => {
  it('连续编辑在 800ms 内合并为一次真实同步请求', async () => {
    const wrapper = await mountTab(testCase, false)
    const setup = (wrapper.vm as any).$.setupState as SetupState

    testCase.edit(setup, 101)
    testCase.edit(setup, 202)
    expect(syncCalls()).toHaveLength(0)
    await vi.advanceTimersByTimeAsync(799)
    expect(syncCalls()).toHaveLength(0)
    await vi.advanceTimersByTimeAsync(1)
    await flushPromises()
    expect(syncCalls()).toHaveLength(1)
    wrapper.unmount()
  })

  it('只读态即使调用编辑入口也不发同步请求', async () => {
    const wrapper = await mountTab(testCase, true)
    const setup = (wrapper.vm as any).$.setupState as SetupState

    testCase.edit(setup, 303)
    await vi.advanceTimersByTimeAsync(800)
    await flushPromises()
    expect(syncCalls()).toHaveLength(0)
    wrapper.unmount()
  })

  it('卸载会取消尚未触发的同步', async () => {
    const wrapper = await mountTab(testCase, false)
    const setup = (wrapper.vm as any).$.setupState as SetupState

    testCase.edit(setup, 404)
    wrapper.unmount()
    await vi.advanceTimersByTimeAsync(800)
    await flushPromises()
    expect(syncCalls()).toHaveLength(0)
  })
})
