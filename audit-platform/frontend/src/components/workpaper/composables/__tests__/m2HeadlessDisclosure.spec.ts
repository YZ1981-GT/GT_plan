/**
 * M2 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①挂载真实的两个披露 Tab（onMounted 经 useM2FormData 取回复、读回表格与说明并重算期末 / 占比），调 Tab 的同步
 * 函数，截下它发出的载荷，与离屏 provider 发出的逐字节相同；夹具有真实数据（含旧字段 increaseShares 兼容、合计行剔除、
 * 说明文本）②只读 M2- 条目、离屏不写底稿 ③两口径分别写 五、53 / 八、58 ④没有已保存行时按默认行（与 Tab 同）
 * ⑤章节保护命中不发请求 ⑥Tab 接线：默认行 / 重算 / 读回 / 快照都走 m2DisclosureForm。
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
}))

import M2TabDisclosureListed from '../../m2/core/M2TabDisclosureListed.vue'
import M2TabDisclosureSoe from '../../m2/core/M2TabDisclosureSoe.vue'
import { m2HeadlessProvider } from '../m2HeadlessDisclosure'
import { M2_SUBTABLE } from '../m2NoteSectionMap'
import { M_SYNC_URL, payloadFromMTab, type MResponseFixture } from './_mDisclosureTabHarness'

const J = JSON.stringify
const r = (item_id: string, remark: string | null) => ({ item_id, remark, conclusion: null })
const NOISE = [r('M20-disclosure-listed-capital-rows', '[]'), r('M3-disclosure-listed-treasury-rows', '[]')]

/** 上市：已保存 4 行（其中一行是旧版字段 increaseShares、缺其余列），「三、股份总数」行不发；两段说明 + 一段空说明 */
const LISTED_RESPONSES: MResponseFixture = [
  r('M2-disclosure-listed-capital-rows', J([
    { item: '一、有限售条件股份', beginShares: 1000, issueNew: 200, bonusShares: 0, reserveToShares: 0, otherChange: 0, endShares: 0, ratio: 0 },
    { item: '  1.国家持股', beginShares: 600, increaseShares: 100 },
    { item: '二、无限售条件股份', beginShares: 4000, issueNew: 0, bonusShares: 400, reserveToShares: 300, otherChange: -50, endShares: 0, ratio: 0 },
    { item: '三、股份总数', beginShares: 5000, issueNew: 200, bonusShares: 400, reserveToShares: 300, otherChange: -50, endShares: 0, ratio: 0 },
  ])),
  r('M2-disclosure-listed-restricted', '限售股份说明'),
  r('M2-disclosure-listed-change-reason', '本期公积金转增股本'),
  r('M2-disclosure-listed-eps', ''),
  ...NOISE,
]

/** 国企：已保存 3 行（含合计），说明两段 */
const SOE_RESPONSES: MResponseFixture = [
  r('M2-disclosure-soe-capital-rows', J([
    { item: '一、国家资本', beginAmount: 6000000, increaseAmount: 1000000, decreaseAmount: 0, endAmount: 0, ratio: 0 },
    { item: '三、法人资本', beginAmount: 4000000, increaseAmount: 0, decreaseAmount: 500000, endAmount: 0, ratio: 0 },
    { item: '合计', beginAmount: 0, increaseAmount: 0, decreaseAmount: 0, endAmount: 0, ratio: 0 },
  ])),
  r('M2-disclosure-soe-state-capital', '国有资本出资说明'),
  r('M2-disclosure-soe-method', '货币出资'),
  ...NOISE,
]

const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-m2', wpCode: 'M2' }
const LISTED = { ...CTX, variant: 'listed' as const, applicableStandards: ['listed_standalone'] }
const SOE = { ...CTX, variant: 'soe' as const, applicableStandards: ['soe_standalone'] }

async function tabPayload(variant: 'soe' | 'listed', responses: MResponseFixture): Promise<any> {
  const Comp = variant === 'soe' ? M2TabDisclosureSoe : M2TabDisclosureListed
  return payloadFromMTab(Comp, { apiGet: h.apiGet, post: h.post }, { wpId: 'wp-m2', responses })
}

describe('m2HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.post.mockResolvedValue({ rows_synced: 4, push_kept: [{ table: M2_SUBTABLE.listed }] })
  })

  it('上市：载荷与挂载的 Tab 逐字节相同，静默写 五、53、只读 M2- 条目、不写底稿', async () => {
    const tabSent = await tabPayload('listed', LISTED_RESPONSES)
    h.post.mockClear()
    h.get.mockResolvedValue(LISTED_RESPONSES)
    const out = await m2HeadlessProvider(LISTED)
    expect(out).toEqual({ sections: [{ section: '五、53', rows: 4, kept: 1 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-m2/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiPut).not.toHaveBeenCalled()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe(M_SYNC_URL)
    expect(cfg).toMatchObject({ _silent: true })
    expect(J(sent)).toBe(J(tabSent))
    const rows = sent.sub_table_data[M2_SUBTABLE.listed] as any[]
    expect(rows.map((x) => x.label)).toEqual(['一、有限售条件股份', '1.国家持股', '二、无限售条件股份', '股份总数'])
    // 旧字段 increaseShares → 发行新股；缺的列按 0
    expect(rows[1]).toMatchObject({ begin_amount: 600, issue_new: 100, bonus_shares: 0, subtotal_change: 100, end_amount: 700 })
    expect(rows[2]).toMatchObject({ subtotal_change: 650, end_amount: 4650 })
    expect(rows[3]).toMatchObject({ begin_amount: 5600, subtotal_change: 950, end_amount: 6550, is_total: true })
    expect(sent.sub_table_data._note_texts).toEqual([
      { section: 'm2-listed-restricted', title: '限售股份说明', text: '限售股份说明' },
      { section: 'm2-listed-change-reason', title: '股本变动原因说明', text: '本期公积金转增股本' },
    ])
  })

  it('国企：载荷与挂载的 Tab 逐字节相同，写 八、58（比例来自读回后的重算）', async () => {
    const tabSent = await tabPayload('soe', SOE_RESPONSES)
    h.post.mockClear()
    h.get.mockResolvedValue(SOE_RESPONSES)
    const out = await m2HeadlessProvider(SOE)
    expect(out.sections.map((s) => s.section)).toEqual(['八、58'])
    const sent = h.post.mock.calls[0][1]
    expect(J(sent)).toBe(J(tabSent))
    expect(sent).toMatchObject({ section_id: '八、58', current_standard: 'soe_standalone' })
    expect(sent.sub_table_data[M2_SUBTABLE.soe]).toEqual([
      { label: '一、国家资本', begin_amount: 6000000, begin_ratio: '66.67', increase: 1000000, decrease: 0, end_amount: 7000000, end_ratio: '66.67' },
      { label: '三、法人资本', begin_amount: 4000000, begin_ratio: '33.33', increase: 0, decrease: 500000, end_amount: 3500000, end_ratio: '33.33' },
      { label: '合计', begin_amount: 10000000, begin_ratio: '100.00', increase: 1000000, decrease: 500000, end_amount: 10500000, end_ratio: '100.00', is_total: true },
    ])
    expect(sent.sub_table_data._note_texts.map((t: any) => t.section)).toEqual(['m2-soe-state-capital', 'm2-soe-method'])
  })

  it('没有已保存行：两版都按默认行发出（与 Tab 相同）', async () => {
    for (const [variant, ctx] of [['listed', LISTED], ['soe', SOE]] as const) {
      const tabSent = await tabPayload(variant, NOISE)
      h.post.mockClear()
      h.get.mockResolvedValue(NOISE)
      await m2HeadlessProvider(ctx)
      const sent = h.post.mock.calls[0][1]
      expect(J(sent), variant).toBe(J(tabSent))
      // 默认 11 行去掉表格自带的合计行，再加 builder 自算的合计行
      expect(Object.values(sent.sub_table_data)[0], variant).toHaveLength(11)
      expect(sent.sub_table_data._note_texts, variant).toBeUndefined()
    }
  })

  it('章节保护命中：不发请求，原因随结果回报', async () => {
    h.get.mockResolvedValue(SOE_RESPONSES)
    const out = await m2HeadlessProvider({ ...SOE, sectionGuard: () => '附注 八、58 已有 1 格人工填写' })
    expect(h.post).not.toHaveBeenCalled()
    expect(out).toEqual({ sections: [{ section: '八、58', rows: 0, skipped: '附注 八、58 已有 1 格人工填写' }] })
  })

  it('Tab 接线：默认行 / 重算 / 读回 / 快照都调 m2DisclosureForm，组件内不再自拼', () => {
    const dir = resolve(__dirname, '../../m2/core')
    for (const [file, v] of [['M2TabDisclosureListed.vue', 'Listed'], ['M2TabDisclosureSoe.vue', 'Soe']] as const) {
      const src = readFileSync(resolve(dir, file), 'utf-8')
      expect(src, file).toContain(`const capitalChangeRows = ref<M2${v}CapitalRow[]>(createM2${v}CapitalRows())`)
      expect(src, file).toContain(`recalcM2${v}Rows(capitalChangeRows.value)`)
      expect(src, file).toContain(`const next = restoreM2${v}Disclosure(formData.allResponses.value, disclosureState())`)
      const sync = src.slice(src.indexOf('async function syncToDisclosureNotes'))
      expect(sync, file).toMatch(new RegExp(`const payload = buildM2${v}TabSyncPayload\\(props\\.wpId, disclosureState\\(\\)\\)`))
      expect(src, file).not.toMatch(/buildM2(?:Listed|Soe)SyncPayload\(|JSON\.parse\(|\.filter\(\(r\) => r\.item !==/)
    }
  })
})
