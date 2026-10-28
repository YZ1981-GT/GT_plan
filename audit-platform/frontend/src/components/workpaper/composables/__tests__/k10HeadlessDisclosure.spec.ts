/**
 * K10 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①挂载真实的两个披露 Tab（setup 默认分类行 + onMounted 读已保存行 / 动态行 / 说明），调 Tab 的同步函数，Tab 发出的
 * 载荷与离屏 provider 发出的载荷逐字节相同；夹具有真实数据 ②「从审定表取数」是按钮动作：K10-1-rows 有数时挂载不取、离屏也不取
 * ③国企「其中：政府补助」按点选汇总 ④只读 K10- 条目、离屏不写底稿；两口径分别写 五、68 / 八、69 ⑤Tab 接线走 k10DisclosureSnapshot。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), apiPost: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { post: h.apiPost, get: vi.fn() } }))
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<typeof import('element-plus')>()
  return { ...actual, ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() } }
})

import K10TabDisclosureListed from '../../k10/core/K10TabDisclosureListed.vue'
import K10TabDisclosureSoe from '../../k10/core/K10TabDisclosureSoe.vue'
import { k10HeadlessProvider } from '../k10HeadlessDisclosure'
import { K10_LISTED_SUBTABLE, K10_SOE_STRUCTURAL_ROW, K10_SOE_SUBTABLE } from '../k10NoteSectionMap'
import { payloadFromTab, SYNC_URL } from './_kDisclosureTabHarness'

const J = JSON.stringify
type Resp = { item_id: string; remark: string | null; conclusion: string | null }
/** 审定表行有数：Tab 挂载时不自动取（按钮动作），离屏也不取 ⇒ 「政府补助-稳岗补贴」保持 0 */
const K101: Resp = { item_id: 'K10-1-rows', remark: J([{ name: '政府补助-稳岗补贴', audited: 999 }]), conclusion: null }
const NOISE: Resp[] = [
  { item_id: 'K10A-proc-1', remark: '程序', conclusion: null },
  { item_id: 'K1-disc-listed-row-0', remark: J({ currentAmount: 7 }), conclusion: null },
]
const LISTED: Resp[] = [
  { item_id: 'K10-disc-listed-row-0', remark: J({
    grantType: '', recognitionMethod: '直接计入', currentAmount: 1200, priorAmount: 1000, remark: '增值税即征即退',
  }), conclusion: null },
  { item_id: 'K10-disc-listed-row-3', remark: 'oops', conclusion: null },
  { item_id: 'K10-disc-listed-row-7', remark: J({ currentAmount: 30, priorAmount: 25 }), conclusion: null },
  { item_id: 'K10-disc-listed-dyn-增值税加计抵减', remark: J({ category: '增值税加计抵减', currentAmount: 88, priorAmount: 66 }), conclusion: null },
  { item_id: 'K10-disc-listed-dyn-坏行', remark: J({ currentAmount: 5 }), conclusion: null },
  { item_id: 'K10-disclosure-listed-narrative', remark: '', conclusion: '其他收益说明（结论字段）' },
  K101,
  ...NOISE,
]
const SOE: Resp[] = [
  { item_id: 'K10-disc-soe-row-0', remark: J({ currentAmount: 500, priorAmount: 400, isGovGrant: '是' }), conclusion: null },
  { item_id: 'K10-disc-soe-row-4', remark: J({ currentAmount: 60, priorAmount: 0, isGovGrant: '否' }), conclusion: null },
  { item_id: 'K10-disc-soe-row-6', remark: J({ currentAmount: 20, priorAmount: 10 }), conclusion: null },
  { item_id: 'K10-disc-soe-dyn-地方财政奖励', remark: J({ category: '地方财政奖励', currentAmount: 70, priorAmount: 0, isGovGrant: '是' }), conclusion: null },
  { item_id: 'K10-disclosure-soe-narrative', remark: '国企其他收益说明', conclusion: null },
  K101,
  ...NOISE,
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-k10', wpCode: 'K10', applicableStandards: [] as string[] }

async function tab(variant: 'listed' | 'soe', responses: Resp[]) {
  return payloadFromTab(variant === 'listed' ? K10TabDisclosureListed : K10TabDisclosureSoe, h.post, { wpId: 'wp-k10', responses })
}

async function headless(variant: 'listed' | 'soe', responses: Resp[]) {
  h.post.mockClear()
  h.get.mockReset()
  h.get.mockResolvedValue(responses)
  const out = await k10HeadlessProvider({ ...CTX, variant })
  return { out, sent: h.post.mock.calls[0]?.[1] }
}

describe('k10HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.post.mockResolvedValue({ rows_synced: 12, push_kept: [] })
  })

  it('上市：已保存行覆盖 + 动态行 + 说明取结论字段，载荷与挂载的 Tab 逐字节相同，静默写 五、68、不写底稿', async () => {
    const tabRun = await tab('listed', LISTED)
    expect(tabRun.saves).toEqual([])
    const { out, sent } = await headless('listed', LISTED)
    expect(out).toEqual({ sections: [{ section: '五、68', rows: 12, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-k10/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiPost).not.toHaveBeenCalled()
    const [url, , cfg] = h.post.mock.calls[0]
    expect(url).toBe(SYNC_URL)
    expect(cfg).toMatchObject({ _silent: true })
    expect(J(sent)).toBe(J(tabRun.payload))
    const rows = sent.sub_table_data[K10_LISTED_SUBTABLE.main] as Array<{ label: string; current_amount: number }>
    expect(rows).toHaveLength(11)
    expect(rows[0]).toEqual({ label: '政府补助-即征即退', current_amount: 1200, prior_amount: 1000 })
    expect(rows.find((r) => r.label === '政府补助-稳岗补贴')?.current_amount).toBe(0)
    expect(rows[9]).toEqual({ label: '增值税加计抵减', current_amount: 88, prior_amount: 66 })
    expect(rows[10]).toMatchObject({ label: '合计', current_amount: 1318, is_total: true })
    expect(sent.sub_table_data._note_texts).toEqual([
      { section: 'k10-note', title: '其他收益说明', text: '其他收益说明（结论字段）' },
    ])
  })

  it('国企：「其中：政府补助」按点选汇总（含动态行、排除改选为否的行），载荷与挂载的 Tab 逐字节相同，写 八、69', async () => {
    const tabRun = await tab('soe', SOE)
    const { out, sent } = await headless('soe', SOE)
    expect(out.sections.map((s) => s.section)).toEqual(['八、69'])
    expect(J(sent)).toBe(J(tabRun.payload))
    const rows = sent.sub_table_data[K10_SOE_SUBTABLE.main] as any[]
    expect(rows.map((r) => r.label)).toEqual([
      '政府补助', '即征即退', '财政贴息', '研发补助', '稳岗补贴', '其他补贴收入', '个税手续费返还', '地方财政奖励',
      '合计', K10_SOE_STRUCTURAL_ROW,
    ])
    expect(rows[8]).toMatchObject({ current_amount: 650, prior_amount: 410, is_total: true })
    expect(rows[9]).toEqual({ label: K10_SOE_STRUCTURAL_ROW, current_amount: 570, prior_amount: 400 })
  })

  it('章节保护命中：不发请求，原因随结果回报', async () => {
    h.get.mockResolvedValue(SOE)
    const out = await k10HeadlessProvider({ ...CTX, variant: 'soe', sectionGuard: () => '附注 八、69 已有 2 格人工填写' })
    expect(h.post).not.toHaveBeenCalled()
    expect(out).toEqual({ sections: [{ section: '八、69', rows: 0, skipped: '附注 八、69 已有 2 格人工填写' }] })
  })

  it('Tab 接线：默认行 / 读回复 / 动态行 / 快照都调 k10DisclosureSnapshot，组件内不再自拼', () => {
    for (const [file, variant] of [['K10TabDisclosureListed.vue', 'listed'], ['K10TabDisclosureSoe.vue', 'soe']] as const) {
      const src = readFileSync(resolve(__dirname, `../../k10/core/${file}`), 'utf-8')
      expect(src).toContain(`ref<DisclosureRow[]>(k10DefaultDisclosureRows('${variant}'))`)
      expect(src).toContain(`loadK10DisclosureState(props.allResponses, '${variant}')`)
      expect(src).toContain(`k10DynamicDisclosureRows(props.allResponses, '${variant}')`)
      expect(src.slice(src.indexOf('async function syncToDisclosureNotes'))).toContain(`buildK10DisclosureSnapshot('${variant}', disclosureRows.value)`)
      expect(src).not.toMatch(/K10-disc-(listed|soe)-row-\$\{i\}/)
    }
  })
})
