/**
 * K13 营业外支出披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 逐行读回 + 动态去向行 + K13-1 审定表取数原在两个 Tab SFC 里内联，抽成 `k13DisclosureTabState` 后 Tab 与离屏同步共用。判据：
 * ①挂载真实 Tab、点「同步到附注」发出的载荷 == 离屏载荷（上市 五、80 / 国企 八、77）②夹具覆盖取数各分支：固定分类精确命中、
 * 审定数为 0 不写、已保存的动态行被审定数更新、未匹配去向新建动态行、动态行前缀按口径分开；没有 K13-1 时只用读回值
 * ③Tab 挂载取数后照旧逐行 / 动态行保存，离屏只改内存、不写底稿 ④静态接线。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), apiGet: vi.fn(), apiPost: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet, post: h.apiPost, put: vi.fn() } }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(() => Promise.resolve()) }),
  useRoute: () => ({ params: {}, query: {}, path: '/', name: 'wp' }),
}))
vi.mock('element-plus', async () => ({
  ...(await vi.importActual<Record<string, unknown>>('element-plus')),
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))
vi.mock('@/components/workpaper/GtIndexChip.vue', () => ({ default: { name: 'GtIndexChip', render: () => null } }))

import { k13HeadlessProvider } from '../k13HeadlessDisclosure'
import K13TabDisclosureListed from '../../k13/core/K13TabDisclosureListed.vue'
import K13TabDisclosureSoe from '../../k13/core/K13TabDisclosureSoe.vue'

const J = JSON.stringify
type Resp = { item_id: string; remark: string | null; conclusion: string | null }
const ROW = (o: Record<string, unknown>) => J({ currentAmount: 0, priorAmount: 0, nonRecurring: 0, remark: '', ...o })
const RESPONSES: Resp[] = [
  {
    item_id: 'K13-1-rows',
    remark: J([
      { name: '非流动资产毁损报废损失', audited: 5000 },
      { name: '罚款滞纳金支出', unadjusted: 300, aje: 0, rje: 0 },
      { name: '债务重组损失', audited: 0 },
      { name: '对外赔偿支出', audited: 800 },
      { name: '违约金支出', audited: 150 },
    ]),
    conclusion: null,
  },
  { item_id: 'K13-disc-listed-row-0', remark: ROW({ currentAmount: 1, priorAmount: 4200, nonRecurring: 5000, remark: '报废' }), conclusion: null },
  { item_id: 'K13-disc-listed-row-12', remark: ROW({ currentAmount: 90, nonRecurring: 90 }), conclusion: null },
  { item_id: 'K13-disc-listed-dyn-对外赔偿支出', remark: ROW({ category: '对外赔偿支出', currentAmount: 10, priorAmount: 600, nonRecurring: 800, remark: '赔偿' }), conclusion: null },
  { item_id: 'K13-disclosure-listed-narrative', remark: '营业外支出说明', conclusion: null },
  { item_id: 'K13-disc-soe-row-6', remark: ROW({ currentAmount: 20, priorAmount: 5, nonRecurring: 20 }), conclusion: null },
  { item_id: 'K13-disc-soe-dyn-国企动态去向', remark: ROW({ category: '国企动态去向', currentAmount: 33, priorAmount: 11 }), conclusion: null },
  { item_id: 'K13A-proc-1', remark: '程序', conclusion: null },
  { item_id: 'K12-1-rows', remark: '[]', conclusion: null },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-k13', wpCode: 'K13' }
const LISTED = { ...CTX, variant: 'listed' as const, applicableStandards: ['listed_standalone'] }
const SOE = { ...CTX, variant: 'soe' as const, applicableStandards: ['soe_standalone'] }

const STUBS = {
  'el-button': { template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>', emits: ['click'] },
  'el-card': { template: '<div><slot name="header" /><slot /></div>' },
  'el-table': true,
  'el-table-column': true,
  'el-input': true,
  'el-icon': true,
  GtIndexChip: true,
  WpAmountInput: true,
}

/** Tab 路径：挂载真实 Tab（同一批 K13- 回复），点「同步到附注」，取它发出的载荷与挂载期的保存 */
async function tabRun(variant: 'listed' | 'soe', list: Resp[] = RESPONSES) {
  const allResponses = new Map(list.filter((r) => r.item_id.startsWith('K13-')).map((r) => [r.item_id, { ...r }]))
  const wrapper = mount(variant === 'listed' ? K13TabDisclosureListed : K13TabDisclosureSoe, {
    props: {
      wpId: 'wp-k13', projectId: 'p1', allResponses, isReadonly: false,
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

/** 非零行：[行名, 本期, 上期, 非经常性] */
function nonZero(sent: any): Array<[string, number, number, number]> {
  return (sent.sub_table_data['营业外支出'] as any[])
    .filter((r) => r.current_amount || r.prior_amount || r.non_recurring_amount)
    .map((r) => [r.label, r.current_amount, r.prior_amount, r.non_recurring_amount])
}

describe('k13HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 17, push_kept: [{ table: '营业外支出' }] })
  })

  it('上市：离屏载荷与真实 Tab 点「同步到附注」发出的逐字节相同，静默发出、不写底稿', async () => {
    const out = await k13HeadlessProvider(LISTED)
    expect(out).toEqual({ sections: [{ section: '五、80', rows: 17, kept: 1 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-k13/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    const tab = await tabRun('listed')
    expect(J(sent)).toBe(J(tab.payload))
    // Tab 挂载取数：固定分类命中两行逐行保存，动态去向一更新一新建各存一次；离屏同一步只改内存
    expect(tab.saves).toEqual([
      'K13-disc-listed-row-0', 'K13-disc-listed-row-7', 'K13-disc-listed-dyn-对外赔偿支出', 'K13-disc-listed-dyn-违约金支出',
    ])
    expect(nonZero(sent)).toEqual([
      ['非流动资产毁损报废损失', 5000, 4200, 5000],
      ['罚款滞纳金支出', 300, 0, 0],
      ['非常损失', 90, 0, 90],
      ['对外赔偿支出', 800, 600, 800],
      ['违约金支出', 150, 0, 0],
      ['合计', 6340, 4800, 5890],
    ])
    expect(sent.sub_table_data['营业外支出']).toHaveLength(17)
    expect(sent.sub_table_data._note_texts).toEqual([{ section: 'k13-note', title: '营业外支出说明', text: '营业外支出说明' }])
    expect(sent.sub_table_data._removed_table_keys).toEqual(['项  目'])
  })

  it('国企：精简分类、动态行只读国企前缀，与真实 Tab 逐字节相同', async () => {
    const out = await k13HeadlessProvider(SOE)
    expect(out.sections.map((s) => s.section)).toEqual(['八、77'])
    const sent = h.post.mock.calls[0][1]
    const tab = await tabRun('soe')
    expect(J(sent)).toBe(J(tab.payload))
    expect(tab.saves).toEqual([
      'K13-disc-soe-row-3', 'K13-disc-soe-dyn-非流动资产毁损报废损失', 'K13-disc-soe-dyn-对外赔偿支出', 'K13-disc-soe-dyn-违约金支出',
    ])
    expect(nonZero(sent)).toEqual([
      ['罚款滞纳金支出', 300, 0, 0],
      ['非常损失', 20, 5, 20],
      ['国企动态去向', 33, 11, 0],
      ['非流动资产毁损报废损失', 5000, 0, 0],
      ['对外赔偿支出', 800, 0, 0],
      ['违约金支出', 150, 0, 0],
      ['合计', 6303, 16, 20],
    ])
    expect(sent.sub_table_data._note_texts).toBeUndefined()
    expect(sent.sub_table_data._removed_table_keys).toBeUndefined()
  })

  it('没有 K13-1 审定表：只用读回行与已保存动态行，与真实 Tab 相同', async () => {
    const list = RESPONSES.filter((r) => r.item_id !== 'K13-1-rows')
    h.get.mockResolvedValue(list)
    await k13HeadlessProvider(LISTED)
    const sent = h.post.mock.calls[0][1]
    const tab = await tabRun('listed', list)
    expect(J(sent)).toBe(J(tab.payload))
    expect(tab.saves).toEqual([])
    expect(nonZero(sent)).toEqual([
      ['非流动资产毁损报废损失', 1, 4200, 5000],
      ['非常损失', 90, 0, 90],
      ['对外赔偿支出', 10, 600, 800],
      ['合计', 101, 4800, 5890],
    ])
  })

  it('静态接线：两个 Tab 调共用的读回 / 动态行 / 取数 / 同步行函数，不再内联', () => {
    const dir = resolve(__dirname, '../../k13/core')
    for (const [file, variant] of [['K13TabDisclosureListed.vue', 'listed'], ['K13TabDisclosureSoe.vue', 'soe']]) {
      const src = readFileSync(resolve(dir, file), 'utf-8')
      expect(src, file).toContain(`const VARIANT = '${variant}'`)
      expect(src, file).toContain('loadK13DisclosureState(props.allResponses, VARIANT)')
      expect(src, file).toContain('loadK13DynamicRows(disclosureRows.value, props.allResponses, VARIANT)')
      expect(src, file).toMatch(/applyK13AutoFill\(disclosureRows\.value, props\.allResponses, VARIANT, \{\s*onFixedFilled: handleRowChange,\s*onDynamicFilled: persistDynamicRow,\s*\}\)/)
      expect(src, file).toContain(
        "buildK13SyncPayload(VARIANT, props.wpId || '', k13DisclosureSyncRows(disclosureRows.value), narrativeText.value)",
      )
      // 逐行保存的条目字面量原样留在 Tab（K 循环键守卫按字面量模板计数）；与读回同形由「挂载期逐行保存」断言钉住
      expect(src, file).toContain('emit(\'save\', `K13-disc-' + variant + '-row-${idx}`, JSON.stringify({')
      expect(src, file).not.toMatch(/function buildAdjAuditedMap|const matchedNames|for \(const \[key, val\] of props\.allResponses\)/)
    }
  })
})
