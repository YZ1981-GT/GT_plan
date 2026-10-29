/**
 * G12 净敞口套期收益披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 快照原在两个 Tab 的 `syncToDisclosureNotes` 里内联，抽成 `g12DisclosureSyncSnapshot`；Tab 挂载时的回填（G12-1 审定 / G12-2 明细
 * 按存在的来源 patch 各行，仅真实变化且可写时保存）抽出只改内存的一步 `applyAdjudicationPatch`，离屏在 prepare 里调它。判据：
 * ①挂载真实 Tab（挂载回填后）点「同步到附注」发出的载荷 == 离屏载荷 ②离屏不写底稿、不广播、不订阅窗口事件
 * ③缺失/明确 0/只读/无变化持久化门 ④口径不适用回空 ⑤静态接线。
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

import { g12HeadlessProvider } from '../g12HeadlessDisclosure'
import { useG12Disclosure } from '../useG12Disclosure'
import { G12_MAIN_SUBTABLE } from '../g12DisclosureSyncPayload'
import G12TabDisclosureListed from '../../g12-net-hedge-gains/core/G12TabDisclosureListed.vue'
import G12TabDisclosureSOE from '../../g12-net-hedge-gains/core/G12TabDisclosureSOE.vue'
import type { ChecklistResponse } from '../useF1FormData'

const J = JSON.stringify
const RESPONSES: ChecklistResponse[] = [
  { item_id: 'G12-disclosure-listed', remark: J([{ rowKey: 'net_hedge', label: '净敞口套期收益', currentAmount: 999, priorAmount: 1, remark: '' }]), conclusion: null },
  { item_id: 'G12-disclosure-listed-note', remark: '上市：净敞口套期收益来自外汇敞口。', conclusion: null },
  {
    item_id: 'G12-disclosure-soe',
    remark: J([
      { rowKey: 'hedged_fv_to_pl', currentAmount: 7, priorAmount: 7, remark: '' },
      { rowKey: 'cf_reserve_to_pl', currentAmount: 7, priorAmount: 7, remark: '' },
    ]),
    conclusion: null,
  },
  { item_id: 'G12-disclosure-soe-note', remark: '国企：两项来源已核对。', conclusion: null },
  { item_id: 'G12-1-adjudicated-amount', conclusion: '1500', remark: null },
  {
    item_id: 'G12-adj-prior',
    remark: J({ net_hedge: { priorAudited: 800 }, item_fv: { priorUnadjusted: 100, priorAdjustment: 20 }, cf_reserve: { priorAudited: 30 } }),
    conclusion: null,
  },
  {
    item_id: 'G12-hedge-detail-rows',
    remark: J([
      { rowKind: 'fv_allocation', instrumentFvCumulative: 100, salesPortion: 60, purchasePortion: 40 },
      { rowKind: 'amortization', hedgeAdjAmortization: 15 },
    ]),
    conclusion: null,
  },
  { item_id: 'G1-disclosure-listed', remark: J([{ rowKey: 'net_hedge', currentAmount: 5 }]), conclusion: null },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-g12', wpCode: 'G12' }
const LISTED = { ...CTX, variant: 'listed' as const, applicableStandards: ['listed_standalone'] }
const SOE = { ...CTX, variant: 'soe' as const, applicableStandards: ['soe_standalone'] }
const SYNC_URL = '/api/projects/p1/disclosure-notes/sync-from-workpaper'

const STUBS = {
  'el-button': { template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>', emits: ['click'] },
  'el-alert': true, 'el-table': true, 'el-table-column': true, 'el-input': true, 'el-card': true,
  GtReviewTrigger: true, GCycleDisclosureExtras: true, GCycleGuideStrip: true, G12CoreWorkflowChecklist: true, WpAmountInput: true,
}

/**
 * Tab 路径：外壳按 `G12` 前缀给出的回复挂载真实 Tab（挂载即回填 + 保存），点「同步到附注」，取它发出的载荷。
 * 回填改了行会排一次 800ms 的自动同步，计时器用假的、取完载荷即清掉。
 */
async function tabPayload(variant: 'soe' | 'listed', stds: string[]) {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  try {
    const debouncedSave = vi.fn()
    const allResponses = new Map(RESPONSES.filter((x) => x.item_id.startsWith('G12')).map((x) => [x.item_id, { ...x }]))
    h.apiPost.mockResolvedValue({ rows_synced: 3 })
    const wrapper = mount(variant === 'soe' ? G12TabDisclosureSOE : G12TabDisclosureListed, {
      props: { wpId: 'wp-g12', projectId: 'p1', allResponses, isReadonly: false, debouncedSave, applicableStandards: stds },
      global: { stubs: STUBS },
    })
    await flushPromises()
    expect(debouncedSave).toHaveBeenCalledWith(`G12-disclosure-${variant}`, expect.anything())
    const before = h.apiPost.mock.calls.length
    const button = wrapper.findAll('button').find((b) => b.text().includes('同步到附注'))
    expect(button, '找不到「同步到附注」按钮').toBeDefined()
    await button!.trigger('click')
    await flushPromises()
    const calls = h.apiPost.mock.calls.slice(before)
    expect(calls.length).toBe(1)
    expect(calls[0][0]).toBe(SYNC_URL)
    wrapper.unmount()
    return calls[0][1]
  } finally {
    vi.clearAllTimers()
    vi.useRealTimers()
  }
}

/** 窗口事件广播的探针（单独成函数以便精确推断类型） */
const spyDispatch = () => vi.spyOn(window, 'dispatchEvent')

function storedG12Map(extra: ChecklistResponse[] = []): Map<string, ChecklistResponse> {
  const responses: ChecklistResponse[] = [
    {
      item_id: 'G12-disclosure-listed',
      remark: J([{ rowKey: 'net_hedge', label: '净敞口套期收益', currentAmount: 91, priorAmount: 81, remark: '已存值' }]),
      conclusion: null,
    },
    { item_id: 'G12-disclosure-listed-note', remark: '已存说明', conclusion: null },
    ...extra,
  ]
  return new Map(responses.map((response) => [response.item_id, response]))
}

function mountG12Disclosure(
  allResponses: Map<string, ChecklistResponse>,
  isReadonly = false,
) {
  const save = vi.fn()
  let disclosure!: ReturnType<typeof useG12Disclosure>
  const wrapper = mount(defineComponent({
    setup() {
      disclosure = useG12Disclosure({
        variant: 'listed',
        allResponses: ref(allResponses),
        wpId: ref('wp-g12'),
        isReadonly: ref(isReadonly),
        debouncedSave: save,
      })
      return () => null
    },
  }))
  return { disclosure, save, wrapper }
}

function savedG12Rows(save: ReturnType<typeof vi.fn>) {
  const rowCalls = save.mock.calls.filter(([itemId]) => itemId === 'G12-disclosure-listed')
  return {
    rowCalls,
    rows: rowCalls.length ? JSON.parse(String(rowCalls[0][1]?.remark)) : [],
  }
}

describe('g12HeadlessProvider', () => {
  let warn: ReturnType<typeof vi.spyOn>
  let listen: ReturnType<typeof vi.spyOn>
  let dispatch: ReturnType<typeof spyDispatch>
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 3, push_kept: [] })
    warn = vi.spyOn(console, 'warn')
    listen = vi.spyOn(window, 'addEventListener')
    dispatch = spyDispatch()
  })
  afterEach(() => {
    warn.mockRestore()
    listen.mockRestore()
    dispatch.mockRestore()
  })

  it('上市：离屏 = 挂载回填后的 Tab 载荷（逐字节），已存旧值被 G12-1 审定数覆盖；静默写 五、70、不写底稿', async () => {
    const out = await g12HeadlessProvider(LISTED)
    expect(out).toEqual({ sections: [{ section: '五、70', rows: 3, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-g12/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiPut).not.toHaveBeenCalled()
    expect(h.apiPost).not.toHaveBeenCalled()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe(SYNC_URL)
    expect(cfg).toMatchObject({ _silent: true })
    expect(sent.sub_table_data[G12_MAIN_SUBTABLE]).toEqual([
      { label: '净敞口套期收益', row_key: 'net_hedge', current_amount: 1500, prior_amount: 800, row_type: 'data' },
      { label: '合计', current_amount: 1500, prior_amount: 800, is_total: true, row_type: 'total' },
    ])
    expect(sent.sub_table_data._note_texts).toEqual([{ section: 'listed-disclosure-note', text: '上市：净敞口套期收益来自外汇敞口。' }])
    expect(J(sent)).toBe(J(await tabPayload('listed', LISTED.applicableStandards)))
  })

  it('国企：两项来源由 G12-2 明细 / 上期审定回填，离屏载荷与 Tab 逐字节相同，写 八、71', async () => {
    const out = await g12HeadlessProvider(SOE)
    expect(out).toEqual({ sections: [{ section: '八、71', rows: 3, kept: 0 }] })
    const sent = h.post.mock.calls[0][1]
    const rows = sent.sub_table_data[G12_MAIN_SUBTABLE] as Array<Record<string, unknown>>
    expect(rows.map((r) => [r.row_key, r.current_amount, r.prior_amount])).toEqual([
      ['hedged_fv_to_pl', 40, 120], ['cf_reserve_to_pl', 15, 30], [undefined, 55, 150],
    ])
    expect(J(sent)).toBe(J(await tabPayload('soe', SOE.applicableStandards)))
  })

  it('离屏不写底稿、不广播、不订阅、不挂钩子；组件挂载无来源时保留非零已存值且不保存', async () => {
    await g12HeadlessProvider(LISTED)
    expect(listen.mock.calls.some(([type]) => type === 'substantive:adjudicated' || type === 'g12:hedge-detail-updated')).toBe(false)
    expect(dispatch.mock.calls.some(([ev]) => (ev as Event).type === 'disclosure:note-text-updated')).toBe(false)
    expect(warn.mock.calls.some((args) => String(args[0]).includes('no active component instance'))).toBe(false)

    const { disclosure, save, wrapper } = mountG12Disclosure(storedG12Map())
    expect(listen.mock.calls.some(([type]) => type === 'g12:hedge-detail-updated')).toBe(true)
    expect(disclosure.rows.value[0]).toMatchObject({ currentAmount: 91, priorAmount: 81, remark: '已存值' })
    expect(save).not.toHaveBeenCalled()
    expect(dispatch.mock.calls.some(([ev]) => (ev as Event).type === 'disclosure:note-text-updated')).toBe(false)
    wrapper.unmount()
  })

  it('挂载时明确 0 会覆盖非零已存值，并只持久化一次最终行状态', () => {
    const map = storedG12Map([
      { item_id: 'G12-1-adjudicated-amount', conclusion: '0', remark: null },
      { item_id: 'G12-adj-prior', conclusion: null, remark: J({ net_hedge: { priorAudited: 0 } }) },
    ])
    const { disclosure, save, wrapper } = mountG12Disclosure(map)
    expect(disclosure.rows.value[0]).toMatchObject({ currentAmount: 0, priorAmount: 0 })
    const saved = savedG12Rows(save)
    expect(saved.rowCalls).toHaveLength(1)
    expect(saved.rows[0]).toMatchObject({ currentAmount: 0, priorAmount: 0 })
    expect(save.mock.calls.filter(([itemId]) => itemId === 'G12-disclosure-listed-note')).toHaveLength(1)
    wrapper.unmount()
  })

  it('只读挂载仍应用来源 patch 供回显，但不持久化', () => {
    const map = storedG12Map([
      { item_id: 'G12-1-adjudicated-amount', conclusion: '123', remark: null },
      { item_id: 'G12-adj-prior', conclusion: null, remark: J({ net_hedge: { priorAudited: 45 } }) },
    ])
    const { disclosure, save, wrapper } = mountG12Disclosure(map, true)
    expect(disclosure.rows.value[0]).toMatchObject({ currentAmount: 123, priorAmount: 45 })
    expect(save).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('来源值与非零已存值相同时不持久化', () => {
    const map = storedG12Map([
      { item_id: 'G12-1-adjudicated-amount', conclusion: '91', remark: null },
      { item_id: 'G12-adj-prior', conclusion: null, remark: J({ net_hedge: { priorAudited: 81 } }) },
    ])
    const { disclosure, save, wrapper } = mountG12Disclosure(map)
    expect(disclosure.rows.value[0]).toMatchObject({ currentAmount: 91, priorAmount: 81 })
    expect(save).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('口径不适用回空，不发请求', async () => {
    expect(await g12HeadlessProvider({ ...SOE, applicableStandards: ['listed_standalone'] })).toEqual({ sections: [] })
    expect(await g12HeadlessProvider({ ...LISTED, applicableStandards: ['soe_standalone'] })).toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('静态接线：两个 Tab 调共用快照函数；挂载回填走结构化 patch 与三条件保存门', () => {
    const dir = resolve(__dirname, '../../g12-net-hedge-gains/core')
    for (const [file, variant] of [['G12TabDisclosureListed.vue', 'listed'], ['G12TabDisclosureSOE.vue', 'soe']] as const) {
      const src = readFileSync(resolve(dir, file), 'utf-8')
      expect(src, file).toContain(`buildG12SyncPayload(props.wpId, '${variant}', props.applicableStandards, g12DisclosureSyncSnapshot(dis))`)
      expect(src, file).not.toMatch(/rows:\s*dis\.rows\.value/)
    }
    const composable = readFileSync(resolve(__dirname, '../useG12Disclosure.ts'), 'utf-8').replace(/\r?\n\r?\n/g, '\n')
    expect(composable).toMatch(/if \(getCurrentInstance\(\)\) \{\s*onMounted\(\(\) => \{\s*pullLatestAdjudicated\(\)/)
    expect(composable).toContain('result.sourceFound && result.changed && !opts.isReadonly.value')
    expect(composable).not.toMatch(/const n = applyAdjudicationPatch\(\)\s*persist\(\)/)
  })
})
