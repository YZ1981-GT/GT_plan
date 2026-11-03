/**
 * H6 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①离屏请求体与「Tab 挂载同步骤：hydrateH6DisclosureState → seedH6ClearingFromLocal → h6DisclosureSyncSnapshot
 * → buildH6Listed/SoeSyncPayloads（空适用准则，与 Tab 同参）」逐字节相同 ②已保存的披露打包优先；清理明细为空时从
 * H6-1/H6-2 带入（离屏不保存）③Tab 的 hydrate / 挂载 / 同步调的就是这几个共用函数（静态接线）④只读 H6- 条目、
 * 静默发出、不写底稿、不跨底稿取数。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, reactive, ref } from 'vue'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), apiGet: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet } }))

import { h6HeadlessProvider } from '../h6HeadlessDisclosure'
import {
  H6_LISTED_KEYS,
  H6_SOE_KEYS,
  createDefaultState,
  h6DisclosureSyncSnapshot,
  hydrateH6DisclosureState,
} from '../h6DisclosureModel'
import { seedH6ClearingFromLocal, useH6Disclosure } from '../useH6Disclosure'
import { buildH6ListedSyncPayloads, buildH6SoeSyncPayloads } from '../h6DisclosureSyncPayload'

const PACK = JSON.stringify({
  faEnd: 9000, faPrior: 8000, clearingNote: '设备报废清理中',
  clearingRows: [{ rowId: 'c1', name: '报废车床', endBalance: 300, priorBalance: 0, reason: '报废' }],
})
const SOURCE_ROWS = [
  { item_id: 'H6-1-end-balance-audited', remark: '450', conclusion: null },
  { item_id: 'H6-2-rows', remark: JSON.stringify([
    { rowId: 'd1', assetName: '旧厂房', status: '清理中', endAudited: 450, beginAudited: 200, disposalReason: '拆除' },
  ]), conclusion: null },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-h6', wpCode: 'H6', applicableStandards: ['listed_standalone'] }
const WP = resolve(__dirname, '../..')

function own(list: Array<{ item_id: string }>) {
  return new Map(list.filter((r) => r.item_id.startsWith('H6-')).map((r) => [r.item_id, r]))
}

async function tabPayloads(variant: 'listed' | 'soe', list: Array<{ item_id: string }>) {
  const map = own(list)
  const scope = effectScope(true)
  const { disclosure, state } = scope.run(() => ({ disclosure: useH6Disclosure(ref(map)), state: reactive(createDefaultState()) }))!
  await nextTick()
  hydrateH6DisclosureState(state, map, variant === 'listed' ? H6_LISTED_KEYS : H6_SOE_KEYS)
  seedH6ClearingFromLocal(state, disclosure.pullFromLocalSources)
  const out = variant === 'listed'
    ? buildH6ListedSyncPayloads('wp-h6', [], h6DisclosureSyncSnapshot(state))
    : buildH6SoeSyncPayloads('wp-h6', [], h6DisclosureSyncSnapshot(state))
  scope.stop()
  return out
}

describe('h6HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.post.mockResolvedValue({ rows_synced: 3, push_kept: [] })
  })

  it('上市·已保存打包：载荷与 Tab 同步骤逐字节相同，静默发出、不写底稿、不跨底稿取数', async () => {
    const list = [{ item_id: H6_LISTED_KEYS.pack, remark: PACK, conclusion: null }, ...SOURCE_ROWS,
      { item_id: 'H1-listed-summary', remark: '[]', conclusion: null }]
    h.get.mockResolvedValue(list)
    const out = await h6HeadlessProvider({ ...CTX, variant: 'listed' })
    expect(out).toEqual({ sections: [{ section: '五、22', rows: 3, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-h6/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiGet).not.toHaveBeenCalled()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    expect(JSON.stringify(sent)).toBe(JSON.stringify((await tabPayloads('listed', list))[0]))
    const rows = sent.sub_table_data['固定资产清理'] as Array<Record<string, unknown>>
    expect(rows.map((r) => r.label)).toEqual(['报废车床', '合计'])
  })

  it('国企·清理明细为空：与 Tab 挂载同口径从 H6-1/H6-2 带入后发出', async () => {
    h.get.mockResolvedValue(SOURCE_ROWS)
    const out = await h6HeadlessProvider({ ...CTX, variant: 'soe', applicableStandards: ['soe_standalone'] })
    expect(out.sections.map((s) => s.section)).toEqual(['八、22'])
    const sent = h.post.mock.calls[0][1]
    expect(JSON.stringify(sent)).toBe(JSON.stringify((await tabPayloads('soe', SOURCE_ROWS))[0]))
    const rows = sent.sub_table_data['固定资产清理'] as Array<Record<string, unknown>>
    expect(rows.find((r) => r.label === '旧厂房')?.end_carrying).toBe(450)
    expect(h.put).not.toHaveBeenCalled()
  })

  it('静态接线：Tab 的 hydrate / 挂载 / 同步调同一组共用函数', () => {
    const tab = readFileSync(resolve(WP, 'h6/core/H6TabDisclosure.vue'), 'utf-8')
    expect(tab).toContain('hydrateH6DisclosureState(state, props.allResponses, keys.value)')
    expect(tab).toContain('if (seedH6ClearingFromLocal(state, pullFromLocalSources)) persistAll()')
    expect(tab).toContain('const payloadState = h6DisclosureSyncSnapshot(state)')
  })
})
