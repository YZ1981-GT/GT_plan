/**
 * K5 预计负债披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 预计负债表的读回 / 默认分类 / 自动取数原在两个 Tab SFC 里内联，抽成 `k5DisclosureTabState` 后 Tab 与离屏同步共用。判据：
 * ①挂载真实 Tab、点「同步到附注」发出的载荷 == 离屏载荷（上市 五、50 走「已保存表 + 按类别自动取数覆盖、合计行不推」，
 * 国企 八、55 走「默认 8 类 + 自动取数」，无回复走默认分类推 0）②夹具有真实数据 ③只读 K5- 条目、离屏不写底稿
 * ④静态接线：Tab 调共用函数，不再内联读回 / 取数 / 默认分类。
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
  ElMessageBox: { confirm: vi.fn(() => Promise.resolve()) },
}))

import { k5HeadlessProvider } from '../k5HeadlessDisclosure'
import { loadK5DisclosureState } from '../k5DisclosureTabState'
import { K5_SUBTABLE } from '../k5NoteSectionMap'
import K5TabDisclosureListed from '../../k5/core/K5TabDisclosureListed.vue'
import K5TabDisclosureSoe from '../../k5/core/K5TabDisclosureSoe.vue'

const J = JSON.stringify
type Resp = { item_id: string; remark: string | null; conclusion: string | null }
const RESPONSES: Resp[] = [
  {
    item_id: 'K5-disclosure-listed-provision-table',
    remark: J([
      { id: 'r1', category: '产品质量保证', beginBalance: 100, increase: 20, decrease: 10, endBalance: 110, remark: '质保', isTotal: false, isAutoFill: false },
      { id: 'r2', category: '未决诉讼', beginBalance: 0, increase: 50, decrease: 0, endBalance: 50, remark: '诉讼甲', isTotal: false, isAutoFill: false },
      { id: 'rt', category: '合计', beginBalance: 100, increase: 70, decrease: 10, endBalance: 160, remark: '', isTotal: true, isAutoFill: false },
    ]),
    conclusion: null,
  },
  {
    item_id: 'K5-1-audited-total',
    remark: J({
      产品质量保证: { beginBalance: 120, increase: 30, decrease: 15, endBalance: 135 },
      担保: { beginBalance: 5, increase: 2, decrease: 0, endBalance: 7 },
    }),
    conclusion: null,
  },
  { item_id: 'K5-disclosure-listed-narrative', remark: '预计负债说明（上市）', conclusion: null },
  { item_id: 'K5-disclosure-soe-narrative', remark: '预计负债说明（国企）', conclusion: null },
  { item_id: 'K5-disclosure-listed-contingent', remark: J([{ id: 'c1', item: '担保事项', nature: '担保', financialImpact: 9, compensationLikelihood: '', disclosure: '' }]), conclusion: null },
  { item_id: 'K5-2-detail-rows', remark: J([{ caseName: '甲诉讼', lossLikelihood: 'possible', amount: 30 }]), conclusion: null },
  { item_id: 'K5A-proc-1', remark: '程序', conclusion: null },
  { item_id: 'K6-2-rows', remark: '[]', conclusion: null },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-k5', wpCode: 'K5' }
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
  'el-empty': true,
  'el-icon': true,
}

/** Tab 路径：挂载真实 Tab（同一批 K5- 回复），点「同步到附注」，取它发出的载荷 */
async function tabPayload(variant: 'listed' | 'soe', list: Resp[] = RESPONSES) {
  const allResponses = new Map(list.filter((r) => r.item_id.startsWith('K5-')).map((r) => [r.item_id, { ...r }]))
  const wrapper = mount(variant === 'listed' ? K5TabDisclosureListed : K5TabDisclosureSoe, {
    props: {
      wpId: 'wp-k5', projectId: 'p1', allResponses, isReadonly: false,
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

describe('k5HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 3, push_kept: [] })
  })

  it('上市：离屏载荷与真实 Tab 点「同步到附注」发出的逐字节相同（已保存表 + 按类别自动取数），静默发出、不写底稿', async () => {
    const out = await k5HeadlessProvider(LISTED)
    expect(out).toEqual({ sections: [{ section: '五、50', rows: 3, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-k5/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    expect(J(sent)).toBe(J(await tabPayload('listed')))
    expect(sent.section_id).toBe('五、50')
    // 产品质量保证：已保存 110 / 100 被 K5-1 按类别取数覆盖为 135 / 120，形成原因保留已保存的变动说明；合计行按非合计行重算
    expect(sent.sub_table_data[K5_SUBTABLE.provision]).toEqual([
      { label: '产品质量保证', values: [135, 120, '质保'] },
      { label: '未决诉讼', values: [50, 0, '诉讼甲'] },
      { label: '合计', values: [185, 120, ''], is_total: true },
    ])
    expect(sent.sub_table_data._note_texts).toEqual([{ section: 'note-provisions', title: '预计负债说明', text: '预计负债说明（上市）' }])
  })

  it('国企：无已保存表 ⇒ 默认 8 类 + 自动取数（担保），载荷与真实 Tab 逐字节相同', async () => {
    const out = await k5HeadlessProvider(SOE)
    expect(out.sections.map((s) => s.section)).toEqual(['八、55'])
    const sent = h.post.mock.calls[0][1]
    expect(J(sent)).toBe(J(await tabPayload('soe')))
    const rows = sent.sub_table_data[K5_SUBTABLE.provision] as Array<{ label: string; values: unknown[] }>
    expect(rows.map((r) => r.label)).toEqual(['产品质量保证', '未决诉讼', '亏损合同', '重组义务', '弃置义务', '担保', '环保义务', '其他', '合计'])
    expect(rows[0].values).toEqual([135, 120, ''])
    expect(rows[5].values).toEqual([7, 5, ''])
    expect(rows.at(-1)).toEqual({ label: '合计', values: [142, 125, ''], is_total: true })
    expect(sent.sub_table_data._note_texts).toEqual([{ section: 'note-provisions', title: '预计负债说明', text: '预计负债说明（国企）' }])
  })

  it('没有任何回复：按默认分类推 0、无附注说明，与真实 Tab 相同', async () => {
    h.get.mockResolvedValue([])
    await k5HeadlessProvider(LISTED)
    const sent = h.post.mock.calls[0][1]
    expect(J(sent)).toBe(J(await tabPayload('listed', [])))
    const rows = sent.sub_table_data[K5_SUBTABLE.provision] as Array<{ label: string; values: unknown[] }>
    expect(rows).toHaveLength(7)
    expect(rows.every((r) => r.values[0] === 0 && r.values[1] === 0)).toBe(true)
    expect(sent.sub_table_data._note_texts).toBeUndefined()
  })

  it('默认表的行身份走调用方注入的工厂（Tab 按 id 编辑行），合计行固定 row-total', () => {
    let seq = 0
    const rows = loadK5DisclosureState(new Map(), 'soe', () => `r${++seq}`).rows
    expect(rows.map((r) => r.id)).toEqual(['r1', 'r2', 'r3', 'r4', 'r5', 'r6', 'r7', 'r8', 'row-total'])
  })

  it('静态接线：两个 Tab 调共用的读回 / 取数 / 同步行函数，不再内联', () => {
    const dir = resolve(__dirname, '../../k5/core')
    for (const [file, variant] of [['K5TabDisclosureListed.vue', 'listed'], ['K5TabDisclosureSoe.vue', 'soe']]) {
      const src = readFileSync(resolve(dir, file), 'utf-8')
      expect(src, file).toContain(`loadK5DisclosureState(props.allResponses, '${variant}', () => newRowIdentity('row'))`)
      expect(src, file).toContain('applyK5ProvisionAutoFill(provisionTable.value, props.allResponses)')
      expect(src, file).toContain(
        `buildK5SyncPayload('${variant}', props.wpId || '', k5DisclosureSyncRows(provisionTable.value, '${variant}'), narrativeText.value)`,
      )
      expect(src, file).not.toMatch(/function initDefaultTable|K5-1-audited-total|provisionTable\.value\.filter\(r => !r\.isTotal\)\.map/)
    }
  })
})
