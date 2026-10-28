/**
 * K2 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①挂载真实的两个披露 Tab（onMounted 读回已存的主表 / 合同取得成本 / 碳排放 / 说明），调 Tab 的同步函数，Tab 发出的载荷
 * 与离屏 provider 发出的逐字节相同；夹具有真实数据（自定义行、两张条件表开启、说明，含坏 JSON 与旧 `value` 存法）②只读 K2-
 * 条目、离屏不写底稿、不弹提示 ③没有已存数据时两边都是模板默认行 ④静态接线：两个 Tab 调共用的初值 / 读回 / 快照函数。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), success: vi.fn(), warning: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('element-plus', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  ElMessage: { success: h.success, warning: h.warning, error: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import K2TabDisclosureListed from '../../k2/core/K2TabDisclosureListed.vue'
import K2TabDisclosureSoe from '../../k2/core/K2TabDisclosureSoe.vue'
import { k2HeadlessProvider } from '../k2HeadlessDisclosure'
import { K2_LISTED_MAIN_ROWS, K2_NOTE_SECTION } from '../k2NoteSectionMap'
import { SYNC_URL, syncPayloadsFromTab, type Resp } from './_k1to6DisclosureTabHarness'

const J = JSON.stringify
const NOISE: Resp[] = [
  { item_id: 'K1-2-detail-rows', remark: '[]', conclusion: null },
  { item_id: 'K21-x', remark: '1', conclusion: null },
]
const LISTED: Resp[] = [
  { item_id: 'K2-disc-listed-main', remark: J([
    { label: '待抵扣进项税额', endAmount: 1200, priorAmount: 800 },
    { label: '预缴企业所得税', endAmount: 300, priorAmount: 0 },
    { label: '自定义：待摊保险费', endAmount: 45.5, priorAmount: 12 },
  ]), conclusion: null },
  { item_id: 'K2-disc-listed-contract-cost', remark: J({
    enabled: true, categories: ['销售佣金', ' ', '渠道费'], cells: [[100, 50], [20, 0], [0, 0], [10, 5]],
  }), conclusion: null },
  { item_id: 'K2-disc-listed-carbon', remark: J({
    enabled: true, rows: [{ label: '期初余额', currentAmount: 7, priorAmount: 3 }, { label: '不认识的行', currentAmount: 9 }],
  }), conclusion: null },
  { item_id: 'K2-disc-listed-texts', remark: J({ significant: '待抵扣进项税额为采购增值税', contractCost: '', carbon: '配额来自免费分配' }),
    conclusion: null },
  ...NOISE,
]
const SOE: Resp[] = [
  { item_id: 'K2-disc-soe-main', remark: J([
    { label: '待抵扣进项税额', endAmount: 900, priorAmount: 600 },
    { label: '委托贷款（一年内）', endAmount: 2000, priorAmount: 0 },
  ]), conclusion: null },
  // 读回里的旧 `value` 兼容分支在生产恒不触发：`GET …/checklist-responses` 只回 conclusion / remark（离屏框架同口径只取这两项）
  { item_id: 'K2-disc-soe-text', remark: J({ text: '国企其他流动资产说明' }), conclusion: null },
  ...NOISE,
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-k2', wpCode: 'K2', applicableStandards: ['soe_standalone'] }

async function headless(variant: 'listed' | 'soe', responses: readonly Resp[]) {
  h.get.mockResolvedValue(responses)
  const before = h.post.mock.calls.length
  const out = await k2HeadlessProvider({ ...CTX, variant })
  return { out, sent: h.post.mock.calls.slice(before).filter(([url]) => url === SYNC_URL).map((c) => c[1]) }
}

describe('k2HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.post.mockResolvedValue({ data: { rows_synced: 5 } })
  })

  it('上市：载荷与 Tab 同步函数逐字节相同（自定义行、条件表开启、文本段只推非空），静默发出、不写底稿', async () => {
    const tab = await syncPayloadsFromTab(K2TabDisclosureListed, h.post, { wpId: 'wp-k2', prefix: 'K2-', responses: LISTED })
    h.post.mockClear()
    const { out, sent } = await headless('listed', LISTED)
    expect(out).toEqual({ sections: [{ section: K2_NOTE_SECTION.listed, rows: 5, kept: 0 }] })
    expect(sent).toHaveLength(1)
    expect(J(sent[0])).toBe(J(tab.payloads[0]))
    expect(h.post.mock.calls[0][2]).toMatchObject({ _silent: true })
    expect(h.put).not.toHaveBeenCalled()
    expect(h.success).not.toHaveBeenCalled()
    // 真实数据进了载荷：自定义行、合同取得成本两个类别（空白类别去掉）、碳排放、非空文本段
    const text = J(sent[0])
    for (const s of ['自定义：待摊保险费', '销售佣金', '渠道费', '待抵扣进项税额为采购增值税', '配额来自免费分配']) expect(text).toContain(s)
    expect(sent[0].sub_table_data._note_texts.map((t: any) => t.section)).toEqual(['k2-significant', 'k2-carbon'])
  })

  it('国企：载荷与 Tab 同步函数逐字节相同（主表自定义行、说明）', async () => {
    const tab = await syncPayloadsFromTab(K2TabDisclosureSoe, h.post, { wpId: 'wp-k2', prefix: 'K2-', responses: SOE })
    h.post.mockClear()
    const { out, sent } = await headless('soe', SOE)
    expect(out.sections.map((s) => s.section)).toEqual([K2_NOTE_SECTION.soe])
    expect(J(sent[0])).toBe(J(tab.payloads[0]))
    expect(J(sent[0])).toContain('委托贷款（一年内）')
    expect(J(sent[0])).toContain('国企其他流动资产说明')
  })

  it('没有已存数据 / 存的是坏 JSON：两边都是模板固定行', async () => {
    const empty: Resp[] = [{ item_id: 'K2-disc-listed-main', remark: '{坏', conclusion: null }]
    const tab = await syncPayloadsFromTab(K2TabDisclosureListed, h.post, { wpId: 'wp-k2', prefix: 'K2-', responses: empty })
    h.post.mockClear()
    const { sent } = await headless('listed', empty)
    expect(J(sent[0])).toBe(J(tab.payloads[0]))
    const main = Object.values(sent[0].sub_table_data).find((v) => Array.isArray(v)) as any[]
    expect(main.map((r) => r.label).slice(0, K2_LISTED_MAIN_ROWS.length)).toEqual([...K2_LISTED_MAIN_ROWS])
  })

  it('章节保护命中：不发请求', async () => {
    h.get.mockResolvedValue(LISTED)
    const out = await k2HeadlessProvider({ ...CTX, variant: 'listed', sectionGuard: () => '已有人工填写' })
    expect(h.post).not.toHaveBeenCalled()
    expect(out).toEqual({ sections: [{ section: K2_NOTE_SECTION.listed, rows: 0, skipped: '已有人工填写' }] })
  })

  it('静态接线：两个 Tab 用共用的初值 / 读回 / 快照函数，不再内联', () => {
    const listed = readFileSync(resolve(__dirname, '../../k2/core/K2TabDisclosureListed.vue'), 'utf-8')
    const soe = readFileSync(resolve(__dirname, '../../k2/core/K2TabDisclosureSoe.vue'), 'utf-8')
    expect(listed).toContain('createK2ListedDisclosureState()')
    expect(listed).toContain('loadK2ListedDisclosureState(props.allResponses, formState)')
    expect(listed).toContain('buildK2ListedDisclosureSnapshot(formState)')
    expect(listed).not.toMatch(/function parseSaved\(/)
    expect(soe).toContain('k2SoeDefaultMainRows()')
    expect(soe).toContain('loadK2SoeDisclosureState(props.allResponses, mainRows)')
    expect(soe).toContain('buildK2SoeDisclosureSnapshot(mainRows, noteText.value)')
    expect(soe).not.toMatch(/function parseSaved\(/)
  })
})
