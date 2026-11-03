/**
 * D7 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①离屏发出的载荷与「外壳 crossSheet（账龄配置段）+ Tab composable → 同一快照函数 → 同一 builder」逐字节相同，
 * 夹具有真实数据（性质分类 / 扣减行 / 超 1 年从 D7-5 带入 / 重大变动 / 说明都非空）②Tab 同步函数调共用快照函数
 * ③读 D7- / D7A- 条目、离屏不写底稿、不订阅事件总线 ④两口径分别写 五、39 / 八、39 ⑤账龄配置取不到时照常同步。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), apiGet: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet } }))

import { d7HeadlessProvider } from '../d7HeadlessDisclosure'
import { useD7CrossSheet } from '../useD7CrossSheet'
import { useD7Disclosure } from '../useD7Disclosure'
import { buildD7SyncPayload } from '../d7NoteSectionMap'
import { buildD7DisclosureSnapshot } from '../d7DisclosureSnapshot'
import { clearAgingConfigCache, PRESET_SEGMENTS } from '@/composables/useAgingConfig'
import { eventBus } from '@/utils/eventBus'
import type { ChecklistResponse } from '../useD7FormData'

const J = JSON.stringify
const RESPONSES = [
  { item_id: 'D7-2-rows', remark: J([
    { rowId: 'r1', natureType: '预收货款', endAudited: 300, priorAudited: 200, agingAudited: { within1: 300 } },
    { rowId: 'r2', natureType: '预收工程款', endAudited: 150, priorAudited: 50, agingAudited: { y1to2: 150 } },
  ]), conclusion: null },
  { item_id: 'D7-1-adj-nature-non-current-deduction-currentAudited', remark: '50', conclusion: null },
  { item_id: 'D7-1-adj-nature-non-current-deduction-priorAudited', remark: '20', conclusion: null },
  { item_id: 'D7-5-rows', remark: J([{ customerName: '甲公司', endBalance: 120, reason: '项目未完工' }]), conclusion: null },
  { item_id: 'D7-note-listed-section3-rows', remark: J([{ rowId: 'c1', label: '合同变更', prior: 10, current: 90 }]), conclusion: null },
  { item_id: 'D7-note-soe-section2-rows', remark: J([{ rowId: 's1', label: '国企变动', prior: 0, current: 60 }]), conclusion: null },
  { item_id: 'D7-note-listed-text-1', remark: '性质说明', conclusion: null },
  { item_id: 'D7-note-listed-qual-2', remark: '定性说明', conclusion: null },
  { item_id: 'D7-note-soe-text-1', remark: '国企性质说明', conclusion: null },
  { item_id: 'D7A-proc-1', remark: '程序', conclusion: null },
  { item_id: 'K1-unrelated', remark: '999', conclusion: null },
]
const CTX = { projectId: 'p1', year: 2025, variant: 'listed' as const, wpId: 'wp-d7', wpCode: 'D7', applicableStandards: ['listed_standalone'] }

/** Tab 路径：外壳 `useD7CrossSheet`（已加载的账龄配置段）+ Tab `useD7Disclosure` → 同一快照函数 → 同一 builder */
function tabPayload(variant: 'listed' | 'soe') {
  const map = new Map<string, ChecklistResponse>(
    RESPONSES.filter((r) => r.item_id.startsWith('D7-') || r.item_id.startsWith('D7A-'))
      .map((r) => [r.item_id, r as ChecklistResponse]),
  )
  const scope = effectScope(true)
  const snapshot = scope.run(() => {
    const allResponses = ref(map)
    const d7 = useD7Disclosure({
      allResponses,
      crossSheet: useD7CrossSheet({ allResponses, segments: ref(PRESET_SEGMENTS.THREE_YEAR) }),
      wpId: ref('wp-d7'), projectId: ref('p1'), saveImmediate: async () => {}, debouncedSave: () => {},
    })
    return buildD7DisclosureSnapshot(variant, {
      listedSections: d7.listedSections.value, soeSections: d7.soeSections.value, noteTexts: d7.noteTexts.value,
    })
  })!
  scope.stop()
  return buildD7SyncPayload(variant, 'wp-d7', null, snapshot)
}

describe('d7HeadlessProvider', () => {
  beforeEach(() => {
    clearAgingConfigCache()
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 9, push_kept: [] })
    h.apiGet.mockResolvedValue({ preset: 'THREE_YEAR', effective_segments: PRESET_SEGMENTS.THREE_YEAR, subject_overrides: {} })
  })

  it('上市：载荷与 Tab 路径逐字节相同、数据非空，经同一端点静默发出、不写底稿、不订阅事件', async () => {
    const before = eventBus.all.get('disclosure:note-text-updated')?.length ?? 0
    const out = await d7HeadlessProvider(CTX)
    expect(out).toEqual({ sections: [{ section: '五、39', rows: 9, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-d7/checklist-responses', expect.anything())
    expect(h.apiGet).toHaveBeenCalledWith('/api/projects/p1/aging/config', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(eventBus.all.get('disclosure:note-text-updated')?.length ?? 0).toBe(before)
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    expect(J(sent)).toBe(J(tabPayload('listed')))
    const main = sent.sub_table_data['合同负债'] as Array<{ label: string; end_amount: number; prior_amount: number }>
    expect(main.map((r) => [r.label, r.end_amount, r.prior_amount])).toEqual([
      ['预收货款', 300, 200], ['开发项目预收款', 0, 0], ['预收工程款', 150, 50], ['其他', 0, 0],
      ['减：计入其他非流动负债的合同负债', 50, 20], ['合  计', 400, 230],
    ])
    expect(sent.sub_table_data['账龄超过1年的重要合同负债'][0]).toEqual({ label: '甲公司', end_amount: 120, reason: '项目未完工' })
    expect(sent.sub_table_data['本期合同负债账面价值的重大变动'][0]).toMatchObject({ label: '合同变更', change_amount: 80 })
    expect(sent.sub_table_data._note_texts.map((t: any) => t.section)).toEqual(['D7-note-listed-text-1', 'D7-note-listed-qual-2'])
  })

  it('国企：写 八、39，载荷与 Tab 路径逐字节相同', async () => {
    const out = await d7HeadlessProvider({ ...CTX, variant: 'soe' })
    expect(out.sections.map((s) => s.section)).toEqual(['八、39'])
    const sent = h.post.mock.calls[0][1]
    expect(J(sent)).toBe(J(tabPayload('soe')))
    expect(sent.sub_table_data['合同负债'].at(-1)).toMatchObject({ label: '合  计', end_amount: 450, prior_amount: 250 })
    expect(sent.sub_table_data._removed_table_keys).toEqual(['合同负债（表2）'])
  })

  it('账龄配置取不到：照常同步（披露表不依赖账龄段），载荷不变', async () => {
    h.apiGet.mockRejectedValue(new Error('offline'))
    await d7HeadlessProvider(CTX)
    expect(J(h.post.mock.calls[0][1])).toBe(J(tabPayload('listed')))
  })

  it('Tab 接线：同步函数调共用快照函数，组件内不再自拼快照', () => {
    const src = readFileSync(resolve(__dirname, '../../d7/D7TabDisclosure.vue'), 'utf-8')
    const sync = src.slice(src.indexOf('async function syncToDisclosureNotes'))
    expect(sync).toMatch(/buildD7DisclosureSnapshot\(variant, \{/)
    expect(sync).toContain("buildD7SyncPayload(variant, props.wpId || '', null, snapshot)")
    expect(src).not.toMatch(/function toSnapRow\b/)
  })
})
