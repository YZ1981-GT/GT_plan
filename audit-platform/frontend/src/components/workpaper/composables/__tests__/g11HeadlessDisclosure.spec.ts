/**
 * G11 投资收益披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * Tab 挂载时读审计说明 / 结论、同步时「快照 → `buildG11SyncPayloads`」原在 `G11TabDisclosureBase` 里内联，抽成
 * `g11DisclosureTabSync`（`readG11DisclosureAuditTexts` / `buildG11TabSyncPayloads`）后 Tab 与离屏同步共用。判据：①挂载真实 Tab
 * （上市 / 国企薄壳 → Base）、点「同步到附注」发出的载荷 == 离屏载荷，夹具有构成表 / 处置交易性子表 / 汇回说明 / 附注文本 /
 * 审计说明与结论 ②抽出的说明 / 结论读取与原实现同口径（结论优先、兼容旧 remark）③离屏不挂钩子、不订阅窗口事件、不广播说明，
 * 组件内照旧 ④只读 G11 条目、静默发出、不写底稿 ⑤口径不适用回空 ⑥静态接线。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), apiGet: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn() }))
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

import { g11HeadlessProvider } from '../g11HeadlessDisclosure'
import { useG11Disclosure } from '../useG11Disclosure'
import { readG11DisclosureAuditTexts } from '../g11DisclosureTabSync'
import { G11_LISTED_TRADING_SUBTABLE, G11_MAIN_SUBTABLE } from '../g11DisclosureSyncPayload'
import G11TabDisclosureListed from '../../g11-investment-income/core/G11TabDisclosureListed.vue'
import G11TabDisclosureSOE from '../../g11-investment-income/core/G11TabDisclosureSOE.vue'
import type { ChecklistResponse } from '../useF1FormData'

const J = JSON.stringify
const RESPONSES: ChecklistResponse[] = [
  {
    item_id: 'G11-disclosure-listed',
    remark: J({
      version: 2,
      rows: [
        { rowKey: 'equity_method', currentAmount: 500, priorAmount: 400, remark: '联营企业' },
        { rowKey: 'trading_dispose', currentAmount: 120, priorAmount: 30, remark: '' },
        { rowKey: 'listed_sub_1', currentAmount: 500, priorAmount: 400, remark: '' },
      ],
      tradingDispose: { equity_stock: { currentAmount: 100, priorAmount: 30 }, debt_bond: { currentAmount: 20, priorAmount: 0 } },
    }),
    conclusion: null,
  },
  { item_id: 'G11-disclosure-listed-note', conclusion: '本期投资收益主要来自联营企业。', remark: null },
  { item_id: 'G11-disclosure-audit-note-listed', remark: '已与 G11-1、利润表勾稽。', conclusion: null },
  { item_id: 'G11-disclosure-audit-conclusion-listed', conclusion: '未见异常。', remark: null },
  {
    item_id: 'G11-disclosure-soe',
    remark: J({
      version: 2,
      rows: [{ rowKey: 'equity_method', currentAmount: 80, priorAmount: 60, remark: '' }, { rowKey: 'other', currentAmount: -5, priorAmount: 0, remark: '' }],
      repatriationNote: '不存在汇回重大限制。',
    }),
    conclusion: null,
  },
  { item_id: 'G11-disclosure-audit-note-soe', remark: '国企口径已核对。', conclusion: null },
  { item_id: 'G11-disclosure-audit-conclusion-soe', remark: '旧版结论写在 remark。', conclusion: null },
  { item_id: 'G11-1-adjudicated-amount', conclusion: '620', remark: null },
  { item_id: 'G1-disclosure-listed', remark: J({ version: 2, rows: [] }), conclusion: null },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-g11', wpCode: 'G11' }
const LISTED = { ...CTX, variant: 'listed' as const, applicableStandards: ['listed_standalone'] }
const SOE = { ...CTX, variant: 'soe' as const, applicableStandards: ['soe_standalone'] }
const SYNC_URL = '/api/projects/p1/disclosure-notes/sync-from-workpaper'

const STUBS = {
  'el-button': { template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>', emits: ['click'] },
  'el-alert': true, 'el-table': true, 'el-table-column': true, 'el-input': true, 'el-card': true,
  GtReviewTrigger: true, G11ImportExportDropdown: true, WpAmountInput: true,
}

/**
 * Tab 路径：外壳按 `G11` 前缀给出的回复挂载真实 Tab，点「同步到附注」，取它发出的载荷。
 * Tab 挂载时读到审计说明会排一次 800ms 的自动同步，计时器用假的、取完载荷即清掉（不串到后面的用例）。
 */
async function tabPayloads(variant: 'soe' | 'listed', stds: string[]) {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  try {
    const debouncedSave = vi.fn()
    const allResponses = new Map(RESPONSES.filter((x) => x.item_id.startsWith('G11')).map((x) => [x.item_id, { ...x }]))
    h.apiPost.mockResolvedValue({ rows_synced: 6 })
    const wrapper = mount(variant === 'soe' ? G11TabDisclosureSOE : G11TabDisclosureListed, {
      props: { wpId: 'wp-g11', projectId: 'p1', allResponses, isReadonly: false, debouncedSave, applicableStandards: stds },
      global: { stubs: STUBS },
    })
    await flushPromises()
    const before = h.apiPost.mock.calls.length
    const button = wrapper.findAll('button').find((b) => b.text().includes('同步到附注'))
    expect(button, '找不到「同步到附注」按钮').toBeDefined()
    await button!.trigger('click')
    await flushPromises()
    const calls = h.apiPost.mock.calls.slice(before)
    expect(calls.length).toBe(1)
    expect(calls[0][0]).toBe(SYNC_URL)
    expect(debouncedSave).not.toHaveBeenCalled()
    wrapper.unmount()
    return calls.map(([, payload]) => payload)
  } finally {
    vi.clearAllTimers()
    vi.useRealTimers()
  }
}

/** 窗口事件广播的探针（单独成函数以便精确推断类型） */
const spyDispatch = () => vi.spyOn(window, 'dispatchEvent')

describe('g11HeadlessProvider', () => {
  let warn: ReturnType<typeof vi.spyOn>
  let listen: ReturnType<typeof vi.spyOn>
  let dispatch: ReturnType<typeof spyDispatch>
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 6, push_kept: [{ table: '投资收益' }] })
    warn = vi.spyOn(console, 'warn')
    listen = vi.spyOn(window, 'addEventListener')
    dispatch = spyDispatch()
  })
  afterEach(() => {
    warn.mockRestore()
    listen.mockRestore()
    dispatch.mockRestore()
  })

  it('上市：离屏载荷与真实 Tab 点「同步到附注」发出的逐字节相同，静默写 五、69、不写底稿', async () => {
    const out = await g11HeadlessProvider(LISTED)
    expect(out).toEqual({ sections: [{ section: '五、69', rows: 6, kept: 1 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-g11/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiPut).not.toHaveBeenCalled()
    expect(h.apiPost).not.toHaveBeenCalled()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe(SYNC_URL)
    expect(cfg).toMatchObject({ _silent: true })
    const main = sent.sub_table_data[G11_MAIN_SUBTABLE] as Array<Record<string, unknown>>
    expect(main.some((r) => r.label === '权益法核算的长期股权投资收益')).toBe(true)
    expect(sent.sub_table_data[G11_LISTED_TRADING_SUBTABLE]).toBeDefined()
    const texts = J(sent.sub_table_data._note_texts)
    for (const t of ['本期投资收益主要来自联营企业。', '已与 G11-1、利润表勾稽。', '未见异常。']) expect(texts).toContain(t)
    expect(J(sent)).toBe(J((await tabPayloads('listed', LISTED.applicableStandards))[0]))
  })

  it('国企：离屏载荷与真实 Tab 逐字节相同，写 八、70（汇回说明 + 旧 remark 结论）', async () => {
    const out = await g11HeadlessProvider(SOE)
    expect(out).toEqual({ sections: [{ section: '八、70', rows: 6, kept: 1 }] })
    const sent = h.post.mock.calls[0][1]
    const texts = J(sent.sub_table_data._note_texts)
    for (const t of ['不存在汇回重大限制。', '国企口径已核对。', '旧版结论写在 remark。']) expect(texts).toContain(t)
    expect(sent.sub_table_data[G11_LISTED_TRADING_SUBTABLE]).toBeUndefined()
    expect(J(sent)).toBe(J((await tabPayloads('soe', SOE.applicableStandards))[0]))
  })

  it('抽出的审计说明 / 结论读取与原实现同口径', () => {
    const m = (entries: Array<[string, Partial<ChecklistResponse>]>) =>
      new Map(entries.map(([k, v]) => [k, { item_id: k, conclusion: null, remark: null, ...v } as ChecklistResponse]))
    expect(readG11DisclosureAuditTexts(new Map(), 'listed')).toEqual({ note: '', conclusion: '' })
    expect(readG11DisclosureAuditTexts(m([
      ['G11-disclosure-audit-note-listed', { remark: '说明', conclusion: '不读' }],
      ['G11-disclosure-audit-conclusion-listed', { conclusion: '结论', remark: '旧' }],
    ]), 'listed')).toEqual({ note: '说明', conclusion: '结论' })
    // 原实现：conclusion 为空串但 remark 有值 ⇒ 进分支、取 conclusion ?? … 得空串
    expect(readG11DisclosureAuditTexts(m([['G11-disclosure-audit-conclusion-soe', { conclusion: '', remark: '旧' }]]), 'soe').conclusion).toBe('')
    expect(readG11DisclosureAuditTexts(m([['G11-disclosure-audit-conclusion-soe', { remark: '旧' }]]), 'soe').conclusion).toBe('旧')
  })

  it('离屏不挂钩子、不订阅窗口事件、不广播说明；组件内照旧', async () => {
    await g11HeadlessProvider(LISTED)
    expect(listen.mock.calls.some(([type]) => type === 'substantive:adjudicated' || type === 'g11:disclosure-pulled')).toBe(false)
    expect(dispatch.mock.calls.some(([ev]) => (ev as Event).type === 'disclosure:note-text-updated')).toBe(false)
    expect(warn.mock.calls.some((args) => String(args[0]).includes('no active component instance'))).toBe(false)

    const w = mount(defineComponent({
      setup() {
        useG11Disclosure({ variant: 'soe', allResponses: ref(new Map()), debouncedSave: () => {}, wpId: ref('wp-g11'), isReadonly: ref(false) })
        return () => null
      },
    }))
    expect(listen.mock.calls.some(([type]) => type === 'g11:disclosure-pulled')).toBe(true)
    expect(dispatch.mock.calls.some(([ev]) => (ev as Event).type === 'disclosure:note-text-updated')).toBe(true)
    w.unmount()
  })

  it('口径不适用回空，不发请求', async () => {
    expect(await g11HeadlessProvider({ ...SOE, applicableStandards: ['listed_standalone'] })).toEqual({ sections: [] })
    expect(await g11HeadlessProvider({ ...LISTED, applicableStandards: ['soe_standalone'] })).toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('静态接线：Tab 调共用的说明 / 结论读取与载荷函数，不再内联', () => {
    const tab = readFileSync(resolve(__dirname, '../../g11-investment-income/core/G11TabDisclosureBase.vue'), 'utf-8')
    expect(tab).toContain('const { note: NOTE_KEY, conclusion: CONCLUSION_KEY } = g11DisclosureAuditTextKeys(props.variant)')
    expect(tab).toContain('const texts = readG11DisclosureAuditTexts(props.allResponses, props.variant)')
    expect(tab).toMatch(/buildG11TabSyncPayloads\(\s*props\.wpId, props\.variant, props\.applicableStandards, dis, auditNote\.value, auditConclusion\.value,?\s*\)/)
    expect(tab).not.toMatch(/buildG11SyncPayloads\(|getSyncSnapshot\(|String\(c\.conclusion/)
    const composable = readFileSync(resolve(__dirname, '../useG11Disclosure.ts'), 'utf-8')
    expect(composable).toMatch(/if \(getCurrentInstance\(\)\) \{\s*onMounted\(/)
  })
})
