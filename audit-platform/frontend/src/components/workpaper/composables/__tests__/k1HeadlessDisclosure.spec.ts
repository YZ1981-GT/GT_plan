/**
 * K1 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①挂载真实的两个披露 Tab（onMounted：没有已存披露数据 ⇒ 从 K1-1/K1-2 强制取数；已存 ⇒ 不取），调 Tab 的同步函数，
 * Tab 发出的载荷与离屏 provider 发出的逐字节相同；夹具有真实数据（K1-2 明细、K1-1 审定、汇总表、说明）②项目账龄配置生效
 * （三年段出现 over3、没有 over5）③只读 K1- 条目（K10~K13 不混入）、离屏不写底稿、不弹提示、不订阅审定事件 ④国企 Tab 传的是
 * 适用准则 getter：composable 同时接受 Ref 与 getter（原只读 `.value` ⇒ getter 恒为 undefined ⇒ 合并口径被写成 soe_standalone、
 * 口径门禁失效）⑤口径不适用回 `{ sections: [] }` ⑥静态接线：Tab 与离屏走同一个 initialFillFromSources / buildSyncPayloads。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'

const h = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), put: vi.fn(), apiGet: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn(),
  success: vi.fn(), warning: vi.fn(),
}))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet, post: h.apiPost, put: h.apiPut } }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }), useRoute: () => ({ params: {}, query: {} }) }))
vi.mock('element-plus', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  ElMessage: { success: h.success, warning: h.warning, error: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))
// 默认三阶段组合行的 rowKey 由值化身份工厂铸造（随机）且进载荷的 row_key ⇒ 两条路径各铸一套；固定下来才能逐字节比
vi.mock('../shared/rowIdentity', () => ({ newRowIdentity: (prefix: string) => `${prefix}-fixed` }))

import K1TabDisclosureListed from '../../k1/core/K1TabDisclosureListed.vue'
import K1TabDisclosureSoe from '../../k1/core/K1TabDisclosureSoe.vue'
import { k1HeadlessProvider } from '../k1HeadlessDisclosure'
import { useK1DisclosureSoe } from '../useK1DisclosureSoe'
import { K1_LISTED_SUBTABLE, K1_SOE_SUBTABLE } from '../k1NoteSectionMap'
import { buildG2ListedSyncPayloads, buildG2SoeSyncPayloads } from '../g2DisclosureSyncPayload'
import { buildG3ListedSyncPayloads, buildG3SoeSyncPayloads } from '../g3DisclosureSyncPayload'
import { clearAgingConfigCache, PRESET_SEGMENTS, primeAgingConfig } from '@/composables/useAgingConfig'
import { SYNC_URL, syncPayloadsFromTab, type Resp } from './_k1to6DisclosureTabHarness'

const J = JSON.stringify
const DETAIL = J([
  { id: 'd1', counterparty: '甲公司', nature: '保证金、押金', beginBalance: 300, endBalance: 500, badDebtProvision: 25,
    stage: 1, agingAudited: { within1: 380, y1to2: 70, over3: 50 }, agingPrior: { within1: 300 } },
  { id: 'd2', counterparty: '乙公司', nature: '备用金', beginBalance: 100, endBalance: 200, badDebtProvision: 10,
    stage: 1, agingAudited: { y2to3: 200 }, agingPrior: { y1to2: 100 } },
])
const SOURCES: Resp[] = [
  { item_id: 'K1-2-detail-rows', remark: DETAIL, conclusion: null },
  { item_id: 'K1-1-audited-receivable', remark: '700', conclusion: null },
  { item_id: 'K1-1-audited-baddebt', remark: '35', conclusion: null },
  { item_id: 'K1-1-prior-audited-baddebt', remark: '20', conclusion: null },
  { item_id: 'K1-1-fs-interest', remark: '50', conclusion: null },
  { item_id: 'K1-1-fs-dividend', remark: '30', conclusion: null },
  { item_id: 'K1-1-audited-net', remark: '665', conclusion: null },
  { item_id: 'K1-1-fs-other-total', remark: '745', conclusion: null },
]
const NOISE: Resp[] = [
  { item_id: 'K10-1-rows', remark: '[]', conclusion: null },
  { item_id: 'K1A-proc-1', remark: '程序', conclusion: null },
  { item_id: 'G2-1-audited', remark: '9', conclusion: null },
]
/** 上市：没有已存披露数据（打开即强制取数）+ 审计说明 */
const LISTED: Resp[] = [...SOURCES, { item_id: 'K1-note-listed-note', remark: '其他应收款审计说明', conclusion: null }, ...NOISE]
/** 国企：已存披露数据（打开不取数，K1-2 明细不会覆盖已存的前五名）+ 说明 */
const SOE_STORED = J({
  version: 2,
  top5Rows: [{ rowId: 't1', unitName: '丙公司（已存）', nature: '押金', endBalance: 120, aging: '1年以内', proportionPct: 40, provision: 6 }],
  govGrantRows: [{ rowId: 'g1', unitName: '财政局', projectName: '稳岗补贴', endBalance: 80, aging: '1年以内', expectedCollection: '2026年' }],
  notes: { balanceChange: '本期新增押金' },
})
const SOE: Resp[] = [
  ...SOURCES,
  { item_id: 'K1-note-soe-rows', remark: SOE_STORED, conclusion: null },
  { item_id: 'K1-note-soe-note', remark: '国企审计说明', conclusion: null },
  ...NOISE,
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-k1', wpCode: 'K1' }

function useResponses(list: Resp[]): void {
  h.get.mockImplementation(async (url: string) => (url.includes('checklist-responses') ? list : {}))
}

async function tabPayloads(variant: 'listed' | 'soe', list: Resp[], applicableStandards: string[]) {
  await primeAgingConfig('p1') // 底稿页打开时项目账龄配置通常已在缓存（宿主 / 明细页取过）；离屏由框架预取
  const Comp = variant === 'listed' ? K1TabDisclosureListed : K1TabDisclosureSoe
  return syncPayloadsFromTab(Comp, h.apiPost, { wpId: 'wp-k1', prefix: 'K1-', responses: list, applicableStandards })
}

function rows(sent: any, name: string): any[] {
  return sent.sub_table_data[name] as any[]
}

describe('k1HeadlessProvider', () => {
  beforeEach(() => {
    clearAgingConfigCache()
    for (const fn of Object.values(h)) fn.mockReset()
    h.apiGet.mockResolvedValue({ preset: 'THREE_YEAR', effective_segments: PRESET_SEGMENTS.THREE_YEAR, subject_overrides: {} })
    h.post.mockResolvedValue({ rows_synced: 31, push_kept: [] })
    h.apiPost.mockResolvedValue({ rows_synced: 31 })
  })

  it('上市：载荷与挂载的 Tab 逐字节相同（打开即从 K1-1/K1-2 强制取数 + 汇总表 + 说明），静默写 五、8、不写底稿不弹提示', async () => {
    useResponses(LISTED)
    const addListener = vi.spyOn(window, 'addEventListener')
    const out = await k1HeadlessProvider({ ...CTX, variant: 'listed', applicableStandards: ['listed_standalone'] })
    expect(out).toEqual({ sections: [{ section: '五、8', rows: 31, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-k1/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiPut).not.toHaveBeenCalled()
    expect(h.apiPost).not.toHaveBeenCalled()
    expect(h.success).not.toHaveBeenCalled()
    expect(addListener.mock.calls.some(([type]) => String(type) === 'substantive:adjudicated')).toBe(false)
    addListener.mockRestore()
    expect(h.post).toHaveBeenCalledTimes(1)
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe(SYNC_URL)
    expect(cfg).toMatchObject({ _silent: true })

    const tab = await tabPayloads('listed', LISTED, ['listed_standalone'])
    expect(tab.payloads).toHaveLength(1)
    expect(J(sent)).toBe(J(tab.payloads[0]))
    // Tab 挂载时同一步取数会存一次披露数据并提示；离屏只改内存
    expect(tab.saves.map(([id]) => id)).toContain('K1-note-listed-rows')
    expect(h.success).toHaveBeenCalledWith('已强制从源底稿覆盖取数')

    // 数据非空：账龄按三年段（有 over3、没有 over5），坏账准备取 K1-1 审定；按性质两行；汇总表四行；说明
    const aging = rows(sent, K1_LISTED_SUBTABLE.aging)
    expect(aging.find((r) => r.segment_key === 'over3')?.['期末余额']).toBe(50)
    expect(aging.some((r) => r.segment_key === 'over5')).toBe(false)
    expect(aging.find((r) => r.row_kind === 'provision')?.['期末余额']).toBe(35)
    expect(rows(sent, K1_LISTED_SUBTABLE.nature).find((r) => r.label === '保证金、押金')?.['期末账面余额']).toBe(500)
    expect(rows(sent, K1_LISTED_SUBTABLE.summary).map((r) => r['期末余额'])).toEqual([50, 30, 665, 745])
    expect(sent.sub_table_data._note_texts).toEqual([{ section: 'listed-audit-note', title: '审计说明', text: '其他应收款审计说明' }])
    expect(sent.sub_table_data._removed_table_keys).toBeUndefined()
  })

  it('国企：已存披露数据不重取；合并口径按 getter 读到 soe_consolidated，载荷与挂载的 Tab 逐字节相同，写 八、9', async () => {
    useResponses(SOE)
    const out = await k1HeadlessProvider({ ...CTX, variant: 'soe', applicableStandards: ['soe_consolidated'] })
    expect(out.sections.map((s) => s.section)).toEqual(['八、9'])
    const sent = h.post.mock.calls[0][1]
    const tab = await tabPayloads('soe', SOE, ['soe_consolidated'])
    expect(J(sent)).toBe(J(tab.payloads[0]))
    expect(tab.saves).toEqual([])
    expect(sent.current_standard).toBe('soe_consolidated')
    expect(rows(sent, K1_SOE_SUBTABLE.top5).map((r) => r.label)).toEqual(['丙公司（已存）', '合  计'])
    expect(rows(sent, K1_SOE_SUBTABLE.govGrant)[0]).toMatchObject({ label: '财政局', 期末余额: 80 })
    expect(sent.sub_table_data._note_texts).toEqual([
      { section: 'soe-audit-note', title: '审计说明', text: '国企审计说明' },
      { section: 'soe-balance-change', title: '本期账面余额显著变动说明', text: '本期新增押金' },
    ])
  })

  it('口径不适用（上市项目的国企披露表）：不发请求，回 { sections: [] }（Tab 同一 builder 判、只提示不同步）', async () => {
    useResponses(SOE)
    expect(await k1HeadlessProvider({ ...CTX, variant: 'soe', applicableStandards: ['listed_standalone'] }))
      .toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('国企 composable 同时接受 Ref 与 getter 的适用准则（原只读 .value，Tab 传 getter 时恒为 undefined）', () => {
    const scope = effectScope(true)
    const read = (applicableStandards: any) => scope.run(() => {
      const disc = useK1DisclosureSoe({
        wpId: ref('wp-k1'), projectId: ref('p1'), allResponses: ref(new Map()), isReadonly: ref(false), applicableStandards,
      })
      return { applicable: disc.isApplicable.value, payloads: disc.buildSyncPayloads() }
    })!
    const viaGetter = read(() => ['soe_consolidated'])
    const viaRef = read(ref(['soe_consolidated']))
    const listedOnly = read(() => ['listed_standalone'])
    scope.stop()
    expect(viaGetter.payloads[0].current_standard).toBe('soe_consolidated')
    expect(viaRef.payloads[0].current_standard).toBe('soe_consolidated')
    expect(viaGetter.applicable).toBe(true)
    expect(listedOnly.applicable).toBe(false)
    expect(listedOnly.payloads).toEqual([])
  })

  it('共用章节 五、8 / 八、9：K1 载荷不带 _removed_table_keys、子表名与 G2 / G3 不相交，依次写入不清掉对方子表', async () => {
    for (const variant of ['listed', 'soe'] as const) {
      h.post.mockClear()
      useResponses(variant === 'listed' ? LISTED : SOE)
      await k1HeadlessProvider({ ...CTX, variant, applicableStandards: [] })
      const k1Sub = h.post.mock.calls[0][1].sub_table_data as Record<string, unknown>
      expect(k1Sub._removed_table_keys, variant).toBeUndefined()
      const g2 = (variant === 'listed' ? buildG2ListedSyncPayloads : buildG2SoeSyncPayloads)(
        'wp-g2', [], { classRows: [], overdueRows: [], eclRows: [], auditNote: '' },
      )[0].sub_table_data as Record<string, unknown>
      const g3 = (variant === 'listed' ? buildG3ListedSyncPayloads : buildG3SoeSyncPayloads)('wp-g3', [], [], '')[0]
        .sub_table_data as Record<string, unknown>
      const tables = (sub: Record<string, unknown>) => Object.keys(sub).filter((k) => !k.startsWith('_'))
      const others = new Set([...tables(g2), ...tables(g3), ...((g2._removed_table_keys as string[]) ?? [])])
      expect(tables(k1Sub).filter((t) => others.has(t)), variant).toEqual([])
    }
  })

  it('章节保护命中：不发请求，原因随结果回报', async () => {
    useResponses(LISTED)
    const out = await k1HeadlessProvider({
      ...CTX, variant: 'listed', applicableStandards: [], sectionGuard: () => '附注 五、8 已有 4 格人工填写',
    })
    expect(h.post).not.toHaveBeenCalled()
    expect(out).toEqual({ sections: [{ section: '五、8', rows: 0, skipped: '附注 五、8 已有 4 格人工填写' }] })
  })

  it('静态接线：Tab 传适用准则 getter；两个 composable 挂载取数与同步都走共用函数，离屏不挂生命周期', () => {
    for (const [tab, composable] of [
      ['K1TabDisclosureListed.vue', 'useK1DisclosureListed.ts'],
      ['K1TabDisclosureSoe.vue', 'useK1DisclosureSoe.ts'],
    ]) {
      const tabSrc = readFileSync(resolve(__dirname, `../../k1/core/${tab}`), 'utf-8')
      expect(tabSrc, tab).toContain('applicableStandards: () => props.applicableStandards')
      const src = readFileSync(resolve(__dirname, `../${composable}`), 'utf-8')
      expect(src, composable).toContain("return typeof s === 'function' ? s() : s.value")
      expect(src, composable).toContain('if (initialFillFromSources()) notifyRefreshed(true)')
      expect(src.slice(src.indexOf('async function syncToNotes')), composable).toContain('const payloads = buildSyncPayloads()')
      expect(src, composable).toContain('if (getCurrentInstance()) {')
      const fill = src.slice(src.indexOf('function fillFromSources'), src.indexOf('function notifyRefreshed'))
      expect(fill, `${composable} 取数步骤不弹提示`).not.toContain('ElMessage')
    }
  })
})
