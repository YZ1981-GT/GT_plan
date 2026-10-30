/**
 * G6 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 上市：Tab 本就调 `useG6DisclosureListed` + `buildG6ListedSyncPayload`，离屏调同一对。国企：Tab 内联的状态 / 回显 / 回填 /
 * 发送体抽成 `g6SoeDisclosureTabState` 后共用。判据：①挂载真实 Tab（外壳回复里带已存披露行 —— 等同会话内保存后的外壳内存），
 * 点「同步到附注 / 同步至附注」发出的载荷 == 离屏载荷（逐字节），载荷里有真实行与说明 ②国企挂载回填（G6-1 / G6-2）离屏同口径、
 * 不保存不提示 ③国企 htmlData 取国企披露页签（render-config）④只读 G6- 条目、不写底稿、不订阅 / 不广播 ⑤上市口径不适用回空
 * ⑥静态接线。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const h = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), put: vi.fn(), apiGet: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn(),
  success: vi.fn(),
}))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet, post: h.apiPost, put: h.apiPut } }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(() => Promise.resolve()) }),
  useRoute: () => ({ params: {}, query: {}, path: '/', name: 'wp' }),
}))
vi.mock('element-plus', async () => ({
  ...(await vi.importActual<Record<string, unknown>>('element-plus')),
  ElMessage: { success: h.success, warning: vi.fn(), error: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))

import { g6HeadlessProvider } from '../g6HeadlessDisclosure'
import { buildDefaultG6ListedState, serializeG6ListedStages, serializeG6ListedState } from '../g6ListedDisclosureRows'
import G6TabDisclosureListed from '../../g6-other-bond-investment-main/core/G6TabDisclosureListed.vue'
import G6TabDisclosureSOE from '../../g6-other-bond-investment-main/core/G6TabDisclosureSOE.vue'
import type { ChecklistResponse } from '../useF1FormData'

const listedState = buildDefaultG6ListedState()
listedState.balanceRows[0] = { ...listedState.balanceRows[0], label: '国债A', endBalance: 1000, priorBalance: 800 }
listedState.fairValueRows[0] = { ...listedState.fairValueRows[0], label: '国债A', openingFv: 800, fvChangeCurrent: 200, cost: 950 }
listedState.stageBlocks[0] = {
  ...listedState.stageBlocks[0],
  individual: { method: 'individual', details: [{ id: 'd1', name: '国债A', bookBalance: 1000, impairment: 5, reason: '未逾期' }] },
}
listedState.fvNote = '其他债权投资情况说明'

const SOE_ROWS = JSON.stringify({
  version: 2,
  balanceRows: [
    { item: '旧名1', endingBalance: 0, openingBalance: 500 },
    { item: '项目2（可改名）', endingBalance: 66, openingBalance: 0 },
    { item: '项目3（可改名）', endingBalance: 0, openingBalance: 0 },
    { item: '项目4（可改名）', endingBalance: 0, openingBalance: 0 },
  ],
  importantRows: [
    { item: '旧重要1', faceValue: 1, amortizedCost: 1, fairValue: 1, ociCumulative: 1, impairment: 7 },
    { item: '重要项目2', faceValue: 0, amortizedCost: 0, fairValue: 0, ociCumulative: 0, impairment: 3 },
    { item: '重要项目3', faceValue: 0, amortizedCost: 0, fairValue: 0, ociCumulative: 0, impairment: 0 },
    { item: '重要项目4', faceValue: 0, amortizedCost: 0, fairValue: 0, ociCumulative: 0, impairment: 0 },
  ],
  movementRows: [],
})
const G6_1_ROWS = JSON.stringify({
  'fv-item-1': { itemLabel: '国债甲', closingUnadjusted: 1200, closingAdjustment: 30, openingUnadjusted: 480, openingAdjustment: 20 },
  'fv-item-2': { itemLabel: '企业债乙', closingUnadjusted: 90, closingAdjustment: 0, openingUnadjusted: 40, openingAdjustment: 0 },
})
const G6_2_ROWS = JSON.stringify([
  { investProject: '重要甲', faceValue: 1000, closingSubtotal: 980, closingAudited: 1010, closingCumulativeFvChange: 30 },
  { investProject: '', closingAudited: 0 },
  { investProject: '重要乙', faceValue: 200, closingSubtotal: 190, closingFairValue: 205, closingCumulativeFvChange: 15 },
])

const RESPONSES: ChecklistResponse[] = [
  { item_id: 'G6-disclosure-listed-rows', conclusion: null, remark: serializeG6ListedState(listedState) },
  { item_id: 'G6-disclosure-listed-stages', conclusion: null, remark: serializeG6ListedStages(listedState) },
  { item_id: 'G6-disclosure-soe-rows', conclusion: null, remark: SOE_ROWS },
  { item_id: 'G6-1-rows', conclusion: G6_1_ROWS, remark: G6_1_ROWS },
  { item_id: 'G6-2-rows', conclusion: G6_2_ROWS, remark: G6_2_ROWS },
  { item_id: 'G6-1-adjudicated-amount', conclusion: '1000', remark: null },
  { item_id: 'G4-disclosure-soe-stages', conclusion: null, remark: '别的底稿' },
]
const G6_ONLY = new Map(RESPONSES.filter((r) => r.item_id.startsWith('G6-')).map((r) => [r.item_id, r]))
/** 国企披露页签的 html_data（Tab 的 htmlData）：附注说明只在这里（回复兜底读 checklist_responses），证明离屏取的是同一页签 */
const SOE_SHEET_HTML_DATA = {
  component_type: 'g6-other-bond-investment-main',
  checklist_responses: { 'G6-disclosure-soe-text': { conclusion: '', remark: '国企其他债权投资说明' } },
  project_context: { applicable_standards: ['soe_standalone'] },
}
const RENDER_CONFIG = {
  applicable_standards: ['soe_consolidated'],
  sheets: [
    { sheet_name: '附注披露信息（上市公司）', componentType: 'g6-other-bond-investment-main', html_data: { component_type: 'x' } },
    { sheet_name: '附注披露信息（国企）', componentType: 'g6-other-bond-investment-main', html_data: SOE_SHEET_HTML_DATA },
  ],
}
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-g6', wpCode: 'G6' }
const SOE = { ...CTX, variant: 'soe' as const, applicableStandards: ['soe_standalone'] }
const LISTED = { ...CTX, variant: 'listed' as const, applicableStandards: ['listed_standalone'] }

const STUBS = {
  'el-button': { template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>', emits: ['click'] },
  'el-alert': true, 'el-card': true, 'el-input': true, 'el-input-number': true, 'el-option': true, 'el-select': true,
  'el-table': true, 'el-table-column': true, 'el-tag': true, 'el-tooltip': true,
  GtIndexChip: true, GtReviewTrigger: true, WpAmountInput: true,
}

/** Tab 路径：挂载真实 Tab（外壳回复里带已存行 = 会话内保存后的外壳内存），点同步按钮，取发出的载荷 */
async function tabPayload(variant: 'soe' | 'listed') {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  try {
    h.apiPost.mockResolvedValue({ rows_synced: 9 })
    const wrapper = mount(variant === 'soe' ? G6TabDisclosureSOE : G6TabDisclosureListed, {
      props: {
        htmlData: variant === 'soe' ? SOE_SHEET_HTML_DATA : RENDER_CONFIG.sheets[0].html_data,
        wpId: 'wp-g6', projectId: 'p1', isReadonly: false, allResponses: new Map(G6_ONLY),
        ...(variant === 'listed' ? { applicableStandards: ['listed_standalone'] } : {}),
      },
      global: { stubs: STUBS, plugins: [createPinia()] },
    })
    await flushPromises()
    const before = h.apiPost.mock.calls.length
    const text = variant === 'soe' ? '同步至附注' : '同步到附注'
    const button = wrapper.findAll('button').find((b) => b.text().includes(text))
    expect(button, `找不到「${text}」按钮`).toBeDefined()
    await button!.trigger('click')
    await flushPromises()
    expect(h.apiPost.mock.calls.length).toBe(before + 1)
    const [url, payload] = h.apiPost.mock.calls[before]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    wrapper.unmount()
    return payload
  } finally {
    vi.clearAllTimers()
    vi.useRealTimers()
  }
}

function rowsOf(payload: any, table: string): Array<Record<string, unknown>> {
  return payload.sub_table_data[table] as Array<Record<string, unknown>>
}

describe('g6HeadlessProvider', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockImplementation(async (url: string) => {
      if (url.endsWith('/checklist-responses')) return RESPONSES
      if (url.endsWith('/render-config')) return RENDER_CONFIG
      return {}
    })
    h.post.mockResolvedValue({ rows_synced: 9, push_kept: [] })
  })
  afterEach(() => vi.restoreAllMocks())

  it('上市：离屏载荷与真实 Tab 点「同步到附注」发出的逐字节相同（主表 / 公允价值表 / 三阶段 / 说明）', async () => {
    const out = await g6HeadlessProvider(LISTED)
    expect(out).toEqual({ sections: [{ section: '五、15', rows: 9, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-g6/checklist-responses', expect.anything())
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    expect(rowsOf(sent, '其他债权投资')[0]).toMatchObject({ label: '国债A', end_balance: 1000, prior_balance: 800 })
    expect(rowsOf(sent, '其他债权投资情况')[0]).toMatchObject({ label: '国债A', opening_fv: 800, closing_fv: 1000 })
    expect(rowsOf(sent, '期末处于第一阶段的其他债权投资的减值准备').find((r) => r.label === '国债A'))
      .toMatchObject({ gross: 1000, provision: 5, reason: '未逾期' })
    expect(sent.sub_table_data._note_texts).toEqual([
      { section: 'listed-fair-value-note', title: '其他债权投资情况说明', text: '其他债权投资情况说明' },
    ])
    expect(JSON.stringify(sent)).toBe(JSON.stringify(await tabPayload('listed')))
  })

  it('国企：离屏载荷与真实 Tab 点「同步至附注」逐字节相同；挂载回填（G6-1 / G6-2）同口径，说明取自国企页签 html_data', async () => {
    const out = await g6HeadlessProvider(SOE)
    expect(out).toEqual({ sections: [{ section: '八、16', rows: 9, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-g6/render-config', expect.anything())
    const sent = h.post.mock.calls[0][1]
    expect(sent).toMatchObject({ wp_id: 'wp-g6', sheet_name: '附注披露信息（国企）', current_standard: 'soe_standalone' })
    // 已存期末为 0 ⇒ 取 G6-1（1200 + 30）；已存期初 500 保留；行名取 G6-1
    expect(rowsOf(sent, '其他债权投资情况')[0]).toMatchObject({ label: '国债甲', end_balance: 1230, prior_balance: 500 })
    expect(rowsOf(sent, '其他债权投资情况')[1]).toMatchObject({ label: '企业债乙', end_balance: 66, prior_balance: 40 })
    expect(rowsOf(sent, '其他债权投资情况').at(-1)).toMatchObject({ label: '合计', end_balance: 1296, prior_balance: 540, is_total: true })
    // 重要投资：前几项取 G6-2（跳过空行），减值准备保留已存
    expect(rowsOf(sent, '期末重要的其他债权投资')[0]).toMatchObject({ label: '重要甲', face_value: 1000, fair_value: 1010, impairment: 7 })
    expect(rowsOf(sent, '期末重要的其他债权投资')[1]).toMatchObject({ label: '重要乙', fair_value: 205, impairment: 3 })
    expect(sent.sub_table_data._removed_table_keys).toEqual(['减值准备计提情况', '减值准备变动'])
    expect(sent.sub_table_data._note_texts).toEqual([
      { section: 'soe-audit-note', title: '其他债权投资审计说明', text: '国企其他债权投资说明' },
    ])
    expect(JSON.stringify(sent)).toBe(JSON.stringify(await tabPayload('soe')))
  })

  it('离屏不写底稿、不保存回填、不提示、不订阅 / 不广播、无组件实例警告（含国企没有已存行时的强制回填）', async () => {
    const add = vi.spyOn(window, 'addEventListener')
    const dispatch = vi.spyOn(window, 'dispatchEvent')
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    await g6HeadlessProvider(LISTED)
    await g6HeadlessProvider(SOE)
    h.get.mockImplementation(async (url: string) => (url.endsWith('/checklist-responses')
      ? RESPONSES.filter((r) => !r.item_id.startsWith('G6-disclosure-'))
      : RENDER_CONFIG))
    await g6HeadlessProvider(SOE)
    const forced = h.post.mock.calls[2][1]
    expect(rowsOf(forced, '其他债权投资情况')[0]).toMatchObject({ label: '国债甲', end_balance: 1230, prior_balance: 500 })
    expect(rowsOf(forced, '期末重要的其他债权投资')[0]).toMatchObject({ label: '重要甲', impairment: 0 })
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiPut).not.toHaveBeenCalled()
    expect(h.apiPost).not.toHaveBeenCalled()
    expect(h.success).not.toHaveBeenCalled()
    expect(add.mock.calls.map((c) => c[0])).not.toContain('substantive:adjudicated')
    expect(dispatch).not.toHaveBeenCalled()
    expect(warn.mock.calls.flat().join(' ')).not.toMatch(/Vue warn/)
    expect(h.post).toHaveBeenCalledTimes(3)
  })

  it('上市口径不适用回空，不发请求（国企 Tab 本身不按准则门控，离屏同口径）', async () => {
    expect(await g6HeadlessProvider({ ...LISTED, applicableStandards: ['soe_standalone'] })).toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('静态接线：两个 Tab 调同一套状态 / 载荷函数，国企不再内联', () => {
    const dir = resolve(__dirname, '../../g6-other-bond-investment-main/core')
    const listed = readFileSync(resolve(dir, 'G6TabDisclosureListed.vue'), 'utf-8')
    expect(listed).toMatch(/useG6DisclosureListed\(\{ allResponses, debouncedSave, isReadonly \}\)/)
    expect(listed).toMatch(/buildG6ListedSyncPayload\(\s*props\.wpId,\s*props\.applicableStandards,\s*dis\.state\.value,\s*\)/)
    const soe = readFileSync(resolve(dir, 'G6TabDisclosureSOE.vue'), 'utf-8')
    expect(soe).toMatch(/useG6SoeDisclosureState\(\{ allResponses: \(\) => props\.allResponses, htmlData: \(\) => props\.htmlData \}\)/)
    expect(soe).toMatch(/soe\.buildSyncPayload\(props\.wpId\)/)
    expect(soe).toMatch(/const hadPersisted = loadPersisted\(\)\s*refreshFromSources\(!hadPersisted\)/)
    expect(soe).toMatch(/soe\.applySourceRows\(force\)\s*persistStructured\(\)/)
    expect(soe).not.toMatch(/function (buildSyncData|loadPersisted|readResponse|parseJson)\b|G6_SOE_COLUMNS|sub_table_data:/)
  })
})
