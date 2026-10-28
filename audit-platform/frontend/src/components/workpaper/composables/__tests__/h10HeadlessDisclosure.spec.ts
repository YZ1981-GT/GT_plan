/**
 * H10 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①离屏请求体与「Tab 同参实例化 useH10Disclosure → getSyncSnapshot → buildH10SyncPayloads」逐字节相同
 * ②只读本底稿 H10 条目、静默发出、不写底稿 ③口径不适用回空。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))

import { h10HeadlessProvider } from '../h10HeadlessDisclosure'
import { useH10Disclosure } from '../useH10Disclosure'
import { buildH10SyncPayloads } from '../h10DisclosureSyncPayload'
import { H10_MAIN_SUBTABLE, H10_TRIAL_SUBTABLE } from '../h10NoteSectionMap'
import type { ChecklistResponse } from '../useF1FormData'

const RESPONSES = [
  { item_id: 'H10-disclosure-listed', remark: JSON.stringify([
    { rowKey: 'fixed_asset_disposal', currentAmount: 5200, priorAmount: 3000, remark: '处置旧设备' },
    { rowKey: 'intangible_disposal', currentAmount: -800, priorAmount: 0 },
  ]), conclusion: null },
  { item_id: 'H10-disclosure-listed-trial', remark: JSON.stringify([
    { rowKey: 'fixed_asset_trial', currentIncome: 1000, currentCost: 600, priorIncome: 0, priorCost: 0 },
  ]), conclusion: null },
  { item_id: 'H10-disclosure-listed-note', remark: null, conclusion: '本期处置固定资产利得主要来自旧设备' },
  { item_id: 'H10-disclosure-soe', remark: JSON.stringify([
    { rowKey: 'fixed_asset_disposal', currentAmount: 5200, priorAmount: 3000, nonRecurringAmount: 5200 },
  ]), conclusion: null },
  { item_id: 'H10-1-adjudicated-amount', remark: null, conclusion: '4400' },
  { item_id: 'H1-listed-summary', remark: '[]', conclusion: null },
]
const OWN = new Map<string, ChecklistResponse>(
  RESPONSES.filter((r) => r.item_id.startsWith('H10')).map((r) => [r.item_id, r as ChecklistResponse]),
)
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-h10', wpCode: 'H10' }

async function tabPayloads(variant: 'listed' | 'soe', standards: string[]) {
  const scope = effectScope(true)
  const dis = scope.run(() => useH10Disclosure({
    variant, allResponses: ref(OWN), debouncedSave: () => {}, wpId: ref('wp-h10'), projectId: ref('p1'), isReadonly: ref(false),
  }))!
  await nextTick()
  dis.pullLatestAdjudicated()
  const out = buildH10SyncPayloads('wp-h10', variant, standards, dis.getSyncSnapshot())
  scope.stop()
  return out
}

describe('h10HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 13, push_kept: [] })
  })

  it('上市：载荷与 Tab 同参 builder 逐字节相同（主表 + 试运行明细），静默发出、不写底稿', async () => {
    const out = await h10HeadlessProvider({ ...CTX, variant: 'listed', applicableStandards: ['listed_standalone'] })
    expect(out).toEqual({ sections: [{ section: '五、78', rows: 13, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-h10/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    expect(JSON.stringify(sent)).toBe(JSON.stringify((await tabPayloads('listed', ['listed_standalone']))[0]))
    const main = sent.sub_table_data[H10_MAIN_SUBTABLE.listed] as Array<Record<string, unknown>>
    expect(main.find((r) => r.row_key === 'fixed_asset_disposal')?.current_amount).toBe(5200)
    expect(sent.sub_table_data[H10_TRIAL_SUBTABLE]).toBeDefined()
  })

  it('国企：载荷与 Tab 同参 builder 逐字节相同', async () => {
    const out = await h10HeadlessProvider({ ...CTX, variant: 'soe', applicableStandards: ['soe_standalone'] })
    expect(out.sections.map((s) => s.section)).toEqual(['八、75'])
    const sent = h.post.mock.calls[0][1]
    expect(JSON.stringify(sent)).toBe(JSON.stringify((await tabPayloads('soe', ['soe_standalone']))[0]))
    const main = sent.sub_table_data[H10_MAIN_SUBTABLE.soe] as Array<Record<string, unknown>>
    expect(main.find((r) => r.row_key === 'fixed_asset_disposal')?.current_amount).toBe(5200)
  })

  it('口径不适用：不发请求、回空', async () => {
    expect(await h10HeadlessProvider({ ...CTX, variant: 'listed', applicableStandards: ['soe_standalone'] }))
      .toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })
})
