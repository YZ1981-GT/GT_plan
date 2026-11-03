/**
 * H2 在建工程披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 两个 Tab 内联的表单状态 / 挂载读回 / 「从审定/明细取数」/ 快照与载荷抽成 `h2DisclosureTabState` 后 Tab 与离屏同步共用。判据：
 * ①挂载真实 Tab（同一批 H2- 回复）、点「同步到附注」发出的载荷 == 离屏载荷（上市 五、23 / 国企 八、23；已存披露表、挂载自动取数、
 * 无回复三种夹具）②只 GET 本底稿回复、不 PUT、不推国企受限资产段 ③外壳种子：披露表与 H2-2 都没存过、外壳会用 render-config 的
 * `detail_prefill` 种 H2-2 时离屏不写并说明（种子在宿主组件里，Tab 拿到的回复离屏复现不了）④静态接线。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('vue-router', async () => ({
  ...(await vi.importActual<Record<string, unknown>>('vue-router')),
  useRouter: () => ({ push: vi.fn(() => Promise.resolve()) }),
}))
vi.mock('element-plus', async () => ({
  ...(await vi.importActual<Record<string, unknown>>('element-plus')),
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn(() => Promise.resolve()) },
}))

import { H2_HOST_SEED_SKIP_REASON, H2_HOST_SEED_UNKNOWN_REASON, h2HeadlessProvider } from '../h2HeadlessDisclosure'
import { H2_LISTED_SUBTABLE, H2_SOE_SUBTABLE } from '../h2NoteSectionMap'
import H2TabDisclosureListed from '../../h2/core/H2TabDisclosureListed.vue'
import H2TabDisclosureSoe from '../../h2/core/H2TabDisclosureSoe.vue'

const J = JSON.stringify
type Resp = { item_id: string; remark: string | null; conclusion: string | null }
const resp = (item_id: string, value: unknown): Resp =>
  ({ item_id, conclusion: null, remark: typeof value === 'string' ? value : J(value) })

/** H2-1 审定表 / H2-2 明细表（「从审定/明细取数」的来源） */
const SOURCES: Resp[] = [
  resp('H2-1-rows', [
    { name: '厂房工程', cipBegin: 3000, cipEnd: 5200, impairment: 200 },
    { name: '仓库改造', cipBegin: 0, audited: 800, impairment: 0 },
  ]),
  resp('H2-2-rows', [
    {
      rowId: 'x1', name: '厂房工程', projectCode: 'P01', cipBegin: 3000, increaseTotal: 2500, increaseInterest: 80,
      transferAmount: 300, decrease: 0, transferOut: 0, cipEnd: 5200, endAudited: 5200, impairEndAud: 200, netEndAud: 5000,
      budget: 10000, accumulatedInput: 5200, fundSource: '自筹', progress: '60%', isMortgaged: 'Y',
    },
    { rowId: 'x2', name: '仓库改造', cipBegin: 0, increaseTotal: 800, cipEnd: 800, endAudited: 800, budget: 0, isMortgaged: 'N' },
  ]),
  resp('H2A-proc-1', '程序表（不是 H2- 前缀）'),
  resp('H1-listed-summary', '[]'),
]
/** 已保存的两版披露表（上市 / 国企各自的键，同一底稿里并存） */
const SAVED: Resp[] = [
  resp('H2-listed-summary', [
    { key: 'cip', label: '在建工程', endBalance: 5000, priorBalance: 3000 },
    { key: 'materials', label: '工程物资', endBalance: 140, priorBalance: 80 },
  ]),
  resp('H2-listed-detail-rows', [
    { rowId: 'd1', name: '厂房工程', endBook: 5200, endImpairment: 200, priorBook: 3000, priorImpairment: 0 },
    { name: '仓库改造', endBook: 800, endImpairment: 0, priorBook: 0, priorImpairment: 0 },
  ]),
  resp('H2-listed-project-rows', [{
    rowId: 'p1', name: '厂房工程', beginBalance: 3000, increase: 2500, transferToFA: 300, otherDecrease: 0, interestCapAccum: 120,
    interestCapCurrent: 80, interestCapRate: 4.35, budget: 10000, cumInputPct: 0, accumulatedInput: 5200, progress: '60%', fundSource: '自筹',
  }]),
  resp('H2-listed-impairment-rows', [{ rowId: 'i1', name: '厂房工程', beginBalance: 0, provision: 200, decrease: 0 }]),
  resp('H2-listed-materials', [
    { key: 'specialMaterial', label: '专用材料', endBalance: 150, priorBalance: 80 },
    { key: 'impairment', label: '工程物资减值准备', endBalance: 10, priorBalance: 0, isDeduction: true },
  ]),
  resp('H2-listed-mortgage-rows', [{ rowId: 'm1', name: '厂房工程', amount: 5000, description: '编号P01；在建工程抵押/担保', remark: '' }]),
  resp('H2-listed-note-impairment', '本期对厂房工程进行减值测试，可收回金额按公允价值减处置费用确定。'),
  resp('H2-listed-note-fund-source', '资金来源为自筹与银行贷款。'),
  resp('H2-soe-summary', [
    { key: 'cip', label: '在建工程', endBook: 6000, endImpairment: 200, beginBook: 3000, beginImpairment: 0 },
    { key: 'materials', label: '工程物资', endBook: 150, endImpairment: 10, beginBook: 80, beginImpairment: 0 },
  ]),
  resp('H2-soe-detail-rows', [{ rowId: 'sd1', name: '厂房工程', endBook: 5200, endImpairment: 200, beginBook: 3000, beginImpairment: 0 }]),
  resp('H2-soe-project-rows', [{
    rowId: 'sp1', name: '厂房工程', budget: 10000, beginBalance: 3000, increase: 2500, transferToFA: 300, otherDecrease: 0,
    interestCapAccum: 120, interestCapCurrent: 80, interestCapRate: 4.35, cumInputPct: 52, progress: '60%', fundSource: '自筹',
  }]),
  resp('H2-soe-impairment-rows', [
    { rowId: 'si1', name: '厂房工程', provisionAmount: 200, reason: '市场价格下跌' },
    { name: '', provisionAmount: 0, reason: '' },
  ]),
  resp('H2-soe-note-impairment', '按可收回金额低于账面价值的差额计提。'),
  ...SOURCES,
]
/** 宿主 render-config：每个页签的 html_data 是同一份 H2 渲染结果；`detail_prefill` 空 = 外壳不种 H2-2 */
const renderConfig = (prefill: unknown[]) => ({
  sheets: ['明细表H2-2', '附注披露信息（上市公司）', '附注披露信息（国有企业）'].map((sheet_name) => ({
    sheet_name, componentType: 'h2-construction-in-progress', html_data: { prefix: 'H2', detail_prefill: prefill },
  })),
})
const PREFILL = [{ name: '在建工程-厂房', cipBegin: 100, cipEnd: 300, category: '自动种子' }]

const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-h2', wpCode: 'H2' }
const LISTED = { ...CTX, variant: 'listed' as const, applicableStandards: ['listed_standalone'] }
const SOE = { ...CTX, variant: 'soe' as const, applicableStandards: ['soe_standalone'] }
const RESPONSES_URL = '/api/workpapers/wp-h2/checklist-responses'
const RENDER_URL = '/api/workpapers/wp-h2/render-config'

function routeGet(list: Resp[], config: unknown = renderConfig([])) {
  h.get.mockImplementation(async (url: string) => {
    if (url === RESPONSES_URL) return list
    if (url === RENDER_URL) {
      if (config instanceof Error) throw config
      return config
    }
    throw new Error(`意外的 GET ${url}`)
  })
}

const STUBS = {
  'el-button': { template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>', emits: ['click'] },
  'el-alert': true, 'el-tag': true, 'el-table': true, 'el-table-column': true, 'el-input': true, 'el-input-number': true,
  GtIndexChip: true, GtReviewTrigger: true, WpNoteTextArea: true, WpDisclosureConsistencyPanel: true, WpAmountInput: true,
}

/** Tab 路径：挂载真实 Tab（外壳回复 = 同一批 H2- 回复），点「同步到附注」，取它发出的全部载荷 */
async function tabPayloads(variant: 'listed' | 'soe', list: Resp[]): Promise<any[]> {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  try {
    const allResponses = new Map(list.filter((x) => x.item_id.startsWith('H2-')).map((x) => [x.item_id, { ...x }]))
    const wrapper = mount(variant === 'listed' ? H2TabDisclosureListed : H2TabDisclosureSoe, {
      props: {
        wpId: 'wp-h2', projectId: 'p1', allResponses, isReadonly: false,
        applicableStandards: [variant === 'listed' ? 'listed_standalone' : 'soe_standalone'],
      },
      global: { stubs: STUBS },
    })
    await flushPromises()
    const before = h.post.mock.calls.length
    const button = wrapper.find(`[data-testid="h2-disclosure-${variant}-sync"]`)
    expect(button.exists(), '找不到「同步到附注」按钮').toBe(true)
    expect(button.text()).toContain('同步到附注')
    await button.trigger('click')
    await flushPromises()
    const calls = h.post.mock.calls.slice(before)
    for (const [url] of calls) expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    wrapper.unmount()
    return calls.map(([, payload]) => payload)
  } finally {
    vi.clearAllTimers()
    vi.useRealTimers()
  }
}

const rowsOf = (payload: any, table: string) => payload.sub_table_data[table] as Array<Record<string, unknown>>
const getUrls = () => h.get.mock.calls.map((c) => c[0])

describe('h2HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.post.mockResolvedValue({ rows_synced: 4, push_kept: [] })
  })

  it('上市：已存披露表 ⇒ 离屏载荷与真实 Tab 点「同步到附注」逐字节相同；只 GET 回复、不 PUT', async () => {
    routeGet(SAVED)
    const out = await h2HeadlessProvider(LISTED)
    expect(out).toEqual({ sections: [{ section: '五、23', rows: 4, kept: 0 }] })
    expect(getUrls()).toEqual([RESPONSES_URL])
    expect(h.put).not.toHaveBeenCalled()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    const tab = await tabPayloads('listed', SAVED)
    expect(tab).toHaveLength(1)
    expect(J(sent)).toBe(J(tab[0]))
    expect(sent).toMatchObject({ wp_id: 'wp-h2', section_id: '五、23', current_standard: 'listed_standalone' })
    expect(rowsOf(sent, H2_LISTED_SUBTABLE.summary).map((r) => [r.label, r.end_balance, r.prior_balance]))
      .toEqual([['在建工程', 5000, 3000], ['工程物资', 140, 80], ['合计', 5140, 3080]])
    const detail = rowsOf(sent, H2_LISTED_SUBTABLE.detail)
    expect(detail.map((r) => [r.label, r.end_net, r.prior_net])).toEqual([['厂房工程', 5000, 3000], ['仓库改造', 800, 0], ['合计', 5800, 3000]])
    expect(rowsOf(sent, H2_LISTED_SUBTABLE.projectMovement)[0]).toMatchObject({ label: '厂房工程', transfer_to_fa: 300, end_balance: 5200 })
    expect(rowsOf(sent, H2_LISTED_SUBTABLE.projectCont)[0]).toMatchObject({ budget: 10000, cum_input_pct: 52, fund_source: '自筹' })
    expect(rowsOf(sent, H2_LISTED_SUBTABLE.materials).at(-1)).toMatchObject({ label: '合计', end_balance: 140, prior_balance: 80 })
    const notes = sent.sub_table_data._note_texts as Array<{ section: string; text: string }>
    expect(notes.map((n) => n.section)).toEqual(['listed-impairment', 'listed-fund-source', 'listed-mortgage'])
    expect(notes[2].text).toContain('厂房工程：抵押/担保金额')
  })

  it('国企：已存披露表 ⇒ 八、23 与 Tab 逐字节相同；Tab 另推的受限资产段（八、93）离屏不推', async () => {
    routeGet(SAVED)
    const out = await h2HeadlessProvider(SOE)
    expect(out.sections.map((s) => s.section)).toEqual(['八、23'])
    expect(getUrls()).toEqual([RESPONSES_URL])
    const sent = h.post.mock.calls.map((c) => c[1])
    const tab = await tabPayloads('soe', SAVED)
    expect(tab.map((p) => p.section_id)).toEqual(['八、23', '八、93'])
    expect(J(sent)).toBe(J(tab.slice(0, 1)))
    expect(h.put).not.toHaveBeenCalled()
    expect(rowsOf(sent[0], H2_SOE_SUBTABLE.summary).map((r) => [r.label, r.end_carrying, r.begin_carrying]))
      .toEqual([['在建工程', 5800, 3000], ['工程物资', 140, 80], ['合计', 5940, 3080]])
    expect(rowsOf(sent[0], H2_SOE_SUBTABLE.projectMovement)[0]).toMatchObject({ label: '厂房工程', end_balance: 5200, cum_input_pct: 52 })
    expect(rowsOf(sent[0], H2_SOE_SUBTABLE.impairment).map((r) => [r.label, r.provision_amount, r.reason]))
      .toEqual([['厂房工程', 200, '市场价格下跌'], ['合计', 200, '']])
  })

  it('披露表没存过、H2-2 有已存明细 ⇒ 挂载自动取数（明细 / 项目 / 抵押取 H2-2，汇总取 H2-1），两版都与 Tab 相同', async () => {
    routeGet(SOURCES)
    await h2HeadlessProvider(LISTED)
    await h2HeadlessProvider(SOE)
    expect(getUrls()).toEqual([RESPONSES_URL, RESPONSES_URL])
    const [listed, soe] = h.post.mock.calls.map((c) => c[1])
    expect(J(listed)).toBe(J((await tabPayloads('listed', SOURCES))[0]))
    expect(J([soe])).toBe(J(await tabPayloads('soe', SOURCES)))
    expect(rowsOf(listed, H2_LISTED_SUBTABLE.summary)[0]).toMatchObject({ label: '在建工程', end_balance: 5800, prior_balance: 3000 })
    expect(rowsOf(listed, H2_LISTED_SUBTABLE.detail).map((r) => [r.label, r.end_book, r.end_impairment]))
      .toEqual([['厂房工程', 5200, 200], ['仓库改造', 800, 0], ['合计', 6000, 200]])
    expect(rowsOf(listed, H2_LISTED_SUBTABLE.projectMovement).map((r) => r.end_balance)).toEqual([5200, 800, 6000])
    expect((listed.sub_table_data._note_texts as any[]).at(-1)).toMatchObject({ section: 'listed-mortgage' })
    expect(rowsOf(soe, H2_SOE_SUBTABLE.summary)[0]).toMatchObject({ end_book: 6000, end_impairment: 200, begin_book: 3000 })
    expect(rowsOf(soe, H2_SOE_SUBTABLE.detail).map((r) => [r.label, r.end_book])).toEqual([['厂房工程', 5200], ['仓库改造', 800], ['合计', 6000]])
    expect(h.put).not.toHaveBeenCalled()
  })

  it('没有任何回复、外壳也不种 H2-2 ⇒ 两版都推默认 0 表，与 Tab 相同（只多取一次 render-config 判种子）', async () => {
    routeGet([])
    await h2HeadlessProvider(LISTED)
    await h2HeadlessProvider(SOE)
    expect(getUrls()).toEqual([RESPONSES_URL, RENDER_URL, RESPONSES_URL, RENDER_URL])
    const [listed, soe] = h.post.mock.calls.map((c) => c[1])
    expect(J(listed)).toBe(J((await tabPayloads('listed', []))[0]))
    expect(J([soe])).toBe(J(await tabPayloads('soe', [])))
    expect(rowsOf(listed, H2_LISTED_SUBTABLE.summary).map((r) => r.end_balance)).toEqual([0, 0, 0])
    expect(rowsOf(listed, H2_LISTED_SUBTABLE.detail)).toEqual([expect.objectContaining({ label: '合计', end_net: 0, is_total: true })])
    expect(listed.sub_table_data._note_texts).toEqual([])
    expect(rowsOf(soe, H2_SOE_SUBTABLE.summary).map((r) => r.end_carrying)).toEqual([0, 0, 0])
    expect(h.put).not.toHaveBeenCalled()
  })

  it('外壳会用 detail_prefill 种 H2-2（披露表与 H2-2 都没存过）⇒ 离屏不写、回报原因；Tab 拿到种子后的载荷离屏复现不了', async () => {
    routeGet(SOURCES.filter((r) => r.item_id !== 'H2-2-rows'), renderConfig(PREFILL))
    expect(await h2HeadlessProvider(LISTED)).toEqual({ sections: [{ section: '五、23', rows: 0, skipped: H2_HOST_SEED_SKIP_REASON }] })
    expect(await h2HeadlessProvider(SOE)).toEqual({ sections: [{ section: '八、23', rows: 0, skipped: H2_HOST_SEED_SKIP_REASON }] })
    expect(h.post).not.toHaveBeenCalled()
    expect(h.put).not.toHaveBeenCalled()
    // 宿主 _seedDetailFromPrefill 种进内存的 H2-2（rowId / name / cipBegin / cipEnd / category）⇒ Tab 取数带出种子行
    const seeded = [...SOURCES.filter((r) => r.item_id !== 'H2-2-rows'), resp('H2-2-rows', [{ rowId: 's1', ...PREFILL[0] }])]
    const [tab] = await tabPayloads('listed', seeded)
    expect(rowsOf(tab, H2_LISTED_SUBTABLE.detail)[0]).toMatchObject({ label: '在建工程-厂房', end_book: 300, prior_book: 100 })

    h.get.mockReset()
    routeGet([], new Error('render-config 500'))
    expect((await h2HeadlessProvider(LISTED)).sections).toEqual([{ section: '五、23', rows: 0, skipped: H2_HOST_SEED_UNKNOWN_REASON }])
    expect(h.post).toHaveBeenCalledTimes(1) // 只有上面 Tab 那一次
  })

  it('静态接线：两个 Tab 调共用的状态 / 读回 / 取数 / 载荷函数，不再内联；外壳确实会种 H2-2（闸门的前提）', () => {
    const dir = resolve(__dirname, '../../h2/core')
    const cases = [
      ['H2TabDisclosureListed.vue', 'useH2ListedDisclosureState', 'listedState'],
      ['H2TabDisclosureSoe.vue', 'useH2SoeDisclosureState', 'soeState'],
    ] as const
    for (const [file, factory, state] of cases) {
      const src = readFileSync(resolve(dir, file), 'utf-8')
      expect(src, file).toContain(`const ${state} = ${factory}()`)
      expect(src, file).toContain(`if (!${state}.load(props.allResponses)) pullFromSources(false)`)
      expect(src, file).toContain(`${state}.applySources(props.allResponses)`)
      expect(src, file).toContain(`const payloads = ${state}.syncPayloads(props.wpId)`)
      expect(src, file).not.toMatch(/function parseJson|function getSnapshot|adjRaw|mapDetailToListedDetail\(|mapDetailToSoeDetail\(|buildH2(?:Listed|Soe)SyncPayloads\(/)
    }
    const soe = readFileSync(resolve(dir, 'H2TabDisclosureSoe.vue'), 'utf-8')
    expect(soe).toMatch(/await\s+syncRestrictedAssets\s*\(/)
    const host = readFileSync(resolve(__dirname, '../../GtH2ConstructionInProgress.vue'), 'utf-8')
    expect(host).toContain("const detailKey = 'H2-2-rows'")
    expect(host).toContain('const prefill = props.htmlData?.detail_prefill')
    expect(host).toContain('_seedDetailFromPrefill()')
  })
})
