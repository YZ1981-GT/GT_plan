/**
 * G14 信用减值损失披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * Tab 本就调 composable 的快照 `getSyncSnapshot()` + `buildG14SyncPayloads`；Tab 挂载时的回填（审定数 + G14-2 明细本期 + G14-1 上期，
 * 两步各自保存）由 `pullLatestAdjudicated({ persist: false })` 只改内存地做一遍（明细回填抽成 `applyDetailPatch`，「从明细同步」=
 * 它 + 保存）。判据：①挂载真实 Tab（挂载回填后）点「同步到附注」发出的载荷 == 离屏载荷，且是回填后的值（国企坏账 / 其他按来源合并）
 * ②离屏不写底稿、不广播、不订阅、不挂钩子，组件内照旧 ③只读 G14 条目、静默发出 ④口径不适用回空 ⑤静态接线。
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

import { g14HeadlessProvider } from '../g14HeadlessDisclosure'
import { useG14Disclosure } from '../useG14Disclosure'
import { G14_MAIN_SUBTABLE } from '../g14NoteSectionMap'
import G14TabDisclosureListed from '../../g14-credit-impairment-loss/G14TabDisclosureListed.vue'
import G14TabDisclosureSOE from '../../g14-credit-impairment-loss/G14TabDisclosureSOE.vue'
import type { ChecklistResponse } from '../useF1FormData'

const J = JSON.stringify
const RESPONSES: ChecklistResponse[] = [
  {
    item_id: 'G14-disclosure-listed',
    remark: J([
      { rowKey: 'ar', label: '应收账款坏账损失', currentAmount: 1, priorAmount: 1, remark: '旧值' },
      { rowKey: 'debt', label: '债权投资减值损失', currentAmount: 7, priorAmount: 6, remark: '' },
    ]),
    conclusion: null,
  },
  { item_id: 'G14-disclosure-listed-note', remark: '上市：信用减值损失主要为应收账款坏账。', conclusion: null },
  { item_id: 'G14-disclosure-soe', remark: J([{ rowKey: 'debt', currentAmount: 9, priorAmount: 8, remark: '' }]), conclusion: null },
  {
    item_id: 'G14-detail-rows',
    remark: J([
      { rowKey: 'ar', currentAudited: -500 },
      { rowKey: 'notes', currentAudited: -20 },
      { rowKey: 'guarantee', currentAudited: -30 },
      { rowKey: 'other', currentAudited: -10 },
    ]),
    conclusion: null,
  },
  {
    item_id: 'G14-adj-prior',
    remark: J({
      ar: { priorAudited: -300 },
      notes: { priorUnadjusted: -10, priorAdjustment: -5 },
      guarantee: { priorAudited: -1 },
      other: { priorAudited: -2 },
    }),
    conclusion: null,
  },
  { item_id: 'G14-1-adjudicated-amount', conclusion: '-570', remark: null },
  { item_id: 'G1-detail-rows', remark: J([{ rowKey: 'ar', currentAudited: 999 }]), conclusion: null },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-g14', wpCode: 'G14' }
const LISTED = { ...CTX, variant: 'listed' as const, applicableStandards: ['listed_standalone'] }
const SOE = { ...CTX, variant: 'soe' as const, applicableStandards: ['soe_standalone'] }
const SYNC_URL = '/api/projects/p1/disclosure-notes/sync-from-workpaper'

const STUBS = {
  'el-button': { template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>', emits: ['click'] },
  'el-alert': true, 'el-table': true, 'el-table-column': true, 'el-input': true, 'el-card': true, 'el-switch': true,
  GtIndexChip: true, GtReviewTrigger: true, GCycleDisclosureExtras: true, WpAmountInput: true,
}

/**
 * Tab 路径：外壳按 `G14` 前缀给出的回复挂载真实 Tab（挂载即回填 + 保存），点「同步到附注」，取它发出的载荷。
 * 挂载回填会排 800ms 自动同步与 2s 说明广播，计时器用假的、取完载荷即清掉。
 */
async function tabPayload(variant: 'soe' | 'listed', stds: string[]) {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  try {
    const debouncedSave = vi.fn()
    const allResponses = new Map(RESPONSES.filter((x) => x.item_id.startsWith('G14')).map((x) => [x.item_id, { ...x }]))
    h.apiPost.mockResolvedValue({ rows_synced: 6 })
    const wrapper = mount(variant === 'soe' ? G14TabDisclosureSOE : G14TabDisclosureListed, {
      props: { wpId: 'wp-g14', projectId: 'p1', allResponses, isReadonly: false, debouncedSave, applicableStandards: stds },
      global: { stubs: STUBS },
    })
    await flushPromises()
    expect(debouncedSave).toHaveBeenCalledWith(`G14-disclosure-${variant}`, expect.anything())
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

const row = (sent: any, variant: 'listed' | 'soe', key: string) =>
  (sent.sub_table_data[G14_MAIN_SUBTABLE[variant]] as Array<Record<string, unknown>>).find((r) => r.row_key === key)

/** 窗口事件广播的探针（单独成函数以便精确推断类型） */
const spyDispatch = () => vi.spyOn(window, 'dispatchEvent')

describe('g14HeadlessProvider', () => {
  let warn: ReturnType<typeof vi.spyOn>
  let listen: ReturnType<typeof vi.spyOn>
  let dispatch: ReturnType<typeof spyDispatch>
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 6, push_kept: [] })
    warn = vi.spyOn(console, 'warn')
    listen = vi.spyOn(window, 'addEventListener')
    dispatch = spyDispatch()
  })
  afterEach(() => {
    warn.mockRestore()
    listen.mockRestore()
    dispatch.mockRestore()
  })

  it('上市：离屏 = 挂载回填后的 Tab 载荷（逐字节）；本期按 G14-2、上期按 G14-1；静默写 五、76、不写底稿', async () => {
    const out = await g14HeadlessProvider(LISTED)
    expect(out).toEqual({ sections: [{ section: '五、76', rows: 6, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-g14/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiPut).not.toHaveBeenCalled()
    expect(h.apiPost).not.toHaveBeenCalled()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe(SYNC_URL)
    expect(cfg).toMatchObject({ _silent: true })
    expect(row(sent, 'listed', 'ar')).toMatchObject({ current_amount: -500, prior_amount: -300, remark: '旧值' })
    expect(row(sent, 'listed', 'notes')).toMatchObject({ current_amount: -20, prior_amount: -15 })
    expect(row(sent, 'listed', 'guarantee')).toMatchObject({ current_amount: -30, prior_amount: -1 })
    expect(row(sent, 'listed', 'debt')).toMatchObject({ current_amount: 7, prior_amount: 6 })
    expect(J(sent)).toBe(J(await tabPayload('listed', LISTED.applicableStandards)))
  })

  it('国企：坏账损失 / 其他按来源合并回填，离屏载荷与 Tab 逐字节相同，写 八、73', async () => {
    const out = await g14HeadlessProvider(SOE)
    expect(out).toEqual({ sections: [{ section: '八、73', rows: 6, kept: 0 }] })
    const sent = h.post.mock.calls[0][1]
    expect(row(sent, 'soe', 'bad_debt')).toMatchObject({ current_amount: -520, prior_amount: -315 })
    expect(row(sent, 'soe', 'other')).toMatchObject({ current_amount: -40, prior_amount: -3 })
    expect(row(sent, 'soe', 'debt')).toMatchObject({ current_amount: 9, prior_amount: 8 })
    expect(J(sent)).toBe(J(await tabPayload('soe', SOE.applicableStandards)))
  })

  it('离屏不写底稿、不广播、不订阅、不挂钩子；组件内照旧', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    try {
      await g14HeadlessProvider(LISTED)
      expect(vi.getTimerCount()).toBe(0)
      expect(listen.mock.calls.some(([type]) => type === 'substantive:adjudicated' || type === 'g14:detail-updated')).toBe(false)
      expect(dispatch.mock.calls.some(([ev]) => (ev as Event).type === 'disclosure:note-text-updated')).toBe(false)
      expect(warn.mock.calls.some((args) => String(args[0]).includes('no active component instance'))).toBe(false)

      const save = vi.fn()
      const map = new Map(RESPONSES.filter((x) => x.item_id.startsWith('G14')).map((x) => [x.item_id, { ...x }]))
      const w = mount(defineComponent({
        setup() {
          useG14Disclosure({ variant: 'soe', allResponses: ref(map), wpId: ref('wp-g14'), isReadonly: ref(false), debouncedSave: save })
          return () => null
        },
      }))
      expect(listen.mock.calls.some(([type]) => type === 'g14:detail-updated')).toBe(true)
      expect(dispatch.mock.calls.some(([ev]) => (ev as Event).type === 'disclosure:note-text-updated')).toBe(true)
      expect(save).toHaveBeenCalledWith('G14-disclosure-soe', expect.anything())
      w.unmount()
    } finally {
      vi.clearAllTimers()
      vi.useRealTimers()
    }
  })

  it('口径不适用回空，不发请求', async () => {
    expect(await g14HeadlessProvider({ ...SOE, applicableStandards: ['listed_standalone'] })).toEqual({ sections: [] })
    expect(await g14HeadlessProvider({ ...LISTED, applicableStandards: ['soe_standalone'] })).toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('静态接线：两个 Tab 调 composable 快照 + 同一 builder；「从明细同步」= 内存回填 + 保存；钩子在组件实例守卫里', () => {
    const dir = resolve(__dirname, '../../g14-credit-impairment-loss')
    for (const [file, variant] of [['G14TabDisclosureListed.vue', 'listed'], ['G14TabDisclosureSOE.vue', 'soe']] as const) {
      const src = readFileSync(resolve(dir, file), 'utf-8')
      expect(src, file).toMatch(new RegExp(
        `buildG14SyncPayloads\\(\\s*props\\.wpId,\\s*'${variant}',\\s*props\\.applicableStandards \\?\\? \\[\\],\\s*dis\\.getSyncSnapshot\\(\\),?\\s*\\)`,
      ))
    }
    const composable = readFileSync(resolve(__dirname, '../useG14Disclosure.ts'), 'utf-8')
    expect(composable).toMatch(/function syncFromDetail\(\): void \{\s*try \{\s*if \(applyDetailPatch\(\)\) persist\(\)/)
    expect(composable).toMatch(/if \(opts\.persist === false\) applyDetailPatch\(\)\s*else syncFromDetail\(\)/)
    expect(composable).toContain('if (opts.persist !== false) persist()')
    expect(composable).toMatch(/if \(getCurrentInstance\(\)\) \{\s*onMounted\(\(\) => \{\s*pullLatestAdjudicated\(\)/)
  })
})
