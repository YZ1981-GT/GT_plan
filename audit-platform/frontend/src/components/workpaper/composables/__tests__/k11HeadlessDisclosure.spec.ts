/**
 * K11 资产减值损失披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 表格行 + 附注说明的读回与自动取数原在两个 Tab SFC 里内联，抽成 `k11DisclosureTabState` 后 Tab 与离屏同步共用。判据：
 * ①挂载真实 Tab、点「同步到附注」发出的载荷 == 离屏载荷（上市 五、77 走「K11-1 审定表行 + 按类别自动取数」，国企 八、74 走
 * 「已保存行 + 自动取数覆盖 + 剔合计行」，无回复走 18 项默认分类）②夹具有真实数据（披露表负数填列）③只读 K11- 条目、
 * 离屏不写底稿 ④静态接线：Tab 调共用函数，不再内联读回 / 取数。
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

import { k11HeadlessProvider } from '../k11HeadlessDisclosure'
import { k11DefaultDisclosureRows, loadK11DisclosureState } from '../k11DisclosureTabState'
import K11TabDisclosureListed from '../../k11/core/K11TabDisclosureListed.vue'
import K11TabDisclosureSoe from '../../k11/core/K11TabDisclosureSoe.vue'

const J = JSON.stringify
type Resp = { item_id: string; remark: string | null; conclusion: string | null }
const RESPONSES: Resp[] = [
  {
    item_id: 'K11-1-rows',
    remark: J([
      { rowKey: 'a1', projectName: '存货跌价准备', audited: 300, priorAudited: 120 },
      { rowKey: 'a2', projectName: '商誉减值准备', currentOccurrence: 500, aje: -20, rje: 0, priorAudited: 0 },
      { rowKey: 'a3', projectName: '', audited: 9 },
    ]),
    conclusion: null,
  },
  {
    item_id: 'K11-1-audited-by-category',
    remark: J({
      存货跌价: { currentProvision: 350, currentReversal: 20, priorAmount: 110, occurrence: 350 },
      固定: { currentProvision: 90, currentReversal: 5, priorAmount: 30, occurrence: 90 },
    }),
    conclusion: null,
  },
  { item_id: 'K11-disclosure-listed-narrative', remark: '本期计提存货跌价准备', conclusion: null },
  {
    item_id: 'K11-disclosure-soe-rows',
    remark: J([
      { id: 's1', category: '固定资产减值损失', currentProvision: 70, currentReversal: 0, priorAmount: 25, remark: '' },
      { id: 's2', category: '其他', currentProvision: 8, currentReversal: 2, priorAmount: 0, remark: '' },
      { id: 's3', category: '合计', currentProvision: 78, currentReversal: 2, priorAmount: 25, remark: '', isTotal: true },
    ]),
    conclusion: null,
  },
  { item_id: 'K11-disclosure-soe-narrative', remark: '国企减值说明', conclusion: null },
  { item_id: 'K11A-proc-1', remark: '程序', conclusion: null },
  { item_id: 'K12-1-rows', remark: '[]', conclusion: null },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-k11', wpCode: 'K11' }
const LISTED = { ...CTX, variant: 'listed' as const, applicableStandards: ['listed_standalone'] }
const SOE = { ...CTX, variant: 'soe' as const, applicableStandards: ['soe_standalone'] }

const STUBS = {
  'el-button': { template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>', emits: ['click'] },
  'el-card': { template: '<div><slot name="header" /><slot /></div>' },
  'el-alert': true,
  'el-table': true,
  'el-table-column': true,
  'el-input': true,
  'el-icon': true,
  GtReviewTrigger: true,
  WpAmountInput: true,
}

/** Tab 路径：挂载真实 Tab（同一批 K11- 回复），点「同步到附注」，取它发出的载荷 */
async function tabPayload(variant: 'listed' | 'soe', list: Resp[] = RESPONSES) {
  const allResponses = new Map(list.filter((r) => r.item_id.startsWith('K11-')).map((r) => [r.item_id, { ...r }]))
  const wrapper = mount(variant === 'listed' ? K11TabDisclosureListed : K11TabDisclosureSoe, {
    props: {
      wpId: 'wp-k11', projectId: 'p1', allResponses, isReadonly: false,
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
  expect(wrapper.emitted('save'), '挂载 + 同步不写底稿').toBeUndefined()
  wrapper.unmount()
  return payload
}

describe('k11HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 3, push_kept: [{ table: '资产减值损失' }] })
  })

  it('上市：离屏载荷与真实 Tab 点「同步到附注」发出的逐字节相同（K11-1 行 + 按类别自动取数），静默发出、不写底稿', async () => {
    const out = await k11HeadlessProvider(LISTED)
    expect(out).toEqual({ sections: [{ section: '五、77', rows: 3, kept: 1 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-k11/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    expect(J(sent)).toBe(J(await tabPayload('listed')))
    expect(sent.section_id).toBe('五、77')
    // 存货跌价准备：K11-1 行 300 / 120 被按类别取数覆盖为 350 − 20 / 110；商誉无类别数据，保持 K11-1 的 500 − 20
    expect(sent.sub_table_data['资产减值损失']).toEqual([
      { label: '存货跌价准备', current_amount: -330, prior_amount: -110 },
      { label: '商誉减值准备', current_amount: -480, prior_amount: 0 },
      { label: '合计', current_amount: -810, prior_amount: -110, is_total: true },
    ])
    expect(sent.sub_table_data._note_texts).toEqual([{ section: 'k11-note', title: '资产减值损失说明', text: '本期计提存货跌价准备' }])
    expect(sent.sub_table_data._removed_table_keys).toEqual(['项  目'])
  })

  it('国企：已保存行 + 自动取数覆盖、合计行不推，载荷与真实 Tab 逐字节相同', async () => {
    const out = await k11HeadlessProvider(SOE)
    expect(out.sections.map((s) => s.section)).toEqual(['八、74'])
    const sent = h.post.mock.calls[0][1]
    expect(J(sent)).toBe(J(await tabPayload('soe')))
    expect(sent.sub_table_data['资产减值损失']).toEqual([
      { label: '固定资产减值损失', current_amount: -85, prior_amount: -30 },
      { label: '其他', current_amount: -6, prior_amount: 0 },
      { label: '合计', current_amount: -91, prior_amount: -30, is_total: true },
    ])
    expect(sent.sub_table_data._note_texts).toEqual([{ section: 'k11-note', title: '资产减值损失说明', text: '国企减值说明' }])
    expect(sent.sub_table_data._removed_table_keys).toBeUndefined()
  })

  it('没有任何回复：按 18 项默认分类推 0，与真实 Tab 相同', async () => {
    h.get.mockResolvedValue([])
    await k11HeadlessProvider(LISTED)
    const sent = h.post.mock.calls[0][1]
    expect(J(sent)).toBe(J(await tabPayload('listed', [])))
    const rows = sent.sub_table_data['资产减值损失'] as Array<{ label: string; current_amount: number }>
    expect(rows).toHaveLength(19)
    expect(rows[16]).toEqual({ label: '商誉减值损失', current_amount: 0, prior_amount: 0 })
    expect(sent.sub_table_data._note_texts).toBeUndefined()
  })

  it('行身份走调用方注入的工厂（Tab 传共享 newRowIdentity，按 id 编辑行；写死会让所有行撞同一个 id）', () => {
    let seq = 0
    const next = () => `r${++seq}`
    const defaults = k11DefaultDisclosureRows(next)
    expect(defaults.map((r) => r.id)).toEqual(defaults.map((_, i) => `r${i + 1}`))
    seq = 0
    const fromAdj = loadK11DisclosureState(new Map(RESPONSES.map((r) => [r.item_id, r])), 'listed', next).rows
    expect(new Set(fromAdj.map((r) => r.id)).size).toBe(fromAdj.length)
    expect(fromAdj.map((r) => r.id)).toEqual(['r1', 'r2'])
  })

  it('静态接线：两个 Tab 调共用的读回 / 取数 / 同步行函数，不再内联', () => {
    const dir = resolve(__dirname, '../../k11/core')
    for (const [file, variant] of [['K11TabDisclosureListed.vue', 'listed'], ['K11TabDisclosureSoe.vue', 'soe']]) {
      const src = readFileSync(resolve(dir, file), 'utf-8')
      expect(src, file).toContain(`loadK11DisclosureState(props.allResponses, '${variant}', () => newRowIdentity('row'))`)
      expect(src, file).toContain("import { newRowIdentity } from '../../composables/shared/rowIdentity'")
      expect(src, file).toContain('applyK11AutoFill(disclosureRows.value, props.allResponses)')
      expect(src, file).toContain(
        `buildK11SyncPayload('${variant}', props.wpId || '', k11DisclosureSyncRows(disclosureRows.value), narrativeText.value)`,
      )
      expect(src, file).toContain(`K11_DISCLOSURE_ITEM_KEYS.${variant}`)
      expect(src, file).not.toMatch(/function buildRowsFromK11|DEFAULT_CATEGORIES_|normalizeImpairmentCategory\(/)
    }
  })
})
