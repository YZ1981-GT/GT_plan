/**
 * K9 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①挂载真实的两个披露 Tab（onMounted 读回复 + 按 K9-1 回填，精确名 / 归一化名两种匹配），调 Tab 的同步函数，
 * Tab 发出的载荷与离屏 provider 发出的载荷逐字节相同；夹具有真实数据 ②只读 K9- 条目、离屏不写底稿
 * ③两口径分别写 五、65 / 八、66 ④章节保护命中不发请求 ⑤Tab 接线走 k9DisclosureSnapshot。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<typeof import('element-plus')>()
  return { ...actual, ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() } }
})

import K9TabDisclosureListed from '../../k9/core/K9TabDisclosureListed.vue'
import K9TabDisclosureSoe from '../../k9/core/K9TabDisclosureSoe.vue'
import { k9HeadlessProvider } from '../k9HeadlessDisclosure'
import { K9_LISTED_SUBTABLE, K9_SOE_SUBTABLE } from '../k9NoteSectionMap'
import { K9_FEE_NATURES_SOE } from '../k9FeeNatures'
import { payloadFromTab, SYNC_URL } from './_kDisclosureTabHarness'

const J = JSON.stringify
type Resp = { item_id: string; remark: string; conclusion: null }
/** K9-1：「研发费用」「低值易耗品」只能靠归一化名对上披露行的「研发费」「低值易耗品摊销」 */
const K91: Resp = {
  item_id: 'K9-1-audited-by-item',
  remark: J({
    职工薪酬: { audited: 900, prior: 800 },
    研发费用: { audited: 300, prior: 250 },
    低值易耗品: { audited: 12, prior: 10 },
    工会经费: { audited: 20, prior: 18 },
  }),
  conclusion: null,
}
const NOISE: Resp[] = [
  { item_id: 'K9A-proc-1', remark: '程序', conclusion: null },
  { item_id: 'K8-disclosure-listed-rows', remark: J([{ id: 'x', project: '别的底稿', currentAmount: 9, priorAmount: 9 }]), conclusion: null },
]
/** 上市：已保存行（含合计行，金额与 K9-1 不同）+ 说明 */
const LISTED: Resp[] = [
  { item_id: 'K9-disclosure-listed-rows', remark: J([
    { id: 'r1', project: '职工薪酬', currentAmount: 1, priorAmount: 1, remark: '' },
    { id: 'r2', project: '研发费', currentAmount: 2, priorAmount: 2, remark: '研发' },
    { id: 'r3', project: '低值易耗品摊销', currentAmount: 3, priorAmount: 3, remark: '' },
    { id: 'r4', project: '办公费', currentAmount: 45, priorAmount: 40, remark: '' },
    { id: 'r5', project: '合计', currentAmount: 51, priorAmount: 46, remark: '', isTotal: true },
  ]), conclusion: null },
  { item_id: 'K9-disclosure-listed-narrative', remark: '管理费用说明', conclusion: null },
  K91,
  ...NOISE,
]
/** 国企：没保存过 ⇒ 国企费用性质清单（含特有项「工会经费」）+ K9-1 回填 */
const SOE: Resp[] = [K91, ...NOISE]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-k9', wpCode: 'K9', applicableStandards: [] as string[] }

async function tab(variant: 'listed' | 'soe', responses: Resp[]) {
  return payloadFromTab(variant === 'listed' ? K9TabDisclosureListed : K9TabDisclosureSoe, h.post, { wpId: 'wp-k9', responses })
}

async function headless(variant: 'listed' | 'soe', responses: Resp[]) {
  h.post.mockClear()
  h.get.mockReset()
  h.get.mockResolvedValue(responses)
  const out = await k9HeadlessProvider({ ...CTX, variant })
  return { out, sent: h.post.mock.calls[0]?.[1] }
}

describe('k9HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.post.mockResolvedValue({ rows_synced: 6, push_kept: [] })
  })

  it('上市：已保存行按 K9-1 回填（精确名 + 归一化名），载荷与挂载的 Tab 逐字节相同，静默写 五、65、不写底稿', async () => {
    const tabRun = await tab('listed', LISTED)
    expect(tabRun.saves).toEqual([])
    const { out, sent } = await headless('listed', LISTED)
    expect(out).toEqual({ sections: [{ section: '五、65', rows: 6, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-k9/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    const [url, , cfg] = h.post.mock.calls[0]
    expect(url).toBe(SYNC_URL)
    expect(cfg).toMatchObject({ _silent: true })
    expect(J(sent)).toBe(J(tabRun.payload))
    expect(sent.sub_table_data[K9_LISTED_SUBTABLE.main]).toEqual([
      { label: '职工薪酬', current_amount: 900, prior_amount: 800 },
      { label: '研发费', current_amount: 300, prior_amount: 250 },
      { label: '低值易耗品摊销', current_amount: 12, prior_amount: 10 },
      { label: '办公费', current_amount: 45, prior_amount: 40 },
      { label: '合计', current_amount: 1257, prior_amount: 1100, is_total: true },
    ])
    expect(sent.sub_table_data._note_texts).toEqual([{ section: 'k9-note', title: '管理费用说明', text: '管理费用说明' }])
    expect(sent.sub_table_data._removed_table_keys).toEqual(['管理费用'])
  })

  it('国企：默认国企费用性质清单 + K9-1 回填，载荷与挂载的 Tab 逐字节相同，写 八、66', async () => {
    const tabRun = await tab('soe', SOE)
    const { out, sent } = await headless('soe', SOE)
    expect(out.sections.map((s) => s.section)).toEqual(['八、66'])
    expect(J(sent)).toBe(J(tabRun.payload))
    const rows = sent.sub_table_data[K9_SOE_SUBTABLE.main] as Array<{ label: string; current_amount: number }>
    expect(rows.map((r) => r.label)).toEqual([...K9_FEE_NATURES_SOE, '合计'])
    expect(rows.find((r) => r.label === '工会经费')?.current_amount).toBe(20)
    expect(rows.find((r) => r.label === '研发费')?.current_amount).toBe(300)
    expect(rows.at(-1)?.current_amount).toBe(1232)
  })

  it('章节保护命中：不发请求，原因随结果回报', async () => {
    h.get.mockResolvedValue(SOE)
    const out = await k9HeadlessProvider({ ...CTX, variant: 'soe', sectionGuard: () => '附注 八、66 已有 4 格人工填写' })
    expect(h.post).not.toHaveBeenCalled()
    expect(out).toEqual({ sections: [{ section: '八、66', rows: 0, skipped: '附注 八、66 已有 4 格人工填写' }] })
  })

  it('Tab 接线：读回复 / 回填 / 明细行都调 k9DisclosureSnapshot，组件内不再自拼', () => {
    for (const [file, variant] of [['K9TabDisclosureListed.vue', 'listed'], ['K9TabDisclosureSoe.vue', 'soe']] as const) {
      const src = readFileSync(resolve(__dirname, `../../k9/core/${file}`), 'utf-8')
      expect(src).toContain(`loadK9DisclosureState(props.allResponses, '${variant}', ROW_IDENTITY)`)
      expect(src).toContain('applyK9AutoFill(props.allResponses, disclosureRows.value)')
      expect(src.slice(src.indexOf('async function syncToDisclosureNotes'))).toContain('k9DisclosureSyncRows(disclosureRows.value)')
      expect(src).not.toMatch(/function (initDefaultRows|normName)\b/)
    }
  })
})
