/**
 * D3 披露表离屏同步 = 底稿两版披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①离屏发出的载荷与「外壳 crossSheet（项目账龄配置段）+ 本口径 Tab composable → 同一快照函数 → 同一 builder」
 * 逐字节相同，夹具有真实数据 ②项目账龄配置真的生效（5 年段时 3-4 年账龄进「超 1 年」与国企 1 年以上桶，3 年段时不进）
 * ③配置取不到时与组件内加载失败同一兜底（D3 默认 3 年段）④两个 Tab 都调共用快照函数 ⑤只读 D3- 条目、不写底稿、不订阅窗口事件。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), apiGet: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet } }))

import { d3HeadlessProvider } from '../d3HeadlessDisclosure'
import { useD3CrossSheet } from '../useD3CrossSheet'
import { useD3DisclosureListed } from '../useD3DisclosureListed'
import { useD3DisclosureSoe } from '../useD3DisclosureSoe'
import { buildD3SyncPayload } from '../d3NoteSectionMap'
import { buildD3ListedSnapshot, buildD3SoeSnapshot } from '../d3DisclosureSnapshot'
import { clearAgingConfigCache, PRESET_SEGMENTS, type AgingSegment } from '@/composables/useAgingConfig'
import type { ChecklistResponse } from '../useD3FormData'

const J = JSON.stringify
const RESPONSES = [
  { item_id: 'D3-det-rows', remark: J([
    { rowId: 'r1', customerName: '甲公司', nature: '货款', endAudited: 500, priorAudited: 300,
      agingAudited: { within1: 400, y1to2: 100 }, agingPrior: { within1: 300 } },
    { rowId: 'r2', customerName: '乙公司', nature: '工程款', endAudited: 80, priorAudited: 0, agingAudited: { y3to4: 80 } },
  ]), conclusion: null },
  { item_id: 'D3-note-listed-section2-rows', remark: J([{ rowId: 'x1', label: '丙公司', endAmount: 50, priorAmount: 0, reason: '未结算' }]), conclusion: null },
  { item_id: 'D3-note-listed-section3-rows', remark: J([{ rowId: 'c1', label: '合同变更', endAmount: 90, priorAmount: 10, reason: '追加' }]), conclusion: null },
  { item_id: 'D3-note-listed-note-1', remark: '性质说明', conclusion: null },
  { item_id: 'D3-note-soe-section2-rows', remark: J([{ rowId: 's1', label: '丁公司', endAmount: 30, priorAmount: 0, reason: '诉讼中' }]), conclusion: null },
  { item_id: 'K1-unrelated', remark: '999', conclusion: null },
]
const CTX = { projectId: 'p1', year: 2025, variant: 'listed' as const, wpId: 'wp-d3', wpCode: 'D3', applicableStandards: ['listed_consolidated', 'listed', 'consolidated'] }
const config = (preset: 'THREE_YEAR' | 'FIVE_YEAR') => ({ preset, effective_segments: PRESET_SEGMENTS[preset], subject_overrides: {} })

/** Tab 路径：外壳 `useD3CrossSheet`（已加载的账龄段）+ 本口径 Tab composable → 同一快照函数 → 同一 builder */
function tabPayload(variant: 'listed' | 'soe', segments: AgingSegment[], standards: string[] = [...CTX.applicableStandards]) {
  const map = new Map<string, ChecklistResponse>(
    RESPONSES.filter((r) => r.item_id.startsWith('D3-')).map((r) => [r.item_id, r as ChecklistResponse]),
  )
  const scope = effectScope(true)
  const payload = scope.run(() => {
    const allResponses = ref(map)
    const options = {
      allResponses, wpId: ref('wp-d3'), projectId: ref('p1'), saveImmediate: async () => {}, debouncedSave: () => {},
      crossSheet: useD3CrossSheet({ allResponses, segments: ref(segments) }), isReadonly: ref(false), applicableStandards: ref(standards),
    }
    if (variant === 'soe') {
      const s = useD3DisclosureSoe(options)
      return buildD3SyncPayload('soe', 'wp-d3', standards, buildD3SoeSnapshot({
        section1Rows: s.section1Rows.value, section1Subtotal: s.section1Subtotal.value,
        section2Rows: s.section2Rows.value, section2Subtotal: s.section2Subtotal.value,
      }))
    }
    const l = useD3DisclosureListed(options)
    return buildD3SyncPayload('listed', 'wp-d3', standards, buildD3ListedSnapshot({
      section1Rows: l.section1Rows.value, section1Subtotal: l.section1Subtotal.value,
      section2Rows: l.section2Rows.value, section2Subtotal: l.section2Subtotal.value, section3Rows: l.section3Rows.value,
      notes: { nature: l.note1.value, longTerm: l.note2.value, change: l.note3.value },
    }))
  })!
  scope.stop()
  return payload
}

describe('d3HeadlessProvider', () => {
  beforeEach(() => {
    clearAgingConfigCache()
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 8, push_kept: [] })
    h.apiGet.mockResolvedValue(config('THREE_YEAR'))
  })

  it('上市（3 年段）：载荷与 Tab 路径逐字节相同、数据非空，经同一端点静默发出、不写底稿、不订阅窗口事件', async () => {
    const addSpy = vi.spyOn(window, 'addEventListener')
    const out = await d3HeadlessProvider(CTX)
    expect(addSpy.mock.calls.some(([type]) => String(type) === 'note:section-updated')).toBe(false)
    addSpy.mockRestore()
    expect(out).toEqual({ sections: [{ section: '五、38', rows: 8, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-d3/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    expect(J(sent)).toBe(J(tabPayload('listed', PRESET_SEGMENTS.THREE_YEAR)))
    const sub = sent.sub_table_data
    expect(sub['预收款项'].map((r: any) => [r.label, r.end_amount, r.prior_amount])).toEqual([
      ['货款', 500, 300], ['工程款', 80, 0], ['合 计', 580, 300],
    ])
    // 3 年段：乙公司的 3-4 年账龄不在配置段里，不进「超 1 年」
    expect(sub['账龄超过1年的重要预收款项'].map((r: any) => [r.label, r.end_amount, r.reason])).toEqual([
      ['甲公司', 500, '1-2年'], ['丙公司', 50, '未结算'], ['合 计', 550, ''],
    ])
    expect(sub['本期预收账款账面价值的重大变动'][0]).toMatchObject({ label: '合同变更', change_amount: 80 })
    expect(sub._note_texts).toEqual([{ section: 'note-nature', title: '按性质分类说明', text: '性质说明' }])
    expect(sent.current_standard).toBe('listed_consolidated')
  })

  it('国企（项目配置 5 年段）：配置生效（3-4 年进 1 年以上桶），载荷与 Tab 路径逐字节相同', async () => {
    h.apiGet.mockResolvedValue(config('FIVE_YEAR'))
    const out = await d3HeadlessProvider({ ...CTX, variant: 'soe', applicableStandards: ['soe_standalone'] })
    expect(out.sections.map((s) => s.section)).toEqual(['八、38'])
    const sent = h.post.mock.calls[0][1]
    expect(J(sent)).toBe(J(tabPayload('soe', PRESET_SEGMENTS.FIVE_YEAR, ['soe_standalone'])))
    expect(sent.sub_table_data['预收款项'].map((r: any) => [r.end_amount, r.prior_amount])).toEqual([[400, 300], [180, 0], [580, 300]])
    expect(sent.sub_table_data['账龄超过1年的重要预收账款'].map((r: any) => r.label)).toEqual(['甲公司', '乙公司', '丁公司', '合计'])
    expect(sent.sub_table_data._removed_table_keys).toEqual(['账龄超过1年的重要预收款项'])
  })

  it('账龄配置取不到：与组件内加载失败同一兜底（D3 默认 3 年段）', async () => {
    h.apiGet.mockRejectedValue(new Error('offline'))
    await d3HeadlessProvider(CTX)
    expect(J(h.post.mock.calls[0][1])).toBe(J(tabPayload('listed', PRESET_SEGMENTS.THREE_YEAR)))
  })

  it('两个 Tab 接线：同步函数调共用快照函数', () => {
    for (const [file, fn] of [['D3TabDisclosureListed.vue', 'buildD3ListedSnapshot'], ['D3TabDisclosureSoe.vue', 'buildD3SoeSnapshot']]) {
      const src = readFileSync(resolve(__dirname, '../../d3', file), 'utf-8')
      const sync = src.slice(src.indexOf('async function syncToDisclosureNotes'))
      expect(sync, file).toContain(`const snapshot = ${fn}({`)
      expect(sync, file).toMatch(/buildD3SyncPayload\('(?:listed|soe)', props\.wpId \|\| '', applicableStandardsRef\.value, snapshot\)/)
    }
  })
})
