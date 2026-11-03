/**
 * H9 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①离屏发出的请求体与「Tab 同参实例化 useH9Listed/SoeDisclosure → buildH9Listed/SoeSyncPayloads」逐字节相同
 * ②只读本底稿 H9- 条目（别的底稿条目混在响应里不影响）、经 sync-from-workpaper 静默发出、不写底稿 ③口径不适用回空。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))

import { h9HeadlessProvider } from '../h9HeadlessDisclosure'
import { useH9ListedDisclosure, useH9SoeDisclosure } from '../useH9Disclosure'
import { buildH9ListedSyncPayloads, buildH9SoeSyncPayloads } from '../h9DisclosureSyncPayload'

const LISTED_PACK = JSON.stringify({
  rows: [
    { rowId: 'H9-listed-1', item: '房屋及建筑物租赁', endBalance: 1200, lastYearEnd: 800 },
    { rowId: 'H9-listed-2', item: '设备租赁', endBalance: 300, lastYearEnd: 0 },
  ],
  withinOneYear: { end: 200, last: 100 },
  interest: { total: 50000, financeExpense: 40000, capitalized: 10000, year: '2025' },
  interestNoteOverride: '',
})
const SOE_PACK = JSON.stringify({
  rows: [
    { key: 'payment', item: '租赁付款额', endBalance: 1500, beginBalance: 900 },
    { key: 'unearned', item: '减：未确认的融资费用', endBalance: 120, beginBalance: 60 },
    { key: 'reclass', item: '重分类至一年内到期的非流动负债', endBalance: 200, beginBalance: 100 },
  ],
  supplementNote: '本期新增房屋租赁 2 项',
})
const RESPONSES = [
  { item_id: 'H9-disc-listed-rows', remark: LISTED_PACK, conclusion: null },
  { item_id: 'H9-disc-soe-rows', remark: SOE_PACK, conclusion: null },
  { item_id: 'H8-listed-movement', remark: '{"cost_begin":{"house":9}}', conclusion: null },
]
const OWN = new Map(RESPONSES.filter((r) => r.item_id.startsWith('H9-')).map((r) => [r.item_id, r]))
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-h9', wpCode: 'H9' }

/** Tab 路径：宿主给的响应 → 同一个 composable（Tab 挂载时 immediate 读取）→ Tab syncToNotes 的同一个 builder */
async function tabPayloads(variant: 'listed' | 'soe', standards: string[]) {
  const scope = effectScope(true)
  const note = scope.run(() => (variant === 'listed'
    ? useH9ListedDisclosure({ allResponses: ref(OWN), onSave: () => {} })
    : useH9SoeDisclosure({ allResponses: ref(OWN), onSave: () => {} })))!
  await nextTick()
  const out = variant === 'listed'
    ? buildH9ListedSyncPayloads('wp-h9', standards, (note as ReturnType<typeof useH9ListedDisclosure>).state.value)
    : buildH9SoeSyncPayloads('wp-h9', standards, (note as ReturnType<typeof useH9SoeDisclosure>).state.value)
  scope.stop()
  return out
}

describe('h9HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 6, push_kept: [] })
  })

  it('上市：载荷与 Tab 同参 builder 逐字节相同，静默发出、不写底稿', async () => {
    const out = await h9HeadlessProvider({ ...CTX, variant: 'listed', applicableStandards: ['listed_standalone'] })
    expect(out).toEqual({ sections: [{ section: '五、47', rows: 6, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-h9/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    const expected = await tabPayloads('listed', ['listed_standalone'])
    expect(expected).toHaveLength(1)
    expect(JSON.stringify(sent)).toBe(JSON.stringify(expected[0]))
    const rows = sent.sub_table_data['租赁负债'] as Array<{ label: string; end_balance: number | null }>
    expect(rows.find((r) => r.label === '房屋及建筑物租赁')?.end_balance).toBe(1200)
  })

  it('国企：载荷与 Tab 同参 builder 逐字节相同', async () => {
    const out = await h9HeadlessProvider({ ...CTX, variant: 'soe', applicableStandards: ['soe_standalone'] })
    expect(out).toEqual({ sections: [{ section: '八、52', rows: 6, kept: 0 }] })
    const sent = h.post.mock.calls[0][1]
    const expected = await tabPayloads('soe', ['soe_standalone'])
    expect(JSON.stringify(sent)).toBe(JSON.stringify(expected[0]))
    const rows = sent.sub_table_data['租赁负债'] as Array<{ label: string; end_balance: number | null }>
    expect(rows.find((r) => r.label === '租赁付款额')?.end_balance).toBe(1500)
  })

  it('口径不适用（上市页、项目只适用国企准则）：不发请求、回空', async () => {
    const out = await h9HeadlessProvider({ ...CTX, variant: 'listed', applicableStandards: ['soe_standalone'] })
    expect(out).toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })
})
