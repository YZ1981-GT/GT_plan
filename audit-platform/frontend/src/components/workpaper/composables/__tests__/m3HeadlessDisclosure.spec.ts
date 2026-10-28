/**
 * M3 库存股披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①挂载真实的上市披露 Tab（onMounted 经 useM3FormData 取回复、读回表格与说明并重算期末），调 Tab 的同步函数，
 * 截下它发出的载荷，与离屏 provider 发出的逐字节相同；夹具有真实数据 ②只读 M3- 条目、离屏不写底稿、不做「从审定表 /
 * 明细表带入」（那是带确认框的用户按钮）③写 五、56；国企口径没有库存股章节 ⇒ 回空、不发请求 ④没有已保存行时按默认行
 * ⑤章节保护命中不发请求 ⑥Tab 接线：默认行 / 重算 / 读回 / 快照都走 m3DisclosureForm。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), put: vi.fn(), apiGet: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn(),
}))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet, post: h.apiPost, put: h.apiPut } }))
vi.mock('element-plus', async (importOriginal) => ({
  ...(await importOriginal<typeof import('element-plus')>()),
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), alert: vi.fn() },
}))

import M3TabDisclosureListed from '../../m3/core/M3TabDisclosureListed.vue'
import { m3HeadlessProvider } from '../m3HeadlessDisclosure'
import { M3_SUBTABLE } from '../m3NoteSectionMap'
import { M_SYNC_URL, payloadFromMTab, type MResponseFixture } from './_mDisclosureTabHarness'

const J = JSON.stringify
const r = (item_id: string, remark: string | null) => ({ item_id, remark, conclusion: null })
const NOISE = [r('M2-disclosure-listed-capital-rows', '[]'), r('K3-disclosure-listed-rows', '[]')]

/** 已保存 3 行 + 两段说明（一段空）；另有 M3-1 / M3-2 审定数据（只有「带入」按钮才用，离屏不带入） */
const RESPONSES: MResponseFixture = [
  r('M3-disclosure-listed-treasury-rows', J([
    { item: '一、库存股合计', beginAmount: 5000000, repurchaseIncrease: 2000000, cancelDecrease: 1000000, endAmount: 0 },
    { item: '  其中：员工持股计划', beginAmount: 3000000, repurchaseIncrease: 2000000, cancelDecrease: 0, endAmount: 0 },
    { item: '  其他', beginAmount: 0, repurchaseIncrease: 0, cancelDecrease: 0, endAmount: 0 },
  ])),
  r('M3-disclosure-listed-purpose', '员工持股计划回购'),
  r('M3-disclosure-listed-execution', ''),
  r('M3-disclosure-listed-equity-impact', '减少每股净资产'),
  r('M3-M3-1-total-audited', '6000000'),
  r('M3-M3-2-row-1-data', J({ repurchaseAmount: 999, cancelAmount: 1, beginAmount: 2 })),
  ...NOISE,
]

const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-m3', wpCode: 'M3' }
const LISTED = { ...CTX, variant: 'listed' as const, applicableStandards: ['listed_standalone'] }
const SOE = { ...CTX, variant: 'soe' as const, applicableStandards: ['soe_standalone'] }

async function tabPayload(responses: MResponseFixture): Promise<any> {
  return payloadFromMTab(M3TabDisclosureListed, { apiGet: h.apiGet, post: h.post }, { wpId: 'wp-m3', responses })
}

describe('m3HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.post.mockResolvedValue({ rows_synced: 4, push_kept: [] })
  })

  it('上市：载荷与挂载的 Tab 逐字节相同，静默写 五、56、只读 M3- 条目、不写底稿、不带入审定表', async () => {
    const tabSent = await tabPayload(RESPONSES)
    h.post.mockClear()
    h.get.mockResolvedValue(RESPONSES)
    const out = await m3HeadlessProvider(LISTED)
    expect(out).toEqual({ sections: [{ section: '五、56', rows: 4, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-m3/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiPut).not.toHaveBeenCalled()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe(M_SYNC_URL)
    expect(cfg).toMatchObject({ _silent: true })
    expect(J(sent)).toBe(J(tabSent))
    expect(sent).toMatchObject({ wp_id: 'wp-m3', section_id: '五、56', current_standard: 'listed_standalone' })
    const rows = sent.sub_table_data[M3_SUBTABLE.main] as any[]
    // 期末按读回后的期初 + 回购 − 注销；审定表 / 明细表的数（6000000 / 999）没有被带入
    expect(rows.slice(0, 3)).toEqual([
      { label: '一、库存股合计', begin_amount: 5000000, increase: 2000000, decrease: 1000000, end_amount: 6000000 },
      { label: '其中：员工持股计划', begin_amount: 3000000, increase: 2000000, decrease: 0, end_amount: 5000000 },
      { label: '其他', begin_amount: 0, increase: 0, decrease: 0, end_amount: 0 },
    ])
    // 疑点（未改，见进度报告）：builder 合计把「一、库存股合计」与其「其中」明细一起加
    expect(rows.at(-1)).toMatchObject({ label: '合计', is_total: true })
    expect(sent.sub_table_data._note_texts).toEqual([
      { section: 'm3-listed-purpose', title: '库存股变动情况及原因', text: '员工持股计划回购' },
      { section: 'm3-listed-equity-impact', title: '股权激励回购比例', text: '减少每股净资产' },
    ])
  })

  it('国企口径没有库存股章节：回空、不发请求', async () => {
    h.get.mockResolvedValue(RESPONSES)
    expect(await m3HeadlessProvider(SOE)).toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('没有已保存行：按默认 5 行发出（与 Tab 相同）', async () => {
    const tabSent = await tabPayload(NOISE)
    h.post.mockClear()
    h.get.mockResolvedValue(NOISE)
    await m3HeadlessProvider(LISTED)
    const sent = h.post.mock.calls[0][1]
    expect(J(sent)).toBe(J(tabSent))
    expect(sent.sub_table_data[M3_SUBTABLE.main]).toHaveLength(6)
  })

  it('章节保护命中：不发请求，原因随结果回报', async () => {
    h.get.mockResolvedValue(RESPONSES)
    const out = await m3HeadlessProvider({ ...LISTED, sectionGuard: () => '附注 五、56 已有 1 格人工填写' })
    expect(h.post).not.toHaveBeenCalled()
    expect(out).toEqual({ sections: [{ section: '五、56', rows: 0, skipped: '附注 五、56 已有 1 格人工填写' }] })
  })

  it('Tab 接线：默认行 / 重算 / 读回 / 快照都调 m3DisclosureForm，组件内不再自拼', () => {
    const src = readFileSync(resolve(__dirname, '../../m3/core/M3TabDisclosureListed.vue'), 'utf-8')
    expect(src).toContain('const treasuryChangeRows = ref<M3TreasuryDisclosureRow[]>(createM3TreasuryRows())')
    expect(src).toContain('recalcM3TreasuryRows(treasuryChangeRows.value)')
    expect(src).toContain('const next = restoreM3TreasuryDisclosure(formData.allResponses.value, disclosureState())')
    const sync = src.slice(src.indexOf('async function syncToDisclosureNotes'))
    expect(sync).toMatch(/const payload = buildM3TabSyncPayload\(props\.wpId, disclosureState\(\)\)/)
    expect(src).not.toMatch(/buildM3SyncPayload\(|calcContraEquityEndBalance|JSON\.parse\(rowData/)
  })
})
