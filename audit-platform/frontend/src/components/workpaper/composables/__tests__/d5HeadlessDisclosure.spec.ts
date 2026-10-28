/**
 * D5 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①离屏发出的载荷与「按 Tab 同样参数实例化外壳 crossSheet + composable → 同一个快照函数 → 同一个 builder」
 * 逐字节相同（夹具有真实数据：分类 / 减值 / 已质押都非零）②Tab 的同步函数与已质押 / 已背书两表的加载确实调用共用函数
 * （静态接线）③只读本底稿 D5- 条目、离屏不写底稿、不订阅窗口事件 ④两个口径分别写 五、6 / 八、6。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), apiGet: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet } }))

import { d5HeadlessProvider } from '../d5HeadlessDisclosure'
import { useD5CrossSheet } from '../useD5CrossSheet'
import { useD5Disclosure } from '../useD5Disclosure'
import { buildD5SyncPayload } from '../d5NoteSectionMap'
import {
  buildD5DisclosureSnapshot,
  defaultD5EndorsedRows,
  defaultD5PledgedRows,
  parseD5NoteRows,
  D5_ENDORSED_ITEM,
  D5_PLEDGED_ITEM,
  type D5EndorsedRow,
  type D5PledgedRow,
} from '../d5DisclosureSnapshot'
import type { ChecklistResponse } from '../useD5FormData'

const J = JSON.stringify
const RESPONSES = [
  { item_id: 'D5-2-rows', remark: J([
    { rowId: 'r1', category: '应收票据', priorAudited: 300, endAudited: 500 },
    { rowId: 'r2', category: '应收账款', priorAudited: 100, endAudited: 200 },
  ]), conclusion: null },
  { item_id: 'D5-4-rows', remark: J([{ rowId: 'f1', fairValue: 680 }]), conclusion: null },
  { item_id: 'D5-4-prior-fv-total', remark: '390', conclusion: null },
  { item_id: 'D5-note-listed-impairment-rows', remark: J([
    { rowId: 'i1', itemName: '应收票据', priorEnd: 10, provision: 5, reversal: 2, writeOff: 1, endBalance: 12 },
  ]), conclusion: null },
  { item_id: D5_PLEDGED_ITEM, remark: J([
    { key: 'bank', label: '银行承兑票据', pledgedAmount: 80 },
    { key: 'commercial', label: '商业承兑票据', pledgedAmount: 0 },
  ]), conclusion: null },
  { item_id: 'D5-note-listed-text-1', remark: '分类说明', conclusion: null },
  { item_id: 'D5-note-listed-text-3', remark: '质押说明', conclusion: null },
  { item_id: 'D5-note-soe-text-1', remark: '国企说明', conclusion: null },
  { item_id: 'K1-unrelated', remark: '999', conclusion: null },
]
const CTX = { projectId: 'p1', year: 2025, variant: 'listed' as const, wpId: 'wp-d5', wpCode: 'D5', applicableStandards: ['listed_consolidated'] }

/** Tab 路径：外壳 `useD5CrossSheet` + Tab `useD5Disclosure`（同一批 D5- 回复）→ Tab 同一快照函数 → 同一 builder（准则照 Tab 传 null） */
function tabPayload(variant: 'listed' | 'soe') {
  const map = new Map<string, ChecklistResponse>(
    RESPONSES.filter((r) => r.item_id.startsWith('D5-')).map((r) => [r.item_id, r as ChecklistResponse]),
  )
  const scope = effectScope(true)
  const snapshot = scope.run(() => {
    const allResponses = ref(map)
    const d5 = useD5Disclosure({
      allResponses, wpId: ref('wp-d5'), projectId: ref('p1'), debouncedSave: () => {}, isReadonly: ref(false),
      crossSheet: useD5CrossSheet({ allResponses }),
    })
    // Tab：两表默认行，持久化为非空数组时替换（D5TabDisclosure 的两个 watcher）
    const pledgedRows = parseD5NoteRows<D5PledgedRow>(map.get(D5_PLEDGED_ITEM)?.remark) ?? defaultD5PledgedRows()
    const endorsedRows = parseD5NoteRows<D5EndorsedRow>(map.get(D5_ENDORSED_ITEM)?.remark) ?? defaultD5EndorsedRows()
    return buildD5DisclosureSnapshot(variant, {
      listedSections: d5.listedSections.value, soeSections: d5.soeSections.value,
      impairmentRows: d5.impairmentRows.value, pledgedRows, endorsedRows, noteTexts: d5.noteTexts.value,
    })
  })!
  scope.stop()
  return buildD5SyncPayload(variant, 'wp-d5', null, snapshot)
}

describe('d5HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 14, push_kept: [{ table: '应收款项融资' }] })
  })

  it('上市：载荷与 Tab 路径逐字节相同、数据非空，经同一端点静默发出、不写底稿', async () => {
    const addSpy = vi.spyOn(window, 'addEventListener')
    const out = await d5HeadlessProvider(CTX)
    expect(out).toEqual({ sections: [{ section: '五、6', rows: 14, kept: 1 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-d5/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(addSpy.mock.calls.some(([type]) => String(type) === 'note:section-updated')).toBe(false)
    addSpy.mockRestore()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    expect(J(sent)).toBe(J(tabPayload('listed')))
    // 夹具确有数据（等价不是两个空载荷相等）
    const main = sent.sub_table_data['应收款项融资'] as Array<{ label: string; end_amount: number; prior_amount: number }>
    expect(main.map((r) => [r.label, r.end_amount, r.prior_amount])).toEqual([
      ['应收票据', 500, 300], ['应收账款', 200, 100], ['小  计', 700, 400],
      ['减：其他综合收益-公允价值变动', 20, 10], ['期末公允价值', 680, 390],
    ])
    expect(sent.sub_table_data['本期计提、收回或转回的减值准备情况'].at(-1)).toMatchObject({ label: '期末余额', amount: 12 })
    expect(sent.sub_table_data['期末本公司已质押的应收票据'].at(-1)).toMatchObject({ pledged_amount: 80, is_total: true })
    expect(sent.sub_table_data._note_texts.map((t: any) => t.section)).toEqual(['note-listed-1', 'note-listed-3'])
    expect(sent.current_standard).toBe('listed_standalone')
  })

  it('国企：写 八、6，载荷与 Tab 路径逐字节相同', async () => {
    const out = await d5HeadlessProvider({ ...CTX, variant: 'soe' })
    expect(out.sections.map((s) => s.section)).toEqual(['八、6'])
    const sent = h.post.mock.calls[0][1]
    expect(J(sent)).toBe(J(tabPayload('soe')))
    expect(sent.sub_table_data['应收款项融资'].at(-1)).toMatchObject({ label: '合  计', end_amount: 700, prior_amount: 400 })
    expect(sent.sub_table_data._note_texts).toEqual([{ section: 'note-soe-1', title: '国企版分类说明', text: '国企说明' }])
  })

  it('Tab 接线：同步函数调共用快照函数，两表加载走共用默认行与解析', () => {
    const src = readFileSync(resolve(__dirname, '../../d5/D5TabDisclosure.vue'), 'utf-8')
    const sync = src.slice(src.indexOf('async function syncToDisclosureNotes'))
    expect(sync).toMatch(/buildD5DisclosureSnapshot\(variant, \{/)
    expect(sync).toContain("buildD5SyncPayload(variant, props.wpId || '', null, snapshot)")
    expect(src).toContain('ref<PledgedRow[]>(defaultD5PledgedRows())')
    expect(src).toContain('ref<EndorsedRow[]>(defaultD5EndorsedRows())')
    expect(src).toContain('parseD5NoteRows<PledgedRow>(val)')
    expect(src).toContain('parseD5NoteRows<EndorsedRow>(val)')
    // 错误提示函数确实被导入（原先误写在块注释里）
    expect(src).toMatch(/^import \{ handleDisclosureSyncError \} from '\.\.\/composables\/disclosureSyncError'$/m)
  })
})
