/**
 * G8 其他权益工具投资披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 逐项目明细行与快照原在 `G8TabDisclosureBase` 里内联（`syncDetailRows` computed + 同步函数拼快照），抽成
 * `g8SyncDetailRows` / `g8DisclosureSyncSnapshot` 后 Tab 与离屏同步共用。判据：①挂载真实 Tab（上市 / 国企）、点「同步到附注」
 * 发出的载荷 == 离屏载荷，夹具有余额 / 明细 / 指定原因 / 说明 ②离屏不挂生命周期钩子、不订阅审定事件、不广播说明，组件内照旧
 * ③只读 G8 条目、静默发出、不写底稿、不走「从 G8-2 带入」④口径不适用回空 ⑤静态接线。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

const h = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), put: vi.fn(), apiGet: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn(), confirm: vi.fn(),
}))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet, post: h.apiPost, put: h.apiPut } }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(() => Promise.resolve()) }),
  useRoute: () => ({ params: {}, query: {}, path: '/', name: 'wp' }),
}))
vi.mock('element-plus', async () => ({
  ...(await vi.importActual<Record<string, unknown>>('element-plus')),
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: h.confirm },
}))

import { g8HeadlessProvider } from '../g8HeadlessDisclosure'
import { useG8Disclosure } from '../useG8Disclosure'
import { G8_DETAIL_SUBTABLE, G8_MAIN_SUBTABLE } from '../g8NoteSectionMap'
import G8TabDisclosureBase from '../../g8-other-equity-instruments/core/G8TabDisclosureBase.vue'
import type { ChecklistResponse } from '../useF1FormData'

const J = JSON.stringify
const RESPONSES: ChecklistResponse[] = [
  {
    item_id: 'G8-disclosure-listed',
    remark: J({
      v: 2,
      balanceRows: [{ label: '甲公司股权', closing: 1000, prior: 900 }, { label: '乙公司股权', closing: 200.25, prior: 0 }],
      designationText: '甲公司股权出于战略目的长期持有，指定为 FVOCI。',
      ociRows: [
        { label: '甲公司股权', ociPeriod: 100, ociCumulative: 300, dividend: 20, transferToRE: 0, derecogReason: '' },
        { label: '丙公司股权', ociPeriod: 0, ociCumulative: 0, dividend: 0, transferToRE: 50, derecogReason: '本期处置' },
      ],
    }),
    conclusion: null,
  },
  { item_id: 'G8-disclosure-listed-note', conclusion: '上市：公允价值第三层次。', remark: null },
  {
    item_id: 'G8-disclosure-soe',
    remark: J({
      v: 2,
      balanceRows: [{ label: '丁公司股权', closing: 800, prior: 750 }],
      designationText: '非交易性权益工具。',
      detailRows: [
        { label: '丁公司股权', dividend: 12, ociPeriod: 50, ociCumulative: 80, transferAmt: 0, transferReason: '' },
        { label: '戊公司股权', dividend: 0, ociPeriod: -5, ociCumulative: 0, transferAmt: 30, transferReason: '处置转出' },
      ],
    }),
    conclusion: null,
  },
  { item_id: 'G8-disclosure-soe-note', conclusion: '国企：按估值技术确定。', remark: null },
  { item_id: 'G8-1-adjudicated-amount', conclusion: '1200.25', remark: null },
  { item_id: 'G9-disclosure-listed', remark: J({ listed_1: { currentAmount: 999 } }), conclusion: null },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-g8', wpCode: 'G8' }
const LISTED = { ...CTX, variant: 'listed' as const, applicableStandards: ['listed_standalone'] }
const SOE = { ...CTX, variant: 'soe' as const, applicableStandards: ['soe_standalone'] }
const SYNC_URL = '/api/projects/p1/disclosure-notes/sync-from-workpaper'

const STUBS = {
  'el-button': { template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>', emits: ['click'] },
  'el-alert': true, 'el-table': true, 'el-table-column': true, 'el-input': true, 'el-input-number': true,
  GtReviewTrigger: true, WpAmountInput: true,
}

/** Tab 路径：外壳按 `G8` 前缀给出的回复挂载真实 Tab，点「同步到附注」，取它发出的载荷 */
async function tabPayload(variant: 'soe' | 'listed', stds: string[]) {
  const debouncedSave = vi.fn()
  const allResponses = new Map(RESPONSES.filter((x) => x.item_id.startsWith('G8')).map((x) => [x.item_id, { ...x }]))
  h.apiPost.mockResolvedValue({ rows_synced: 7 })
  const wrapper = mount(G8TabDisclosureBase, {
    props: { variant, wpId: 'wp-g8', projectId: 'p1', allResponses, isReadonly: false, debouncedSave, applicableStandards: stds },
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

describe('g8HeadlessProvider', () => {
  let warn: ReturnType<typeof vi.spyOn>
  let listen: ReturnType<typeof vi.spyOn>
  let dispatch: ReturnType<typeof spyDispatch>
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 7, push_kept: [] })
    warn = vi.spyOn(console, 'warn')
    listen = vi.spyOn(window, 'addEventListener')
    dispatch = spyDispatch()
  })
  afterEach(() => {
    warn.mockRestore()
    listen.mockRestore()
    dispatch.mockRestore()
  })

  it('上市：离屏载荷与真实 Tab 点「同步到附注」发出的逐字节相同，静默写 五、19、不写底稿', async () => {
    const out = await g8HeadlessProvider(LISTED)
    expect(out).toEqual({ sections: [{ section: '五、19', rows: 7, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-g8/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiPut).not.toHaveBeenCalled()
    expect(h.apiPost).not.toHaveBeenCalled()
    expect(h.confirm).not.toHaveBeenCalled()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe(SYNC_URL)
    expect(cfg).toMatchObject({ _silent: true })
    const data = sent.sub_table_data
    expect(data[G8_MAIN_SUBTABLE.listed].map((r: any) => [r.label, r.end_balance, r.prior_balance])).toEqual([
      ['甲公司股权', 1000, 900], ['乙公司股权', 200.25, 0], ['合计', 1200.25, 900],
    ])
    expect(data[G8_DETAIL_SUBTABLE].map((r: any) => [r.label, r.oci_current, r.derecognition_to_re, r.derecognition_reason])).toEqual([
      ['甲公司股权', 100, 0, ''], ['丙公司股权', 0, 50, '本期处置'],
    ])
    expect(data._note_texts).toEqual([
      { section: 'listed-designation-reason', text: '甲公司股权出于战略目的长期持有，指定为 FVOCI。' },
      { section: 'listed-disclosure-note', text: '上市：公允价值第三层次。' },
    ])
    expect(J(sent)).toBe(J(await tabPayload('listed', LISTED.applicableStandards)))
  })

  it('国企：离屏载荷与真实 Tab 逐字节相同，写 八、19（期末明细表带合计行）', async () => {
    const out = await g8HeadlessProvider(SOE)
    expect(out).toEqual({ sections: [{ section: '八、19', rows: 7, kept: 0 }] })
    const sent = h.post.mock.calls[0][1]
    const detail = sent.sub_table_data[G8_DETAIL_SUBTABLE] as Array<Record<string, unknown>>
    expect(detail.map((r) => [r.label, r.dividend_income, r.oci_to_re, r.oci_to_re_reason])).toEqual([
      ['丁公司股权', 12, 0, ''], ['戊公司股权', 0, 30, '处置转出'], ['合计', 12, 30, ''],
    ])
    expect(sent.sub_table_data[G8_MAIN_SUBTABLE.soe][0]).toMatchObject({ label: '丁公司股权', end_balance: 800, opening_balance: 750 })
    expect(J(sent)).toBe(J(await tabPayload('soe', SOE.applicableStandards)))
  })

  it('离屏不挂生命周期钩子、不订阅审定事件、不广播说明；组件内照旧', async () => {
    await g8HeadlessProvider(LISTED)
    expect(listen.mock.calls.some(([type]) => type === 'substantive:adjudicated')).toBe(false)
    expect(dispatch.mock.calls.some(([ev]) => (ev as Event).type === 'disclosure:note-text-updated')).toBe(false)
    expect(warn.mock.calls.some((args) => String(args[0]).includes('no active component instance'))).toBe(false)

    const w = mount(defineComponent({
      setup() {
        useG8Disclosure({
          variant: 'listed', wpId: ref('wp-g8'), allResponses: ref(new Map()), debouncedSave: () => {}, isReadonly: ref(false),
        })
        return () => null
      },
    }))
    expect(listen.mock.calls.some(([type]) => type === 'substantive:adjudicated')).toBe(true)
    expect(dispatch.mock.calls.some(([ev]) => (ev as Event).type === 'disclosure:note-text-updated')).toBe(true)
    w.unmount()
  })

  it('口径不适用回空，不发请求', async () => {
    expect(await g8HeadlessProvider({ ...SOE, applicableStandards: ['listed_standalone'] })).toEqual({ sections: [] })
    expect(await g8HeadlessProvider({ ...LISTED, applicableStandards: ['soe_standalone'] })).toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('静态接线：Tab 调共用明细行 / 快照函数，不再内联；钩子在组件实例守卫里', () => {
    const tab = readFileSync(resolve(__dirname, '../../g8-other-equity-instruments/core/G8TabDisclosureBase.vue'), 'utf-8')
    expect(tab).toContain('const syncDetailRows = computed(() => g8SyncDetailRows(props.variant, disc))')
    expect(tab).toContain(
      'buildG8SyncPayload(props.wpId, props.variant, props.applicableStandards, g8DisclosureSyncSnapshot(props.variant, disc))',
    )
    expect(tab).not.toMatch(/balanceRows:\s*disc\.store\.value\.balanceRows|\.filter\(\(r: any\) => !r\.isTotal\)/)
    expect(tab).toMatch(/watch\(\s*\[\(\) => disc\.store\.value\.balanceRows, syncDetailRows, disc\.designationText, disc\.noteText\]/)
    const composable = readFileSync(resolve(__dirname, '../useG8Disclosure.ts'), 'utf-8')
    expect(composable).toMatch(/if \(getCurrentInstance\(\)\) \{\s*onMounted\(/)
  })
})
