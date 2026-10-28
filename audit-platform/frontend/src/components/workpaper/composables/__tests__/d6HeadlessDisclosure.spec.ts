/**
 * D6 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①离屏发出的载荷与「外壳 crossSheet + Tab composable → 同一快照函数 → 同一 builder」逐字节相同，夹具有真实数据
 * （重大变动 / 上年年末计提情况 / 上年年末单项 / 逐组组合 / 说明都非空）②Tab 同步函数与简化式主表行调共用函数
 * ③读 D6- / D6A- 条目、离屏不写底稿、不订阅事件总线 ④两口径分别写 五、10 / 八、11。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), apiGet: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet } }))

import { d6HeadlessProvider } from '../d6HeadlessDisclosure'
import { useD6CrossSheet } from '../useD6CrossSheet'
import { useD6Disclosure } from '../useD6Disclosure'
import { buildD6SyncPayload } from '../d6NoteSectionMap'
import { buildD6DisclosureSnapshot } from '../d6DisclosureSnapshot'
import { eventBus } from '@/utils/eventBus'
import type { ChecklistResponse } from '../useD6FormData'

const J = JSON.stringify
const RESPONSES = [
  { item_id: 'D6-2-rows', remark: J([{ rowId: 'a1', contractType: '工程施工', priorAudited: 100, endAudited: 200 }]), conclusion: null },
  { item_id: 'D6-note-listed-major-change', remark: J([{ rowId: 'm1', label: '工程结算', amount: 50, reason: '结算' }]), conclusion: null },
  { item_id: 'D6-note-listed-s2-prior-rows', remark: J([
    { rowId: 'p1', label: '按单项计提', balance: 30, ratio: 10, provision: 3, lossRate: 10 },
  ]), conclusion: null },
  { item_id: 'D6-note-listed-s3-prior-rows', remark: J([
    { rowId: 'q1', label: '乙公司', balance: 20, provision: 2, lossRate: 10, reason: '诉讼' },
  ]), conclusion: null },
  { item_id: 'D6-note-listed-section4-groups', remark: J([{ groupName: '质量保证金', rows: [
    { rowId: 'g1', label: '1年以内', balance: 80, provision: 4, lossRate: 0.05, priorBalance: 60, priorProvision: 3, priorLossRate: 5 },
  ] }]), conclusion: null },
  { item_id: 'D6-note-listed-text-1', remark: '分类说明', conclusion: null },
  { item_id: 'D6-note-soe-text-2', remark: '国企减值说明', conclusion: null },
  { item_id: 'D6A-proc-1', remark: '程序', conclusion: null },
  { item_id: 'K1-unrelated', remark: '999', conclusion: null },
]
const CTX = { projectId: 'p1', year: 2025, variant: 'listed' as const, wpId: 'wp-d6', wpCode: 'D6', applicableStandards: ['listed_standalone'] }

/** Tab 路径：外壳 `useD6CrossSheet` + Tab `useD6Disclosure`（同一批 D6- / D6A- 回复）→ 同一快照函数 → 同一 builder */
function tabPayload(variant: 'listed' | 'soe') {
  const map = new Map<string, ChecklistResponse>(
    RESPONSES.filter((r) => r.item_id.startsWith('D6-') || r.item_id.startsWith('D6A-'))
      .map((r) => [r.item_id, r as ChecklistResponse]),
  )
  const scope = effectScope(true)
  const snapshot = scope.run(() => {
    const allResponses = ref(map)
    const d6 = useD6Disclosure({
      allResponses, crossSheet: useD6CrossSheet({ allResponses }),
      wpId: ref('wp-d6'), projectId: ref('p1'), saveImmediate: async () => {}, debouncedSave: () => {},
    })
    return buildD6DisclosureSnapshot(variant, {
      listedSections: d6.listedSections.value, soeSections: d6.soeSections.value,
      majorChangeRows: d6.majorChangeRows.value, mainFormat: d6.mainFormat.value,
      impairmentPriorRows: d6.impairmentPriorRows.value, singlePriorRows: d6.singlePriorRows.value,
      groupedDetails: d6.groupedDetails.value, noteTexts: d6.noteTexts.value,
    })
  })!
  scope.stop()
  return buildD6SyncPayload(variant, 'wp-d6', null, snapshot)
}

describe('d6HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 12, push_kept: [{ table: '合同资产' }, { table: '合同资产' }] })
  })

  it('上市：载荷与 Tab 路径逐字节相同、数据非空，经同一端点静默发出、不写底稿、不订阅事件', async () => {
    const before = eventBus.all.get('note:section-updated' as any)?.length ?? 0
    const out = await d6HeadlessProvider(CTX)
    expect(out).toEqual({ sections: [{ section: '五、10', rows: 12, kept: 2 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-d6/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(eventBus.all.get('note:section-updated' as any)?.length ?? 0).toBe(before)
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    expect(J(sent)).toBe(J(tabPayload('listed')))
    const sub = sent.sub_table_data
    expect(sub['本期合同资产账面价值的重大变动'][0]).toEqual({ label: '工程结算', change_amount: 50, reason: '结算' })
    expect(sub['合同资产减值准备计提情况（续：上年年末余额）'][0]).toMatchObject({
      label: '按单项计提', balance_amount: 30, balance_ratio: 10, provision_amount: 3, provision_loss_rate: 10,
    })
    expect(sub['按单项计提减值准备（续：上年年末余额）'][0]).toMatchObject({ label: '乙公司', balance: 20, reason: '诉讼' })
    expect(sub['组合计提项目：质量保证金'][0]).toMatchObject({
      label: '1年以内', end_balance: 80, end_loss_rate: 5, prior_balance: 60, prior_provision: 3,
    })
    expect(sub._note_texts).toEqual([{ section: 'D6-note-listed-text-1', title: '合同资产分类说明', text: '分类说明' }])
  })

  it('国企：写 八、11，载荷与 Tab 路径逐字节相同', async () => {
    const out = await d6HeadlessProvider({ ...CTX, variant: 'soe' })
    expect(out.sections.map((s) => s.section)).toEqual(['八、11'])
    const sent = h.post.mock.calls[0][1]
    expect(J(sent)).toBe(J(tabPayload('soe')))
    expect(sent.sub_table_data['本期合同资产账面价值的重大变动'].at(-1)).toMatchObject({ change_amount: 50, is_total: true })
    expect(sent.sub_table_data._note_texts).toEqual([{ section: 'D6-note-soe-text-2', title: '减值准备变动说明', text: '国企减值说明' }])
  })

  it('Tab 接线：同步函数与简化式主表行调共用函数，组件内不再自拼快照', () => {
    const src = readFileSync(resolve(__dirname, '../../d6/D6TabDisclosure.vue'), 'utf-8')
    const sync = src.slice(src.indexOf('async function syncToDisclosureNotes'))
    expect(sync).toMatch(/buildD6DisclosureSnapshot\(variant, \{/)
    expect(sync).toContain("buildD6SyncPayload(variant, props.wpId || '', null, snapshot)")
    expect(src).toContain("findD6Section(listedSections.value, 'listed-1')")
    expect(src).not.toMatch(/function findSection\b/)
  })
})
