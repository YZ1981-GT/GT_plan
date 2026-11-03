/**
 * J2 长期应付职工薪酬披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 两个 Tab 内联的表单状态 / 挂载读回（含国企动态行还原、按 J2-1 审定表带数）/ 同步请求体抽成 `j2DisclosureTabState` 后
 * Tab 与离屏同步共用。判据：①挂载真实 Tab（同一批 J2- 回复），调它的「同步到附注」截下 api.post 请求体，与离屏发出的
 * 逐字节相同（上市 五、49 + 净负债期末为负时 五、17；国企 八、54）②只 GET 本底稿回复、不 PUT ③静态接线。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { computed } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: h.apiPost, put: h.apiPut } }))
vi.mock('@/composables/useAuditContext', () => ({
  useAuditContext: () => ({ projectId: computed(() => 'p1'), year: computed(() => 2025) }),
}))
vi.mock('element-plus', async () => ({
  ...(await vi.importActual<Record<string, unknown>>('element-plus')),
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
  ElMessageBox: { prompt: vi.fn(), confirm: vi.fn() },
}))

import { j2HeadlessProvider } from '../j2HeadlessDisclosure'
import { J2_LISTED_SUBTABLE, J2_SOE_SUBTABLE } from '../j2DisclosureSyncPayload'
import J2TabDisclosureListed from '../../j2/J2TabDisclosureListed.vue'
import J2TabDisclosureSoe from '../../j2/J2TabDisclosureSoe.vue'

const J = JSON.stringify
type Resp = { item_id: string; remark: string | null; conclusion: string | null }
const resp = (item_id: string, value: unknown): Resp =>
  ({ item_id, conclusion: null, remark: typeof value === 'string' ? value : J(value) })

const zeroMv = { dboCur: 0, dboPrior: 0, assetCur: 0, assetPrior: 0, netCur: 0, netPrior: 0 }
const RESPONSES: Resp[] = [
  resp('J2-listed-summary', [
    { key: 'dbp_net', label: '设定受益计划净负债', end: 1000, begin: 800 },
    { key: 'termination', label: '辞退福利', end: 200, begin: 100 },
  ]),
  resp('J2-listed-dbo', [{ key: 'begin', cur: 900, prior: 850 }, { key: 'pl_service', cur: 60, prior: 55 }, { key: 'end', cur: 960, prior: 900 }]),
  resp('J2-listed-netliab', [
    { key: 'begin', cur: -50, prior: 0 }, { key: 'pl', cur: -20, prior: 0 }, { key: 'oci', cur: 5, prior: 0 },
    { key: 'other', cur: -10, prior: 0 }, { key: 'end', cur: -75, prior: 0 },
  ]),
  resp('J2-listed-assumptions', [{ key: 'discount', end: 0.031, begin: 0.035 }]),
  resp('J2-listed-note-dbp', '设定受益计划为补充退休福利'),
  resp('J2-soe-change', [
    { key: 'begin', ...zeroMv, dboCur: 500, netCur: 500 },
    { key: 'pl_service', ...zeroMv, dboCur: 30, netCur: 30 },
    { key: 'other_3', label: '合同变更', indent: 1, kind: 'leaf', ...zeroMv, dboCur: 12, netCur: 12 },
  ]),
  resp('J2-soe-assets', [
    { key: 'cash', end: 40, begin: 30 },
    { key: 'equity_3', label: '银行理财产品', indent: 1, end: 15, begin: 0 },
  ]),
  resp('J2-soe-note-sensitivity', '国企敏感性说明'),
  resp('J2-1-main', [
    { key: 'dbp', beginUnadj: 300, beginAje: 20, endUnadj: 400, endAje: 0 },
    { key: 'termination', beginUnadj: 50, beginAje: 0, endUnadj: 60, endAje: 0 },
  ]),
  resp('J2A-proc-1', '程序表（不是 J2- 前缀）'),
  resp('J3-1-rows', '[]'),
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-j2', wpCode: 'J2' }
const LISTED = { ...CTX, variant: 'listed' as const, applicableStandards: ['listed_standalone'] }
const SOE = { ...CTX, variant: 'soe' as const, applicableStandards: ['soe_standalone'] }
const STUBS = {
  'el-alert': true, 'el-table': true, 'el-table-column': true, 'el-input': true, 'el-button': true, 'el-tag': true,
  'el-tooltip': true, 'el-icon': true, GtIndexChip: true, WpAmountInput: true, WpFourTableSourcePanel: true,
  J2DisclosureConsistencyPanel: true,
}

/** Tab 路径：挂载真实 Tab（宿主回复 = 同一批 J2- 回复），调它的「同步到附注」，取它经 api.post 发出的全部请求体 */
async function tabRequests(variant: 'listed' | 'soe', list: Resp[] = RESPONSES): Promise<any[]> {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  try {
    const allResponses = new Map(list.filter((x) => x.item_id.startsWith('J2-')).map((x) => [x.item_id, { ...x }]))
    const wrapper = mount(variant === 'listed' ? J2TabDisclosureListed : J2TabDisclosureSoe, {
      props: { wpId: 'wp-j2', projectId: 'p1', allResponses, isReadonly: false, saveImmediate: vi.fn() },
      global: { stubs: STUBS },
    })
    await flushPromises()
    h.apiPost.mockClear()
    await (wrapper.vm as any).$.setupState.syncToDisclosureNotes()
    await flushPromises()
    const calls = h.apiPost.mock.calls.slice()
    for (const [url] of calls) expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    wrapper.unmount()
    return calls.map(([, body]) => body)
  } finally {
    vi.clearAllTimers()
    vi.useRealTimers()
  }
}

const rowsOf = (body: any, table: string) => body.sub_table_data[table] as Array<Record<string, unknown>>

describe('j2HeadlessProvider', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 5, push_kept: [] })
    h.apiPost.mockResolvedValue({})
  })

  it('上市：五、49 + 净负债期末为负另推 五、17，与真实 Tab 发出的逐字节相同；只 GET 回复、不 PUT', async () => {
    const out = await j2HeadlessProvider(LISTED)
    expect(out).toEqual({ sections: [{ section: '五、49', rows: 5, kept: 0 }, { section: '五、17', rows: 5, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-j2/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    const sent = h.post.mock.calls.map((c) => c[1])
    for (const c of h.post.mock.calls) expect(c[2]).toMatchObject({ _silent: true })
    const tab = await tabRequests('listed')
    expect(J(sent)).toBe(J(tab))
    expect(sent[0]).toMatchObject({ wp_id: 'wp-j2', section_id: '五、49', current_standard: 'listed_standalone', year: 2025 })
    expect(rowsOf(sent[0], J2_LISTED_SUBTABLE.summary).slice(0, 2)).toEqual([
      expect.objectContaining({ label: '设定受益计划净负债', end: 1000, begin: 800 }),
      expect.objectContaining({ label: '辞退福利', end: 200, begin: 100 }),
    ])
    expect(sent[1].section_id).toBe('五、17')
  })

  it('国企：读回动态「其他变动」与计划资产子类别行、汇总表全 0 时按 J2-1 带期初，与真实 Tab 逐字节相同', async () => {
    const out = await j2HeadlessProvider(SOE)
    expect(out.sections.map((s) => s.section)).toEqual(['八、54'])
    const sent = h.post.mock.calls.map((c) => c[1])
    const tab = await tabRequests('soe')
    expect(J(sent)).toBe(J(tab))
    expect(sent[0]).toMatchObject({ section_id: '八、54', current_standard: 'soe_standalone', year: 2025 })
    expect(J(sent[0])).toContain('合同变更')
    expect(J(sent[0])).toContain('银行理财产品')
    expect(rowsOf(sent[0], J2_SOE_SUBTABLE.summary)[0]).toEqual(expect.objectContaining({ label: '设定受益计划净负债', begin: 320 }))
  })

  it('没有任何回复：两版都按默认行推（上市净负债不为负 ⇒ 只推 五、49），与 Tab 相同', async () => {
    h.get.mockResolvedValue([])
    await j2HeadlessProvider(LISTED)
    await j2HeadlessProvider(SOE)
    const [listed, soe] = h.post.mock.calls.map((c) => c[1])
    expect(h.post).toHaveBeenCalledTimes(2)
    expect(J([listed])).toBe(J(await tabRequests('listed', [])))
    expect(J([soe])).toBe(J(await tabRequests('soe', [])))
    expect(listed.section_id).toBe('五、49')
    expect(soe.section_id).toBe('八、54')
  })

  it('静态接线：两个 Tab 的状态 / 读回 / 请求体都调共用模块，不再内联', () => {
    const dir = resolve(__dirname, '../../j2')
    for (const [file, factory, state] of [
      ['J2TabDisclosureListed.vue', 'useJ2ListedDisclosureState', 'listedState'],
      ['J2TabDisclosureSoe.vue', 'useJ2SoeDisclosureState', 'soeState'],
    ] as const) {
      const src = readFileSync(resolve(dir, file), 'utf-8')
      expect(src, file).toContain(`const ${state} = ${factory}()`)
      expect(src, file).toContain(`${state}.load(props.allResponses)`)
      expect(src, file).toContain(`${state}.syncRequests(props.wpId, auditYear.value)`)
      expect(src, file).not.toMatch(/function parseJson|function assignRows|'J2-1-main'|buildJ2(?:Listed|Soe)SyncPayload\(|buildJ2NetAssetPayload\(|toJ2SyncRequest\(/)
    }
  })
})
