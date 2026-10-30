/**
 * K8 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①挂载真实的两个披露 Tab（onMounted 读回复 + 按 K8-1 自动取数），调 Tab 的同步函数，Tab 发出的载荷与离屏
 * provider 发出的载荷逐字节相同；夹具有真实数据（已保存行被 K8-1 回填 + 追加新费用项目 / 按 K8-1 建行 / 默认清单）
 * ②Tab 挂载时自动取数会保存披露行，离屏不写底稿（不调 PUT）③两口径分别写 五、64 / 八、65 ④章节保护命中不发请求
 * ⑤Tab 接线：读回复、自动取数、明细行都走 k8DisclosureSnapshot。
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

import K8TabDisclosureListed from '../../k8/core/K8TabDisclosureListed.vue'
import K8TabDisclosureSoe from '../../k8/core/K8TabDisclosureSoe.vue'
import { k8HeadlessProvider } from '../k8HeadlessDisclosure'
import { K8_LISTED_SUBTABLE, K8_SOE_SUBTABLE } from '../k8NoteSectionMap'
import { payloadFromTab, SYNC_URL } from './_kDisclosureTabHarness'

const J = JSON.stringify
type Resp = { item_id: string; remark: string; conclusion: null }
const K81: Resp = {
  item_id: 'K8-1-audited-by-item',
  remark: J({ 职工薪酬: { audited: 500, prior: 450 }, 广告宣传费: { audited: 300, prior: 100 }, 直播推广费: { audited: 80, prior: 0 } }),
  conclusion: null,
}
const NOISE: Resp[] = [
  { item_id: 'K8A-proc-1', remark: '程序', conclusion: null },
  { item_id: 'K9-disclosure-listed-rows', remark: J([{ id: 'x', project: '别的底稿', currentAmount: 9, priorAmount: 9 }]), conclusion: null },
]
/** 上市：已保存行（含合计行）被 K8-1 回填 + 追加 K8-1 独有的两个费用项目 + 说明 */
const LISTED: Resp[] = [
  { item_id: 'K8-disclosure-listed-rows', remark: J([
    { id: 'r1', project: '职工薪酬', currentAmount: 1, priorAmount: 2, remark: '人工' },
    { id: 'r2', project: '差旅费', currentAmount: 60, priorAmount: 40, remark: '' },
    { id: 'r3', project: '合计', currentAmount: 61, priorAmount: 42, remark: '', isTotal: true },
  ]), conclusion: null },
  { item_id: 'K8-disclosure-listed-narrative', remark: '销售费用增长主要系广告投放增加', conclusion: null },
  K81,
  ...NOISE,
]
/** 国企：没保存过 ⇒ 按 K8-1 审定表项目建行 */
const SOE: Resp[] = [
  { item_id: 'K8-disclosure-soe-narrative', remark: '国企销售费用说明', conclusion: null },
  K81,
  ...NOISE,
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-k8', wpCode: 'K8', applicableStandards: [] as string[] }

async function tab(variant: 'listed' | 'soe', responses: Resp[]) {
  return payloadFromTab(variant === 'listed' ? K8TabDisclosureListed : K8TabDisclosureSoe, h.post, { wpId: 'wp-k8', responses })
}

async function headless(variant: 'listed' | 'soe', responses: Resp[]) {
  h.post.mockClear()
  h.get.mockReset()
  h.get.mockResolvedValue(responses)
  const out = await k8HeadlessProvider({ ...CTX, variant })
  return { out, sent: h.post.mock.calls[0]?.[1] }
}

describe('k8HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.post.mockResolvedValue({ rows_synced: 5, push_kept: [] })
  })

  it('上市：已保存行 + K8-1 回填 / 追加，载荷与挂载的 Tab 逐字节相同，静默写 五、64、不写底稿', async () => {
    const tabRun = await tab('listed', LISTED)
    // Tab 自己挂载即自动取数并保存披露行（写底稿）；离屏不做这一步
    expect(tabRun.saves).toContain('K8-disclosure-listed-rows')
    const { out, sent } = await headless('listed', LISTED)
    expect(out).toEqual({ sections: [{ section: '五、64', rows: 5, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-k8/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.post).toHaveBeenCalledTimes(1)
    const [url, , cfg] = h.post.mock.calls[0]
    expect(url).toBe(SYNC_URL)
    expect(cfg).toMatchObject({ _silent: true })
    expect(J(sent)).toBe(J(tabRun.payload))
    expect(sent.sub_table_data[K8_LISTED_SUBTABLE.main]).toEqual([
      { label: '职工薪酬', current_amount: 500, prior_amount: 450 },
      { label: '差旅费', current_amount: 60, prior_amount: 40 },
      { label: '广告宣传费', current_amount: 300, prior_amount: 100 },
      { label: '直播推广费', current_amount: 80, prior_amount: 0 },
      { label: '合计', current_amount: 940, prior_amount: 590, is_total: true },
    ])
    expect(sent.sub_table_data._note_texts).toEqual([
      { section: 'k8-note', title: '销售费用说明', text: '销售费用增长主要系广告投放增加' },
    ])
  })

  it('国企：没保存过 ⇒ 按 K8-1 建行，载荷与挂载的 Tab 逐字节相同，写 八、65', async () => {
    const tabRun = await tab('soe', SOE)
    const { out, sent } = await headless('soe', SOE)
    expect(out.sections.map((s) => s.section)).toEqual(['八、65'])
    expect(J(sent)).toBe(J(tabRun.payload))
    const rows = sent.sub_table_data[K8_SOE_SUBTABLE.main] as Array<{ label: string }>
    expect(rows.map((r) => r.label)).toEqual(['职工薪酬', '广告宣传费', '直播推广费', '合计'])
    expect(sent.sub_table_data._removed_table_keys).toBeUndefined()
  })

  it('没有任何数据：两版都回默认费用性质清单，载荷与 Tab 相同', async () => {
    for (const variant of ['listed', 'soe'] as const) {
      const responses = NOISE
      const tabRun = await tab(variant, responses)
      expect(tabRun.saves).toEqual([])
      const { sent } = await headless(variant, responses)
      expect(J(sent)).toBe(J(tabRun.payload))
      const rows = sent.sub_table_data[variant === 'listed' ? K8_LISTED_SUBTABLE.main : K8_SOE_SUBTABLE.main] as any[]
      expect(rows.length).toBe(variant === 'listed' ? 30 : 20)
    }
  })

  it('章节保护命中：不发请求，原因随结果回报', async () => {
    h.get.mockResolvedValue(LISTED)
    const out = await k8HeadlessProvider({ ...CTX, variant: 'listed', sectionGuard: () => '附注 五、64 已有 1 格人工填写' })
    expect(h.post).not.toHaveBeenCalled()
    expect(out).toEqual({ sections: [{ section: '五、64', rows: 0, skipped: '附注 五、64 已有 1 格人工填写' }] })
  })

  it('Tab 接线：读回复 / 自动取数 / 明细行都调 k8DisclosureSnapshot，组件内不再自拼', () => {
    for (const [file, variant] of [['K8TabDisclosureListed.vue', 'listed'], ['K8TabDisclosureSoe.vue', 'soe']] as const) {
      const src = readFileSync(resolve(__dirname, `../../k8/core/${file}`), 'utf-8')
      expect(src).toContain(`loadK8DisclosureState(props.allResponses, '${variant}', ROW_IDENTITY)`)
      expect(src).toContain(`applyK8AutoFill(data, disclosureRows.value, '${variant}', ROW_IDENTITY)`)
      expect(src.slice(src.indexOf('async function syncToDisclosureNotes'))).toContain('k8DisclosureSyncRows(disclosureRows.value)')
      expect(src).not.toMatch(/function (initDefaultRows|_readK81Map|buildRowsFromK81)\b/)
    }
  })
})
