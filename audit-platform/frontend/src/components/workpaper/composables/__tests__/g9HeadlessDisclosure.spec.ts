/**
 * G9 其他非流动金融资产披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 快照原在 `G9TabDisclosureBase.syncToDisclosureNotes` 里内联拼 `{ rows, noteText }`，抽成 `g9DisclosureSyncSnapshot` 后
 * Tab 与离屏同步共用。判据：①挂载真实 Tab（上市 / 国企薄壳 → Base）、点「同步到附注」发出的载荷 == 离屏载荷，夹具有真实数据
 * ②离屏不挂生命周期钩子、不订阅审定事件、不广播说明，组件内照旧 ③只读 G9 条目、静默发出、不写底稿 ④口径不适用回空
 * ⑤静态接线。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), apiGet: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet, post: h.apiPost, put: h.apiPut } }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(() => Promise.resolve()) }),
  useRoute: () => ({ params: {}, query: {}, path: '/', name: 'wp' }),
}))
vi.mock('element-plus', async () => ({
  ...(await vi.importActual<Record<string, unknown>>('element-plus')),
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

import { g9HeadlessProvider } from '../g9HeadlessDisclosure'
import { useG9Disclosure } from '../useG9Disclosure'
import G9TabDisclosureListed from '../../g9-other-noncurrent-financial/core/G9TabDisclosureListed.vue'
import G9TabDisclosureSOE from '../../g9-other-noncurrent-financial/core/G9TabDisclosureSOE.vue'
import type { ChecklistResponse } from '../useF1FormData'

const J = JSON.stringify
const RESPONSES: ChecklistResponse[] = [
  {
    item_id: 'G9-disclosure-listed',
    remark: J({
      listed_1: { currentAmount: 1200.5, priorAmount: 800, noteText: '' },
      listed_2: { currentAmount: 300, priorAmount: 0, noteText: '非上市股权' },
    }),
    conclusion: null,
  },
  { item_id: 'G9-disclosure-listed-note', conclusion: '上市：以公允价值计量。', remark: null },
  {
    item_id: 'G9-disclosure-soe',
    remark: J({ soe_1: { currentAmount: 500, priorAmount: 450, noteText: '' }, soe_4: { currentAmount: 20, priorAmount: 0, noteText: '' } }),
    conclusion: null,
  },
  { item_id: 'G9-disclosure-soe-note', conclusion: '国企：期末按估值技术确定。', remark: null },
  { item_id: 'G9-1-adjudicated-amount', conclusion: '1500.5', remark: null },
  { item_id: 'G8-disclosure-listed', remark: J({ listed_1: { currentAmount: 999 } }), conclusion: null },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-g9', wpCode: 'G9' }
const LISTED = { ...CTX, variant: 'listed' as const, applicableStandards: ['listed_standalone'] }
const SOE = { ...CTX, variant: 'soe' as const, applicableStandards: ['soe_standalone'] }
const SYNC_URL = '/api/projects/p1/disclosure-notes/sync-from-workpaper'

const STUBS = {
  'el-button': { template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>', emits: ['click'] },
  'el-tag': { template: '<span><slot /></span>' },
  'el-alert': true, 'el-table': true, 'el-table-column': true, 'el-input-number': true,
  GtIndexChip: true, GtReviewTrigger: true, G9ImportExportDropdown: true,
}

/** Tab 路径：外壳按 `G9` 前缀给出的回复挂载真实 Tab，点「同步到附注」，取它发出的载荷 */
async function tabPayload(variant: 'soe' | 'listed', stds: string[]) {
  const debouncedSave = vi.fn()
  const allResponses = new Map(RESPONSES.filter((x) => x.item_id.startsWith('G9')).map((x) => [x.item_id, { ...x }]))
  h.apiPost.mockResolvedValue({ rows_synced: 5 })
  const wrapper = mount(variant === 'soe' ? G9TabDisclosureSOE : G9TabDisclosureListed, {
    props: { wpId: 'wp-g9', projectId: 'p1', allResponses, isReadonly: false, debouncedSave, applicableStandards: stds },
    global: { stubs: STUBS },
  })
  await flushPromises()
  const before = h.apiPost.mock.calls.length
  const button = wrapper.findAll('button').find((b) => b.text().includes('同步到附注'))
  expect(button, '找不到「同步到附注」按钮').toBeDefined()
  await button!.trigger('click')
  await flushPromises()
  expect(h.apiPost.mock.calls.length).toBe(before + 1)
  const [url, payload] = h.apiPost.mock.calls[before]
  expect(url).toBe(SYNC_URL)
  expect(debouncedSave).not.toHaveBeenCalled()
  wrapper.unmount()
  return payload
}

/** 窗口事件广播的探针（单独成函数以便精确推断类型） */
const spyDispatch = () => vi.spyOn(window, 'dispatchEvent')

describe('g9HeadlessProvider', () => {
  let warn: ReturnType<typeof vi.spyOn>
  let listen: ReturnType<typeof vi.spyOn>
  let dispatch: ReturnType<typeof spyDispatch>
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 5, push_kept: [{ table: '其他非流动金融资产' }] })
    warn = vi.spyOn(console, 'warn')
    listen = vi.spyOn(window, 'addEventListener')
    dispatch = spyDispatch()
  })
  afterEach(() => {
    warn.mockRestore()
    listen.mockRestore()
    dispatch.mockRestore()
  })

  it('上市：离屏载荷与真实 Tab 点「同步到附注」发出的逐字节相同，静默写 五、20、不写底稿', async () => {
    const out = await g9HeadlessProvider(LISTED)
    expect(out).toEqual({ sections: [{ section: '五、20', rows: 5, kept: 1 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-g9/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiPut).not.toHaveBeenCalled()
    expect(h.apiPost).not.toHaveBeenCalled()
    expect(h.post).toHaveBeenCalledTimes(1)
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe(SYNC_URL)
    expect(cfg).toMatchObject({ _silent: true })
    const rows = sent.sub_table_data['其他非流动金融资产'] as Array<Record<string, unknown>>
    expect(rows.map((r) => [r.row_key, r.end_balance, r.prior_balance])).toEqual([
      ['listed_1', 1200.5, 800], ['listed_2', 300, 0], ['listed_3', 0, 0], ['listed_4', 0, 0], [undefined, 1500.5, 800],
    ])
    expect(sent.sub_table_data._note_texts).toEqual([{ section: 'listed-disclosure-note', text: '上市：以公允价值计量。' }])
    expect(J(sent)).toBe(J(await tabPayload('listed', LISTED.applicableStandards)))
  })

  it('国企：离屏载荷与真实 Tab 逐字节相同，写 八、20（期末 / 期初公允价值）', async () => {
    const out = await g9HeadlessProvider(SOE)
    expect(out).toEqual({ sections: [{ section: '八、20', rows: 5, kept: 1 }] })
    const sent = h.post.mock.calls[0][1]
    const rows = sent.sub_table_data['其他非流动金融资产'] as Array<Record<string, unknown>>
    expect(rows[0]).toMatchObject({ row_key: 'soe_1', end_fair_value: 500, opening_fair_value: 450 })
    expect(rows.at(-1)).toMatchObject({ label: '合计', end_fair_value: 520, opening_fair_value: 450, is_total: true })
    expect(J(sent)).toBe(J(await tabPayload('soe', SOE.applicableStandards)))
  })

  it('离屏不挂生命周期钩子、不订阅审定事件、不广播说明；组件内照旧', async () => {
    await g9HeadlessProvider(SOE)
    expect(listen.mock.calls.some(([type]) => type === 'substantive:adjudicated')).toBe(false)
    expect(dispatch.mock.calls.some(([ev]) => (ev as Event).type === 'disclosure:note-text-updated')).toBe(false)
    expect(warn.mock.calls.some((args) => String(args[0]).includes('no active component instance'))).toBe(false)

    const w = mount(defineComponent({
      setup() {
        useG9Disclosure({
          variant: 'soe', wpId: ref('wp-g9'), allResponses: ref(new Map()), debouncedSave: () => {}, isReadonly: ref(false),
        })
        return () => null
      },
    }))
    expect(listen.mock.calls.some(([type]) => type === 'substantive:adjudicated')).toBe(true)
    expect(dispatch.mock.calls.some(([ev]) => (ev as Event).type === 'disclosure:note-text-updated')).toBe(true)
    w.unmount()
  })

  it('口径不适用回空，不发请求', async () => {
    expect(await g9HeadlessProvider({ ...SOE, applicableStandards: ['listed_standalone'] })).toEqual({ sections: [] })
    expect(await g9HeadlessProvider({ ...LISTED, applicableStandards: ['soe_standalone'] })).toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('静态接线：Tab 调共用快照函数，不再内联拼快照；钩子在组件实例守卫里', () => {
    const tab = readFileSync(resolve(__dirname, '../../g9-other-noncurrent-financial/core/G9TabDisclosureBase.vue'), 'utf-8')
    expect(tab).toContain(
      'buildG9SyncPayload(props.wpId, props.variant, props.applicableStandards, g9DisclosureSyncSnapshot(disc))',
    )
    expect(tab).not.toMatch(/rows:\s*disc\.dataRows\.value/)
    const composable = readFileSync(resolve(__dirname, '../useG9Disclosure.ts'), 'utf-8')
    expect(composable).toMatch(/if \(getCurrentInstance\(\)\) \{\s*onMounted\(/)
  })
})
