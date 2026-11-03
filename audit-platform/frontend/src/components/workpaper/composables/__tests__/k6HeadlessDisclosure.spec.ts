/**
 * K6 持有待售披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 资产主表的读回 / 默认分类 / 明细聚合取数与载荷组装原在两个 Tab SFC 里内联，抽成 `k6DisclosureTabState` 后 Tab 与离屏同步
 * 共用；附注 4 个录入区块两边都用同一个 `useK6NoteBlocks`。判据：①挂载真实 Tab、点「同步到附注」发出的载荷 == 离屏载荷
 * （上市 五、11 一条；国企 八、12 + 八、43 两条）②夹具有真实数据（明细按类别聚合、找不到类别归兜底类、期初取已保存值）
 * ③只读 K6- 条目、离屏不写底稿 ④静态接线：Tab 调共用函数，不再内联。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('element-plus', async () => ({
  ...(await vi.importActual<Record<string, unknown>>('element-plus')),
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

import { k6HeadlessProvider } from '../k6HeadlessDisclosure'
import { loadK6DisclosureState } from '../k6DisclosureTabState'
import { K6_LISTED_SUBTABLE, K6_SOE_LIABILITY_SUBTABLE, K6_SOE_SUBTABLE } from '../k6NoteSectionMap'
import K6TabDisclosureListed from '../../k6/core/K6TabDisclosureListed.vue'
import K6TabDisclosureSoe from '../../k6/core/K6TabDisclosureSoe.vue'

const J = JSON.stringify
type Resp = { item_id: string; remark: string | null; conclusion: string | null }
const listedAsset = (id: string, category: string, openingBalance: number, isTotal = false) => ({
  id, category, originalCost: 0, accumulatedDep: 0, impairment: 0, bookValue: 0, fairValue: 0, sellingCost: 0,
  fairValueNet: 0, openingBalance, closingBalance: 0, remark: '', isTotal, isAutoFill: false,
})
const RESPONSES: Resp[] = [
  {
    item_id: 'K6-disclosure-listed-asset-table',
    remark: J([listedAsset('a1', '固定资产', 500), listedAsset('a2', '其他非流动资产', 20), listedAsset('at', '合计', 520, true)]),
    conclusion: null,
  },
  {
    item_id: 'K6-2-rows',
    remark: J([
      { category: '固定资产', costValue: 1000, accumulatedDep: 300, impairmentProvision: 50, bookValue: 650, fairValue: 700, sellingCost: 20, fairValueNet: 680 },
      { category: '未登记类', costValue: 200, accumulatedDep: 0, impairmentProvision: 10, bookValue: 190, fairValue: 0, sellingCost: 0, fairValueNet: 0 },
    ]),
    conclusion: null,
  },
  { item_id: 'K6-disclosure-listed-impairment-rows', remark: J([{ id: 'i1', project: '固定资产', priorAmount: 10, increase: 40, reverse: 0, disposal: 0 }]), conclusion: null },
  { item_id: 'K6-disclosure-listed-liabilities-rows', remark: J([{ id: 'l1', project: '应付账款', endAmount: 30, priorAmount: 5 }]), conclusion: null },
  { item_id: 'K6-disclosure-listed-narrative', remark: '持有待售说明（上市）', conclusion: null },
  { item_id: 'K6-disclosure-soe-liabilities-rows', remark: J([{ id: 's1', project: '应付账款', endBook: 30, endFairValue: 28, disposalFee: 1, timetable: '2026年' }]), conclusion: null },
  { item_id: 'K6-disclosure-soe-narrative', remark: '持有待售说明（国企）', conclusion: null },
  { item_id: 'K6-disclosure-listed-cas42', remark: J({ impairmentLoss: 0, disposalGroupProfit: 3, isDiscontinuedOp: 'no' }), conclusion: null },
  { item_id: 'K6-1-impairment-total', remark: '60', conclusion: null },
  { item_id: 'K6A-proc-1', remark: '程序', conclusion: null },
  { item_id: 'K5-1-audited-total', remark: '{}', conclusion: null },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-k6', wpCode: 'K6' }
const LISTED = { ...CTX, variant: 'listed' as const, applicableStandards: ['listed_standalone'] }
const SOE = { ...CTX, variant: 'soe' as const, applicableStandards: ['soe_standalone'] }

const STUBS = {
  'el-button': { template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>', emits: ['click'] },
  'el-card': { template: '<div><slot name="header" /><slot /></div>' },
  'el-table': true,
  'el-table-column': true,
  'el-input': true,
  'el-select': true,
  'el-option': true,
  'el-tag': true,
  'el-icon': true,
  WpAmountInput: true,
  K6NoteBlockTables: true,
}

/** Tab 路径：挂载真实 Tab（同一批 K6- 回复），点「同步到附注」，取它发出的全部载荷 */
async function tabPayloads(variant: 'listed' | 'soe', list: Resp[] = RESPONSES) {
  const allResponses = new Map(list.filter((r) => r.item_id.startsWith('K6-')).map((r) => [r.item_id, { ...r }]))
  const wrapper = mount(variant === 'listed' ? K6TabDisclosureListed : K6TabDisclosureSoe, {
    props: {
      wpId: 'wp-k6', projectId: 'p1', allResponses, isReadonly: false,
      applicableStandards: [variant === 'listed' ? 'listed_standalone' : 'soe_standalone'],
    },
    global: { stubs: STUBS },
  })
  await flushPromises()
  const before = h.post.mock.calls.length
  const button = wrapper.findAll('button').find((b) => b.text().includes('同步到附注'))
  expect(button, '找不到「同步到附注」按钮').toBeDefined()
  await button!.trigger('click')
  await flushPromises()
  const calls = h.post.mock.calls.slice(before)
  for (const [url] of calls) expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
  expect(wrapper.emitted('save'), '挂载 + 同步不写底稿').toBeUndefined()
  wrapper.unmount()
  return calls.map(([, payload]) => payload)
}

describe('k6HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 4, push_kept: [] })
  })

  it('上市：离屏载荷与真实 Tab 点「同步到附注」发出的逐字节相同（已保存期初 + 明细聚合 + 4 个区块），静默发出、不写底稿', async () => {
    const out = await k6HeadlessProvider(LISTED)
    expect(out).toEqual({ sections: [{ section: '五、11', rows: 4, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-k6/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    const tab = await tabPayloads('listed')
    expect(tab).toHaveLength(1)
    expect(J(sent)).toBe(J(tab[0]))
    // 固定资产取明细 650 / 50、期初保留已保存的 500；未登记类归「其他非流动资产」（190 / 10，期初 20）
    expect(sent.sub_table_data[K6_LISTED_SUBTABLE.main]).toEqual([
      { label: '固定资产', values: [700, 50, 650, null, null, 500] },
      { label: '其他非流动资产', values: [200, 10, 190, null, null, 20] },
      { label: '合计', values: [900, 60, 840, null, null, 520], is_total: true },
    ])
    expect(sent.sub_table_data[K6_LISTED_SUBTABLE.liability]).toEqual([
      { label: '应付账款', end_amount: 30, prior_amount: 5 },
      { label: '合计', end_amount: 30, prior_amount: 5, is_total: true },
    ])
    expect(Object.keys(sent.sub_table_data)).toContain(K6_LISTED_SUBTABLE.impairment)
    expect(sent.sub_table_data._removed_table_keys).toEqual(
      expect.arrayContaining([K6_LISTED_SUBTABLE.nonCurrent, K6_LISTED_SUBTABLE.disposalGroup]),
    )
    expect(sent.sub_table_data._note_texts?.[0]?.text).toBe('持有待售说明（上市）')
  })

  it('国企：无已保存资产表 ⇒ 默认 5 类 + 明细聚合；八、12 与 八、43 两条载荷都与真实 Tab 逐字节相同', async () => {
    const out = await k6HeadlessProvider(SOE)
    expect(out.sections.map((s) => s.section)).toEqual(['八、12', '八、43'])
    const sent = h.post.mock.calls.map((c) => c[1])
    const tab = await tabPayloads('soe')
    expect(J(sent)).toBe(J(tab))
    const main = sent[0].sub_table_data[K6_SOE_SUBTABLE.main] as Array<{ label: string; values: unknown[] }>
    expect(main.map((r) => r.label)).toEqual(['固定资产', '在建工程', '无形资产', '长期股权投资', '其他', '合计'])
    expect(main[0].values).toEqual([700, 50, 650, null, null, 0])
    expect(main[4].values).toEqual([200, 10, 190, null, null, 0])
    expect(sent[1].section_id).toBe('八、43')
    expect(sent[1].sub_table_data[K6_SOE_LIABILITY_SUBTABLE.liability][0]).toEqual(
      { label: '应付账款', end_book: 30, end_fair_value: 28, disposal_fee: 1, timetable: '2026年' },
    )
  })

  it('国企没有负债区块：八、43 仍发清理载荷（与 Tab 一致），一个章节失败不影响另一个', async () => {
    const list = RESPONSES.filter((r) => r.item_id !== 'K6-disclosure-soe-liabilities-rows')
    h.get.mockResolvedValue(list)
    h.post.mockResolvedValueOnce({ rows_synced: 6, push_kept: [] }).mockRejectedValueOnce({ message: '网络中断' })
    const out = await k6HeadlessProvider(SOE)
    expect(out.sections).toEqual([
      { section: '八、12', rows: 6, kept: 0 },
      { section: '八、43', rows: 0, error: '网络中断' },
    ])
    const sent = h.post.mock.calls.map((c) => c[1])
    expect(sent[1].sub_table_data._removed_table_keys).toEqual([K6_SOE_LIABILITY_SUBTABLE.liability])
    expect(sent[1].sub_table_data[K6_SOE_LIABILITY_SUBTABLE.liability]).toBeUndefined()
    h.post.mockReset()
    h.post.mockResolvedValue({ rows_synced: 1, push_kept: [] })
    expect(J(sent)).toBe(J(await tabPayloads('soe', list)))
  })

  it('默认资产表的行身份走调用方注入的工厂（Tab 按 id 编辑行），合计行 id 固定', () => {
    let seq = 0
    expect(loadK6DisclosureState(new Map(), 'listed', () => `a${++seq}`).assets.map((r) => r.id))
      .toEqual(['a1', 'a2', 'a3', 'a4', 'a5', 'a6', 'asset-total'])
    seq = 0
    expect(loadK6DisclosureState(new Map(), 'soe', () => `s${++seq}`).assets.map((r) => r.id))
      .toEqual(['s1', 's2', 's3', 's4', 's5', 'soe-asset-total'])
  })

  it('静态接线：两个 Tab 调共用的读回 / 取数 / 载荷组装函数，不再内联', () => {
    const dir = resolve(__dirname, '../../k6/core')
    const cases = [
      ['K6TabDisclosureListed.vue', 'listed', 'asset', 'assetTable', 'disposalNarrative'],
      ['K6TabDisclosureSoe.vue', 'soe', 'soe-asset', 'assetSummary', 'narrativeText'],
    ] as const
    for (const [file, variant, idPrefix, table, narrative] of cases) {
      const src = readFileSync(resolve(dir, file), 'utf-8')
      expect(src, file).toContain(`loadK6DisclosureState(props.allResponses, '${variant}', () => newRowIdentity('${idPrefix}'))`)
      expect(src, file).toContain(`applyK6AssetAutoFill(${table}.value, props.allResponses, '${variant}')`)
      expect(src.replace(/\(\s+/g, '(').replace(/\s+/g, ' '), file).toContain(
        `k6DisclosurePayloads('${variant}', props.wpId || '', ${table}.value, noteBlocks, ${narrative}.value`,
      )
      expect(src, file).not.toMatch(/function initDefaultAssetTable|function recalcAssetTotals|K6-2-rows|buildK6SyncPayload\(/)
    }
  })
})
