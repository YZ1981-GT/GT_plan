/**
 * G5 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 快照与载荷（含上市组合计提表的孤儿表差集）原在两个 Tab 的 `syncToDisclosureNotes` 里内联，抽成 `g5DisclosureTabSync`
 * 后 Tab 与离屏同步共用。判据：①挂载真实 Tab（宿主表单数据照常加载、onMounted 后 loadPersisted）、点「同步到附注」发出的
 * 载荷 == 离屏载荷 ②上市按「上次已同步表名」清理旧组合表，离屏不记账（不写底稿）③只读 G5- 条目 ④口径不适用回空 ⑤静态接线。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const h = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), put: vi.fn(), apiGet: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn(),
}))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet, post: h.apiPost, put: h.apiPut } }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(() => Promise.resolve()) }),
  useRoute: () => ({ params: {}, query: {}, path: '/', name: 'wp' }),
}))
vi.mock('element-plus', async () => ({
  ...(await vi.importActual<Record<string, unknown>>('element-plus')),
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

import { g5HeadlessProvider } from '../g5HeadlessDisclosure'
import { G5_LISTED_SYNCED_TABLES_ITEM } from '../g5DisclosureTabSync'
import { buildDefaultListedState, createEmptyPortfolio, serializeListedDisclosure } from '../g5ListedDisclosureRows'
import { buildDefaultSoeState, serializeSoeDisclosure } from '../g5SoeDisclosureRows'
import G5TabDisclosureListed from '../../g5-long-term-receivable/core/G5TabDisclosureListed.vue'
import G5TabDisclosureSOE from '../../g5-long-term-receivable/core/G5TabDisclosureSOE.vue'
import type { ChecklistResponse } from '../useF1FormData'

function withNature<T extends { natureRows: Array<{ rowKey: string; end: unknown; prior: unknown }> }>(state: T): T {
  state.natureRows = state.natureRows.map((r) => (r.rowKey === 'finance-lease'
    ? { ...r, end: { balance: 800, provision: 40 }, prior: { balance: 600, provision: 30 } }
    : r)) as T['natureRows']
  return state
}

const listedState = withNature(buildDefaultListedState())
const portfolio = createEmptyPortfolio('账龄组合')
portfolio.agingRows = portfolio.agingRows.map((r, i) => (i === 0 ? { ...r, endBalance: 500, endProvision: 25 } : r))
listedState.portfolios = [portfolio]
listedState.unrealizedNote = '未实现融资收益说明'
const soeState = withNature(buildDefaultSoeState())
soeState.derecogRows = [{ id: 'dr-1', item: '应收融资租赁款保理', transferMethod: '无追索权保理', amount: 300, gainLoss: -5 }]
soeState.continuing = { assetEnd: 10, liabilityEnd: 8 }
soeState.provisionMethodNote = '按组合计提'

const LISTED_JSON = serializeListedDisclosure(listedState)
const SOE_JSON = serializeSoeDisclosure(soeState)
const RESPONSES: ChecklistResponse[] = [
  { item_id: 'G5-note-listed-rows', remark: LISTED_JSON, conclusion: LISTED_JSON },
  { item_id: 'G5-note-listed-note', remark: '上市长期应收款说明', conclusion: null },
  {
    item_id: G5_LISTED_SYNCED_TABLES_ITEM,
    remark: JSON.stringify(['组合计提项目：旧组合', '组合计提项目：账龄组合']),
    conclusion: null,
  },
  { item_id: 'G5-note-soe-rows', remark: SOE_JSON, conclusion: SOE_JSON },
  { item_id: 'G5-note-soe-note', remark: '国企长期应收款说明', conclusion: null },
  { item_id: 'G4-disclosure-listed-stages', remark: '别的底稿', conclusion: null },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-g5', wpCode: 'G5' }
const SOE = { ...CTX, variant: 'soe' as const, applicableStandards: ['soe_standalone'] }
const LISTED = { ...CTX, variant: 'listed' as const, applicableStandards: ['listed_standalone'] }

const STUBS = {
  'el-button': { template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>', emits: ['click'] },
  'el-alert': true, 'el-card': true, 'el-dialog': true, 'el-input': true, 'el-input-number': true, 'el-option': true,
  'el-select': true, 'el-switch': true, 'el-table': true, 'el-table-column': true, 'el-tag': true,
  G5AuditTextCards: true, GtIndexChip: true, GtReviewTrigger: true, WpAmountInput: true,
}

/** Tab 路径：挂载真实 Tab（宿主表单数据照常加载），点「同步到附注」，取它发出的载荷 */
async function tabPayload(variant: 'soe' | 'listed') {
  h.apiGet.mockImplementation(async (url: string) => (url.endsWith('/checklist-responses') ? RESPONSES : { sheets: [] }))
  h.apiPost.mockResolvedValue({ rows_synced: 9 })
  const wrapper = mount(variant === 'soe' ? G5TabDisclosureSOE : G5TabDisclosureListed, {
    props: {
      wpId: 'wp-g5', projectId: 'p1', readonly: false,
      applicableStandards: variant === 'soe' ? ['soe_standalone'] : ['listed_standalone'],
    },
    global: { stubs: STUBS },
  })
  await flushPromises()
  const before = h.apiPost.mock.calls.length
  const button = wrapper.findAll('button').find((b) => b.text().includes('同步到附注'))
  expect(button, '找不到「同步到附注」按钮').toBeDefined()
  await button!.trigger('click')
  await flushPromises()
  expect(h.apiPost.mock.calls.length).toBe(before + 1)
  const [url, payload] = h.apiPost.mock.calls[before]
  expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
  wrapper.unmount()
  return payload
}

describe('g5HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 9, push_kept: [{ table: '长期应收款按性质披露' }] })
  })

  it('上市：离屏载荷与真实 Tab 点「同步到附注」发出的逐字节相同；按上次已同步表名清理旧组合表、不记账', async () => {
    const out = await g5HeadlessProvider(LISTED)
    expect(out).toEqual({ sections: [{ section: '五、16', rows: 9, kept: 1 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-g5/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiPut).not.toHaveBeenCalled()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    expect(sent.sub_table_data._removed_table_keys).toEqual(['组合计提项目：旧组合'])
    const pf = sent.sub_table_data['组合计提项目：账龄组合'] as Array<{ end_gross: number; is_total?: boolean }>
    expect(pf[0].end_gross).toBe(500)
    expect(pf.at(-1)).toMatchObject({ is_total: true, end_gross: 500 })
    const nature = sent.sub_table_data['长期应收款按性质披露'] as Array<{ row_key?: string; end_gross: number }>
    expect(nature.find((r) => r.row_key === 'finance-lease')?.end_gross).toBe(800)
    expect(sent.sub_table_data._note_texts).toEqual([
      { section: 'listed-unrealized-finance-income', text: '未实现融资收益说明' },
      { section: 'listed-disclosure-note', text: '上市长期应收款说明' },
    ])
    expect(JSON.stringify(sent)).toBe(JSON.stringify(await tabPayload('listed')))
  })

  it('国企：离屏载荷与真实 Tab 逐字节相同（性质 / 终止确认 / 继续涉入）', async () => {
    const out = await g5HeadlessProvider(SOE)
    expect(out).toEqual({ sections: [{ section: '八、17', rows: 9, kept: 1 }] })
    const sent = h.post.mock.calls[0][1]
    expect(sent.sub_table_data['终止确认的长期应收款']?.[0]).toMatchObject({ label: '应收融资租赁款保理', derecognized_amount: 300 })
    expect(sent.sub_table_data._removed_table_keys).toBeUndefined()
    expect(h.apiPut).not.toHaveBeenCalled()
    expect(JSON.stringify(sent)).toBe(JSON.stringify(await tabPayload('soe')))
  })

  it('口径不适用回空，不发请求', async () => {
    expect(await g5HeadlessProvider({ ...SOE, applicableStandards: ['listed_standalone'] })).toEqual({ sections: [] })
    expect(await g5HeadlessProvider({ ...LISTED, applicableStandards: ['soe_standalone'] })).toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('静态接线：两个 Tab 调同一个载荷函数，不再内联组快照', () => {
    const dir = resolve(__dirname, '../../g5-long-term-receivable/core')
    const listed = readFileSync(resolve(dir, 'G5TabDisclosureListed.vue'), 'utf-8')
    expect(listed).toMatch(/buildG5ListedTabSyncPayload\(\s*props\.wpId,\s*props\.applicableStandards,\s*dis,\s*g5Notes\.allResponses\.value,?\s*\)/)
    expect(listed).toContain('g5Notes.debouncedSave(G5_LISTED_SYNCED_TABLES_ITEM')
    expect(listed).not.toMatch(/function listedSnapshot|buildRemovedTableKeys\(/)
    const soe = readFileSync(resolve(dir, 'G5TabDisclosureSOE.vue'), 'utf-8')
    expect(soe).toMatch(/buildG5SoeTabSyncPayload\(props\.wpId, props\.applicableStandards, dis\)/)
    expect(soe).not.toMatch(/buildG5SoeSyncPayload\(/)
  })
})
