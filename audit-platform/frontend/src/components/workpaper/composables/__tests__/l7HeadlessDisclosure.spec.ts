/**
 * L7 其他非流动负债披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①挂载真实的两个披露 Tab（自建 useL7FormData 经 apiProxy 读回复 → onMounted restoreRows），调 Tab 的同步函数，Tab 发出
 * 的请求体与离屏 provider 发出的请求体逐字节相同；夹具有真实数据（整表键多行有数，含空行名行与非数字金额）②旧版逐格键 / 整表键
 * 损坏 / 没有已存三种读回分支同样等价 ③只读 L7- 条目、静默、不写底稿 ④上市写 五、52、国企写 八、57（国企底稿列序年初在前，
 * 载荷按期末 / 期初投影）⑤章节保护命中不发请求 ⑥Tab 接线：默认行 / 读回 / 快照都调 l7DisclosureTabState。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { routerKey } from 'vue-router'

const h = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), put: vi.fn(), apiGet: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn(),
}))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet, post: h.apiPost, put: h.apiPut } }))
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<typeof import('element-plus')>()
  return {
    ...actual,
    ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
    ElMessageBox: { confirm: vi.fn() },
  }
})

import L7TabDisclosureListed from '../../l7/core/L7TabDisclosureListed.vue'
import L7TabDisclosureSoe from '../../l7/core/L7TabDisclosureSoe.vue'
import { l7HeadlessProvider } from '../l7HeadlessDisclosure'
import { L7_SUBTABLE } from '../l7NoteSectionMap'
import { SYNC_URL, syncRequestsFromTab, type Resp } from './_lDisclosureTabHarness'

const J = JSON.stringify
const LISTED_ROWS = J([
  { item: '递延收益', endAmount: 1200.5, priorYearEnd: 800 },
  { item: '长期保证金/押金', endAmount: '300', priorYearEnd: 100 },
  { item: '   ', endAmount: 999, priorYearEnd: 999 },
  { item: '政府补助（非流动）', endAmount: 'abc', priorYearEnd: 50 },
])
const SOE_ROWS = J([
  { item: '待转销项税额', beginBalance: 40, endBalance: 60 },
  { item: '合同负债', beginBalance: 0, endBalance: 250 },
  { item: '', beginBalance: 7, endBalance: 7 },
])
const RESPONSES: Resp[] = [
  { item_id: 'L7-disclosure-listed-rows', remark: LISTED_ROWS, conclusion: null },
  { item_id: 'L7-disclosure-soe-rows', remark: SOE_ROWS, conclusion: null },
  { item_id: 'L7-disc-listed-conclusion', remark: '上市核对一致', conclusion: null },
  { item_id: 'L7-disclosure-soe-special', remark: '国资专项说明', conclusion: null },
  { item_id: 'L7-L7-2-full-data', remark: J([{ rowId: 'l72det-1', endBalance: 5 }]), conclusion: null },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-l7', wpCode: 'L7', applicableStandards: [] as string[] }
const WP = resolve(__dirname, '../..')

let responses: Resp[] = RESPONSES

/** Tab 路径：挂载真实 Tab（useL7FormData 经 apiProxy 读回复 → restoreRows）→ 调它的同步函数 → 截下请求体 */
async function tabBody(variant: 'listed' | 'soe'): Promise<any> {
  const [req] = await syncRequestsFromTab(variant === 'listed' ? L7TabDisclosureListed : L7TabDisclosureSoe, h.post, {
    wpId: 'wp-l7',
    provide: { [routerKey as symbol]: { push: vi.fn() } },
  })
  expect(req.url).toBe(SYNC_URL)
  h.post.mockClear()
  h.apiGet.mockClear()
  return req.body
}

function mainRows(sent: any): any[] {
  return sent.sub_table_data[L7_SUBTABLE.main] as any[]
}

describe('l7HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    responses = RESPONSES
    h.apiGet.mockImplementation(async (url: string) => (url.includes('checklist-responses') ? responses : {}))
    h.get.mockImplementation(async () => responses)
    h.post.mockResolvedValue({ rows_synced: 4, push_kept: [{ table: L7_SUBTABLE.main }] })
  })

  it('上市：请求体与挂载的 Tab 逐字节相同，静默写 五、52、不写底稿；空行名不推、非数字金额按 0', async () => {
    const tabSent = await tabBody('listed')
    const out = await l7HeadlessProvider({ ...CTX, variant: 'listed' })
    expect(out).toEqual({ sections: [{ section: '五、52', rows: 4, kept: 1 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-l7/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiPut).not.toHaveBeenCalled()
    expect(h.apiGet).not.toHaveBeenCalled()
    expect(h.post).toHaveBeenCalledTimes(1)
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe(SYNC_URL)
    expect(cfg).toMatchObject({ _silent: true })
    expect(J(sent)).toBe(J(tabSent))
    expect(sent).toMatchObject({
      wp_id: 'wp-l7', sheet_name: '附注披露信息（上市公司）', section_id: '五、52', current_standard: 'listed_standalone',
    })
    expect(mainRows(sent)).toEqual([
      { label: '递延收益', end_amount: 1200.5, prior_amount: 800 },
      { label: '长期保证金/押金', end_amount: 300, prior_amount: 100 },
      { label: '政府补助（非流动）', end_amount: 0, prior_amount: 50 },
      { label: '合计', end_amount: 1500.5, prior_amount: 950, is_total: true },
    ])
    expect(Object.keys(sent.sub_table_data)).toEqual([L7_SUBTABLE.main])
  })

  it('国企：请求体与挂载的 Tab 逐字节相同，写 八、57；年初 / 期末投影成期末 / 期初，列序年初在前', async () => {
    const tabSent = await tabBody('soe')
    const out = await l7HeadlessProvider({ ...CTX, variant: 'soe' })
    expect(out.sections.map((s) => s.section)).toEqual(['八、57'])
    const sent = h.post.mock.calls[0][1]
    expect(J(sent)).toBe(J(tabSent))
    expect(sent).toMatchObject({ sheet_name: '附注披露信息(国企)', section_id: '八、57', current_standard: 'soe_standalone' })
    expect(mainRows(sent)).toEqual([
      { label: '待转销项税额', end_amount: 60, prior_amount: 40 },
      { label: '合同负债', end_amount: 250, prior_amount: 0 },
      { label: '合计', end_amount: 310, prior_amount: 40, is_total: true },
    ])
    expect(sent.columns[L7_SUBTABLE.main].map((c: any) => c.key)).toEqual(['label', 'prior_amount', 'end_amount'])
    expect(sent.sub_table_data._note_texts).toBeUndefined()
  })

  it('旧版逐格键（整表键损坏）/ 没有已存：两口径都与 Tab 读回同一份', async () => {
    responses = [
      { item_id: 'L7-disclosure-listed-rows', remark: '{坏的', conclusion: null },
      { item_id: 'L7-disclosure-listed-0-endAmount', remark: '100', conclusion: null },
      { item_id: 'L7-disclosure-listed-1-priorYearEnd', remark: '20', conclusion: null },
      { item_id: 'L7-disclosure-listed-5-endAmount', remark: '999', conclusion: null },
      { item_id: 'L7-disclosure-soe-0-beginBalance', remark: '5', conclusion: null },
      { item_id: 'L7-disclosure-soe-4-endBalance', remark: 'x', conclusion: null },
      { item_id: 'L7-disclosure-soe-3-endBalance', remark: '9', conclusion: null },
    ]
    for (const variant of ['listed', 'soe'] as const) {
      const tabSent = await tabBody(variant)
      await l7HeadlessProvider({ ...CTX, variant })
      const sent = h.post.mock.calls[0][1]
      expect(J(sent), variant).toBe(J(tabSent))
      h.post.mockClear()
    }
    // 上市旧格式按默认 5 行回填（第 6 行旧合计丢弃）
    await l7HeadlessProvider({ ...CTX, variant: 'listed' })
    expect(mainRows(h.post.mock.calls[0][1]).slice(0, 2)).toEqual([
      { label: '递延收益', end_amount: 100, prior_amount: 0 },
      { label: '长期保证金/押金', end_amount: 0, prior_amount: 20 },
    ])
    expect(mainRows(h.post.mock.calls[0][1]).at(-1)).toMatchObject({ label: '合计', end_amount: 100, prior_amount: 20 })
    h.post.mockClear()
    // 国企旧格式按旧默认 5 行名回填（不是现在的模板 seed）
    await l7HeadlessProvider({ ...CTX, variant: 'soe' })
    expect(mainRows(h.post.mock.calls[0][1]).map((r) => r.label)).toEqual(
      ['递延收益', '长期保证金/押金', '政府补助（非流动）', '预收款项（非流动）', '其他', '合计'],
    )
    expect(mainRows(h.post.mock.calls[0][1]).at(-1)).toMatchObject({ end_amount: 9, prior_amount: 5 })
    h.post.mockClear()

    responses = []
    const tabSent = await tabBody('soe')
    await l7HeadlessProvider({ ...CTX, variant: 'soe' })
    expect(J(h.post.mock.calls[0][1])).toBe(J(tabSent))
    expect(mainRows(tabSent).map((r) => r.label)).toEqual(['待转销项税额', '合同负债', '合计'])
  })

  it('只读本底稿 L7- 条目：别的前缀的同名条目不影响载荷', async () => {
    responses = [...RESPONSES, { item_id: 'L70-disclosure-listed-rows', remark: J([{ item: '串号', endAmount: 1 }]), conclusion: null }]
    await l7HeadlessProvider({ ...CTX, variant: 'listed' })
    expect(mainRows(h.post.mock.calls[0][1]).map((r) => r.label)).not.toContain('串号')
    expect(mainRows(h.post.mock.calls[0][1]).at(-1)).toMatchObject({ end_amount: 1500.5 })
  })

  it('章节保护命中：不发请求，原因随结果回报', async () => {
    const out = await l7HeadlessProvider({ ...CTX, variant: 'listed', sectionGuard: () => '附注 五、52 已有 3 格人工填写' })
    expect(h.post).not.toHaveBeenCalled()
    expect(out).toEqual({ sections: [{ section: '五、52', rows: 0, skipped: '附注 五、52 已有 3 格人工填写' }] })
  })

  it('Tab 接线：默认行 / 读回 / 快照都调 l7DisclosureTabState，组件内不再自算', () => {
    for (const [file, v, V] of [['L7TabDisclosureListed.vue', 'listed', 'Listed'], ['L7TabDisclosureSoe.vue', 'soe', 'Soe']] as const) {
      const src = readFileSync(resolve(WP, `l7/core/${file}`), 'utf-8')
      const sync = src.slice(src.indexOf('async function syncToDisclosureNotes'))
      expect(sync).toContain(`buildL7SyncPayload(props.wpId, buildL7${V}DisclosureSnapshot(disclosureRows.value))`)
      const restore = src.slice(src.indexOf('function restoreRows'))
      expect(restore).toContain(`restoreL7${V}Disclosure(formData.allResponses.value)`)
      expect(src).toContain(`ref<L7${V}DisclosureRow[]>(createL7${V}DisclosureRows())`)
      expect(src).toContain(`const ROWS_ITEM_ID = L7_DISCLOSURE_ROWS_ITEM_ID.${v}`)
      expect(src).not.toMatch(/function defaultRows|JSON\.parse\(packed\)/)
    }
  })
})
