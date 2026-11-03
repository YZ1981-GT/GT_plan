/**
 * L1 短期借款披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①按外壳同样方式建表单（`useL1FormData` + `selfLoad()`，经 apiProxy 读回复）注入、挂载真实的两个披露 Tab，调 Tab 的
 * 同步函数，Tab 发出的请求体与离屏 provider 发出的逐字节相同；外壳两种时序（先加载再挂 Tab / 先挂 Tab 再加载）都相同
 * ②夹具有真实数据（审定表 4 类派生分类表、逾期表、审计结论）③只读 L1- 条目、静默、不写底稿 ④两口径写 五、33 / 八、33，逾期表为空
 * 时同一 builder 把逾期表放进 `_removed_table_keys` ⑤章节保护命中不发请求 ⑥接线：Tab 调共用入参 / 请求体，外壳 / selfLoad 走同一个
 * `applyResponses`。
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

import L1TabDisclosureListed from '../../l1/core/L1TabDisclosureListed.vue'
import L1TabDisclosureSoe from '../../l1/core/L1TabDisclosureSoe.vue'
import { l1HeadlessProvider } from '../l1HeadlessDisclosure'
import { useL1FormData } from '@/composables/useL1FormData'
import { L1_SUBTABLE } from '../l1NoteSectionMap'
import { SYNC_URL, syncRequestsFromTab, type Resp } from './_lDisclosureTabHarness'

const J = JSON.stringify
const OVERDUE = { item_id: 'L1-disclosure-overdue-rows', remark: J([
  { borrower: '甲银行', endBalance: 300, rate: 4.35, overdueTime: '90天', penaltyRate: 6.5 },
  { borrower: '', endBalance: 0, rate: 0, overdueTime: '', penaltyRate: 0 },
]), conclusion: null }
const RESPONSES: Resp[] = [
  // 审定表 L1-1（1 信用 / 2 抵押 / 3 保证 / 4 质押）
  { item_id: 'L1-adj-1-beginUnadjusted', remark: '800', conclusion: null },
  { item_id: 'L1-adj-1-endUnadjusted', remark: '1000', conclusion: null },
  { item_id: 'L1-adj-1-endAje', remark: '50', conclusion: null },
  { item_id: 'L1-adj-2-beginUnadjusted', remark: '1500', conclusion: null },
  { item_id: 'L1-adj-2-beginRje', remark: '-100', conclusion: null },
  { item_id: 'L1-adj-2-endUnadjusted', remark: '2000', conclusion: null },
  { item_id: 'L1-adj-4-endUnadjusted', remark: '600', conclusion: null },
  { item_id: 'L1-adj-4-endRje', remark: '40', conclusion: null },
  OVERDUE,
  { item_id: 'L1-disclosure-listed-conclusion', remark: '上市：分类披露完整', conclusion: null },
  { item_id: 'L1-disclosure-soe-conclusion', remark: '国企：逾期已披露', conclusion: null },
  { item_id: 'L1-disclosure-listed-note', remark: '抵押物为厂房', conclusion: null },
  { item_id: 'L1-disclosure-listed-transfer-in', remark: '120', conclusion: null },
  { item_id: 'L1-2-rows', remark: J([{ rowId: 'r1', loanType: '信用借款', bank: '甲银行', beginning: 800, creditAmount: 200 }]), conclusion: null },
  { item_id: 'L2-L2-2-rows', remark: J([{ source: '短期借款应付利息', audited: 9 }]), conclusion: null },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-l1', wpCode: 'L1', applicableStandards: [] as string[] }
const WP = resolve(__dirname, '../..')
const SRC = resolve(WP, '../..')

/**
 * Tab 路径：按外壳同样方式建表单（useL1FormData + selfLoad）注入 → 挂载真实 Tab → 调它的同步函数 → 截下请求体。
 * `loadFirst`：外壳没有 htmlData 时先加载完再挂 Tab；有 htmlData 时先挂 Tab、加载在后（Tab 靠 watch 补读回）。
 */
async function tabBody(variant: 'listed' | 'soe', list: Resp[], loadFirst = true): Promise<any> {
  h.apiGet.mockImplementation(async (url: string) => (url.includes('checklist-responses') ? list : {}))
  const scope = effectScope(true)
  const formData = scope.run(() => useL1FormData(ref('wp-l1'), ref('p1'), ref(false)))!
  if (loadFirst) await formData.selfLoad()
  const [req] = await syncRequestsFromTab(variant === 'listed' ? L1TabDisclosureListed : L1TabDisclosureSoe, h.post, {
    wpId: 'wp-l1',
    provide: { l1FormData: formData, [routerKey as symbol]: { push: vi.fn() } },
    afterMount: loadFirst ? undefined : () => formData.selfLoad(),
  })
  scope.stop()
  h.post.mockClear()
  h.apiGet.mockClear()
  expect(req.url).toBe(SYNC_URL)
  return req.body
}

function rows(sent: any, table: string): any[] {
  return sent.sub_table_data[table] as any[]
}

describe('l1HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 7, push_kept: [] })
  })

  it('上市：请求体与挂载的 Tab 逐字节相同（外壳两种加载时序都相同），静默写 五、33、不写底稿', async () => {
    const tabSent = await tabBody('listed', RESPONSES)
    expect(J(await tabBody('listed', RESPONSES, false))).toBe(J(tabSent))
    const out = await l1HeadlessProvider({ ...CTX, variant: 'listed' })
    expect(out).toEqual({ sections: [{ section: '五、33', rows: 7, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-l1/checklist-responses', expect.anything())
    expect(h.apiGet).not.toHaveBeenCalled()
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiPut).not.toHaveBeenCalled()
    expect(h.post).toHaveBeenCalledTimes(1)
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe(SYNC_URL)
    expect(cfg).toMatchObject({ _silent: true })
    expect(J(sent)).toBe(J(tabSent))
    expect(sent).toMatchObject({ wp_id: 'wp-l1', sheet_name: 'L1-note-listed', section_id: '五、33', current_standard: 'listed_standalone' })
    expect(rows(sent, L1_SUBTABLE.category)).toEqual([
      { label: '信用借款', values: [1050, 800] },
      { label: '抵押借款', values: [2000, 1400] },
      { label: '保证借款', values: [0, 0] },
      { label: '质押借款', values: [640, 0] },
      { label: '合  计', values: [3690, 2200], is_total: true },
    ])
    expect(rows(sent, L1_SUBTABLE.overdue.listed)).toEqual([{ label: '甲银行', values: [300, 4.35, '90天', 6.5] }])
    expect(sent.sub_table_data._removed_table_keys).toEqual(['逾期借款情况'])
    expect(sent.sub_table_data._note_texts).toEqual([{ section: 'conclusion', title: '说明', text: '上市：分类披露完整' }])
  })

  it('国企：请求体与挂载的 Tab 逐字节相同，写 八、33（逾期表 3 列、国企结论）', async () => {
    const tabSent = await tabBody('soe', RESPONSES)
    const out = await l1HeadlessProvider({ ...CTX, variant: 'soe' })
    expect(out.sections.map((s) => s.section)).toEqual(['八、33'])
    const sent = h.post.mock.calls[0][1]
    expect(J(sent)).toBe(J(tabSent))
    expect(sent.current_standard).toBe('soe_standalone')
    expect(rows(sent, L1_SUBTABLE.overdue.soe)).toEqual([{ label: '甲银行', values: [300, 4.35] }])
    expect(sent.sub_table_data._note_texts[0].text).toBe('国企：逾期已披露')
  })

  it('国企没有逾期行：同一 builder 把逾期表放进 _removed_table_keys、列头不声明逾期表（与 Tab 相同）', async () => {
    const list = RESPONSES.filter((r) => r.item_id !== OVERDUE.item_id)
    const tabSent = await tabBody('soe', list)
    h.get.mockResolvedValue(list)
    await l1HeadlessProvider({ ...CTX, variant: 'soe' })
    const sent = h.post.mock.calls[0][1]
    expect(J(sent)).toBe(J(tabSent))
    expect(sent.sub_table_data._removed_table_keys).toEqual(['逾期借款情况', L1_SUBTABLE.overdue.soe])
    expect(Object.keys(sent.columns)).toEqual([L1_SUBTABLE.category])
  })

  it('章节保护命中：不发请求，原因随结果回报', async () => {
    const out = await l1HeadlessProvider({ ...CTX, variant: 'listed', sectionGuard: () => '附注 五、33 已有 1 格人工填写' })
    expect(h.post).not.toHaveBeenCalled()
    expect(out).toEqual({ sections: [{ section: '五、33', rows: 0, skipped: '附注 五、33 已有 1 格人工填写' }] })
  })

  it('接线：Tab 调共用入参 / 请求体；外壳 selfLoad 与离屏走同一个 applyResponses', () => {
    for (const [file, variant] of [['L1TabDisclosureListed.vue', 'listed'], ['L1TabDisclosureSoe.vue', 'soe']] as const) {
      const src = readFileSync(resolve(WP, `l1/core/${file}`), 'utf-8')
      const body = src.slice(src.indexOf('async function syncToDisclosureNotes'))
      expect(body).toContain(`buildL1SyncPayload(buildL1SyncOptions('${variant}', {`)
      expect(body).toContain(`buildL1SyncRequestBody('${variant}', props.wpId, payload)`)
      expect(src).not.toMatch(/sheet_name:\s*'L1-note-/)
      expect(src).toContain("inject<ReturnType<typeof useL1FormData>>('l1FormData')!")
    }
    const shell = readFileSync(resolve(WP, 'GtL1ShortTermLoans.vue'), 'utf-8')
    expect(shell).toContain('const formData = useL1FormData(')
    expect(shell).toContain("provide('l1FormData', formData)")
    expect(shell).toContain('await formData.selfLoad()')
    const formData = readFileSync(resolve(SRC, 'composables/useL1FormData.ts'), 'utf-8')
    const selfLoad = formData.slice(formData.indexOf('async function selfLoad'), formData.indexOf('// ─── Parse helpers'))
    expect(selfLoad).toContain('applyResponses(responses)')
  })
})
