/**
 * K12 营业外收入披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 逐行读回 + 附注说明 + K12-1 审定表取数原在两个 Tab SFC 里内联，抽成 `k12DisclosureTabState` 后 Tab 与离屏同步共用。判据：
 * ①挂载真实 Tab、点「同步到附注」发出的载荷 == 离屏载荷（上市 五、79 / 国企 八、76；第 4 列「计入当期非经常性损益的金额」
 * 来自读回行）②夹具有真实数据：审定表命中的行覆盖读回金额，未命中的行保持读回值，坏行保持 0 ③Tab 挂载取数后照旧逐行保存，
 * 离屏只改内存、不写底稿 ④国企政府补助明细子表不进载荷 ⑤静态接线。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), apiGet: vi.fn(), apiPost: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet, post: h.apiPost, put: vi.fn() } }))
vi.mock('element-plus', async () => ({
  ...(await vi.importActual<Record<string, unknown>>('element-plus')),
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

import { k12HeadlessProvider } from '../k12HeadlessDisclosure'
import K12TabDisclosureListed from '../../k12/core/K12TabDisclosureListed.vue'
import K12TabDisclosureSoe from '../../k12/core/K12TabDisclosureSoe.vue'

const J = JSON.stringify
type Resp = { item_id: string; remark: string | null; conclusion: string | null }
const RESPONSES: Resp[] = [
  {
    item_id: 'K12-1-rows',
    remark: J([
      { name: '捐赠利得', audited: 800, priorAudited: 300 },
      { name: '与日常活动无关的政府补助', unadjusted: 1000, aje: 200, rje: 0, priorUnadj: 500, priorAje: 0, priorRje: 0 },
      { name: '未在披露分类里的项目', audited: 50, priorAudited: 0 },
    ]),
    conclusion: null,
  },
  { item_id: 'K12-disc-listed-row-1', remark: J({ currentAmount: 1, priorAmount: 1, nonRecurringAmount: 800, remark: '' }), conclusion: null },
  { item_id: 'K12-disc-listed-row-2', remark: J({ currentAmount: 60, priorAmount: 40, nonRecurringAmount: 60, remark: '盘盈' }), conclusion: null },
  // 真库形态：逐行保存只落了行说明（空串）⇒ 解析失败，该行保持默认 0
  { item_id: 'K12-disc-listed-row-4', remark: '', conclusion: null },
  { item_id: 'K12-disclosure-listed-narrative', remark: '营业外收入说明文字', conclusion: null },
  { item_id: 'K12-disc-soe-row-3', remark: J({ currentAmount: 70, priorAmount: 0, nonRecurringAmount: 70, remark: '' }), conclusion: null },
  { item_id: 'K12-disclosure-soe-narrative', remark: null, conclusion: '国企说明（结论栏）' },
  { item_id: 'K12-disc-soe-govgrant-rows', remark: J([{ rowKey: 'gg-1', item: '搬迁补助', currentAmount: 999, priorAmount: 0 }]), conclusion: null },
  { item_id: 'K12A-proc-1', remark: '程序', conclusion: null },
  { item_id: 'K13-1-rows', remark: '[]', conclusion: null },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-k12', wpCode: 'K12' }
const LISTED = { ...CTX, variant: 'listed' as const, applicableStandards: ['listed_standalone'] }
const SOE = { ...CTX, variant: 'soe' as const, applicableStandards: ['soe_standalone'] }

const STUBS = {
  'el-button': { template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>', emits: ['click'] },
  'el-card': { template: '<div><slot name="header" /><slot /></div>' },
  'el-table': true,
  'el-table-column': true,
  'el-input': true,
  'el-icon': true,
  'el-tooltip': true,
  WpAmountInput: true,
}

/** Tab 路径：挂载真实 Tab（同一批 K12- 回复），点「同步到附注」，取它发出的载荷与挂载期的逐行保存 */
async function tabRun(variant: 'listed' | 'soe') {
  const allResponses = new Map(RESPONSES.filter((r) => r.item_id.startsWith('K12-')).map((r) => [r.item_id, { ...r }]))
  const wrapper = mount(variant === 'listed' ? K12TabDisclosureListed : K12TabDisclosureSoe, {
    props: {
      wpId: 'wp-k12', projectId: 'p1', allResponses, isReadonly: false,
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
  expect(h.post.mock.calls.length).toBe(before + 1)
  const [url, payload] = h.post.mock.calls[before]
  expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
  const saves = (wrapper.emitted('save') ?? []).map((args) => args[0])
  wrapper.unmount()
  return { payload, saves }
}

describe('k12HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 6, push_kept: [] })
  })

  it('上市：离屏载荷与真实 Tab 点「同步到附注」发出的逐字节相同，静默发出、不写底稿', async () => {
    const out = await k12HeadlessProvider(LISTED)
    expect(out).toEqual({ sections: [{ section: '五、79', rows: 6, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-k12/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    const tab = await tabRun('listed')
    expect(J(sent)).toBe(J(tab.payload))
    // Tab 挂载时审定表命中的两行照旧逐行保存；离屏同一步只改内存
    expect(tab.saves).toEqual(['K12-disc-listed-row-0', 'K12-disc-listed-row-1'])
    expect(sent.sub_table_data['营业外收入']).toEqual([
      { label: '与日常活动无关的政府补助', current_amount: 1200, prior_amount: 500, non_recurring_amount: 0 },
      { label: '捐赠利得', current_amount: 800, prior_amount: 300, non_recurring_amount: 800 },
      { label: '盘盈利得（不包括存货盘盈及固定资产盘盈）', current_amount: 60, prior_amount: 40, non_recurring_amount: 60 },
      { label: '碳排放配额出售利得', current_amount: 0, prior_amount: 0, non_recurring_amount: 0 },
      { label: '其他', current_amount: 0, prior_amount: 0, non_recurring_amount: 0 },
      { label: '合计', current_amount: 2060, prior_amount: 840, is_total: true, non_recurring_amount: 860 },
    ])
    expect(sent.sub_table_data._note_texts).toEqual([{ section: 'k12-note', title: '营业外收入说明', text: '营业外收入说明文字' }])
    expect(sent.sub_table_data._removed_table_keys).toEqual(['项  目'])
  })

  it('国企：附注说明取结论栏、政府补助明细不进载荷，与真实 Tab 逐字节相同', async () => {
    const out = await k12HeadlessProvider(SOE)
    expect(out.sections.map((s) => s.section)).toEqual(['八、76'])
    const sent = h.post.mock.calls[0][1]
    const tab = await tabRun('soe')
    expect(J(sent)).toBe(J(tab.payload))
    expect(tab.saves).toEqual(['K12-disc-soe-row-0', 'K12-disc-soe-row-1'])
    const rows = sent.sub_table_data['营业外收入'] as Array<Record<string, unknown>>
    expect(rows[3]).toEqual({ label: '碳排放配额出售利得', current_amount: 70, prior_amount: 0, non_recurring_amount: 70 })
    expect(rows.at(-1)).toEqual({ label: '合计', current_amount: 2070, prior_amount: 800, is_total: true, non_recurring_amount: 70 })
    expect(sent.sub_table_data._note_texts).toEqual([{ section: 'k12-note', title: '营业外收入说明', text: '国企说明（结论栏）' }])
    expect(sent.sub_table_data._removed_table_keys).toBeUndefined()
    expect(J(sent)).not.toContain('搬迁补助')
  })

  it('静态接线：两个 Tab 调共用的读回 / 取数 / 同步行函数，不再内联', () => {
    const dir = resolve(__dirname, '../../k12/core')
    for (const [file, variant] of [['K12TabDisclosureListed.vue', 'listed'], ['K12TabDisclosureSoe.vue', 'soe']]) {
      const src = readFileSync(resolve(dir, file), 'utf-8')
      expect(src, file).toContain(`loadK12DisclosureState(props.allResponses, '${variant}')`)
      expect(src, file).toContain('applyK12AutoFill(disclosureRows.value, props.allResponses, handleRowChange)')
      expect(src, file).toContain(
        `buildK12SyncPayload('${variant}', props.wpId || '', k12DisclosureSyncRows(disclosureRows.value), narrativeText.value)`,
      )
      // 逐行保存的条目字面量原样留在 Tab（K 循环键守卫按字面量模板计数）；与读回同形由上面两条「挂载期逐行保存」断言钉住
      expect(src, file).toContain('emit(\'save\', `K12-disc-' + variant + '-row-${idx}`, {')
      expect(src, file).not.toMatch(/const CATEGORIES\s*=|new Map<string, \{ audited: number; prior: number \}>/)
    }
  })
})
