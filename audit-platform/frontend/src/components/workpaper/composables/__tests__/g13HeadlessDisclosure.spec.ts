/**
 * G13 公允价值变动收益披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * Tab 本就调 composable 的快照 `getSyncSnapshot()` + `buildG13SyncPayloads`；Tab 挂载时的回填（审定数 + G13-2 明细本期 + G13-1 上期，
 * 明细回填后保存）由 `pullLatestAdjudicated({ persist: false })` 只改内存地做一遍（明细回填抽成 `applyDetailPatch`，「从明细同步」=
 * 它 + 保存）。判据：①挂载真实 Tab（挂载回填后）点「同步到附注」发出的载荷 == 离屏载荷，且是回填后的值 ②离屏不写底稿、不广播、
 * 不订阅、不挂钩子，组件内照旧 ③只读 G13 条目、静默发出 ④口径不适用回空 ⑤静态接线。
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

import { g13HeadlessProvider } from '../g13HeadlessDisclosure'
import { useG13Disclosure } from '../useG13Disclosure'
import { G13_MAIN_SUBTABLE } from '../g13NoteSectionMap'
import G13TabDisclosureListed from '../../g13-fair-value-changes/G13TabDisclosureListed.vue'
import G13TabDisclosureSOE from '../../g13-fair-value-changes/G13TabDisclosureSOE.vue'
import type { ChecklistResponse } from '../useF1FormData'

const J = JSON.stringify
const RESPONSES: ChecklistResponse[] = [
  {
    item_id: 'G13-disclosure-listed',
    remark: J([
      { rowKey: 'trading_assets', label: '交易性金融资产', currentAmount: 1, priorAmount: 1, remark: '旧值' },
      { rowKey: 'other', label: '其他', currentAmount: 5, priorAmount: 4, remark: '' },
    ]),
    conclusion: null,
  },
  { item_id: 'G13-disclosure-listed-note', remark: '上市：公允价值变动主要来自股票投资。', conclusion: null },
  { item_id: 'G13-disclosure-soe', remark: J([{ rowKey: 'trading_assets', currentAmount: 9, priorAmount: 9, remark: '' }]), conclusion: null },
  {
    item_id: 'G13-detail-rows',
    remark: J([
      { belongAccount: 'G1', instrumentType: '股票', currentAudited: 300 },
      { belongAccount: 'G1', instrumentType: '指定FVTPL债券', currentAudited: 50 },
      { belongAccount: 'G9', instrumentType: '利率互换', currentAudited: -20 },
      { belongAccount: 'H3', instrumentType: '投资性房地产', currentAudited: 100 },
    ]),
    conclusion: null,
  },
  {
    item_id: 'G13-adj-prior',
    remark: J({
      trading_assets: { priorAudited: 200 },
      derivative_assets: { priorUnadjusted: 10, priorAdjustment: -2 },
      designated_fv_assets: { priorAudited: 30 },
    }),
    conclusion: null,
  },
  { item_id: 'G13-1-adjudicated-amount', conclusion: '430', remark: null },
  { item_id: 'G1-detail-rows', remark: J([{ belongAccount: 'G1', currentAudited: 999 }]), conclusion: null },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-g13', wpCode: 'G13' }
const LISTED = { ...CTX, variant: 'listed' as const, applicableStandards: ['listed_standalone'] }
const SOE = { ...CTX, variant: 'soe' as const, applicableStandards: ['soe_standalone'] }
const SYNC_URL = '/api/projects/p1/disclosure-notes/sync-from-workpaper'

const STUBS = {
  'el-button': { template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>', emits: ['click'] },
  'el-alert': true, 'el-table': true, 'el-table-column': true, 'el-input': true, 'el-card': true, 'el-switch': true,
  GtIndexChip: true, GtReviewTrigger: true, GCycleDisclosureExtras: true, WpAmountInput: true,
}

/**
 * Tab 路径：外壳按 `G13` 前缀给出的回复挂载真实 Tab（挂载即回填 + 保存），点「同步到附注」，取它发出的载荷。
 * 挂载回填会排 800ms 自动同步与 2s 说明广播，计时器用假的、取完载荷即清掉。
 */
async function tabPayload(variant: 'soe' | 'listed', stds: string[]) {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  try {
    const debouncedSave = vi.fn()
    const allResponses = new Map(RESPONSES.filter((x) => x.item_id.startsWith('G13')).map((x) => [x.item_id, { ...x }]))
    h.apiPost.mockResolvedValue({ rows_synced: 5 })
    const wrapper = mount(variant === 'soe' ? G13TabDisclosureSOE : G13TabDisclosureListed, {
      props: { wpId: 'wp-g13', projectId: 'p1', allResponses, isReadonly: false, debouncedSave, applicableStandards: stds },
      global: { stubs: STUBS },
    })
    await flushPromises()
    expect(debouncedSave).toHaveBeenCalledWith(`G13-disclosure-${variant}`, expect.anything())
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

const row = (sent: any, key: string) => (sent.sub_table_data[G13_MAIN_SUBTABLE] as Array<Record<string, unknown>>)
  .find((r) => r.row_key === key)

/** 窗口事件广播的探针（单独成函数以便精确推断类型） */
const spyDispatch = () => vi.spyOn(window, 'dispatchEvent')

describe('g13HeadlessProvider', () => {
  let warn: ReturnType<typeof vi.spyOn>
  let listen: ReturnType<typeof vi.spyOn>
  let dispatch: ReturnType<typeof spyDispatch>
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 5, push_kept: [] })
    warn = vi.spyOn(console, 'warn')
    listen = vi.spyOn(window, 'addEventListener')
    dispatch = spyDispatch()
  })
  afterEach(() => {
    warn.mockRestore()
    listen.mockRestore()
    dispatch.mockRestore()
  })

  it('上市：离屏 = 挂载回填后的 Tab 载荷（逐字节）；本期按 G13-2 明细、上期按 G13-1 回填；静默写 五、75、不写底稿', async () => {
    const out = await g13HeadlessProvider(LISTED)
    expect(out).toEqual({ sections: [{ section: '五、75', rows: 5, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-g13/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiPut).not.toHaveBeenCalled()
    expect(h.apiPost).not.toHaveBeenCalled()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe(SYNC_URL)
    expect(cfg).toMatchObject({ _silent: true })
    expect(row(sent, 'trading_assets')).toMatchObject({ current_amount: 350, prior_amount: 200, remark: '旧值' })
    expect(row(sent, 'designated_fv_assets')).toMatchObject({ current_amount: 50, prior_amount: 30, of_which: true })
    expect(row(sent, 'derivatives')).toMatchObject({ current_amount: -20, prior_amount: 8 })
    expect(row(sent, 'other')).toMatchObject({ current_amount: 5, prior_amount: 4 })
    expect(J(sent)).toBe(J(await tabPayload('listed', LISTED.applicableStandards)))
  })

  it('国企：离屏载荷与 Tab 逐字节相同，写 八、72（无说明时按回填行自动生成说明）', async () => {
    const out = await g13HeadlessProvider(SOE)
    expect(out).toEqual({ sections: [{ section: '八、72', rows: 5, kept: 0 }] })
    const sent = h.post.mock.calls[0][1]
    expect(row(sent, 'trading_assets')).toMatchObject({ current_amount: 350, prior_amount: 200 })
    expect(row(sent, 'derivative_assets')).toMatchObject({ current_amount: -20, prior_amount: 8 })
    expect(row(sent, 'investment_property')).toMatchObject({ current_amount: 100 })
    expect(sent.sub_table_data._note_texts?.[0]?.text).toBeTruthy()
    expect(J(sent)).toBe(J(await tabPayload('soe', SOE.applicableStandards)))
  })

  it('离屏不写底稿、不广播、不订阅、不挂钩子；组件内照旧', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    try {
      await g13HeadlessProvider(LISTED)
      expect(vi.getTimerCount()).toBe(0)
      expect(listen.mock.calls.some(([type]) => type === 'substantive:adjudicated')).toBe(false)
      expect(dispatch.mock.calls.some(([ev]) => (ev as Event).type === 'disclosure:note-text-updated')).toBe(false)
      expect(warn.mock.calls.some((args) => String(args[0]).includes('no active component instance'))).toBe(false)

      const save = vi.fn()
      const map = new Map(RESPONSES.filter((x) => x.item_id.startsWith('G13')).map((x) => [x.item_id, { ...x }]))
      const w = mount(defineComponent({
        setup() {
          useG13Disclosure({ variant: 'soe', allResponses: ref(map), wpId: ref('wp-g13'), isReadonly: ref(false), debouncedSave: save })
          return () => null
        },
      }))
      expect(listen.mock.calls.some(([type]) => type === 'substantive:adjudicated')).toBe(true)
      expect(dispatch.mock.calls.some(([ev]) => (ev as Event).type === 'disclosure:note-text-updated')).toBe(true)
      expect(save).toHaveBeenCalledWith('G13-disclosure-soe', expect.anything())
      w.unmount()
    } finally {
      vi.clearAllTimers()
      vi.useRealTimers()
    }
  })

  it('口径不适用回空，不发请求', async () => {
    expect(await g13HeadlessProvider({ ...SOE, applicableStandards: ['listed_standalone'] })).toEqual({ sections: [] })
    expect(await g13HeadlessProvider({ ...LISTED, applicableStandards: ['soe_standalone'] })).toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('静态接线：两个 Tab 调 composable 快照 + 同一 builder；「从明细同步」= 内存回填 + 保存；钩子在组件实例守卫里', () => {
    const dir = resolve(__dirname, '../../g13-fair-value-changes')
    for (const [file, variant] of [['G13TabDisclosureListed.vue', 'listed'], ['G13TabDisclosureSOE.vue', 'soe']] as const) {
      const src = readFileSync(resolve(dir, file), 'utf-8')
      expect(src, file).toMatch(new RegExp(
        `buildG13SyncPayloads\\(\\s*props\\.wpId,\\s*'${variant}',\\s*props\\.applicableStandards \\?\\? \\[\\],\\s*dis\\.getSyncSnapshot\\(\\),?\\s*\\)`,
      ))
    }
    const composable = readFileSync(resolve(__dirname, '../useG13Disclosure.ts'), 'utf-8')
    expect(composable).toMatch(/function syncFromDetail\(\): void \{\s*try \{\s*if \(applyDetailPatch\(\)\) persist\(\)/)
    expect(composable).toMatch(/if \(opts\.persist === false\) applyDetailPatch\(\)\s*else syncFromDetail\(\)/)
    expect(composable).toMatch(/if \(getCurrentInstance\(\)\) \{\s*onMounted\(\(\) => \{\s*pullLatestAdjudicated\(\)/)
  })
})
