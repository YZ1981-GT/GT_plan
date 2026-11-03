/**
 * G2 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①国企 / 上市离屏载荷与「组件里挂载同一个 composable（onMounted 首次初始化）→ `getSyncSnapshot` → 同一个 builder」
 * 逐字节相同 ②只读 G2- 条目、离屏不写底稿 ③口径不适用回空 ④与 G3、K1 共用的 五、8 / 八、9：G2 / G3 推的子表名与
 * `_removed_table_keys` 都不碰 K1 的子表（R1.5）⑤Tab 仍调同一组函数（静态接线）。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), apiPut: vi.fn(), apiPost: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: h.apiPost, put: h.apiPut } }))

import { g2HeadlessProvider } from '../g2HeadlessDisclosure'
import { useG2DisclosureSoe } from '../useG2DisclosureSoe'
import { useG2DisclosureListed } from '../useG2DisclosureListed'
import { buildG2ListedSyncPayloads, buildG2SoeSyncPayloads } from '../g2DisclosureSyncPayload'
import { buildG3ListedSyncPayloads, buildG3SoeSyncPayloads } from '../g3DisclosureSyncPayload'
import { K1_LISTED_SUBTABLE, K1_SOE_SUBTABLE } from '../k1NoteSectionMap'
import type { ChecklistResponse } from '../useF1FormData'

const RESPONSES: ChecklistResponse[] = [
  {
    item_id: 'G2-1-rows',
    remark: JSON.stringify({
      'gross-collective': { closingUnadjusted: 1500, openingUnadjusted: 800 },
      'provision-collective': { closingUnadjusted: 30, openingUnadjusted: 10 },
    }),
    conclusion: null,
  },
  {
    item_id: 'G2-2-detail-rows',
    remark: JSON.stringify([
      { investType: '定期存款', closingAudited: 1000, openingAudited: 600 },
      { investType: '债券投资', closingAudited: 500, openingAudited: 200 },
    ]),
    conclusion: null,
  },
  { item_id: 'G2-note-soe-note', remark: '国企应收利息说明', conclusion: null },
  { item_id: 'G2-note-listed-note', remark: '上市应收利息说明', conclusion: null },
  { item_id: 'G3-disclosure-soe-text', remark: '别的底稿', conclusion: null },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-g2', wpCode: 'G2' }
const SOE = { ...CTX, variant: 'soe' as const, applicableStandards: ['soe_standalone'] }
const LISTED = { ...CTX, variant: 'listed' as const, applicableStandards: ['listed_standalone'] }

function g2Map(): Map<string, ChecklistResponse> {
  return new Map(RESPONSES.filter((r) => r.item_id.startsWith('G2-')).map((r) => [r.item_id, { ...r }]))
}

/** Tab 路径：组件里挂载同一个 composable（onMounted 做首次初始化）→ 同一个快照函数 → 同一个 builder */
async function tabPayloads(variant: 'soe' | 'listed') {
  let snap: () => ReturnType<ReturnType<typeof useG2DisclosureSoe>['getSyncSnapshot']> = () => { throw new Error('未挂载') }
  const Host = defineComponent({
    setup() {
      const opts = { allResponses: ref(g2Map()), debouncedSave: () => {}, isReadonly: ref(false) }
      const dis = variant === 'soe' ? useG2DisclosureSoe(opts) : useG2DisclosureListed(opts)
      snap = dis.getSyncSnapshot
      return () => null
    },
  })
  const wrapper = mount(Host)
  await nextTick()
  const payloads = variant === 'soe'
    ? buildG2SoeSyncPayloads('wp-g2', ['soe_standalone'], snap())
    : buildG2ListedSyncPayloads('wp-g2', ['listed_standalone'], snap())
  wrapper.unmount()
  return payloads
}

describe('g2HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 12, push_kept: [] })
  })

  it('国企：八、9 载荷与 Tab 逐字节相同，经同一端点静默发出、不写底稿', async () => {
    const out = await g2HeadlessProvider(SOE)
    expect(out).toEqual({ sections: [{ section: '八、9', rows: 12, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-g2/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiPut).not.toHaveBeenCalled()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    expect(JSON.stringify([sent])).toBe(JSON.stringify(await tabPayloads('soe')))
    const cls = sent.sub_table_data['应收利息分类'] as Array<{ row_key: string; end_balance: number }>
    expect(cls.find((r) => r.row_key === 'fixed-deposit')?.end_balance).toBe(1000)
    expect(cls.find((r) => r.row_key === 'provision')?.end_balance).toBe(30)
    const ecl = sent.sub_table_data['坏账准备计提情况'] as Array<{ row_key: string; stage1: number }>
    expect(ecl.find((r) => r.row_key === 'opening')?.stage1).toBe(10)
    expect(sent.sub_table_data._note_texts).toEqual([{ section: 'soe-audit-note', text: '国企应收利息说明' }])
  })

  it('上市：五、8 载荷与 Tab 逐字节相同（不推「坏账准备计提情况」，只清它的历史残留）', async () => {
    const out = await g2HeadlessProvider(LISTED)
    expect(out).toEqual({ sections: [{ section: '五、8', rows: 12, kept: 0 }] })
    const sent = h.post.mock.calls[0][1]
    expect(JSON.stringify([sent])).toBe(JSON.stringify(await tabPayloads('listed')))
    expect(sent.sub_table_data['坏账准备计提情况']).toBeUndefined()
    expect(sent.sub_table_data._removed_table_keys).toEqual(['坏账准备计提情况'])
    expect(sent.sub_table_data._note_texts).toEqual([{ section: 'listed-audit-note', text: '上市应收利息说明' }])
    expect(h.put).not.toHaveBeenCalled()
  })

  it('口径不适用回空，不发请求', async () => {
    expect(await g2HeadlessProvider({ ...SOE, applicableStandards: ['listed_standalone'] })).toEqual({ sections: [] })
    expect(await g2HeadlessProvider({ ...LISTED, applicableStandards: ['soe_standalone'] })).toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('共用章节 五、8 / 八、9：G2 / G3 推的子表名与要删的子表都不碰 K1 的子表', async () => {
    const k1 = new Set<string>([...Object.values(K1_LISTED_SUBTABLE), ...Object.values(K1_SOE_SUBTABLE)])
    const payloads = [
      ...(await tabPayloads('soe')),
      ...(await tabPayloads('listed')),
      ...buildG3SoeSyncPayloads('wp-g3', ['soe_standalone'], [{ investeeName: 'A', openingBalance: 1, currentChange: 1 }], ''),
      ...buildG3ListedSyncPayloads('wp-g3', ['listed_standalone'], [{ investeeName: 'A', openingBalance: 1, currentIncrease: 1, currentDecrease: 0 }], ''),
    ]
    for (const p of payloads) {
      const sub = p.sub_table_data as Record<string, unknown>
      const tables = Object.keys(sub).filter((k) => !k.startsWith('_'))
      const removed = (sub._removed_table_keys as string[] | undefined) ?? []
      expect(tables.filter((t) => k1.has(t)), `${p.section_id} 推了 K1 的表`).toEqual([])
      expect(removed.filter((t) => k1.has(t)), `${p.section_id} 要删 K1 的表`).toEqual([])
    }
  })

  it('静态接线：两个 Tab 仍调同一个 composable / 快照函数 / builder', () => {
    const dir = resolve(__dirname, '../../g2-interest-receivable')
    for (const [file, use, build] of [
      ['G2TabDisclosureSOE.vue', 'useG2DisclosureSoe', 'buildG2SoeSyncPayloads'],
      ['G2TabDisclosureListed.vue', 'useG2DisclosureListed', 'buildG2ListedSyncPayloads'],
    ]) {
      const src = readFileSync(resolve(dir, file), 'utf-8')
      expect(src, file).toMatch(new RegExp(`${use}\\(\\{`))
      expect(src, file).toMatch(new RegExp(`${build}\\(\\s*props\\.wpId \\|\\| '',\\s*props\\.applicableStandards,\\s*dis\\.getSyncSnapshot\\(\\),?\\s*\\)`))
    }
  })
})
