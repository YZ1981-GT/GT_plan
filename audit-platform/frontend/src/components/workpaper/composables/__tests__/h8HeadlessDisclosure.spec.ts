/**
 * H8 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①离屏请求体与「Tab 同参实例化 useH8Listed/SoeDisclosure → h8ListedSyncSnapshot / h8SoeSyncSnapshot → builder」
 * 逐字节相同 ②两个 Tab 的「同步到附注」调的就是这两个快照函数（静态接线）③只读本底稿 H8- 条目、静默发出、不写底稿
 * ④口径不适用回空。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))

import { h8HeadlessProvider } from '../h8HeadlessDisclosure'
import { h8ListedSyncSnapshot, h8SoeSyncSnapshot, useH8ListedDisclosure, useH8SoeDisclosure } from '../useH8Disclosure'
import { buildH8ListedSyncPayloads, buildH8SoeSyncPayloads } from '../h8DisclosureSyncPayload'
import { createDefaultSoeLayers } from '../h8SoeDisclosureModel'

const SOE_LAYERS = createDefaultSoeLayers().map((l) => (l.layer === 'cost'
  ? { ...l, categories: l.categories.map((c) => (c.key === 'building' ? { ...c, begin: 900, increase: 300 } : c)) }
  : l.layer === 'dep'
    ? { ...l, categories: l.categories.map((c) => (c.key === 'building' ? { ...c, begin: 100, increase: 60 } : c)) }
    : l))
const RESPONSES = [
  { item_id: 'H8-listed-movement', remark: JSON.stringify({ cost_begin: { buildings: 800 }, cost_inc_lease: { buildings: 400 }, dep_begin: { buildings: 120 }, dep_inc_provision: { buildings: 80 } }), conclusion: null },
  { item_id: 'H8-listed-note-short-low', remark: '本期短期租赁费用 12 万元', conclusion: null },
  { item_id: 'H8-soe-layers', remark: JSON.stringify(SOE_LAYERS), conclusion: null },
  { item_id: 'H8-soe-note-impairment', remark: '本期未计提减值', conclusion: null },
  { item_id: 'H9-disc-listed-rows', remark: '{"rows":[]}', conclusion: null },
]
const OWN = new Map(RESPONSES.filter((r) => r.item_id.startsWith('H8-')).map((r) => [r.item_id, r]))
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-h8', wpCode: 'H8' }
const WP = resolve(__dirname, '../..')

async function tabPayloads(variant: 'listed' | 'soe', standards: string[]) {
  const scope = effectScope(true)
  const out = scope.run(() => {
    if (variant === 'listed') {
      const note = useH8ListedDisclosure({ allResponses: ref(OWN), onSave: () => {} })
      return () => buildH8ListedSyncPayloads('wp-h8', standards, h8ListedSyncSnapshot(note))
    }
    const note = useH8SoeDisclosure({ allResponses: ref(OWN), onSave: () => {} })
    return () => buildH8SoeSyncPayloads('wp-h8', standards, h8SoeSyncSnapshot(note))
  })!
  await nextTick()
  const payloads = out()
  scope.stop()
  return payloads
}

describe('h8HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 40, push_kept: [{ table: '使用权资产' }] })
  })

  it('上市：载荷与 Tab 同一快照函数 + builder 逐字节相同，静默发出、不写底稿', async () => {
    const out = await h8HeadlessProvider({ ...CTX, variant: 'listed', applicableStandards: ['listed_standalone'] })
    expect(out).toEqual({ sections: [{ section: '五、25', rows: 40, kept: 1 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-h8/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    expect(JSON.stringify(sent)).toBe(JSON.stringify((await tabPayloads('listed', ['listed_standalone']))[0]))
    const rows = Object.values(sent.sub_table_data)[0] as Array<Record<string, unknown>>
    expect(rows.find((r) => r.label === '1.期初余额')?.buildings).toBe(800)
  })

  it('国企：载荷与 Tab 同一快照函数 + builder 逐字节相同', async () => {
    const out = await h8HeadlessProvider({ ...CTX, variant: 'soe', applicableStandards: ['soe_standalone'] })
    expect(out.sections.map((s) => s.section)).toEqual(['八、26'])
    const sent = h.post.mock.calls[0][1]
    expect(JSON.stringify(sent)).toBe(JSON.stringify((await tabPayloads('soe', ['soe_standalone']))[0]))
    const rows = Object.values(sent.sub_table_data)[0] as Array<Record<string, unknown>>
    expect(rows.find((r) => r.label === '房屋、建筑物')?.begin).toBe(900)
  })

  it('口径不适用：不发请求、回空', async () => {
    expect(await h8HeadlessProvider({ ...CTX, variant: 'soe', applicableStandards: ['listed_standalone'] }))
      .toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('静态接线：两个 Tab 的「同步到附注」调同一个快照函数', () => {
    const listed = readFileSync(resolve(WP, 'h8/core/H8TabDisclosureListed.vue'), 'utf-8')
    const soe = readFileSync(resolve(WP, 'h8/core/H8TabDisclosureSoe.vue'), 'utf-8')
    expect(listed).toMatch(/buildH8ListedSyncPayloads\([^)]*h8ListedSyncSnapshot\(listedNote\)\)/)
    expect(soe).toMatch(/buildH8SoeSyncPayloads\([^)]*h8SoeSyncSnapshot\(soeNote\)\)/)
  })
})
