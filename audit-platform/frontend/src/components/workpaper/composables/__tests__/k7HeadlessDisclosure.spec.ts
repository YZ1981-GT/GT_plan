/**
 * K7 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①挂载真实的两个披露 Tab（onMounted 读回复 + 从 K7-1 自动取数），调 Tab 的同步函数，Tab 发出的载荷与离屏
 * provider 发出的载荷逐字节相同；夹具有真实数据（已保存行 / 默认行 + 自动取数 / 政府补助明细 / 说明都非空）
 * ②只读 K7- 条目、离屏不写底稿 ③两口径分别写 五、51 / 八、56 ④章节保护命中不发请求 ⑤Tab 接线：读回复、自动取数、
 * 快照都走 k7DisclosureSnapshot，组件内不再自拼。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<typeof import('element-plus')>()
  return {
    ...actual,
    ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
    ElMessageBox: { confirm: vi.fn() },
  }
})

import K7TabDisclosureListed from '../../k7/core/K7TabDisclosureListed.vue'
import K7TabDisclosureSoe from '../../k7/core/K7TabDisclosureSoe.vue'
import { k7HeadlessProvider } from '../k7HeadlessDisclosure'
import { K7_SUBTABLE } from '../k7NoteSectionMap'
import { payloadFromTab, SYNC_URL } from './_kDisclosureTabHarness'

const J = JSON.stringify
const AUDITED_BY_TYPE = {
  item_id: 'K7-1-audited-by-type',
  remark: J({
    assetRelated: { 设备购置补助: { beginBalance: 1100, increase: 600, decrease: 250 } },
    incomeRelated: { 稳岗补贴: { beginBalance: 90 } },
  }),
  conclusion: null,
}
const NOISE = [
  { item_id: 'K7A-proc-1', remark: '程序', conclusion: null },
  { item_id: 'K1-unrelated', remark: '999', conclusion: null },
]

/** 国企：已保存两张表 + 明细（一行旧载荷缺列、金额是字符串）+ 说明 + 自动取数 */
const SOE_RESPONSES = [
  { item_id: 'K7-disclosure-soe-asset-rows', remark: J([
    { id: 'a1', project: '设备购置补助', beginBalance: 1000, increase: 500, decrease: 200 },
    { id: 'a2', project: '技改项目补助', beginBalance: 300, increase: 0, decrease: 100 },
  ]), conclusion: null },
  { item_id: 'K7-disclosure-soe-income-rows', remark: J([
    { id: 'i1', project: '稳岗补贴', beginBalance: 80, increase: 20, decrease: 50 },
  ]), conclusion: null },
  { item_id: 'K7-disclosure-soe-grant-rows', remark: J([
    { id: 'g1', grantItem: '智能制造专项', beginBalance: 900, newGrant: 300, toPl: 150, plLineItem: '其他收益',
      refund: 0, otherChange: 0, grantKind: '与资产相关', refundReason: '' },
    { grantItem: '稳岗补贴', beginBalance: '80', toPl: 30 },
  ]), conclusion: null },
  { item_id: 'K7-disclosure-soe-narrative', remark: '政府补助说明', conclusion: null },
  AUDITED_BY_TYPE,
  ...NOISE,
]

/** 上市：与资产相关行没保存（两张表回默认行）+ 与收益相关已保存（带形成原因）+ 说明 + 自动取数 */
const LISTED_RESPONSES = [
  { item_id: 'K7-disclosure-listed-income-rows', remark: J([
    { id: 'i1', project: '稳岗补贴', beginBalance: 80, increase: 20, decrease: 50, reason: '人社局稳岗返还' },
    { id: 'i2', project: '研发费用补助', beginBalance: 0, increase: 40, decrease: 40, reason: '' },
  ]), conclusion: null },
  { item_id: 'K7-disclosure-listed-narrative', remark: '递延收益说明', conclusion: null },
  AUDITED_BY_TYPE,
  ...NOISE,
]

const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-k7', wpCode: 'K7', applicableStandards: [] as string[] }

/** Tab 路径：挂载真实 Tab（onMounted 读回复 + 自动取数）→ 调它的同步函数 → 截下发出的载荷 */
async function tabPayload(variant: 'listed' | 'soe', responses: typeof SOE_RESPONSES): Promise<any> {
  const Comp = variant === 'listed' ? K7TabDisclosureListed : K7TabDisclosureSoe
  return (await payloadFromTab(Comp, h.post, { wpId: 'wp-k7', responses })).payload
}

function tableRows(sent: any, name: string): any[] {
  return sent.sub_table_data[name] as any[]
}

describe('k7HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.post.mockResolvedValue({ rows_synced: 11, push_kept: [{ table: '递延收益' }] })
  })

  it('国企：载荷与挂载的 Tab 逐字节相同（已保存行 + 自动取数 + 明细 + 说明），静默写 八、56、不写底稿', async () => {
    const tabSent = await tabPayload('soe', SOE_RESPONSES)
    h.post.mockClear()
    h.get.mockResolvedValue(SOE_RESPONSES)
    const out = await k7HeadlessProvider({ ...CTX, variant: 'soe' })
    expect(out).toEqual({ sections: [{ section: '八、56', rows: 11, kept: 1 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-k7/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.post).toHaveBeenCalledTimes(1)
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe(SYNC_URL)
    expect(cfg).toMatchObject({ _silent: true })
    expect(J(sent)).toBe(J(tabSent))
    // 数据非空：自动取数覆盖了已保存的「设备购置补助」，明细两行 + 合计，说明在
    const main = tableRows(sent, K7_SUBTABLE.deferredIncome)
    expect(main.find((r) => r.label === '设备购置补助')?.values).toEqual([1100, 600, 250, 1450])
    expect(main.find((r) => r.label === '稳岗补贴')?.values).toEqual([90, 0, 0, 90])
    const grants = tableRows(sent, K7_SUBTABLE.grantDetail)
    expect(grants.map((r) => r.grant_item)).toEqual(['智能制造专项', '稳岗补贴', '合计'])
    expect(grants[1]).toMatchObject({ begin_amount: 80, to_pl: 30, end_amount: 50 })
    expect(sent.sub_table_data._note_texts).toEqual([
      { section: 'note-deferred-revenue', title: '递延收益说明', text: '政府补助说明' },
    ])
  })

  it('上市：默认行 + 自动取数 + 已保存的形成原因，载荷与挂载的 Tab 逐字节相同，写 五、51', async () => {
    const tabSent = await tabPayload('listed', LISTED_RESPONSES)
    h.post.mockClear()
    h.get.mockResolvedValue(LISTED_RESPONSES)
    const out = await k7HeadlessProvider({ ...CTX, variant: 'listed' })
    expect(out.sections.map((s) => s.section)).toEqual(['五、51'])
    const sent = h.post.mock.calls[0][1]
    expect(J(sent)).toBe(J(tabSent))
    const main = tableRows(sent, K7_SUBTABLE.deferredIncome)
    // 与资产相关回默认 5 行（其中设备购置补助被自动取数），与收益相关取已保存的 2 行，再加合计
    expect(main).toHaveLength(8)
    expect(main[0]).toEqual({ label: '设备购置补助', values: [1100, 600, 250, 1450, ''] })
    expect(main.find((r) => r.label === '稳岗补贴')?.values).toEqual([90, 0, 0, 90, '人社局稳岗返还'])
    expect(sent.sub_table_data[K7_SUBTABLE.grantDetail]).toBeUndefined()
    expect(sent.sub_table_data._removed_table_keys).toBeUndefined()
  })

  it('国企没有明细行：明细表进 _removed_table_keys（与 Tab 同一 builder 判）', async () => {
    const responses = SOE_RESPONSES.filter((r) => r.item_id !== 'K7-disclosure-soe-grant-rows')
    const tabSent = await tabPayload('soe', responses)
    h.post.mockClear()
    h.get.mockResolvedValue(responses)
    await k7HeadlessProvider({ ...CTX, variant: 'soe' })
    const sent = h.post.mock.calls[0][1]
    expect(J(sent)).toBe(J(tabSent))
    expect(sent.sub_table_data._removed_table_keys).toEqual([K7_SUBTABLE.grantDetail])
  })

  it('章节保护命中：不发请求，原因随结果回报', async () => {
    h.get.mockResolvedValue(SOE_RESPONSES)
    const out = await k7HeadlessProvider({ ...CTX, variant: 'soe', sectionGuard: () => '附注 八、56 已有 2 格人工填写' })
    expect(h.post).not.toHaveBeenCalled()
    expect(out).toEqual({ sections: [{ section: '八、56', rows: 0, skipped: '附注 八、56 已有 2 格人工填写' }] })
  })

  it('Tab 接线：读回复 / 自动取数 / 快照都调 k7DisclosureSnapshot，组件内不再自拼', () => {
    for (const [file, variant] of [['K7TabDisclosureListed.vue', 'listed'], ['K7TabDisclosureSoe.vue', 'soe']] as const) {
      const src = readFileSync(resolve(__dirname, `../../k7/core/${file}`), 'utf-8')
      expect(src).toContain(`loadK7DisclosureState(allResponsesRef.value, '${variant}', ROW_IDENTITY)`)
      expect(src).toContain('applyK7AutoFill(allResponsesRef.value, assetRelatedRows.value, incomeRelatedRows.value)')
      expect(src.slice(src.indexOf('async function syncToDisclosureNotes'))).toContain(`buildK7DisclosureSnapshot('${variant}', {`)
      expect(src).not.toMatch(/function (initDefaultRows|normalizeGrantRow|toGrantPayloadRow)\b/)
      expect(src).not.toContain("get('K7-1-audited-by-type')")
    }
  })
})
