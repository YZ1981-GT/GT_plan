/**
 * D4 披露表离屏同步 = 两版底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①离屏发出的载荷与「Tab 同款 composable → 挂载时同一步首载刷新 → 同一快照函数 → 同一 builder」逐字节相同，
 * 夹具有真实数据（收入 / 成本取试算表、分产品从 D4-2 / D4-3 带入、说明非空）②有试算表缓存时不再取数（与 Tab 挂载同口径）
 * ③首载刷新只改内存、不写底稿，不订阅窗口事件 ④两版 Tab 都调共用快照函数 ⑤两口径分别写 五、62 / 八、64。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), apiGet: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet } }))

import { d4HeadlessProvider } from '../d4HeadlessDisclosure'
import { useD4Disclosure } from '../useD4Disclosure'
import { buildD4SyncPayload } from '../d4NoteSectionMap'
import { buildD4DisclosureSnapshot, readD4Section6Rows } from '../d4DisclosureSnapshot'

const J = JSON.stringify
const row = (item_id: string, remark: unknown) => ({ item_id, remark: typeof remark === 'string' ? remark : J(remark), conclusion: null })
const BALANCES = { 2025: [1000, 200, 600, 50], 2024: [800, 100, 500, 40] } as Record<number, number[]>
const BASE = [
  row('D4-2-rows', [{ productName: '产品A', months: [100, 200], auditAdjustment: 50, priorAudited: 300 }]),
  row('D4-3-rows', [{ name: '租金收入', currentUnadjusted: 40, currentAdjustment: 0, priorAudited: 10 }]),
  row('D4-disc-listed-note-1', '收入确认说明'),
  row('D4-disc-soe-note-2', '国企分解说明'),
  row('K1-unrelated', '999'),
]
const CACHE = row('D4-disc-listed-tb-balances', {
  revenue_6001: 7, revenue_6051: 1, cost_6401: 3, cost_6402: 1,
  prior_revenue_6001: 0, prior_revenue_6051: 0, prior_cost_6401: 0, prior_cost_6402: 0, _refreshTime: '2026-01-01T00:00:00Z',
})
const CTX = { projectId: 'p1', year: 2025, variant: 'listed' as const, wpId: 'wp-d4', wpCode: 'D4', applicableStandards: ['listed_standalone'] }
let responses = BASE

/** 试算表取数接口：按年度回收入 / 成本审定数；其余 GET 回底稿回复 */
function mockGet(url: string, cfg?: any) {
  if (url.includes('/auto-data/d4_analysis_indicators')) {
    const [r1, r2, c1, c2] = BALANCES[cfg?.params?.year] ?? [0, 0, 0, 0]
    return Promise.resolve({ data: { balances: { revenue_6001: r1, revenue_6051: r2, cost_6401: c1, cost_6402: c2 } } })
  }
  return Promise.resolve(responses)
}

/** Tab 路径：Tab 同款 `useD4Disclosure`（同一批 D4- 回复、主入口同一审计年度）→ 挂载时同一步首载刷新 → 同一快照函数 → 同一 builder */
async function tabPayload(variant: 'listed' | 'soe') {
  const map = new Map<string, any>(responses.filter((r) => r.item_id.startsWith('D4-')).map((r) => [r.item_id, { ...r }]))
  const scope = effectScope(true)
  const d4 = scope.run(() => useD4Disclosure({
    allResponses: ref(map), wpId: ref('wp-d4'), projectId: ref('p1'), variant,
    saveBatch: () => {}, isReadonly: ref(false), auditYear: ref<number | null>(2025),
  }))!
  await d4.initialRefresh()
  await nextTick()
  const payload = buildD4SyncPayload(variant, 'wp-d4', null, buildD4DisclosureSnapshot(d4, {
    section6Rows: readD4Section6Rows(map, variant), auditYear: 2025,
  }))
  scope.stop()
  return payload
}

describe('d4HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    responses = BASE
    h.get.mockImplementation(mockGet)
    h.post.mockResolvedValue({ rows_synced: 20, push_kept: [{ table: '营业收入和营业成本' }] })
  })

  it('上市（无试算表缓存）：首载刷新取数后与 Tab 路径逐字节相同、数据非空，不写底稿、不订阅窗口事件', async () => {
    const addSpy = vi.spyOn(window, 'addEventListener')
    const out = await d4HeadlessProvider(CTX)
    expect(addSpy.mock.calls.some(([type]) => String(type) === 'note:section-updated')).toBe(false)
    addSpy.mockRestore()
    expect(out).toEqual({ sections: [{ section: '五、62', rows: 20, kept: 1 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-d4/checklist-responses', expect.anything())
    expect(h.get).toHaveBeenCalledWith('/api/projects/p1/auto-data/d4_analysis_indicators', expect.objectContaining({ params: { year: 2024 } }))
    expect(h.put).not.toHaveBeenCalled()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    h.post.mockClear()
    expect(J(sent)).toBe(J(await tabPayload('listed')))
    const sub = sent.sub_table_data
    expect(sub['营业收入和营业成本'].map((r: any) => [r.label, r.endRevenue, r.endCost, r.priorRevenue])).toEqual([
      ['主营业务', 1000, 600, 800], ['其他业务', 200, 50, 100], ['合计', 1200, 650, 900],
    ])
    expect(sub['营业收入、营业成本按行业（或产品类型）划分'].map((r: any) => [r.label, r.endRevenue])).toEqual([
      ['产品A', 350], ['租金收入', 40], ['合计', 390],
    ])
    expect(sub._note_texts.map((t: any) => t.text)).toEqual(['收入确认说明'])
  })

  it('有试算表缓存：不再取数（与 Tab 挂载同口径），主表取缓存值', async () => {
    responses = [...BASE, CACHE]
    await d4HeadlessProvider(CTX)
    expect(h.get.mock.calls.some(([u]) => String(u).includes('/auto-data/'))).toBe(false)
    const sent = h.post.mock.calls[0][1]
    expect(J(sent)).toBe(J(await tabPayload('listed')))
    expect(sent.sub_table_data['营业收入和营业成本'].at(-1)).toMatchObject({ label: '合计', endRevenue: 8, endCost: 4 })
  })

  it('国企：写 八、64，载荷与 Tab 路径逐字节相同', async () => {
    const out = await d4HeadlessProvider({ ...CTX, variant: 'soe', applicableStandards: ['soe_standalone'] })
    expect(out.sections.map((s) => s.section)).toEqual(['八、64'])
    const sent = h.post.mock.calls[0][1]
    expect(J(sent)).toBe(J(await tabPayload('soe')))
    expect(sent.sub_table_data['营业收入、营业成本'].at(-1)).toMatchObject({ label: '合计', endRevenue: 1200 })
    expect(sent.sub_table_data._note_texts.map((t: any) => t.text)).toEqual(['国企分解说明'])
  })

  it('两版 Tab 接线：buildSnapshot 与（6）行读取调共用函数', () => {
    for (const [file, variant] of [['D4TabDisclosureListed.vue', 'listed'], ['D4TabDisclosureSoe.vue', 'soe']]) {
      const src = readFileSync(resolve(__dirname, '../../d4/core', file), 'utf-8')
      expect(src, file).toContain('return buildD4DisclosureSnapshot(d4, { section6Rows: section6Rows.value, auditYear: auditYear.value })')
      expect(src, file).toContain(`readD4Section6Rows(props.allResponses, '${variant}')`)
      expect(src, file).toContain("buildD4SyncPayload(VARIANT, props.wpId || '', null, buildSnapshot())")
    }
  })
})
