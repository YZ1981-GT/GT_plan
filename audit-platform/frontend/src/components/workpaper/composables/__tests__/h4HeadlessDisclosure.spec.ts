/**
 * H4 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①离屏请求体与「Tab 同参实例化 useH4Disclosure + useH4Listed/SoeDisclosureForm → load → snapshot → builder」
 * 逐字节相同（上市 Tab 发送时另带 year，离屏同样带附注页年度；国企不带）②上市分类表全空时与 Tab 挂载同口径从 H4-2/H4-7
 * 取数；国企在建工程行为空时回放本会话的 H2 审定缓存 ③Tab 的读回 / 取数 / 同步调的就是共用表单（静态接线）
 * ④只读 H4- 条目、静默发出、不写底稿；载荷不带 _removed_table_keys（与 H2 共用章节，不删 H2 的子表）。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))

import { h4HeadlessProvider } from '../h4HeadlessDisclosure'
import { useH4Disclosure } from '../useH4Disclosure'
import { useH4ListedDisclosureForm, useH4SoeDisclosureForm } from '../h4DisclosureForm'
import { buildH4ListedSyncPayloads } from '../h4DisclosureSyncPayload'
import { buildH4SoeSyncPayloads } from '../h4SoeDisclosureSyncPayload'
import { H2_CIP_CACHE_PREFIX } from '../h2CipBridge'

const DETAIL = JSON.stringify([
  { category: '专用材料', beginAmount: 300, auditedEnd: 500 },
  { category: '专用设备', beginAmount: 100, auditedEnd: 250, auditedImpairEnd: 20 },
])
const LISTED_FROM_SOURCE = [
  { item_id: 'H4-2-rows', remark: DETAIL, conclusion: null },
  { item_id: 'H4-1-significant-changes', remark: JSON.stringify([{ name: '专用材料', auditedChangeRate: 66.7 }]), conclusion: null },
  { item_id: 'H2-1-rows', remark: '[{"cipEnd":9}]', conclusion: null },
]
const SOE_SAVED = [
  { item_id: 'H4-soe-summary', remark: JSON.stringify([
    { key: 'materials', endBook: 750, endImpairment: 20, beginBook: 400, beginImpairment: 0 },
  ]), conclusion: null },
  { item_id: 'H4-disclosure-soe-text', remark: '工程物资期末较期初增加', conclusion: null },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-h4', wpCode: 'H4', applicableStandards: ['listed_standalone'] }
const WP = resolve(__dirname, '../..')
type ResponseRow = { item_id: string; remark: string | null; conclusion: string | null }
const own = (list: ResponseRow[]) => new Map(list.filter((r) => r.item_id.startsWith('H4-')).map((r) => [r.item_id, r]))

async function tabPayloads(variant: 'listed' | 'soe', list: ResponseRow[]) {
  const map = own(list)
  const scope = effectScope(true)
  const run = scope.run(() => {
    const disclosure = useH4Disclosure(ref(map))
    if (variant === 'listed') {
      const form = useH4ListedDisclosureForm({ disclosure, onChange: () => {} })
      return () => { form.load(map); return buildH4ListedSyncPayloads('wp-h4', null, form.snapshot()) }
    }
    const form = useH4SoeDisclosureForm({ disclosure, onChange: () => {} })
    return () => { form.load(map, 'p1'); return buildH4SoeSyncPayloads('wp-h4', null, form.snapshot()) }
  })!
  await nextTick()
  const out = run()
  scope.stop()
  return out
}

describe('h4HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.post.mockResolvedValue({ rows_synced: 6, push_kept: [] })
    sessionStorage.clear()
  })
  afterEach(() => sessionStorage.clear())

  it('上市·分类表全空：与 Tab 挂载同口径从 H4-2 取数，请求体 = Tab 载荷 + year，静默发出、不写底稿', async () => {
    h.get.mockResolvedValue(LISTED_FROM_SOURCE)
    const out = await h4HeadlessProvider({ ...CTX, variant: 'listed' })
    expect(out).toEqual({ sections: [{ section: '五、23', rows: 6, kept: 0 }] })
    // H4-2 有已存明细 ⇒ 外壳不种，不取 render-config
    expect(h.get.mock.calls.map((c) => c[0])).toEqual(['/api/workpapers/wp-h4/checklist-responses'])
    expect(h.put).not.toHaveBeenCalled()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    const expected = (await tabPayloads('listed', LISTED_FROM_SOURCE))[0]
    expect(JSON.stringify(sent)).toBe(JSON.stringify({ ...expected, year: 2025 }))
    const rows = sent.sub_table_data['工程物资'] as Array<{ label: string; end_balance: number }>
    expect(rows.find((r) => r.label === '专用材料')?.end_balance).toBe(500)
    expect(sent.sub_table_data._removed_table_keys).toBeUndefined()
    expect(JSON.stringify(sent.sub_table_data._note_texts)).toContain('重大变动')
  })

  it('国企·已保存汇总 + 本会话 H2 审定缓存：回放在建工程行，请求体 = Tab 载荷（不带 year）', async () => {
    sessionStorage.setItem(`${H2_CIP_CACHE_PREFIX}p1`, JSON.stringify({ endBook: 9000, endImpairment: 100, beginBook: 6000, beginImpairment: 0 }))
    h.get.mockResolvedValue(SOE_SAVED)
    const out = await h4HeadlessProvider({ ...CTX, variant: 'soe', applicableStandards: ['soe_standalone'] })
    expect(out.sections.map((s) => s.section)).toEqual(['八、23'])
    const sent = h.post.mock.calls[0][1]
    expect(JSON.stringify(sent)).toBe(JSON.stringify((await tabPayloads('soe', SOE_SAVED))[0]))
    expect(sent.year).toBeUndefined()
    const rows = sent.sub_table_data['在建工程'] as Array<{ label: string; end_book: number }>
    expect(rows.find((r) => r.label === '在建工程')?.end_book).toBe(9000)
    expect(rows.find((r) => r.label === '工程物资')?.end_book).toBe(750)
    expect(sent.sub_table_data._removed_table_keys).toBeUndefined()
    expect(h.put).not.toHaveBeenCalled()
  })

  it('上市·分类表与 H4-2 都没存过：按外壳同一个 buildH4DetailSeedRows 用 render-config 的 detail_prefill 补种再取数（= 打开底稿看到的）', async () => {
    const prefill = [
      { category: '专用材料', name: '钢材', accountCode: '160501', beginAmount: 40, purchaseAmount: 80, usageAmount: 20, endAmount: 100, source: 'tb_balance' },
      { category: '专用设备', name: '吊机', accountCode: '160502', beginAmount: 0, purchaseAmount: 60, usageAmount: 0, endAmount: 60, source: 'tb_balance' },
    ]
    const list = [{ item_id: 'H4-1-significant-changes', remark: '[]', conclusion: null }]
    h.get.mockImplementation(async (url: string) => (url.endsWith('/render-config')
      ? { sheets: [{ sheet_name: '附注披露信息（上市公司）', html_data: { prefix: 'H4', detail_prefill: prefill } }] }
      : list))
    await h4HeadlessProvider({ ...CTX, variant: 'listed' })
    expect(h.get.mock.calls.map((c) => c[0])).toEqual(['/api/workpapers/wp-h4/checklist-responses', '/api/workpapers/wp-h4/render-config'])
    const sent = h.post.mock.calls[0][1]
    // 外壳种子：宿主把 buildH4DetailSeedRows(prefill, 已存 H4-2) 种成内存里的 H4-2-rows，披露 Tab 挂载取数用的就是它
    const { buildH4DetailSeedRows } = await import('../h4DetailPrefill')
    const seeded = [...list, { item_id: 'H4-2-rows', remark: JSON.stringify(buildH4DetailSeedRows(prefill, undefined)), conclusion: null }]
    expect(JSON.stringify(sent)).toBe(JSON.stringify({ ...(await tabPayloads('listed', seeded))[0], year: 2025 }))
    const rows = sent.sub_table_data['工程物资'] as Array<{ label: string; end_balance: number }>
    expect(rows.find((r) => r.label === '专用材料')?.end_balance).toBe(100)
    expect(h.put).not.toHaveBeenCalled()
  })

  it('上市·要补种但取不到 render-config：这一节不写、说明原因', async () => {
    const { H4_HOST_SEED_UNKNOWN_REASON } = await import('../h4HeadlessDisclosure')
    h.get.mockImplementation(async (url: string) => {
      if (url.endsWith('/render-config')) throw new Error('500')
      return []
    })
    const out = await h4HeadlessProvider({ ...CTX, variant: 'listed' })
    expect(out).toEqual({ sections: [{ section: '五、23', rows: 0, skipped: H4_HOST_SEED_UNKNOWN_REASON }] })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('静态接线：两个 Tab 的读回 / 取数 / 同步调共用表单', () => {
    const listed = readFileSync(resolve(WP, 'h4/core/H4TabDisclosureListed.vue'), 'utf-8')
    const soe = readFileSync(resolve(WP, 'h4/core/H4TabDisclosureSoe.vue'), 'utf-8')
    expect(listed).toContain('useH4ListedDisclosureForm({ disclosure, onChange: () => scheduleSave() })')
    expect(listed).toContain('form.load(props.allResponses)')
    expect(listed).toContain('buildH4ListedSyncPayloads(props.wpId, null, form.snapshot())')
    expect(soe).toContain('useH4SoeDisclosureForm({ disclosure, onChange: () => scheduleSave() })')
    expect(soe).toContain('form.load(props.allResponses, props.projectId)')
    expect(soe).toContain('buildH4SoeSyncPayloads(props.wpId, null, form.snapshot())')
  })
})
