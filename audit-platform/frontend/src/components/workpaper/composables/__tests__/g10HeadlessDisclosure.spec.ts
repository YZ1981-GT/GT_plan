/**
 * G10 交易性金融负债披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * Tab 的审计说明读取与「快照 → 选本版本 builder」原在 `G10TabDisclosureBase` 里内联，抽成 `readG10DisclosureAuditNote` /
 * `buildG10TabSyncPayloads` 后 Tab 与离屏同步共用；审计年度在 Tab 里由 Runtime Boundary 注入，离屏由 `ctx.year` 显式传入。
 * 判据：①挂载真实 Tab（上市 / 国企薄壳 → Base，Runtime 年度 2025）、点「同步到附注」发出的每条载荷 == 离屏逐条载荷（上市
 * 五、34 + 五、35 两章节逐章节回报）②列头与旧表名清理用上 2025 年度 ③离屏不挂钩子、不订阅窗口事件、不 inject，组件内照旧
 * ④只读 G10 条目、静默发出、不写底稿 ⑤口径不适用回空 ⑥静态接线。
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

import { g10HeadlessProvider } from '../g10HeadlessDisclosure'
import { useG10Disclosure } from '../useG10Disclosure'
import { WorkpaperRuntimeContextKey } from '../useWorkpaperScaffold'
import { G10_SUBTABLE, G10_DERIVATIVE_SUBTABLE } from '../g10NoteSectionMap'
import G10TabDisclosureListed from '../../g10-trading-financial-liabilities/core/G10TabDisclosureListed.vue'
import G10TabDisclosureSOE from '../../g10-trading-financial-liabilities/core/G10TabDisclosureSOE.vue'
import type { ChecklistResponse } from '../useF1FormData'

const J = JSON.stringify
const mv = (o: number, i: number, d: number) => ({ openingAmount: o, increaseAmount: i, decreaseAmount: d, closingAmount: o + i - d })
const RESPONSES: ChecklistResponse[] = [
  {
    item_id: 'G10-disclosure-listed',
    remark: J({
      version: 2,
      movement: { mv_trading_bond: mv(100, 50, 30), mv_derivative: mv(10, 0, 0), mv_designated_bond: mv(200, 0, 20) },
      designatedDetail: { designated_1: { label: '结构性票据', openingAmount: 200, closingAmount: 180, designationReason: '消除会计错配' } },
      fvCreditRisk: { fv_1: { label: '结构性票据', fvChangeAmount: -5, creditRiskCurrent: 1.5, creditRiskCumulative: 3 } },
      derivativeRows: [{ rowKey: 'deriv_1', label: '利率互换', currentAmount: 10, priorAmount: 8 }],
      derivativeNote: '利率互换用于套期。',
      maturityDiffNote: '到期应付金额与账面价值差 2 万元。',
    }),
    conclusion: null,
  },
  { item_id: 'G10-disclosure-listed-audit-note', remark: '上市：已核对 G10-1 审定数。', conclusion: null },
  {
    item_id: 'G10-disclosure-soe',
    remark: J({
      version: 2,
      balance: { soe_trading_bond: { currentAmount: 300, priorAmount: 260 }, soe_hybrid_tool: { currentAmount: 40, priorAmount: 0 } },
      fvCreditRisk: { fv_1: { label: '混合工具', fvChangeAmount: 2, creditRiskCurrent: 0.5, creditRiskCumulative: 0.5 } },
      maturityDiffNote: '',
    }),
    conclusion: null,
  },
  { item_id: 'G10-disclosure-soe-audit-note', remark: '国企：列报恰当。', conclusion: null },
  { item_id: 'G10-1-adjudicated-amount', conclusion: '340', remark: null },
  { item_id: 'G1-disclosure-listed', remark: J({ version: 2 }), conclusion: null },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-g10', wpCode: 'G10' }
const LISTED = { ...CTX, variant: 'listed' as const, applicableStandards: ['listed_standalone'] }
const SOE = { ...CTX, variant: 'soe' as const, applicableStandards: ['soe_standalone'] }
const SYNC_URL = '/api/projects/p1/disclosure-notes/sync-from-workpaper'

const STUBS = {
  'el-button': { template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>', emits: ['click'] },
  'el-alert': true, 'el-table': true, 'el-table-column': true, 'el-input': true,
  GtIndexChip: true, GtReviewTrigger: true, G10AuditTextCards: true, G10ImportExportDropdown: true, WpAmountInput: true,
}

/** Tab 路径：Runtime 年度 2025、外壳按 `G10` 前缀给出的回复挂载真实 Tab，点「同步到附注」，取它逐条发出的载荷 */
async function tabPayloads(variant: 'soe' | 'listed', stds: string[]) {
  const debouncedSave = vi.fn()
  const allResponses = new Map(RESPONSES.filter((x) => x.item_id.startsWith('G10')).map((x) => [x.item_id, { ...x }]))
  h.apiPost.mockResolvedValue({ rows_synced: 4 })
  const wrapper = mount(variant === 'soe' ? G10TabDisclosureSOE : G10TabDisclosureListed, {
    props: { wpId: 'wp-g10', projectId: 'p1', allResponses, isReadonly: false, debouncedSave, applicableStandards: stds },
    global: { stubs: STUBS, provide: { [WorkpaperRuntimeContextKey as symbol]: { year: ref(2025) } } },
  })
  await flushPromises()
  const before = h.apiPost.mock.calls.length
  const button = wrapper.findAll('button').find((b) => b.text().includes('同步到附注'))
  expect(button, '找不到「同步到附注」按钮').toBeDefined()
  await button!.trigger('click')
  await flushPromises()
  const calls = h.apiPost.mock.calls.slice(before)
  expect(calls.every(([url]) => url === SYNC_URL)).toBe(true)
  expect(debouncedSave).not.toHaveBeenCalled()
  wrapper.unmount()
  return calls.map(([, payload]) => payload)
}

describe('g10HeadlessProvider', () => {
  let warn: ReturnType<typeof vi.spyOn>
  let listen: ReturnType<typeof vi.spyOn>
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockImplementation(async (_url: string, body: any) => ({ section_id: body.section_id, rows_synced: 4, push_kept: [] }))
    warn = vi.spyOn(console, 'warn')
    listen = vi.spyOn(window, 'addEventListener')
  })
  afterEach(() => {
    warn.mockRestore()
    listen.mockRestore()
  })

  it('上市：五、34 + 五、35 两章节逐条与真实 Tab 发出的逐字节相同，逐章节回报，静默、不写底稿', async () => {
    const out = await g10HeadlessProvider(LISTED)
    expect(out).toEqual({ sections: [{ section: '五、34', rows: 4, kept: 0 }, { section: '五、35', rows: 4, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-g10/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiPut).not.toHaveBeenCalled()
    expect(h.apiPost).not.toHaveBeenCalled()
    expect(h.post.mock.calls.every(([url, , cfg]) => url === SYNC_URL && (cfg as any)?._silent === true)).toBe(true)
    const sent = h.post.mock.calls.map(([, body]) => body)
    const trading = sent[0].sub_table_data[G10_SUBTABLE.listed.trading] as Array<Record<string, unknown>>
    expect(trading.find((r) => r.row_key === 'mv_trading_bond')).toMatchObject({ begin_balance: 100, current_increase: 50, end_balance: 120 })
    expect(trading.at(-1)).toMatchObject({ label: '合计', begin_balance: 310, end_balance: 310 })
    expect(sent[0].columns[G10_SUBTABLE.listed.fvCredit][1].label).toBe('2025年公允价值变动额')
    expect(sent[0].sub_table_data._note_texts.at(-1)).toEqual({ section: 'listed-audit-note', text: '上市：已核对 G10-1 审定数。' })
    expect(sent[1].sub_table_data[G10_DERIVATIVE_SUBTABLE.listed][0]).toMatchObject({ label: '利率互换', end_balance: 10, prior_balance: 8 })
    expect(J(sent)).toBe(J(await tabPayloads('listed', LISTED.applicableStandards)))
  })

  it('国企：八、34 与真实 Tab 逐字节相同', async () => {
    const out = await g10HeadlessProvider(SOE)
    expect(out).toEqual({ sections: [{ section: '八、34', rows: 4, kept: 0 }] })
    const sent = h.post.mock.calls.map(([, body]) => body)
    const balance = sent[0].sub_table_data[G10_SUBTABLE.soe.trading] as Array<Record<string, unknown>>
    expect(balance.at(-1)).toMatchObject({ label: '合计', end_fv: 340, begin_fv: 260 })
    expect(sent[0].sub_table_data._note_texts.at(-1)).toEqual({ section: 'soe-audit-note', text: '国企：列报恰当。' })
    expect(J(sent)).toBe(J(await tabPayloads('soe', SOE.applicableStandards)))
  })

  it('离屏不挂钩子、不订阅窗口事件、不 inject；组件内照旧订阅', async () => {
    await g10HeadlessProvider(LISTED)
    expect(listen.mock.calls.some(([type]) => String(type).startsWith('g10:') || type === 'substantive:adjudicated')).toBe(false)
    expect(warn.mock.calls.some((args) => /no active component instance|inject\(\) can only be used/.test(String(args[0])))).toBe(false)

    const w = mount(defineComponent({
      setup() {
        useG10Disclosure({
          variant: 'soe', wpId: ref('wp-g10'), allResponses: ref(new Map()), debouncedSave: () => {}, isReadonly: ref(false),
        })
        return () => null
      },
    }))
    for (const type of ['substantive:adjudicated', 'g10:detail-to-adjudication', 'g10:disclosure-pulled']) {
      expect(listen.mock.calls.some(([t]) => t === type), type).toBe(true)
    }
    w.unmount()
  })

  it('口径不适用回空，不发请求', async () => {
    expect(await g10HeadlessProvider({ ...SOE, applicableStandards: ['listed_standalone'] })).toEqual({ sections: [] })
    expect(await g10HeadlessProvider({ ...LISTED, applicableStandards: ['soe_standalone'] })).toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('静态接线：Tab 调共用的审计说明读取与载荷函数，不再内联选 builder；钩子在组件实例守卫里', () => {
    const tab = readFileSync(resolve(__dirname, '../../g10-trading-financial-liabilities/core/G10TabDisclosureBase.vue'), 'utf-8')
    expect(tab).toContain('const auditNote = ref(readG10DisclosureAuditNote(props.allResponses, props.variant))')
    expect(tab).toContain(
      'buildG10TabSyncPayloads(props.wpId, props.variant, props.applicableStandards, dis, auditNote.value)',
    )
    expect(tab).not.toMatch(/buildG10(Listed|Soe)SyncPayloads\(|getSyncSnapshot\(/)
    const composable = readFileSync(resolve(__dirname, '../useG10Disclosure.ts'), 'utf-8')
    expect(composable).toMatch(/if \(getCurrentInstance\(\)\) \{\s*onMounted\(/)
    expect(composable).toMatch(/opts\.auditYear\s*\?\s*computed\(\(\) => resolveAuditYearNumber\(opts\.auditYear\)\)\s*:\s*useWorkpaperAuditYear\(\)/)
  })
})
