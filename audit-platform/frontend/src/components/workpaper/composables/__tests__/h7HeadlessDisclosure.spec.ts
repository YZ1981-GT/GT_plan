/**
 * H7 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①离屏请求体与「Tab 的 hydrate 解析 readH7ListedForm / readH7SoeForm → h7ListedSyncSnapshot / h7SoeSyncSnapshot
 * → buildH7Listed/SoeSyncPayloads」逐字节相同 ②两个 Tab 的 hydrate 与「同步到附注」调的就是这几个共用函数（静态接线）
 * ③只读本底稿 H7-disc- 条目、静默发出、不写底稿 ④口径不适用回空。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))

import { h7HeadlessProvider } from '../h7HeadlessDisclosure'
import { h7ListedSyncSnapshot, h7SoeSyncSnapshot, readH7ListedForm, readH7SoeForm } from '../h7DisclosureForm'
import { buildH7ListedSyncPayloads, buildH7SoeSyncPayloads } from '../h7DisclosureSyncPayload'
import { H7_LISTED_SUBTABLE, H7_SOE_SUBTABLE } from '../h7NoteSectionMap'

const CATEGORIES = [
  { key: 'crop_1', label: '苹果树', industry: 'crop' },
  { key: 'livestock_1', label: '奶牛', industry: 'livestock' },
]
const SOE_COST = [
  { key: 'crop', selfAmounts: { begin: 0, increase: 0, decrease: 0 }, categories: [{ id: 'crop-1', name: '苹果树', begin: 500, increase: 80, decrease: 20 }] },
  { key: 'livestock', selfAmounts: { begin: 300, increase: 40, decrease: 0 }, categories: [] },
]
const RESPONSES = [
  { item_id: 'H7-disc-listed-categories', remark: JSON.stringify(CATEGORIES), conclusion: null },
  { item_id: 'H7-disc-listed-cost', remark: JSON.stringify({ cost_begin: { crop_1: 500, livestock_1: 300 } }), conclusion: null },
  { item_id: 'H7-disc-listed-policy', remark: '采用成本模式计量，按年限平均法计提折旧', conclusion: null },
  { item_id: 'H7-disc-soe-cost', remark: JSON.stringify(SOE_COST), conclusion: null },
  { item_id: 'H7-disc-soe-fair-basis', remark: null, conclusion: '按评估报告确认' },
  { item_id: 'H7-1-cost-rows', remark: '[{"name":"x","audited":1}]', conclusion: null },
]
const OWN = new Map(RESPONSES.filter((r) => r.item_id.startsWith('H7-disc-')).map((r) => [r.item_id, r]))
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-h7', wpCode: 'H7' }
const WP = resolve(__dirname, '../..')

describe('h7HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 45, push_kept: [] })
  })

  it('上市：载荷与 Tab 同一解析 + 快照 + builder 逐字节相同，静默发出、不写底稿', async () => {
    const out = await h7HeadlessProvider({ ...CTX, variant: 'listed', applicableStandards: ['listed_standalone'] })
    expect(out).toEqual({ sections: [{ section: '五、24', rows: 45, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-h7/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    const expected = buildH7ListedSyncPayloads('wp-h7', ['listed_standalone'], h7ListedSyncSnapshot(readH7ListedForm(OWN)))
    expect(JSON.stringify(sent)).toBe(JSON.stringify(expected[0]))
    const cost = sent.sub_table_data[H7_LISTED_SUBTABLE.cost] as Array<Record<string, unknown>>
    expect(cost.find((r) => r.label === '1.期初余额')?.crop_1).toBe(500)
    expect(JSON.stringify(sent.sub_table_data._note_texts)).toContain('年限平均法')
  })

  it('国企：载荷与 Tab 同一解析 + 快照 + builder 逐字节相同（conclusion 兜底的说明也读到）', async () => {
    const out = await h7HeadlessProvider({ ...CTX, variant: 'soe', applicableStandards: ['soe_standalone'] })
    expect(out.sections.map((s) => s.section)).toEqual(['八、24'])
    const sent = h.post.mock.calls[0][1]
    const expected = buildH7SoeSyncPayloads('wp-h7', ['soe_standalone'], h7SoeSyncSnapshot(readH7SoeForm(OWN)))
    expect(JSON.stringify(sent)).toBe(JSON.stringify(expected[0]))
    expect(JSON.stringify(sent.sub_table_data[H7_SOE_SUBTABLE.cost])).toContain('苹果树')
    expect(JSON.stringify(sent.sub_table_data._note_texts)).toContain('评估报告')
  })

  it('口径不适用：不发请求、回空', async () => {
    expect(await h7HeadlessProvider({ ...CTX, variant: 'listed', applicableStandards: ['soe_standalone'] }))
      .toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('静态接线：两个 Tab 的 hydrate / 同步到附注调同一组共用函数', () => {
    const listed = readFileSync(resolve(WP, 'h7/core/H7TabDisclosureListed.vue'), 'utf-8')
    const soe = readFileSync(resolve(WP, 'h7/core/H7TabDisclosureSoe.vue'), 'utf-8')
    expect(listed).toContain('readH7ListedForm(localResponses.value)')
    expect(listed).toMatch(/buildH7ListedSyncPayloads\([^)]*h7ListedSyncSnapshot\(\{/)
    expect(soe).toContain('readH7SoeForm(localResponses.value)')
    expect(soe).toMatch(/buildH7SoeSyncPayloads\([^)]*h7SoeSyncSnapshot\(\{/)
  })
})
