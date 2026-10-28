/**
 * K4 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①挂载真实的两个披露 Tab（onMounted：读已保存的表 + 从 K4-1 自动取数），调 Tab 的同步函数，Tab 发出的载荷与离屏
 * provider 发出的逐字节相同；夹具有真实数据（汇总表四类、债券明细 / 续表、四段说明）②只读 K4- 条目、离屏不写底稿、不弹提示
 * ③上市 五、44 / 国企 八、48 ④🔴 国企读回：原 loadSavedData 只读 `saved?.value`，而宿主 checklist 回复只有 remark / conclusion
 * （Tab 保存经 emit('save') 落 remark）⇒ 已存四段从不读回（打开即默认空表，载荷全 0、没有说明；下次编辑把空段写回）。现读 remark、
 * 兼容旧 value，用例钉住修后的行为 ⑤🔴 国企 Tab 原缺 `ref` 的 import：生产构建由 unplugin-auto-import 补上，vitest 不带该插件 ⇒
 * 挂载即 ReferenceError（Tab 对拍跑不起来）；已补 import ⑥章节保护命中不发请求 ⑦静态接线：两 Tab 的初值 / 读回 / 取数 / 快照都调
 * k4DisclosureTabState，组件内不再自拼。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), success: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('element-plus', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  ElMessage: { success: h.success, warning: vi.fn(), error: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import K4TabDisclosureListed from '../../k4/core/K4TabDisclosureListed.vue'
import K4TabDisclosureSoe from '../../k4/core/K4TabDisclosureSoe.vue'
import { k4HeadlessProvider } from '../k4HeadlessDisclosure'
import { K4_SUBTABLE } from '../k4NoteSectionMap'
import { createK4SoeDisclosureSections, loadK4SoeDisclosureState } from '../k4DisclosureTabState'
import { SYNC_URL, syncPayloadsFromTab, type Resp } from './_k1to6DisclosureTabHarness'

const J = JSON.stringify
const NOISE: Resp[] = [
  { item_id: 'K4A-proc-1', remark: '程序', conclusion: null },
  { item_id: 'K1-note-listed-rows', remark: '[]', conclusion: null },
]
const natureRow = (rowIdx: number, item: string, endBalance: number, beginBalance: number, extra: object = {}) =>
  ({ rowIdx, item, endBalance, beginBalance, remark: '', ...extra })
/** 国企：已存三段（按性质 6 行 + 合计 / 增减变动 / 其他），与 Tab 保存同形 `{ rows, textContent }` 落在 remark */
const SOE: Resp[] = [
  { item_id: 'K4-disc-soe-nature', remark: J({
    rows: [
      natureRow(0, '预提费用', 500, 300), natureRow(1, '待转销项税额', 800, 650), natureRow(2, '代扣代缴款项', 40, 0),
      natureRow(3, '待认证进项税额', 0, 0), natureRow(4, '应付短期利息', 60, 20), natureRow(5, '其他', 0, 30),
      natureRow(6, '合计', 9999, 8888, { isFormula: true, isAutoFilled: true }),
    ],
    textContent: '其他流动负债主要为待转销项税额',
  }), conclusion: null },
  { item_id: 'K4-disc-soe-change', remark: J({
    rows: [natureRow(0, '本期增加', 500, 0), natureRow(1, '本期减少', 100, 0), natureRow(2, '净变动', 400, 0, { isFormula: true })],
    textContent: '本期增加系预提费用增加',
  }), conclusion: null },
  { item_id: 'K4-disc-soe-other', remark: J({ rows: [], textContent: '无其他披露事项' }), conclusion: null },
  ...NOISE,
]
/** 上市：汇总表四类（合计行存的是旧值）+ 债券明细（一行空白，builder 过滤）+ 续表 + 政府补助（不进载荷）+ 说明 + K4-1 审定合计 */
const LISTED: Resp[] = [
  { item_id: 'K4-disc-listed-summary', remark: J([
    { item: '短期应付债券', endBalance: 1000, beginBalance: 0, remark: '一年内到期' },
    { item: '政府补助', endBalance: 300, beginBalance: 200, remark: '' },
    { item: '待转销项税额', endBalance: 150, beginBalance: 100, remark: '' },
    { item: '应付退货款', endBalance: 0, beginBalance: 0, remark: '' },
    { item: '合计', endBalance: 1, beginBalance: 1, remark: '', isTotal: true },
  ]), conclusion: null },
  { item_id: 'K4-disc-listed-bonds', remark: J([
    { name: '25XX SCP001', faceValue: 1000, couponRate: 0.025, issueDate: '2025-03-01', term: '270天', issueAmount: 1000 },
    { name: '', faceValue: 0, couponRate: 0, issueDate: '', term: '', issueAmount: 0 },
  ]), conclusion: null },
  { item_id: 'K4-disc-listed-bond-cont', remark: J([
    { name: '25XX SCP001', beginBalance: 0, issued: 1000, interestAccrued: 18.5, premiumAmort: 0, repaid: 0, defaulted: '否' },
  ]), conclusion: null },
  { item_id: 'K4-disc-listed-grants', remark: J([{ item: '稳岗补贴', beginBalance: 0, increase: 300, decrease: 0, reason: '人社局' }]), conclusion: null },
  { item_id: 'K4-disc-listed-note', remark: '短期应付债券为超短期融资券', conclusion: null },
  { item_id: 'K4-1-audited-total', remark: '1450', conclusion: null },
  ...NOISE,
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-k4', wpCode: 'K4', applicableStandards: [] as string[] }

function useResponses(list: Resp[]): void {
  h.get.mockImplementation(async (url: string) => (url.includes('checklist-responses') ? list : {}))
}

async function tabSync(variant: 'listed' | 'soe', list: Resp[]) {
  const Comp = variant === 'listed' ? K4TabDisclosureListed : K4TabDisclosureSoe
  return syncPayloadsFromTab(Comp, h.post, { wpId: 'wp-k4', prefix: 'K4-', responses: list })
}

function rows(sent: any, name: string): any[] {
  return sent.sub_table_data[name] as any[]
}

describe('k4HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.post.mockResolvedValue({ rows_synced: 7, push_kept: [{ table: '其他流动负债' }] })
  })

  it('国企：读回已存四段（原只读 value ⇒ 恒读不回），载荷与挂载的 Tab 逐字节相同，静默写 八、48、不写底稿不弹提示', async () => {
    useResponses(SOE)
    const out = await k4HeadlessProvider({ ...CTX, variant: 'soe' })
    expect(out).toEqual({ sections: [{ section: '八、48', rows: 7, kept: 1 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-k4/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.success).not.toHaveBeenCalled()
    expect(h.post).toHaveBeenCalledTimes(1)
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe(SYNC_URL)
    expect(cfg).toMatchObject({ _silent: true })

    const tab = await tabSync('soe', SOE)
    expect(tab.payloads).toHaveLength(1)
    expect(J(sent)).toBe(J(tab.payloads[0]))
    expect(tab.saves).toEqual([])

    // 数据非空：只推按性质 6 行（合计由 builder 按明细重算，不用存的 9999 / 自动取数的 0）；三段说明按段序拼接
    expect(rows(sent, K4_SUBTABLE.summary).map((r) => [r.label, r.end_amount, r.prior_amount])).toEqual([
      ['预提费用', 500, 300], ['待转销项税额', 800, 650], ['代扣代缴款项', 40, 0], ['待认证进项税额', 0, 0],
      ['应付短期利息', 60, 20], ['其他', 0, 30], ['合计', 1400, 1000],
    ])
    expect(sent.sub_table_data._note_texts).toEqual([{
      section: 'note-other-current-liability',
      title: '其他流动负债说明',
      text: '其他流动负债主要为待转销项税额\n\n本期增加系预提费用增加\n\n无其他披露事项',
    }])
    expect(Object.keys(sent.columns)).toEqual([K4_SUBTABLE.summary])
  })

  it('国企读回：remark 优先、兼容旧 value；没有已存 / 损坏的段保持初值（原只认 value，remark 形态一段都读不回）', () => {
    const fromRemark = createK4SoeDisclosureSections()
    loadK4SoeDisclosureState(new Map(SOE.map((r) => [r.item_id, r])), fromRemark)
    expect(fromRemark[0].rows[1]).toMatchObject({ item: '待转销项税额', endBalance: 800 })
    expect(fromRemark.map((s) => s.textContent)).toEqual(['其他流动负债主要为待转销项税额', '本期增加系预提费用增加', '', '无其他披露事项'])

    const legacy = createK4SoeDisclosureSections()
    loadK4SoeDisclosureState(new Map([
      ['K4-disc-soe-nature', { value: { rows: [natureRow(0, '预提费用', 9, 8)], textContent: '旧格式' } }],
      ['K4-disc-soe-change', { remark: '{损坏' }],
    ]), legacy)
    expect(legacy[0].rows).toEqual([natureRow(0, '预提费用', 9, 8)])
    expect(legacy[0].textContent).toBe('旧格式')
    expect(legacy[1]).toEqual(createK4SoeDisclosureSections()[1])
  })

  it('上市：载荷与挂载的 Tab 逐字节相同（汇总表 + 债券明细 / 续表 + 说明），写 五、44', async () => {
    useResponses(LISTED)
    const out = await k4HeadlessProvider({ ...CTX, variant: 'listed' })
    expect(out.sections.map((s) => s.section)).toEqual(['五、44'])
    expect(h.success).not.toHaveBeenCalled()
    const sent = h.post.mock.calls[0][1]
    const tab = await tabSync('listed', LISTED)
    expect(J(sent)).toBe(J(tab.payloads[0]))
    expect(tab.saves).toEqual([])
    expect(rows(sent, K4_SUBTABLE.summary).map((r) => [r.label, r.end_amount, r.prior_amount])).toEqual([
      ['短期应付债券', 1000, 0], ['政府补助', 300, 200], ['待转销项税额', 150, 100], ['应付退货款', 0, 0], ['合计', 1450, 300],
    ])
    expect(rows(sent, K4_SUBTABLE.bond)).toEqual([{
      label: '25XX SCP001', face_value: 1000, coupon_rate: 0.025, issue_date: '2025-03-01', term: '270天', issue_amount: 1000,
    }])
    expect(rows(sent, K4_SUBTABLE.bondCont)[0]).toMatchObject({ label: '25XX SCP001', issued: 1000, end_amount: 1018.5, defaulted: '否' })
    expect(sent.sub_table_data._note_texts).toEqual([
      { section: 'note-other-current-liability', title: '其他流动负债说明', text: '短期应付债券为超短期融资券' },
    ])
    expect(sent.sub_table_data._removed_table_keys).toEqual(['债券名称'])
  })

  it('上市没有已存数据：默认四类 0 值、无债券表（与 Tab 同一 builder 判），K4-1 审定合计只进合计行备注、不进载荷', async () => {
    const list: Resp[] = [{ item_id: 'K4-1-audited-total', remark: '1450', conclusion: null }]
    useResponses(list)
    await k4HeadlessProvider({ ...CTX, variant: 'listed' })
    const sent = h.post.mock.calls[0][1]
    const tab = await tabSync('listed', list)
    expect(J(sent)).toBe(J(tab.payloads[0]))
    expect(rows(sent, K4_SUBTABLE.summary).map((r) => r.end_amount)).toEqual([0, 0, 0, 0, 0])
    expect(Object.keys(sent.columns)).toEqual([K4_SUBTABLE.summary])
    expect(sent.sub_table_data._note_texts).toBeUndefined()
  })

  it('章节保护命中：不发请求，原因随结果回报', async () => {
    useResponses(LISTED)
    const out = await k4HeadlessProvider({ ...CTX, variant: 'listed', sectionGuard: () => '附注 五、44 已有 1 格人工填写' })
    expect(h.post).not.toHaveBeenCalled()
    expect(out).toEqual({ sections: [{ section: '五、44', rows: 0, skipped: '附注 五、44 已有 1 格人工填写' }] })
  })

  it('静态接线：两 Tab 的初值 / 读回 / 自动取数 / 快照都调 k4DisclosureTabState，组件内不再自拼；国企 Tab 显式 import ref', () => {
    const soe = readFileSync(resolve(__dirname, '../../k4/core/K4TabDisclosureSoe.vue'), 'utf-8')
    expect(soe).toMatch(/import \{[^}]*\bref\b[^}]*\} from 'vue'/)
    expect(soe).toContain('reactive<K4SoeDisclosureSection[]>(createK4SoeDisclosureSections())')
    expect(soe).toContain('loadK4SoeDisclosureState(props.allResponses, sections)')
    expect(soe).toContain('applyK4SoeAutoFill(props.allResponses, sections)')
    expect(soe).toContain('const snapshot = buildK4SoeDisclosureSnapshot(sections)')
    expect(soe).not.toMatch(/saved\?\.value|function (makeRow|buildSections|getResponseNumber)\b/)
    const listed = readFileSync(resolve(__dirname, '../../k4/core/K4TabDisclosureListed.vue'), 'utf-8')
    expect(listed).toContain('reactive<SummaryRow[]>(createK4ListedSummaryRows())')
    expect(listed).toContain('loadK4ListedDisclosureState(props.allResponses, summaryRows)')
    expect(listed).toContain('applyK4ListedAutoFill(props.allResponses, summaryRows)')
    expect(listed).toContain('const snapshot = buildK4ListedDisclosureSnapshot({')
    expect(listed).not.toMatch(/function _parse\b|SUMMARY_TYPES|summaryRows\.filter\(r => !r\.isTotal\)\.map/)
  })
})
