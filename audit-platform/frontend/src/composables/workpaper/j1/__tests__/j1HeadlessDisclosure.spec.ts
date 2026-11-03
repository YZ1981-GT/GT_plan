/**
 * J1 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①两版离屏载荷与「Tab 同样参数实例化 useJ1DisclosureSections → hydrate（Tab onMounted）→ Tab 同一个快照函数 →
 * buildJ1SyncPayload」逐字节相同 ②快照函数就是 Tab 原先内联的四份状态 ③Tab 源码用同一份默认骨架与快照函数
 * ④只读 J1 条目、不写底稿；「其中：」子项上卷父行（hydrate 时的 syncParentSums）在离屏同样生效。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))

import { j1HeadlessProvider } from '../j1HeadlessDisclosure'
import { useJ1DisclosureSections } from '../useJ1DisclosureSections'
import { J1_DISCLOSURE_DEFAULTS } from '../j1DisclosureDefaults'
import {
  buildJ1SyncPayload,
  j1DisclosureSnapshotOf,
  j1NoteKeys,
  J1_SUB_TABLE_KEYS,
} from '@/components/workpaper/composables/j1NoteSectionMap'

const row = (id: string, label: string, category: string, begin: number, inc: number, dec: number, indent = 0) =>
  ({ id, label, category, indent, beginBalance: begin, increase: inc, decrease: dec })
const RESPONSES = [
  {
    item_id: 'J1-disc-listed-summary', conclusion: null,
    remark: JSON.stringify([row('s-1', '短期薪酬', 'summary', 100, 900, 850), row('s-3', '辞退福利', 'summary', 0, 30, 10)]),
  },
  {
    item_id: 'J1-disc-listed-short-term', conclusion: null,
    remark: JSON.stringify([
      row('st-3', '社会保险费', 'short_term', 0, 0, 0),
      row('st-4', '其中：1. 医疗保险费', 'short_term', 10, 60, 50, 1),
      row('st-5', '2. 工伤保险费', 'short_term', 2, 8, 6, 1),
    ]),
  },
  { item_id: 'J1-disc-listed-notes', conclusion: null, remark: JSON.stringify({ shortTerm: '非货币性福利说明', severance: '' }) },
  { item_id: 'J1-disc-soe-notes', conclusion: null, remark: JSON.stringify({ soeNonMonetary: '国企非货币性福利说明' }) },
  { item_id: 'K1-unrelated', conclusion: null, remark: '999' },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-j1', wpCode: 'J1' }
const SECTION = { listed: '五、40', soe: '八、40' } as const

/** Tab 路径：同样参数实例化 useJ1DisclosureSections → hydrate → Tab 同步函数的快照 + builder */
async function tabBody(variant: 'listed' | 'soe') {
  const map = new Map(RESPONSES.filter((r) => r.item_id.startsWith('J1-')).map((r) => [r.item_id, r]))
  const save = vi.fn(async () => {})
  const scope = effectScope(true)
  const sections = scope.run(() => useJ1DisclosureSections({
    variant,
    defaults: J1_DISCLOSURE_DEFAULTS[variant],
    allResponses: ref(map),
    saveImmediate: save,
    isReadonly: ref(false),
    noteKeys: j1NoteKeys(variant),
  }))!
  sections.hydrate()
  await nextTick()
  const snapshot = j1DisclosureSnapshotOf(sections)
  // 快照就是 Tab 原先内联的四份状态
  expect(snapshot).toEqual({
    summary: sections.summaryData.value,
    shortTerm: sections.shortTermData.value,
    postEmployment: sections.postEmploymentData.value,
    notes: sections.notes.value,
  })
  const { body } = buildJ1SyncPayload({ variant, wpId: 'wp-j1', year: 2025, snapshot })
  scope.stop()
  return body
}

describe('j1HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 28 })
  })

  it.each(['listed', 'soe'] as const)('%s：载荷与 Tab 同一套代码逐字节相同，静默发出、不写底稿', async (variant) => {
    const out = await j1HeadlessProvider({ ...CTX, variant, applicableStandards: [`${variant}_standalone`] })
    expect(out).toEqual({ sections: [{ section: SECTION[variant], rows: 28, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-j1/checklist-responses', expect.anything())
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    expect(h.put).not.toHaveBeenCalled()
    expect(JSON.stringify(sent)).toBe(JSON.stringify(await tabBody(variant)))
  })

  it('载荷带真实数据：父行按「其中：」子项上卷、合计行由载荷层补、年度与说明都在', async () => {
    await j1HeadlessProvider({ ...CTX, variant: 'listed', applicableStandards: ['listed_standalone'] })
    const sent = h.post.mock.calls[0][1]
    expect(sent.year).toBe(2025)
    const summary = sent.sub_table_data[J1_SUB_TABLE_KEYS.listed.summary] as Array<{ label: string; values: number[] }>
    expect(summary.find((r) => r.label === '短期薪酬')?.values).toEqual([100, 900, 850, 150])
    expect(summary.at(-1)).toMatchObject({ label: '合计', values: [100, 930, 860, 170], is_total: true })
    const shortTerm = sent.sub_table_data[J1_SUB_TABLE_KEYS.listed.shortTerm] as Array<{ label: string; values: number[] }>
    expect(shortTerm.find((r) => r.label === '社会保险费')?.values).toEqual([12, 68, 56, 24])
    expect(sent.sub_table_data._note_texts).toEqual([{ section: 'shortTerm', title: '短期薪酬说明', text: '非货币性福利说明' }])
  })

  it('两版 Tab 用同一份默认骨架与同一个快照函数', () => {
    for (const [tab, variant] of [['J1TabDisclosureListed.vue', 'listed'], ['J1TabDisclosureSoe.vue', 'soe']] as const) {
      const src = readFileSync(resolve(__dirname, '../../../../components/workpaper/j1/core', tab), 'utf-8')
      expect(src, tab).toContain(`defaults: J1_DISCLOSURE_DEFAULTS.${variant},`)
      expect(src, tab).toMatch(/snapshot: j1DisclosureSnapshotOf\(\{ summaryData, shortTermData, postEmploymentData, notes \}\)/)
      expect(src, tab).not.toMatch(/const DEFAULT_(SUMMARY|SHORT_TERM|POST)\b/)
      expect(src, tab).toMatch(/onMounted\(\(\) => \{\s*hydrate\(\)\s*\}\)|onMounted\(hydrate\)/)
    }
  })
})
