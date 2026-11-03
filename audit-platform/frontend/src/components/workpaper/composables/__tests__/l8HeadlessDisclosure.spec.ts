/**
 * L8 财务费用披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①挂载真实的两个披露 Tab（自建 useL8FormData 经 apiProxy 读回复 → onMounted _restoreData），调 Tab 的同步函数，Tab 发出
 * 的请求体与离屏 provider 发出的请求体逐字节相同；夹具有真实数据（上市新格式两期 8 个录入键 + 资本化说明；国企旧格式自造行按
 * 行名映射）②上市旧格式 / 已存损坏 / 没有已存同样等价 ③只读 L8- 条目、静默、不写底稿、不取试算表发生额 ④上市写 五、67 带利息
 * 资本化说明，国企写 八、68、专项事项与文本说明不进附注 ⑤章节保护命中不发请求 ⑥Tab 接线：读回 / 快照都调 l8DisclosureTabState。
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

import L8TabDisclosureListed from '../../l8/core/L8TabDisclosureListed.vue'
import L8TabDisclosureSoe from '../../l8/core/L8TabDisclosureSoe.vue'
import { l8HeadlessProvider } from '../l8HeadlessDisclosure'
import { L8_LISTED_SUBTABLE, L8_SOE_SUBTABLE } from '../l8NoteSectionMap'
import { SYNC_URL, syncRequestsFromTab, type Resp } from './_lDisclosureTabHarness'

const J = JSON.stringify
const CAPITALIZATION = '利息资本化金额已计入在建工程，本期资本化率为 4.5%（上期：4.2%）'
const RESPONSES: Resp[] = [
  {
    item_id: 'L8-disclosure-listed-data',
    remark: J({
      current: {
        interestTotal: 1000, interestCapitalized: 100, interestIncome: 50, acceptanceDiscount: 20,
        exchangeLoss: 30, exchangeGain: 10, exchangeCapitalized: 5, feeAndOther: 15,
      },
      prior: { interestTotal: 800, interestIncome: '40', feeAndOther: 12 },
    }),
    conclusion: null,
  },
  { item_id: 'L8-disclosure-listed-capitalization', remark: CAPITALIZATION, conclusion: null },
  { item_id: 'L8-disclosure-listed-note', remark: '上市文本说明（不进附注）', conclusion: null },
  { item_id: 'L8-disc-listed-conclusion', remark: '上市核对一致', conclusion: null },
  {
    item_id: 'L8-disclosure-soe-data',
    remark: J([
      { item: '利息费用', currentAmount: 500, priorAmount: 400 },
      { item: '减：利息资本化', currentAmount: 50, priorAmount: 0 },
      { item: '其中：金融机构借款利息', currentAmount: 300, priorAmount: 200 },
      { item: '减：利息收入', currentAmount: 20, priorAmount: 10 },
      { item: '手续费', currentAmount: 8, priorAmount: 6 },
    ]),
    conclusion: null,
  },
  { item_id: 'L8-disclosure-soe-extra', remark: '资金占用费 12 万（不进附注）', conclusion: null },
  { item_id: 'L8-2-full-data', remark: J([{ key: 'GTROW-L82-0001', monthly: [1] }]), conclusion: null },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-l8', wpCode: 'L8', applicableStandards: [] as string[] }
const WP = resolve(__dirname, '../..')

let responses: Resp[] = RESPONSES

/** Tab 路径：挂载真实 Tab（useL8FormData 经 apiProxy 读回复 → _restoreData）→ 调它的同步函数 → 截下请求体 */
async function tabBody(variant: 'listed' | 'soe'): Promise<any> {
  const [req] = await syncRequestsFromTab(variant === 'listed' ? L8TabDisclosureListed : L8TabDisclosureSoe, h.post, {
    wpId: 'wp-l8',
    provide: { [routerKey as symbol]: { push: vi.fn() } },
  })
  expect(req.url).toBe(SYNC_URL)
  h.post.mockClear()
  h.apiGet.mockClear()
  return req.body
}

function row(sent: any, table: string, label: string): any {
  return (sent.sub_table_data[table] as any[]).find((r) => r.label === label)
}

describe('l8HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    responses = RESPONSES
    h.apiGet.mockImplementation(async (url: string) => (url.includes('checklist-responses') ? responses : {}))
    h.get.mockImplementation(async () => responses)
    h.post.mockResolvedValue({ rows_synced: 12, push_kept: [] })
  })

  it('上市：请求体与挂载的 Tab 逐字节相同，静默写 五、67、不写底稿；派生行读时推导，带利息资本化说明', async () => {
    const tabSent = await tabBody('listed')
    const out = await l8HeadlessProvider({ ...CTX, variant: 'listed' })
    expect(out).toEqual({ sections: [{ section: '五、67', rows: 12, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-l8/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiPut).not.toHaveBeenCalled()
    expect(h.apiGet).not.toHaveBeenCalled()
    expect(h.post).toHaveBeenCalledTimes(1)
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe(SYNC_URL)
    expect(cfg).toMatchObject({ _silent: true })
    expect(J(sent)).toBe(J(tabSent))
    expect(sent).toMatchObject({
      wp_id: 'wp-l8', sheet_name: '附注披露信息（上市公司）', section_id: '五、67', current_standard: 'listed_standalone',
    })
    const T = L8_LISTED_SUBTABLE.main
    expect(sent.sub_table_data[T]).toHaveLength(12)
    expect(row(sent, T, '利息费用')).toEqual({ label: '利息费用', current_amount: 900, prior_amount: 800, is_subtotal: true })
    expect(row(sent, T, '减：利息收入')).toEqual({ label: '减：利息收入', current_amount: 50, prior_amount: 40 })
    expect(row(sent, T, '汇兑净损失')).toMatchObject({ current_amount: 15, prior_amount: 0 })
    expect(row(sent, T, '合计')).toEqual({ label: '合计', current_amount: 900, prior_amount: 772, is_total: true })
    expect(sent.sub_table_data._note_texts).toEqual([
      { section: 'l8-listed-capitalization', title: '利息资本化说明', text: CAPITALIZATION },
    ])
  })

  it('国企：请求体与挂载的 Tab 逐字节相同，写 八、68；旧格式按行名映射，源模板没有的行丢弃；专项事项不进附注', async () => {
    const tabSent = await tabBody('soe')
    const out = await l8HeadlessProvider({ ...CTX, variant: 'soe' })
    expect(out.sections.map((s) => s.section)).toEqual(['八、68'])
    const sent = h.post.mock.calls[0][1]
    expect(J(sent)).toBe(J(tabSent))
    expect(sent).toMatchObject({ sheet_name: '附注披露信息（国企）', section_id: '八、68', current_standard: 'soe_standalone' })
    const T = L8_SOE_SUBTABLE.main
    expect(row(sent, T, '利息费用总额')).toMatchObject({ current_amount: 500, prior_amount: 400 })
    expect(row(sent, T, '减：利息资本化')).toMatchObject({ current_amount: 50, prior_amount: 0 })
    expect(row(sent, T, '合计')).toEqual({ label: '合计', current_amount: 438, prior_amount: 396, is_total: true })
    expect(Object.keys(sent.sub_table_data)).toEqual([T])
    expect(J(sent)).not.toContain('资金占用费')
  })

  it('上市旧格式 / 已存损坏 / 没有已存：与 Tab 读回同一份', async () => {
    const cases: Resp[][] = [
      [
        {
          item_id: 'L8-disclosure-listed-data',
          remark: J([
            { item: '利息费用', currentAmount: 70, priorAmount: 60 },
            { item: '  其中：利息资本化金额', currentAmount: 7, priorAmount: 6 },
            { item: '汇兑损益（净损失以"+"号列示）', currentAmount: 3, priorAmount: 'x' },
            { item: '自造行', currentAmount: 999, priorAmount: 999 },
          ]),
          conclusion: null,
        },
      ],
      [
        { item_id: 'L8-disclosure-listed-data', remark: '{坏的', conclusion: null },
        { item_id: 'L8-disclosure-listed-capitalization', remark: '只有说明', conclusion: null },
      ],
      [],
    ]
    const totals: any[] = []
    for (const list of cases) {
      responses = list
      const tabSent = await tabBody('listed')
      await l8HeadlessProvider({ ...CTX, variant: 'listed' })
      const sent = h.post.mock.calls[0][1]
      expect(J(sent)).toBe(J(tabSent))
      totals.push([row(sent, L8_LISTED_SUBTABLE.main, '合计'), sent.sub_table_data._note_texts])
      h.post.mockClear()
    }
    expect(totals[0][0]).toMatchObject({ current_amount: 66, prior_amount: 54 })
    expect(totals[1]).toEqual([
      { label: '合计', current_amount: 0, prior_amount: 0, is_total: true },
      [{ section: 'l8-listed-capitalization', title: '利息资本化说明', text: '只有说明' }],
    ])
    expect(totals[2][1]).toBeUndefined()
  })

  it('章节保护命中：不发请求，原因随结果回报', async () => {
    const out = await l8HeadlessProvider({ ...CTX, variant: 'soe', sectionGuard: () => '附注 八、68 已有 5 格人工填写' })
    expect(h.post).not.toHaveBeenCalled()
    expect(out).toEqual({ sections: [{ section: '八、68', rows: 0, skipped: '附注 八、68 已有 5 格人工填写' }] })
  })

  it('Tab 接线：读回 / 快照都调 l8DisclosureTabState，组件内不再自算', () => {
    for (const [file, v] of [['L8TabDisclosureListed.vue', 'listed'], ['L8TabDisclosureSoe.vue', 'soe']] as const) {
      const src = readFileSync(resolve(WP, `l8/core/${file}`), 'utf-8')
      const sync = src.slice(src.indexOf('async function syncToDisclosureNotes'))
      expect(sync).toContain(`buildL8SyncPayload(props.wpId, buildL8DisclosureSnapshot('${v}', {`)
      const restore = src.slice(src.indexOf('function _restoreData'))
      expect(restore).toContain(`restoreL8Disclosure('${v}', formData.allResponses.value)`)
      expect(src).toContain(`const DATA_ITEM_ID = L8_DISCLOSURE_DATA_ITEM_ID.${v}`)
      expect(src).not.toMatch(/LEGACY_LABEL_TO_KEY|JSON\.parse\(data\.remark\)/)
    }
  })
})
