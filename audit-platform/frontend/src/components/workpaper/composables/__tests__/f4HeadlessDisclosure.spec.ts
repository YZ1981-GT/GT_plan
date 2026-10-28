/**
 * F4 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①离屏载荷与「按 Tab 同样参数实例化 composable → 同一个 buildSyncPayload」逐字节相同（两版）②国企账龄段跟项目
 * 账龄配置（5 年段比 3 年段多两档）③只读 F4 条目、不写底稿（不 PUT、不发保存 / 正文联动事件）④适用准则 getter 与 Ref
 * 都生效（原先 Tab 传 getter、composable 只读 `.value` ⇒ 合并项目恒按单体口径）。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), apiGet: vi.fn(), apiPost: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet, post: h.apiPost, put: h.put } }))

import { f4HeadlessProvider } from '../f4HeadlessDisclosure'
import { useF4DisclosureListed } from '../useF4DisclosureListed'
import { useF4DisclosureSOE } from '../useF4DisclosureSOE'
import { F4_LISTED_SUBTABLE, F4_SOE_SUBTABLE } from '../f4NoteSectionMap'
import { clearAgingConfigCache, PRESET_SEGMENTS, primeAgingConfig } from '@/composables/useAgingConfig'

const adj = (rowKey: string, label: string, opening: number, closing: number) => ({
  rowKey, label, isFixed: true, openingUnadjusted: opening, openingAje: 0, openingRje: 0,
  closingUnadjusted: closing, closingAje: 0, closingRje: 0,
})
const RESPONSES = [
  { item_id: 'F4-1-adj-nature-rows', remark: JSON.stringify([adj('goods', '货款', 700, 900), adj('construction', '工程款', 100, 300)]) },
  { item_id: 'F4-1-adj-aging-rows', remark: JSON.stringify([adj('within1year', '1年以内（含1年）', 600, 800), adj('1to2year', '1至2年（含2年）', 200, 400)]) },
  { item_id: 'F4-disclosure-listed-aging-rows', remark: JSON.stringify([{ rowId: 'm1', sourceRowId: '', creditor: '甲公司', amount: 300, reason: '质量纠纷' }]) },
  { item_id: 'F4-disclosure-listed', remark: '上市披露说明' },
  { item_id: 'F4-disclosure-soe-important-rows', remark: JSON.stringify([{ rowId: 'i1', sourceRowId: '', creditor: '乙公司', amount: 200, reason: '未结算' }]) },
  { item_id: 'F4-disclosure-soe', remark: '国企披露说明' },
  { item_id: 'K1-unrelated', remark: '999' },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-f4', wpCode: 'F4' }
const ctxOf = (variant: 'listed' | 'soe', standards: string[]) => ({ ...CTX, variant, applicableStandards: standards })

/** Tab 路径：同一批 F4 响应、同样参数（适用准则传 getter）实例化 composable → 同一个 buildSyncPayload */
async function tabPayload(variant: 'listed' | 'soe', standards: string[]) {
  await primeAgingConfig('p1')
  const map = new Map(RESPONSES.filter((r) => r.item_id.startsWith('F4-'))
    .map((r) => [r.item_id, { item_id: r.item_id, conclusion: null, remark: r.remark }]))
  const options = {
    wpId: ref('wp-f4'), projectId: ref('p1'), allResponses: ref(map), isReadonly: ref(false),
    applicableStandards: () => standards,
  }
  const scope = effectScope(true)
  const api = scope.run(() => (variant === 'listed' ? useF4DisclosureListed(options) : useF4DisclosureSOE(options)))!
  await nextTick()
  const payload = api.buildSyncPayload()
  scope.stop()
  return payload
}

function agingPreset(name: 'THREE_YEAR' | 'FIVE_YEAR') {
  return { preset: name, effective_segments: PRESET_SEGMENTS[name], subject_overrides: {} }
}

describe('f4HeadlessProvider', () => {
  const events: string[] = []
  const onEvent = (e: Event) => events.push(e.type)

  beforeEach(() => {
    clearAgingConfigCache()
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 9 })
    h.apiGet.mockResolvedValue(agingPreset('THREE_YEAR'))
    events.length = 0
    for (const t of ['f4:save-items', 'disclosure:note-text-updated']) window.addEventListener(t, onEvent)
  })
  afterEach(() => {
    for (const t of ['f4:save-items', 'disclosure:note-text-updated']) window.removeEventListener(t, onEvent)
  })

  it.each(['listed', 'soe'] as const)('%s：载荷与 Tab 同一套代码逐字节相同，经同一端点静默发出、不写底稿', async (variant) => {
    const standards = [`${variant}_standalone`]
    const out = await f4HeadlessProvider(ctxOf(variant, standards))
    expect(out).toEqual({ sections: [{ section: variant === 'listed' ? '五、37' : '八、37', rows: 9, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-f4/checklist-responses', expect.anything())
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiPost).not.toHaveBeenCalled()
    expect(events).toEqual([])
    clearAgingConfigCache()
    expect(JSON.stringify(sent)).toBe(JSON.stringify(await tabPayload(variant, standards)))
  })

  it('载荷带真实数据：上市按性质取 F4-1 审定数、手工超 1 年行与披露正文都在', async () => {
    await f4HeadlessProvider(ctxOf('listed', ['listed_standalone']))
    const sent = h.post.mock.calls[0][1]
    const nature = sent.sub_table_data[F4_LISTED_SUBTABLE.nature] as Array<{ label: string; end_amount: number; prior_amount: number }>
    expect(nature.find((r) => r.label === '货款')).toMatchObject({ end_amount: 900, prior_amount: 700 })
    expect(nature.at(-1)).toMatchObject({ label: '合计', end_amount: 1200, prior_amount: 800 })
    expect(sent.sub_table_data[F4_LISTED_SUBTABLE.over1y][0]).toMatchObject({ label: '甲公司', end_amount: 300 })
    expect(sent.sub_table_data._note_texts[0].text).toBe('上市披露说明')
  })

  it('国企账龄段跟项目账龄配置：5 年段比 3 年段多两档', async () => {
    await f4HeadlessProvider(ctxOf('soe', ['soe_standalone']))
    const three = h.post.mock.calls[0][1].sub_table_data[F4_SOE_SUBTABLE.aging] as unknown[]
    clearAgingConfigCache()
    h.apiGet.mockResolvedValue(agingPreset('FIVE_YEAR'))
    await f4HeadlessProvider(ctxOf('soe', ['soe_standalone']))
    const five = h.post.mock.calls[1][1].sub_table_data[F4_SOE_SUBTABLE.aging] as unknown[]
    expect(three).toHaveLength(4 + 1)
    expect(five).toHaveLength(6 + 1)
  })

  it('适用准则 getter / Ref 都生效：合并项目按合并口径（Tab 传的是 getter）', async () => {
    expect((await tabPayload('listed', ['listed_consolidated'])).current_standard).toBe('listed_consolidated')
    expect((await tabPayload('soe', ['soe_consolidated'])).current_standard).toBe('soe_consolidated')
    const scope = effectScope(true)
    const viaRef = scope.run(() => useF4DisclosureListed({
      wpId: ref('w'), projectId: ref('p'), allResponses: ref(new Map()), applicableStandards: ref(['listed_consolidated']),
    }))!
    expect(viaRef.buildSyncPayload().current_standard).toBe('listed_consolidated')
    scope.stop()
    await f4HeadlessProvider(ctxOf('listed', ['listed_consolidated']))
    expect(h.post.mock.calls[0][1].current_standard).toBe('listed_consolidated')
    for (const tab of ['F4TabDisclosureListed.vue', 'F4TabDisclosureSOE.vue']) {
      const src = readFileSync(resolve(__dirname, '../../f4-accounts-payable', tab), 'utf-8')
      expect(src, tab).toMatch(/applicableStandards:\s*\(\)\s*=>\s*props\.applicableStandards/)
    }
  })
})
