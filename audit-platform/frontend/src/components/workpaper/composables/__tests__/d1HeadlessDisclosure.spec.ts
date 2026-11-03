/**
 * D1 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①离屏发出的载荷与「Tab 同款 composable → 同一组展开行 / 说明加载 / 快照函数 → 同一 builder」逐字节相同，
 * 夹具有真实数据（主表取审定表共享模型、分类 / 单项 / 组合 / 质押 / 变动 / 说明都非空）②Tab 的展开行、说明加载与同步
 * 都调共用函数（静态接线）③只读 D1- 条目、离屏不写底稿、不推受限资产段 ④两口径分别写 五、4 / 八、4。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), apiGet: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet } }))

import { d1HeadlessProvider } from '../d1HeadlessDisclosure'
import { useD1Disclosure } from '../useD1Disclosure'
import { buildD1SyncPayload } from '../d1NoteSectionMap'
import { buildD1DisclosureSnapshot, readD1SectionNotes } from '../d1DisclosureSnapshot'
import { d1AdjAnchor } from '../d1AdjudicationModel'
import type { ChecklistResponse } from '../useD1FormData'

const J = JSON.stringify
const row = (item_id: string, remark: unknown) => ({ item_id, remark: typeof remark === 'string' ? remark : J(remark), conclusion: null })
const classRows = (period: 'end' | 'prior', [single, bank, commercial]: number[][]) => [
  { rowId: `class-${period}-individual`, rowType: 'fixed', label: '按单项计提', isFixed: true, balance: single[0], provision: single[1] },
  { rowId: `class-${period}-portfolio-bank`, rowType: 'fixed', label: '按组合计提-银行承兑汇票', isFixed: true, balance: bank[0], provision: bank[1] },
  { rowId: `class-${period}-portfolio-commercial`, rowType: 'fixed', label: '按组合计提-商业承兑汇票', isFixed: true, balance: commercial[0], provision: commercial[1] },
]
const mv = (rowId: string, label: string, v: number[]) => ({
  rowId, rowType: 'fixed', label, isFixed: true,
  priorBalance: v[0], provision: v[1], reversal: v[2], writeOff: v[3], transfer: 0, other: 0, endBalance: v[4],
})

const RESPONSES = [
  // 审定表共享模型（主表取数源）
  row(d1AdjAnchor('gross', 'bank', 'current-unadj'), '500'),
  row(d1AdjAnchor('gross', 'bank', 'prior-unadj'), '400'),
  row(d1AdjAnchor('bd', 'bank', 'current-unadj'), '5'),
  row(d1AdjAnchor('gross', 'commercial', 'current-unadj'), '200'),
  row(d1AdjAnchor('bd', 'commercial', 'current-unadj'), '20'),
  ...(['listed', 'soe'] as const).flatMap((v) => [
    row(`D1-disc-${v}-class-end-rows`, classRows('end', [[100, 10], [400, 4], [200, 20]])),
    row(`D1-disc-${v}-class-prior-rows`, classRows('prior', [[0, 0], [300, 3], [0, 0]])),
    row(`D1-disc-${v}-individual-end-rows`, [{ rowId: 'ind1', rowType: 'dynamic', name: '甲公司', isFixed: false, balance: 100, provision: 10, lossRate: 0.1, basis: '诉讼' }]),
    row(`D1-disc-${v}-commercial-portfolio-end-rows`, [{ rowId: 'pf1', rowType: 'dynamic', drawerTypeOrAging: '1年以内', isFixed: false, balance: 200, provision: 20, lossRate: 0.1 }]),
    row(`D1-disc-${v}-pledged-rows`, [
      { rowId: 'pledged-fixed-bank', rowType: 'fixed', category: '银行承兑票据', isFixed: true, pledgedAmount: 80 },
      { rowId: 'pledged-fixed-commercial', rowType: 'fixed', category: '商业承兑票据', isFixed: true, pledgedAmount: 0 },
    ]),
  ]),
  row('D1-disc-listed-movement-rows', [mv('mv-total', '合计', [30, 10, 2, 3, 35])]),
  row('D1-disc-soe-movement-rows', [mv('mv-individual', '按单项计提', [10, 0, 0, 0, 10]), mv('mv-portfolio', '按组合计提', [20, 4, 0, 0, 24]), mv('mv-total', '合计', [0, 0, 0, 0, 0])]),
  row('D1-disc-soe-movement-detail-rows', [mv('mvd1', '商业承兑汇票', [20, 5, 1, 0, 24])]),
  row('D1-disc-listed-note-top', '总体说明'),
  row('D1-disc-listed-note-transfer', '转应收说明'),
  row('D1-disc-soe-note-badDebtClass', '国企坏账说明'),
  row('K1-unrelated', '999'),
]
const CTX = { projectId: 'p1', year: 2025, variant: 'listed' as const, wpId: 'wp-d1', wpCode: 'D1', applicableStandards: ['listed_consolidated', 'listed', 'consolidated'] }

/** Tab 路径：Tab 同款 `useD1Disclosure`（同一批 D1- 回复）→ Tab 同一说明加载 / 快照函数 → 同一 builder（宿主准则） */
function tabPayload(variant: 'listed' | 'soe', standards: string[]) {
  const map = new Map<string, ChecklistResponse>(
    RESPONSES.filter((r) => r.item_id.startsWith('D1-')).map((r) => [r.item_id, r as ChecklistResponse]),
  )
  const scope = effectScope(true)
  const snapshot = scope.run(() => {
    const d1 = useD1Disclosure({
      allResponses: ref(map), wpId: ref('wp-d1'), projectId: ref('p1'), variant,
      saveImmediate: async () => {}, isReadonly: ref(false),
    })
    return buildD1DisclosureSnapshot(variant, d1, readD1SectionNotes(map, variant))
  })!
  scope.stop()
  return buildD1SyncPayload(variant, 'wp-d1', standards, snapshot)
}

describe('d1HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 31, push_kept: [{ table: '应收票据' }] })
  })

  it('上市：载荷与 Tab 路径逐字节相同、数据非空，只发一条（不推受限资产段）、不写底稿', async () => {
    const out = await d1HeadlessProvider(CTX)
    expect(out).toEqual({ sections: [{ section: '五、4', rows: 31, kept: 1 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-d1/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.post).toHaveBeenCalledTimes(1)
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    expect(J(sent)).toBe(J(tabPayload('listed', CTX.applicableStandards)))
    const sub = sent.sub_table_data
    expect(sub['应收票据'].at(-1)).toMatchObject({ label: '合计', end_balance: 700, end_provision: 25, prior_balance: 400, is_total: true })
    expect(sub['按坏账计提方法分类（期末余额）'].map((r: any) => r.label)).toEqual([
      '按单项计提坏账准备', '其中：', '甲公司', '按组合计提坏账准备', '其中：', '银行承兑汇票', '商业承兑汇票', '合计',
    ])
    expect(sub['组合计提项目：商业承兑汇票'][0]).toMatchObject({ label: '1年以内' })
    expect(sub['期末已质押的应收票据'].at(-1)).toMatchObject({ is_total: true })
    expect(sub._note_texts.map((t: any) => t.section)).toEqual(['note-top', 'note-transfer'])
    expect(sent.current_standard).toBe('listed_consolidated')
  })

  it('国企：写 八、4，组合账龄行 / 变动「其中：」明细与 Tab 路径逐字节相同', async () => {
    const standards = ['soe_standalone', 'soe', 'standalone']
    const out = await d1HeadlessProvider({ ...CTX, variant: 'soe', applicableStandards: standards })
    expect(out.sections.map((s) => s.section)).toEqual(['八、4'])
    const sent = h.post.mock.calls[0][1]
    expect(J(sent)).toBe(J(tabPayload('soe', standards)))
    const portfolio = sent.sub_table_data['按组合计提坏账准备的应收票据'] as Array<{ label: string; balance: number }>
    expect(portfolio.map((r) => [r.label, r.balance])).toEqual([
      ['商业承兑汇票小计：', 200], ['1年以内', 200], ['银行承兑汇票小计：', 400], ['合计', 600],
    ])
    const movement = sent.sub_table_data['本期计提、收回或转回的应收票据坏账准备情况'] as Array<{ label: string; end_balance: number }>
    expect(movement.find((r) => r.label === '按组合计提预期信用损失的应收票据')?.end_balance).toBe(24)
    expect(movement.find((r) => r.label === '合计')?.end_balance).toBe(34)
    expect(sent.sub_table_data._note_texts.map((t: any) => t.section)).toEqual(['note-badDebtClass'])
  })

  it('Tab 接线：展开行、说明加载与同步快照都调共用函数', () => {
    const src = readFileSync(resolve(__dirname, '../../d1/D1TabDisclosure.vue'), 'utf-8')
    expect(src).toContain("computed(() => buildD1BadDebtDisplayRows(d1, 'end'))")
    expect(src).toContain('computed(() => buildD1SoeAgingRows(d1))')
    expect(src).toContain('computed(() => buildD1SoeMovementDisplayRows(d1))')
    expect(src).toContain('readD1SectionNotes(props.allResponses, props.variant, NOTE_SECTION_KEYS)')
    const sync = src.slice(src.indexOf('async function syncToDisclosureNotes'))
    expect(sync).toContain('const snapshot = buildD1DisclosureSnapshot(props.variant, d1, sectionNotes.value)')
    expect(src).not.toMatch(/function buildBadDebtRows\b/)
  })
})
