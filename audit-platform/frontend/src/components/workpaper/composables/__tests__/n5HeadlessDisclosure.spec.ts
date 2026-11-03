/**
 * N5 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①两版离屏载荷与「Tab 同样参数实例化 useN5DisclosureTables → restore → buildPayload」逐字节相同 ②只读 N5 条目、
 * 不写底稿（不 PUT）③表（2）末行是公式行（排除首行利润总额），载荷有真实数据。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))

import { n5HeadlessProvider } from '../n5HeadlessDisclosure'
import { useN5DisclosureTables } from '../useN5DisclosureTables'
import { N5_SUB_TABLE_KEYS } from '../n5NoteSectionMap'

const rows = (pairs: Array<[string, number]>) => JSON.stringify(pairs.map(([item, current]) => ({ item, current, prior: null })))
const RESPONSES = [
  { item_id: 'N5-disclosure-listed-detail', conclusion: rows([['按税法及相关规定计算的当期所得税', 300], ['递延所得税费用', -20]]), remark: null },
  { item_id: 'N5-disclosure-listed-reconcile', conclusion: rows([['利润总额', 1000], ['按法定（或适用）税率计算的所得税费用（利润总额*XX%）', 250], ['不可抵扣的成本、费用和损失', 30]]), remark: null },
  { item_id: 'N5-disclosure-listed-conclusion', conclusion: null, remark: '有效税率与法定税率差异说明' },
  { item_id: 'N5-disclosure-soe-detail', conclusion: rows([['当期所得税费用', 280], ['递延所得税调整', 5]]), remark: null },
  { item_id: 'N5-disclosure-soe-reconcile', conclusion: rows([['利润总额', 900], ['按适定/适用税率计算的所得税费用', 225]]), remark: null },
  { item_id: 'N4-disclosure-listed-taxes', conclusion: '[]', remark: null },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-n5', wpCode: 'N5' }
const SECTION = { listed: '五、81', soe: '八、78' } as const

async function tabPayload(variant: 'listed' | 'soe') {
  const map = new Map(RESPONSES.filter((r) => r.item_id.startsWith('N5-')).map((r) => [r.item_id, r]))
  const scope = effectScope(true)
  const tables = scope.run(() => useN5DisclosureTables({ variant, allResponses: ref(map) }))!
  tables.restore()
  await nextTick()
  const payload = tables.buildPayload({ wpId: 'wp-n5', year: 2025 })
  scope.stop()
  return payload
}

describe('n5HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 7 })
  })

  it.each(['listed', 'soe'] as const)('%s：载荷与 Tab 同一套代码逐字节相同，静默发出、不写底稿', async (variant) => {
    const out = await n5HeadlessProvider({ ...CTX, variant, applicableStandards: [`${variant}_standalone`] })
    expect(out).toEqual({ sections: [{ section: SECTION[variant], rows: 7, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-n5/checklist-responses', expect.anything())
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    expect(h.put).not.toHaveBeenCalled()
    expect(JSON.stringify(sent)).toBe(JSON.stringify(await tabPayload(variant)))
  })

  it('载荷带真实数据：表（2）末行 = 第二行起之和（不含利润总额）', async () => {
    await n5HeadlessProvider({ ...CTX, variant: 'listed', applicableStandards: ['listed_standalone'] })
    const sent = h.post.mock.calls[0][1]
    const detail = sent.sub_table_data[N5_SUB_TABLE_KEYS.listed.detail] as Array<{ current: number | null }>
    const reconcile = sent.sub_table_data[N5_SUB_TABLE_KEYS.listed.reconcile] as Array<{ label: string; current: number | null }>
    expect(detail.at(-1)?.current).toBe(280)
    expect(reconcile.at(-1)).toMatchObject({ label: '所得税费用', current: 280 })
    expect(sent.sub_table_data._note_texts[0].text).toBe('有效税率与法定税率差异说明')
  })

  it('Tab 的同步走的是同一个 buildPayload（loadData + restore 后）', () => {
    const src = readFileSync(resolve(__dirname, '../../n5/shared/N5DisclosureBody.vue'), 'utf-8')
    expect(src).toMatch(/tables\.buildPayload\(\{\s*wpId:\s*props\.wpId,\s*year:\s*syncYear\.value\s*\}\)/)
    expect(src).toMatch(/await formData\.loadData\(\)\s*\n\s*tables\.restore\(\)/)
  })
})
