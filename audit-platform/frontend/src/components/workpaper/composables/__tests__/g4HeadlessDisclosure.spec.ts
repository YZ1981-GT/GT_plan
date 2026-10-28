/**
 * G4 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 段落默认行 / 打开时回显 / 同步快照原在两个 Tab 里内联，抽成 `g4DisclosureTabState` 后 Tab 与离屏同步共用。判据：
 * ①挂载真实 Tab（htmlData 按回显函数支持的 `checklist_responses` 形态带已存三阶段明细 / 说明），点「同步到附注」发出的
 *   载荷 == 离屏载荷（逐字节），载荷里有真实明细行与说明 ②国企回显按国企骨架解析阶段表（表名 / 末列名是国企模板写法）
 * ③只读 G4- 条目、不写底稿、不订阅 / 不广播、无实例警告 ④口径不适用回空 ⑤静态接线 ⑥现状钉住：render-config 只下发
 *   `responses_snapshot` 时 Tab 回显不到（缺陷已登记，修好后本条要改）。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
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
  ElMessageBox: { confirm: vi.fn() },
}))

import { g4HeadlessProvider } from '../g4HeadlessDisclosure'
import { useG4DisclosureTabState } from '../g4DisclosureTabState'
import {
  buildDefaultSoeStageBlocks,
  buildDefaultStageBlocks,
  isPlaceholderStageDetail,
  serializeStageBlocks,
  type G4StageBlock,
} from '../g4ListedStageDisclosure'
import G4TabDisclosureListed from '../../g4-bond-investment-main/core/G4TabDisclosureListed.vue'
import G4TabDisclosureSOE from '../../g4-bond-investment-main/core/G4TabDisclosureSOE.vue'
import type { ChecklistResponse } from '../useF1FormData'

type Detail = { name: string; bookBalance: number; impairment: number; reason: string }

function withDetails(blocks: G4StageBlock[], fill: Record<string, { individual?: Detail[]; portfolio?: Detail[] }>) {
  return blocks.map((b, i) => {
    const f = fill[b.id]
    if (!f) return b
    const mk = (ds: Detail[] | undefined, fallback: G4StageBlock['individual']) => (ds
      ? { ...fallback, details: ds.map((d, j) => ({ id: `d-${i}-${j}`, ...d })) }
      : fallback)
    return { ...b, individual: mk(f.individual, b.individual), portfolio: mk(f.portfolio, b.portfolio) }
  })
}

const LISTED_STAGES = serializeStageBlocks(withDetails(buildDefaultStageBlocks(), {
  'ending-s1': {
    individual: [{ name: '国债A', bookBalance: 1000, impairment: 10, reason: '信用风险未显著增加' }],
    portfolio: [{ name: '企业债组合', bookBalance: 500, impairment: 25, reason: '按组合' }],
  },
  'ending-s2': { individual: [{ name: '企业债B', bookBalance: 300, impairment: 60, reason: '逾期 30 天' }] },
  'prior-s1': { portfolio: [{ name: '上年组合', bookBalance: 400, impairment: 4, reason: '按组合' }] },
}))
const SOE_STAGES = serializeStageBlocks(withDetails(buildDefaultSoeStageBlocks(), {
  'ending-s1': { individual: [{ name: '国企债A', bookBalance: 800, impairment: 8, reason: '未逾期' }] },
  'ending-s3': { portfolio: [{ name: '违约债组合', bookBalance: 200, impairment: 150, reason: '已违约' }] },
}))

const RESPONSES: ChecklistResponse[] = [
  { item_id: 'G4-disclosure-listed-stages', conclusion: null, remark: LISTED_STAGES },
  { item_id: 'G4-disclosure-listed-stage-note', conclusion: null, remark: '上市三阶段说明' },
  { item_id: 'G4-disclosure-soe-stages', conclusion: null, remark: SOE_STAGES },
  { item_id: 'G4-disclosure-soe-stage-note', conclusion: null, remark: '国企三阶段说明' },
  { item_id: 'G4-1-adjudicated-amount', conclusion: '8800', remark: null },
  { item_id: 'G6-disclosure-listed-stages', conclusion: null, remark: '别的底稿' },
]
const G4_ONLY = RESPONSES.filter((r) => r.item_id.startsWith('G4-'))
/** Tab 回显函数支持的 htmlData 形态（键 → 回复） */
const TAB_HTML_DATA = {
  checklist_responses: Object.fromEntries(
    G4_ONLY.map((r) => [r.item_id, { conclusion: r.conclusion ?? '', remark: r.remark ?? '' }]),
  ),
}
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-g4', wpCode: 'G4' }
const SOE = { ...CTX, variant: 'soe' as const, applicableStandards: ['soe_standalone'] }
const LISTED = { ...CTX, variant: 'listed' as const, applicableStandards: ['listed_standalone'] }

const STUBS = {
  'el-button': { template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>', emits: ['click'] },
  'el-alert': true, 'el-card': true, 'el-input': true, 'el-table': true, 'el-table-column': true,
  GtReviewTrigger: true, WpAmountInput: true,
}

/** Tab 路径：挂载真实 Tab（onMounted 回显），点「同步到附注」，取它发出的载荷；回显触发的自动同步用假计时器拦住 */
async function tabPayload(variant: 'soe' | 'listed') {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  try {
    h.apiPost.mockResolvedValue({ rows_synced: 9 })
    const wrapper = mount(variant === 'soe' ? G4TabDisclosureSOE : G4TabDisclosureListed, {
      props: {
        htmlData: TAB_HTML_DATA, wpId: 'wp-g4', projectId: 'p1', isReadonly: false,
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
  } finally {
    vi.clearAllTimers()
    vi.useRealTimers()
  }
}

function labels(rows: unknown): string[] {
  return (rows as Array<{ label: string }>).map((r) => r.label)
}

describe('g4HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockImplementation(async (url: string) => (url.endsWith('/checklist-responses') ? RESPONSES : {}))
    h.post.mockResolvedValue({ rows_synced: 9, push_kept: [{ table: '债权投资' }] })
  })
  afterEach(() => vi.restoreAllMocks())

  it('上市：离屏载荷与真实 Tab 点「同步到附注」发出的逐字节相同（主表 + 六张三阶段表 + 说明）', async () => {
    const out = await g4HeadlessProvider(LISTED)
    expect(out).toEqual({ sections: [{ section: '五、14', rows: 9, kept: 1 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-g4/checklist-responses', expect.anything())
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    expect(sent.section_id).toBe('五、14')
    expect(labels(sent.sub_table_data['债权投资'])).toEqual(
      ['国债', '企业债', '其他债权投资', '小计', '减：一年内到期的债权投资', '合计'],
    )
    const s1 = sent.sub_table_data['期末处于第一阶段的债权投资的减值准备'] as Array<Record<string, unknown>>
    expect(s1.find((r) => r.label === '国债A')).toMatchObject({ gross: 1000, provision: 10, reason: '信用风险未显著增加' })
    expect(s1.at(-1)).toMatchObject({ label: '合计', gross: 1500, provision: 35, is_total: true })
    expect(labels(sent.sub_table_data['上年年末处于第一阶段的债权投资的减值准备'])).toContain('上年组合')
    expect(sent.sub_table_data._note_texts).toEqual([{ section: 'listed-stage-note', text: '上市三阶段说明' }])
    expect(JSON.stringify(sent)).toBe(JSON.stringify(await tabPayload('listed')))
  })

  it('国企：离屏载荷与真实 Tab 逐字节相同；阶段表按国企骨架回显（表名 / 末列名是国企模板写法）', async () => {
    const out = await g4HeadlessProvider(SOE)
    expect(out).toEqual({ sections: [{ section: '八、15', rows: 9, kept: 1 }] })
    const sent = h.post.mock.calls[0][1]
    expect(labels(sent.sub_table_data['债权投资情况'])).toEqual(['项目1', '项目2', '项目3', '合计'])
    const stageTables = Object.keys(sent.sub_table_data).filter((k) => k.includes('阶段'))
    expect(stageTables).toEqual([
      '期末，处于第一阶段的债权投资的减值准备',
      '期末，处于第二阶段的债权投资的减值准备',
      '期末，处于第三阶段的债权投资的减值准备',
    ])
    expect(labels(sent.sub_table_data['期末，处于第三阶段的债权投资的减值准备'])).toContain('违约债组合')
    expect(sent.columns['期末，处于第二阶段的债权投资的减值准备'].at(-1).label).toBe('理由')
    expect(sent.sub_table_data._note_texts).toEqual([{ section: 'soe-stage-note', text: '国企三阶段说明' }])
    expect(JSON.stringify(sent)).toBe(JSON.stringify(await tabPayload('soe')))
  })

  it('离屏不写底稿、不订阅审定事件、不广播、无组件实例警告', async () => {
    const add = vi.spyOn(window, 'addEventListener')
    const dispatch = vi.spyOn(window, 'dispatchEvent')
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    await g4HeadlessProvider(LISTED)
    await g4HeadlessProvider(SOE)
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiPut).not.toHaveBeenCalled()
    expect(h.apiPost).not.toHaveBeenCalled()
    expect(add.mock.calls.map((c) => c[0])).not.toContain('substantive:adjudicated')
    expect(dispatch).not.toHaveBeenCalled()
    expect(warn.mock.calls.flat().join(' ')).not.toMatch(/Vue warn/)
    expect(h.post).toHaveBeenCalledTimes(2)
  })

  it('口径不适用回空，不发请求', async () => {
    expect(await g4HeadlessProvider({ ...SOE, applicableStandards: ['listed_standalone'] })).toEqual({ sections: [] })
    expect(await g4HeadlessProvider({ ...LISTED, applicableStandards: ['soe_standalone'] })).toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('现状钉住（缺陷已登记）：render-config 只下发 responses_snapshot 时 Tab 回显不到已存三阶段明细 / 说明', () => {
    const snapshot = TAB_HTML_DATA.checklist_responses
    for (const variant of ['listed', 'soe'] as const) {
      const st = useG4DisclosureTabState(variant, () => ({ responses_snapshot: snapshot }))
      st.loadFromHtmlData()
      expect(st.stageNoteText.value).toBe('')
      const details = st.stageBlocks.value.flatMap((b) => [...b.individual.details, ...b.portfolio.details])
      expect(details.every((d) => isPlaceholderStageDetail(d))).toBe(true)
    }
  })

  it('静态接线：两个 Tab 调同一个状态 / 回显 / 快照函数，不再内联', () => {
    const dir = resolve(__dirname, '../../g4-bond-investment-main/core')
    for (const [file, variant] of [['G4TabDisclosureListed.vue', 'listed'], ['G4TabDisclosureSOE.vue', 'soe']] as const) {
      const src = readFileSync(resolve(dir, file), 'utf-8')
      expect(src).toMatch(new RegExp(`useG4DisclosureTabState\\('${variant}', \\(\\) => props\\.htmlData\\)`))
      expect(src).toMatch(new RegExp(
        `buildG4SyncPayload\\(\\s*props\\.wpId, '${variant}', props\\.applicableStandards, buildSyncSnapshot\\(\\),\\s*\\)`,
      ))
      expect(src).toMatch(/window\.addEventListener\('substantive:adjudicated', handleAdjudicated\)\s*loadFromHtmlData\(\)/)
      expect(src).toMatch(new RegExp(`G4_DISCLOSURE_STAGE_KEYS\\.${variant}\\b`))
      expect(src).not.toMatch(/function (readSaved|buildSections|loadFromHtmlData|buildSyncSnapshot)\b/)
    }
  })
})
