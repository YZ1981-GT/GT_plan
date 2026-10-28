/**
 * L2 应付利息披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①挂载真实的两个披露 Tab（自建 useL2FormData 读回复 → useL2Disclosure 聚合），调 Tab 的同步函数，Tab 发出的请求体
 * 与离屏 provider 发出的请求体逐字节相同；夹具有真实数据（分类表多类别有数、逾期表两行）②只读 L2- 条目、静默发出、
 * 不写底稿 ③两口径分别写 五、42 / 八、42，国企「其他」→「其他利息」、上市丢弃「其他」行 ④与 K3 / M1 共用章节：载荷只有
 * L2 的两张子表、不带 `_removed_table_keys` ⑤章节保护命中不发请求 ⑥Tab 接线：快照 / 请求体都调 l2DisclosureSync。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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

import L2TabDisclosureListed from '../../l2/core/L2TabDisclosureListed.vue'
import L2TabDisclosureSoe from '../../l2/core/L2TabDisclosureSoe.vue'
import { l2HeadlessProvider } from '../l2HeadlessDisclosure'
import { L2_LISTED_SUBTABLE, L2_SOE_SUBTABLE } from '../l2NoteSectionMap'
import { ownResponses, SYNC_URL, syncRequestsFromTab, type Resp } from './_lDisclosureTabHarness'

const J = JSON.stringify
const DETAIL = J([
  { source: '分期付息到期还本的长期借款利息', creditor: '工商银行', audited: 1200, adjustedBegin: 800 },
  { source: '企业债券利息', endBalance: 300, adjustedBegin: 100 },
  { source: '短期借款应付利息', creditor: '建设银行', audited: 50, adjustedBegin: 20, isOverdue: true, overdueReason: '资金紧张' },
  { source: '优先股工具1', audited: 70, adjustedBegin: 10 },
  { source: '永续债工具2', audited: 30 },
  { source: '其他', contractName: '其他借款合同', audited: 5, overdueMonths: 2 },
])
const RESPONSES: Resp[] = [
  { item_id: 'L2-L2-2-rows', remark: DETAIL, conclusion: null },
  { item_id: 'L2-L2-1-adjudicated_amount', remark: '1655', conclusion: null },
  { item_id: 'K3-disclosure-listed-interest', remark: J([{ label: '应付利息', endAmount: 9 }]), conclusion: null },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-l2', wpCode: 'L2', applicableStandards: [] as string[] }
const WP = resolve(__dirname, '../..')

/** Tab 路径：挂载真实 Tab（useL2FormData 经 apiProxy 读回复）→ 调它的同步函数 → 截下请求体 */
async function tabBody(variant: 'listed' | 'soe'): Promise<any> {
  const [req] = await syncRequestsFromTab(variant === 'listed' ? L2TabDisclosureListed : L2TabDisclosureSoe, h.apiPost, { wpId: 'wp-l2' })
  expect(req.url).toBe(SYNC_URL)
  return req.body
}

function rows(sent: any, table: string): any[] {
  return sent.sub_table_data[table] as any[]
}

describe('l2HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.apiGet.mockImplementation(async (url: string) => (url.includes('checklist-responses') ? RESPONSES : {}))
    h.apiPost.mockResolvedValue({})
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 9, push_kept: [{ table: '应付利息' }] })
  })

  it('上市：请求体与挂载的 Tab 逐字节相同，静默写 五、42、不写底稿；只推两张子表、丢弃模板没有的「其他」行', async () => {
    const tabSent = await tabBody('listed')
    const out = await l2HeadlessProvider({ ...CTX, variant: 'listed' })
    expect(out).toEqual({ sections: [{ section: '五、42', rows: 9, kept: 1 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-l2/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiPut).not.toHaveBeenCalled()
    expect(h.post).toHaveBeenCalledTimes(1)
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe(SYNC_URL)
    expect(cfg).toMatchObject({ _silent: true })
    expect(J(sent)).toBe(J(tabSent))
    expect(sent).toMatchObject({ wp_id: 'wp-l2', section_id: '五、42', current_standard: 'listed_standalone' })
    const interest = rows(sent, L2_LISTED_SUBTABLE.interest)
    expect(interest.find((r) => r.label === '分期付息到期还本的长期借款利息')).toMatchObject({ end_amount: 1200, prior_amount: 800 })
    expect(interest.find((r) => r.label === '划分为金融负债的优先股\\永续债利息')).toMatchObject({ end_amount: 100, prior_amount: 10 })
    expect(interest.some((r) => r.label === '其他')).toBe(false)
    expect(interest.at(-1)).toMatchObject({ label: '合计', end_amount: 1655 })
    expect(rows(sent, L2_LISTED_SUBTABLE.overdue)).toEqual([
      { label: '建设银行', overdue_amount: 50, overdue_reason: '资金紧张' },
      { label: '其他借款合同', overdue_amount: 5, overdue_reason: '-' },
    ])
    expect(Object.keys(sent.sub_table_data).sort()).toEqual([L2_LISTED_SUBTABLE.interest, L2_LISTED_SUBTABLE.overdue].sort())
    expect(sent.sub_table_data._removed_table_keys).toBeUndefined()
  })

  it('国企：请求体与挂载的 Tab 逐字节相同，写 八、42；「其他」→「其他利息」', async () => {
    const tabSent = await tabBody('soe')
    const out = await l2HeadlessProvider({ ...CTX, variant: 'soe' })
    expect(out.sections.map((s) => s.section)).toEqual(['八、42'])
    const sent = h.post.mock.calls[0][1]
    expect(J(sent)).toBe(J(tabSent))
    expect(sent.current_standard).toBe('soe_standalone')
    expect(rows(sent, L2_SOE_SUBTABLE.interest).find((r) => r.label === '其他利息')).toMatchObject({ end_amount: 5 })
    expect(rows(sent, L2_SOE_SUBTABLE.overdue)).toHaveLength(2)
    expect(sent.sub_table_data._removed_table_keys).toBeUndefined()
  })

  it('只读本底稿 L2- 条目：别的底稿条目不影响载荷（与 Tab 读回同口径）', async () => {
    const withNoise = [...RESPONSES, { item_id: 'L20-L2-2-rows', remark: J([{ source: '企业债券利息', audited: 999 }]), conclusion: null }]
    h.get.mockResolvedValue(withNoise)
    await l2HeadlessProvider({ ...CTX, variant: 'listed' })
    const own = ownResponses('L2-', withNoise)
    expect(own.map((r) => r.item_id)).toEqual(['L2-L2-2-rows', 'L2-L2-1-adjudicated_amount'])
    const bond = rows(h.post.mock.calls[0][1], L2_LISTED_SUBTABLE.interest).find((r) => r.label === '企业债券利息')
    expect(bond.end_amount).toBe(300)
  })

  it('章节保护命中：不发请求，原因随结果回报', async () => {
    const out = await l2HeadlessProvider({ ...CTX, variant: 'soe', sectionGuard: () => '附注 八、42 已有 4 格人工填写' })
    expect(h.post).not.toHaveBeenCalled()
    expect(out).toEqual({ sections: [{ section: '八、42', rows: 0, skipped: '附注 八、42 已有 4 格人工填写' }] })
  })

  it('Tab 接线：同步函数调共用快照 / 请求体，组件内不再自拼', () => {
    for (const [file, variant] of [['L2TabDisclosureListed.vue', 'listed'], ['L2TabDisclosureSoe.vue', 'soe']] as const) {
      const src = readFileSync(resolve(WP, `l2/core/${file}`), 'utf-8')
      const body = src.slice(src.indexOf('async function syncToDisclosureNotes'))
      expect(body).toContain('buildL2DisclosureSnapshot(disclosureTableData.value, overdueRows.value)')
      expect(body).toContain(`buildL2SyncPayload('${variant}', snap.interestRows, snap.overdueRows)`)
      expect(body).toContain(`buildL2SyncRequestBody('${variant}', props.wpId, payload)`)
      expect(src).not.toMatch(/sheet_name:\s*L2_DISCLOSURE_SHEET_NAME/)
    }
  })
})
