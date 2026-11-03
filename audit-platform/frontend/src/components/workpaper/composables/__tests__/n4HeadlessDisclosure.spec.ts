/**
 * N4 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①上市离屏载荷与「Tab 同样参数实例化 useN4DisclosureTables → restore → buildPayload」逐字节相同 ②只读 N4 条目、
 * 不写底稿（不 PUT；已同步表名不回写）③国企版 builder 恒 null ⇒ `{ sections: [] }`、不发请求。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))

import { n4HeadlessProvider } from '../n4HeadlessDisclosure'
import { useN4DisclosureTables } from '../useN4DisclosureTables'
import { N4_SUB_TABLE_KEYS, N4_TOTAL_LABEL } from '../n4NoteSectionMap'

const ROWS = [
  { item: '城市维护建设税', current: 120, prior: 100 },
  { item: '教育费附加', current: 60, prior: 50 },
  { item: '印花税', current: 8.5, prior: null },
]
const RESPONSES = [
  { item_id: 'N4-disclosure-listed-taxes', conclusion: JSON.stringify(ROWS), remark: null },
  { item_id: 'N4-disclosure-listed-standard-note', conclusion: null, remark: '计缴标准详见附注四' },
  { item_id: 'N4-disclosure-listed-conclusion', conclusion: null, remark: '披露完整' },
  { item_id: 'N4-disclosure-listed-synced-tables', conclusion: JSON.stringify(['税金及附加']), remark: null },
  { item_id: 'N5-disclosure-listed-detail', conclusion: '[]', remark: null },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-n4', wpCode: 'N4', applicableStandards: ['listed_standalone'] }

/** Tab 路径：同一批 N4 响应 → useN4DisclosureTables → restore()（Tab onMounted）→ buildPayload（Tab 同步函数） */
async function tabPayload() {
  const map = new Map(RESPONSES.filter((r) => r.item_id.startsWith('N4-')).map((r) => [r.item_id, r]))
  const scope = effectScope(true)
  const tables = scope.run(() => useN4DisclosureTables({ allResponses: ref(map) }))!
  tables.restore()
  await nextTick()
  const payload = tables.buildPayload({ wpId: 'wp-n4', year: 2025 })
  scope.stop()
  return payload
}

describe('n4HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 4 })
  })

  it('上市：载荷与 Tab 同一套代码逐字节相同，经同一端点静默发出、不写底稿', async () => {
    const out = await n4HeadlessProvider({ ...CTX, variant: 'listed' })
    expect(out).toEqual({ sections: [{ section: '五、63', rows: 4, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-n4/checklist-responses', expect.anything())
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    expect(h.put).not.toHaveBeenCalled()
    expect(JSON.stringify(sent)).toBe(JSON.stringify(await tabPayload()))
    const rows = sent.sub_table_data[N4_SUB_TABLE_KEYS.listed.taxes] as Array<{ label: string; current: number | null }>
    expect(rows.map((r) => r.label)).toEqual(['城市维护建设税', '教育费附加', '印花税', N4_TOTAL_LABEL])
    expect(rows.at(-1)).toMatchObject({ current: 188.5, is_total: true })
    expect(sent.sub_table_data._note_texts.map((t: { text: string }) => t.text)).toEqual(['计缴标准详见附注四', '披露完整'])
  })

  it('国企版不披露：没有章节、不发请求', async () => {
    const out = await n4HeadlessProvider({ ...CTX, variant: 'soe', applicableStandards: ['soe_standalone'] })
    expect(out).toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('Tab 的同步走的是同一个 buildPayload（restore 后）', () => {
    const src = readFileSync(resolve(__dirname, '../../n4/core/N4TabDisclosureListed.vue'), 'utf-8')
    expect(src).toMatch(/tables\.buildPayload\(\{\s*wpId:\s*props\.wpId,\s*year:\s*syncYear\.value\s*\}\)/)
    expect(src).toMatch(/await formData\.selfLoad\(\)\s*\n\s*tables\.restore\(\)/)
  })
})
