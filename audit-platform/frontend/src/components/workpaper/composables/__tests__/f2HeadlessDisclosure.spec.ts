/**
 * F2 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①两版离屏载荷与「Tab 同样参数实例化 composable → getSyncSnapshot → 子表 builder → buildF2SyncPayload」逐字节
 * 相同 ②Tab 源码就是这条组合 ③只读 F2 条目、不写底稿、离屏结束不留窗口监听 ④口径不适用 ⇒ `{ sections: [] }`。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))

import { f2HeadlessProvider } from '../f2HeadlessDisclosure'
import { useF2DisclosureListed } from '../useF2DisclosureListed'
import { useF2DisclosureSoe } from '../useF2DisclosureSoe'
import { buildF2ListedSubTableData, buildF2SoeSubTableData, buildF2SyncPayload } from '../f2DisclosureSyncPayload'

const field = (block: string, key: string, name: string, v: number) =>
  ({ item_id: `F2-1-${block}-${key}-${name}`, conclusion: String(v), remark: null })
const RESPONSES = [
  field('gross', 'raw-materials', 'opening', 1000),
  field('gross', 'raw-materials', 'increase', 500),
  field('gross', 'raw-materials', 'decrease', 300),
  field('impairment', 'raw-materials', 'opening', 40),
  field('impairment', 'raw-materials', 'increase', 20),
  field('gross', 'finished-goods', 'opening', 800),
  { item_id: 'F2-note-listed-note-category', conclusion: null, remark: '存货分类说明（上市）' },
  { item_id: 'F2-note-soe-note-category', conclusion: null, remark: '存货分类说明（国企）' },
  { item_id: 'K1-unrelated', conclusion: '999', remark: null },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-f2', wpCode: 'F2' }
const SECTION = { listed: '五、9', soe: '八、10' } as const

/** Tab 路径：同一批 F2 响应、同样参数实例化 composable → Tab 同步函数里的同一条组合 */
async function tabPayload(variant: 'listed' | 'soe', standards: string[]) {
  const map = new Map(RESPONSES.filter((r) => r.item_id.startsWith('F2-')).map((r) => [r.item_id, r]))
  const options = { allResponses: ref(map), isReadonly: ref(false), applicableStandards: ref(standards) }
  const scope = effectScope(true)
  const payload = await scope.run(async () => {
    if (variant === 'listed') {
      const { getSyncSnapshot } = useF2DisclosureListed(options)
      await nextTick()
      return buildF2SyncPayload('listed', 'wp-f2', standards, buildF2ListedSubTableData(getSyncSnapshot()))
    }
    const { getSyncSnapshot } = useF2DisclosureSoe(options)
    await nextTick()
    return buildF2SyncPayload('soe', 'wp-f2', standards, buildF2SoeSubTableData(getSyncSnapshot()))
  })
  scope.stop()
  return payload
}

describe('f2HeadlessProvider', () => {
  let listeners = 0
  const add = window.addEventListener.bind(window)
  const remove = window.removeEventListener.bind(window)

  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 30 })
    listeners = 0
    vi.spyOn(window, 'addEventListener').mockImplementation((type: string, ...rest: any[]) => {
      if (type === 'substantive:adjudicated') listeners += 1
      return (add as any)(type, ...rest)
    })
    vi.spyOn(window, 'removeEventListener').mockImplementation((type: string, ...rest: any[]) => {
      if (type === 'substantive:adjudicated') listeners -= 1
      return (remove as any)(type, ...rest)
    })
  })
  afterEach(() => vi.restoreAllMocks())

  it.each(['listed', 'soe'] as const)('%s：载荷与 Tab 同一套代码逐字节相同，静默发出、不写底稿、不留窗口监听', async (variant) => {
    const standards = [`${variant}_standalone`]
    const out = await f2HeadlessProvider({ ...CTX, variant, applicableStandards: standards })
    expect(out).toEqual({ sections: [{ section: SECTION[variant], rows: 30, kept: 0 }] })
    expect(listeners).toBe(0)
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-f2/checklist-responses', expect.anything())
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    expect(h.put).not.toHaveBeenCalled()
    expect(JSON.stringify(sent)).toBe(JSON.stringify(await tabPayload(variant, standards)))
  })

  it('载荷带真实数据：存货分类取 F2-1 审定数与说明', async () => {
    await f2HeadlessProvider({ ...CTX, variant: 'listed', applicableStandards: ['listed_standalone'] })
    const sent = h.post.mock.calls[0][1]
    const cls = sent.sub_table_data['存货分类'] as Array<Record<string, unknown>>
    expect(cls.find((r) => r.label === '原材料')).toMatchObject({ end_gross: 1200, prior_gross: 1000, end_impairment: 60 })
    expect(cls.find((r) => r.label === '库存商品')).toMatchObject({ prior_gross: 800 })
    expect(sent.sub_table_data._note_texts[0]).toMatchObject({ text: '存货分类说明（上市）' })
  })

  it('口径不适用：没有章节、不发请求', async () => {
    const out = await f2HeadlessProvider({ ...CTX, variant: 'listed', applicableStandards: ['soe_standalone'] })
    expect(out).toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('两版 Tab 的同步就是同一条组合（快照 → 子表 builder → buildF2SyncPayload）', () => {
    const dir = resolve(__dirname, '../../f2/core')
    const listed = readFileSync(resolve(dir, 'F2TabDisclosureListed.vue'), 'utf-8')
    const soe = readFileSync(resolve(dir, 'F2TabDisclosureSoe.vue'), 'utf-8')
    expect(listed).toMatch(/buildF2SyncPayload\(\s*'listed',\s*props\.wpId,\s*props\.applicableStandards,\s*buildF2ListedSubTableData\(getSyncSnapshot\(\)\),?\s*\)/)
    expect(soe).toMatch(/buildF2SyncPayload\(\s*'soe',\s*props\.wpId,\s*props\.applicableStandards,\s*buildF2SoeSubTableData\(getSyncSnapshot\(\)\),?\s*\)/)
    expect(listed).toMatch(/useF2DisclosureListed\(\{[\s\S]{0,400}applicableStandards: toRef\(props, 'applicableStandards'\)/)
    expect(soe).toMatch(/useF2DisclosureSoe\(\{[\s\S]{0,400}applicableStandards: toRef\(props, 'applicableStandards'\)/)
  })
})
