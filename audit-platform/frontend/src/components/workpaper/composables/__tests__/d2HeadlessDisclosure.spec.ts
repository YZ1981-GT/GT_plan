/**
 * D2 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-header-formula-closure R2.3 / note-pull-followup-closure R1）。
 *
 * 判据：①离屏发出的载荷与 Tab 发送函数 `postD2DisclosureSync`（同一批响应 + 同一账龄配置 + 同一附注现存表名）发出的载荷逐字节
 * 相同 ②项目账龄配置真的生效（3 年段项目出现「3年以上」行，默认 5 年段没有）③只读本底稿 D2- 条目、离屏不写底稿（不调 PUT）
 * ④首次同步按附注现存表名播种孤儿表基线 ⑤章节保护命中时不发请求。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), apiGet: vi.fn(), detail: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet } }))
vi.mock('@/services/auditPlatformApi', () => ({ getDisclosureNoteDetail: h.detail }))

import { d2HeadlessProvider } from '../d2HeadlessDisclosure'
import { useD2DisclosureNote } from '../useD2DisclosureNote'
import { postD2DisclosureSync, seedD2SyncBaseline } from '../d2DisclosureSync'
import { D2_TABLE_NAMES } from '../d2NoteSectionMap'
import { clearAgingConfigCache, PRESET_SEGMENTS, primeAgingConfig } from '@/composables/useAgingConfig'
import type { ChecklistResponse } from '../useD2FormData'

const DETAIL = JSON.stringify([
  { rowId: 'r1', customerName: 'A公司', currentAudited: 650, agingAudited: { within1: 600, over3: 50 }, agingPrior: { within1: 400 } },
  { rowId: 'r2', customerName: 'B公司', currentAudited: 100, agingAudited: { y1to2: 100 }, agingPrior: {} },
])
const RESPONSES = [
  { item_id: 'D2-detail-rows', remark: DETAIL, conclusion: null },
  { item_id: 'D2-adj-tb-amount', remark: '750', conclusion: null },
  { item_id: 'K1-unrelated', remark: '999', conclusion: null },
]
const ORPHAN = '组合计提项目：旧组合名'
const CTX = { projectId: 'p1', year: 2025, variant: 'soe' as const, wpId: 'wp-d2', wpCode: 'D2', applicableStandards: ['soe_standalone'] }

/** Tab 路径：底稿披露 Tab 的发送函数（同一批 D2- 响应、同一账龄缓存、同一附注现存表名） */
async function tabPayload() {
  await primeAgingConfig('p1')
  const map = new Map<string, ChecklistResponse>(
    RESPONSES.filter((r) => r.item_id.startsWith('D2-')).map((r) => [r.item_id, r as ChecklistResponse]),
  )
  const scope = effectScope(true)
  const api = scope.run(() => useD2DisclosureNote({
    allResponses: ref(map), wpId: ref('wp-d2'), projectId: ref('p1'), variant: 'soe', save: () => {}, isReadonly: ref(false),
  }))!
  await nextTick()
  const before = h.post.mock.calls.length
  await postD2DisclosureSync(api, { projectId: 'p1', year: 2025, variant: 'soe', wpId: 'wp-d2', applicableStandards: ['soe_standalone'] })
  scope.stop()
  return h.post.mock.calls[before][1]
}

describe('d2HeadlessProvider', () => {
  beforeEach(() => {
    clearAgingConfigCache()
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 22, push_kept: [{ table: 't' }] })
    h.apiGet.mockResolvedValue({ preset: 'THREE_YEAR', effective_segments: PRESET_SEGMENTS.THREE_YEAR, subject_overrides: {} })
    h.detail.mockResolvedValue({ table_data: { _tables: [{ name: ORPHAN }], sub_table_data: { [ORPHAN]: [] } } })
  })

  it('载荷与 Tab 发送函数逐字节相同，经同一端点静默发出、不写底稿', async () => {
    const out = await d2HeadlessProvider(CTX)
    expect(out).toEqual({ sections: [{ section: '八、5', rows: 22, kept: 1 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-d2/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    clearAgingConfigCache()
    expect(JSON.stringify(sent)).toBe(JSON.stringify(await tabPayload()))
  })

  it('项目账龄配置生效：3 年段出现「3年以上」行；孤儿表按附注现存表名清理', async () => {
    await d2HeadlessProvider(CTX)
    const sent = h.post.mock.calls[0][1]
    const aging = sent.sub_table_data[D2_TABLE_NAMES.soe.aging] as Array<{ label: string; end_amount: number }>
    expect(aging.find((r) => r.label === '3年以上')?.end_amount).toBe(50)
    expect(aging.some((r) => r.label === '5年以上')).toBe(false)
    expect(sent.sub_table_data._removed_table_keys).toEqual([ORPHAN])
  })

  it('账龄配置取不到：按 D2 默认 5 年段（与底稿页加载失败同一兜底）', async () => {
    h.apiGet.mockRejectedValue(new Error('offline'))
    await d2HeadlessProvider(CTX)
    const aging = h.post.mock.calls[0][1].sub_table_data[D2_TABLE_NAMES.soe.aging] as Array<{ label: string }>
    expect(aging.some((r) => r.label === '5年以上')).toBe(true)
  })

  it('播种只在首次同步做：已有「上次已同步表名」或没有审计年度时不读附注', async () => {
    const source = { syncedTableNames: ref(['旧表']), seedSyncedTablesFromNote: vi.fn() }
    await seedD2SyncBaseline(source, { projectId: 'p1', year: 2025, variant: 'soe' })
    source.syncedTableNames.value = []
    await seedD2SyncBaseline(source, { projectId: 'p1', year: null, variant: 'soe' })
    expect(h.detail).not.toHaveBeenCalled()
    await seedD2SyncBaseline(source, { projectId: 'p1', year: 2025, variant: 'soe' })
    expect(h.detail).toHaveBeenCalledWith('p1', 2025, '八、5')
    expect(source.seedSyncedTablesFromNote).toHaveBeenCalledTimes(1)
  })

  it('章节保护命中：不发请求，原因随结果回报', async () => {
    const out = await d2HeadlessProvider({ ...CTX, sectionGuard: () => '附注 八、5 已有 3 格人工填写' })
    expect(h.post).not.toHaveBeenCalled()
    expect(out).toEqual({ sections: [{ section: '八、5', rows: 0, skipped: '附注 八、5 已有 3 格人工填写' }] })
  })
})
