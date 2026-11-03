/**
 * L3 长期借款披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①按外壳同样方式建表单（`useL3FormData` + `loadData()`，经 apiProxy 读回复）注入、挂载真实的两个披露 Tab，调 Tab
 * 的同步函数：上市请求体与离屏逐字节相同；国企 Tab 一次批量发两节，离屏逐节各发一次同一批量端点，每次请求体 = Tab 请求体只留
 * 这一节（item 逐字节相同）②夹具有真实数据（4 类借款 + 一年内到期 + 利率区间 + 说明 / 结论）③只读 L3- 条目、静默、不写底稿
 * ④逐章节回报，章节保护 / 单节失败只影响这一节 ⑤Tab 接线：入参 / 请求体都调 l3DisclosureSync。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'
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

import L3TabDisclosureListed from '../../l3/core/L3TabDisclosureListed.vue'
import L3TabDisclosureSoe from '../../l3/core/L3TabDisclosureSoe.vue'
import { l3HeadlessProvider } from '../l3HeadlessDisclosure'
import { useL3FormData } from '../useL3FormData'
import { L3_SUBTABLE } from '../l3NoteSectionMap'
import { BATCH_URL, SYNC_URL, syncRequestsFromTab, type Resp } from './_lDisclosureTabHarness'

const J = JSON.stringify
const DETAIL = J([
  { loanType: '质押借款', audited: 5000, beginning: 4000, currentPortion: 1000 },
  { loanType: '抵押借款', endBalance: 3000, beginning: 2500 },
  { loanType: '保证借款', audited: 2000, beginning: 1800, currentPortion: 500 },
  { loanType: '信用借款', audited: 800, beginning: 0 },
])
const RESPONSES: Resp[] = [
  { item_id: 'L3-L3-2-rows', remark: DETAIL, conclusion: null },
  { item_id: 'L3-disc-listed-rate-pledge-end', remark: '3.5%~4.2%', conclusion: null },
  { item_id: 'L3-disc-listed-rate-credit-prior', remark: '4.0%', conclusion: null },
  { item_id: 'L3-disc-listed-deduct-prior', remark: '300', conclusion: null },
  { item_id: 'L3-disc-listed-property-note', remark: '以厂房抵押', conclusion: null },
  { item_id: 'L3-disc-listed-conclusion', remark: '上市披露一致', conclusion: null },
  { item_id: 'L3-disc-soe-rate-mortgage-end', remark: '4.35%', conclusion: null },
  { item_id: 'L3-disc-soe-property-note', remark: '国企不推的抵押说明', conclusion: null },
  { item_id: 'L3-disc-soe-repaid-note', remark: '日后已偿还 100 元', conclusion: null },
  { item_id: 'L3-disc-soe-conclusion', remark: '国企披露一致', conclusion: null },
  { item_id: 'L1-adj-1-endUnadjusted', remark: '999', conclusion: null },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-l3', wpCode: 'L3', applicableStandards: [] as string[] }
const WP = resolve(__dirname, '../..')

/** Tab 路径：按外壳同样方式建表单（useL3FormData + loadData）注入 → 挂载真实 Tab → 调它的同步函数 → 截下请求 */
async function tabRequest(variant: 'listed' | 'soe'): Promise<{ url: string; body: any }> {
  const scope = effectScope(true)
  const formData = scope.run(() => useL3FormData({ wpId: ref('wp-l3'), projectId: ref('p1') }))!
  await formData.loadData()
  const [req] = await syncRequestsFromTab(variant === 'listed' ? L3TabDisclosureListed : L3TabDisclosureSoe, h.post, {
    wpId: 'wp-l3',
    provide: { l3FormData: formData, [routerKey as symbol]: { push: vi.fn() } },
  })
  scope.stop()
  h.post.mockClear()
  return req
}

function soeBatchResult(_url: string, body: any) {
  const section = body.items[0].section_id
  return Promise.resolve({ success: true, results: [{ section_id: section, rows_synced: section === '八、49' ? 8 : 5, push_kept: [] }] })
}

describe('l3HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.apiGet.mockImplementation(async (url: string) => (url.includes('checklist-responses') ? RESPONSES : {}))
    h.get.mockResolvedValue(RESPONSES)
  })

  it('上市：请求体与挂载的 Tab 逐字节相同，静默写 五、45、不写底稿', async () => {
    h.post.mockResolvedValue({ rows_synced: 8, push_kept: [{ table: '长期借款' }] })
    const tab = await tabRequest('listed')
    expect(tab.url).toBe(SYNC_URL)
    const out = await l3HeadlessProvider({ ...CTX, variant: 'listed' })
    expect(out).toEqual({ sections: [{ section: '五、45', rows: 8, kept: 1 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-l3/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiPut).not.toHaveBeenCalled()
    expect(h.post).toHaveBeenCalledTimes(1)
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe(SYNC_URL)
    expect(cfg).toMatchObject({ _silent: true })
    expect(J(sent)).toBe(J(tab.body))
    expect(sent).toMatchObject({ wp_id: 'wp-l3', sheet_name: 'L3-note-listed', section_id: '五、45', current_standard: 'listed_standalone' })
    const main = sent.sub_table_data[L3_SUBTABLE.main] as any[]
    expect(main.find((r) => r.label === '质押借款')?.values).toEqual([5000, '3.5%~4.2%', 4000, ''])
    expect(main.find((r) => r.label === '信用借款')?.values).toEqual([800, '', 0, '4.0%'])
    expect(main.find((r) => r.label === '减：一年内到期的长期借款')?.values).toEqual([1500, '', 300, ''])
    expect(main.at(-1)).toEqual({ label: '合计', values: [9300, '', 8000, ''], is_total: true })
    expect(sent.sub_table_data._note_texts).toEqual([
      { section: 'property', title: '抵押质押说明', text: '以厂房抵押' },
      { section: 'conclusion', title: '审计结论', text: '上市披露一致' },
    ])
  })

  it('国企：逐章节各发一次同一批量端点，每次请求体 = Tab 批量请求体只留这一节；逐章节回报', async () => {
    h.post.mockResolvedValue({ success: true, results: [] })
    const tab = await tabRequest('soe')
    expect(tab.url).toBe(BATCH_URL)
    expect(tab.body.items.map((i: any) => i.section_id)).toEqual(['八、49', '八、45'])
    h.post.mockImplementation(soeBatchResult)
    const out = await l3HeadlessProvider({ ...CTX, variant: 'soe', applicableStandards: ['soe_standalone'] })
    expect(out).toEqual({ sections: [
      { section: '八、49', rows: 8, kept: 0 },
      { section: '八、45', rows: 5, kept: 0 },
    ] })
    expect(h.post).toHaveBeenCalledTimes(2)
    h.post.mock.calls.forEach(([url, sent, cfg], i) => {
      expect(url).toBe(BATCH_URL)
      expect(cfg).toMatchObject({ _silent: true })
      expect(J(sent)).toBe(J({ ...tab.body, items: [tab.body.items[i]] }))
    })
    expect(J(h.post.mock.calls.flatMap(([, sent]) => sent.items))).toBe(J(tab.body.items))
    const main = h.post.mock.calls[0][1].items[0].sub_table_data
    expect(main[L3_SUBTABLE.main].find((r: any) => r.label === '抵押借款')?.values).toEqual([3000, '4.35%', 2500, ''])
    expect(main._note_texts).toEqual([{ section: 'conclusion', title: '审计结论', text: '国企披露一致' }])
    const within1y = h.post.mock.calls[1][1].items[0].sub_table_data[L3_SUBTABLE.within1ySoe]
    expect(within1y.at(-1)).toEqual({ label: '合计', values: [1500, 0], is_total: true })
    expect(h.put).not.toHaveBeenCalled()
  })

  it('国企：章节保护只挡这一节；单节失败只记这一节，另一节照常写', async () => {
    h.post.mockImplementation(soeBatchResult)
    const guarded = await l3HeadlessProvider({
      ...CTX, variant: 'soe', sectionGuard: (s) => (s === '八、45' ? '附注 八、45 已有 2 格人工填写' : null),
    })
    expect(guarded.sections).toEqual([
      { section: '八、49', rows: 8, kept: 0 },
      { section: '八、45', rows: 0, skipped: '附注 八、45 已有 2 格人工填写' },
    ])
    expect(h.post).toHaveBeenCalledTimes(1)
    h.post.mockReset()
    h.post.mockImplementation((url: string, body: any) => (body.items[0].section_id === '八、49'
      ? Promise.reject({ response: { data: { detail: '附注批量同步失败: 锁冲突' } } })
      : soeBatchResult(url, body)))
    const failed = await l3HeadlessProvider({ ...CTX, variant: 'soe' })
    expect(failed.sections).toEqual([
      { section: '八、49', rows: 0, error: '附注批量同步失败: 锁冲突' },
      { section: '八、45', rows: 5, kept: 0 },
    ])
  })

  it('国企：响应标记整节人工覆盖 ⇒ 回报未写入', async () => {
    h.post.mockResolvedValue({ results: [{ section_id: '八、49', rows_synced: 0, blocked_by_manual_override: true }] })
    const out = await l3HeadlessProvider({ ...CTX, variant: 'soe', sectionGuard: (s) => (s === '八、49' ? null : '') })
    expect(out.sections).toEqual([
      { section: '八、49', rows: 0, skipped: '附注 八、49 标记了整节人工覆盖，未写入' },
      { section: '八、45', rows: 0, skipped: '' },
    ])
  })

  it('Tab 接线：同步函数调共用入参 / 请求体，组件内不再自拼', () => {
    const listed = readFileSync(resolve(WP, 'l3/core/L3TabDisclosureListed.vue'), 'utf-8')
    const soe = readFileSync(resolve(WP, 'l3/core/L3TabDisclosureSoe.vue'), 'utf-8')
    const body = (src: string) => src.slice(src.indexOf('async function syncToDisclosureNotes'))
    expect(body(listed)).toContain("buildL3SyncPayload(buildL3SyncOptions('listed', {")
    expect(body(listed)).toContain('buildL3ListedSyncBody(props.wpId, item)')
    expect(body(soe)).toContain("buildL3SyncPayload(buildL3SyncOptions('soe', {")
    expect(body(soe)).toContain('buildL3SoeBatchBody(props.wpId, items)')
    for (const src of [listed, soe]) expect(src).not.toMatch(/sheet_name:\s*'L3-note-/)
  })
})
