/**
 * N2 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①两版离屏载荷与 Tab 路径逐字节相同 —— Tab 路径 = Tab 自己的加载器 `useN2FormData.loadData()` + 外壳传给 Tab 的
 * 披露 sheet `html_data.adjudication_prefill` → `useN2DisclosureTables` → restore → buildPayload ②预填取的是本口径披露
 * sheet（不是别的 sheet）③只读 N2 条目、不写底稿。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, effectScope, nextTick, ref } from 'vue'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), apiGet: vi.fn(), apiPut: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet, put: h.apiPut, post: vi.fn() } }))

import { n2HeadlessProvider } from '../n2HeadlessDisclosure'
import { useN2DisclosureTables } from '../useN2DisclosureTables'
import { useN2FormData } from '../useN2FormData'
import { N2_SUB_TABLE_KEYS } from '../n2NoteSectionMap'

const prefill = (vat: number) => [
  { tax_type: '增值税', begin_unadj: 100, end_unadj: vat },
  { tax_type: '企业所得税', begin_unadj: 50, end_unadj: 80 },
]
const RENDER_CONFIG = {
  sheets: [
    { sheet_name: '审定表N2-1', html_data: { adjudication_prefill: prefill(1) } },
    { sheet_name: '附注披露信息（上市公司）', html_data: { adjudication_prefill: prefill(150) } },
    { sheet_name: '附注披露信息（国企）', html_data: { adjudication_prefill: prefill(160) } },
  ],
}
/** 外壳在披露 sheet 上传给 Tab 的 htmlData（GtWpRenderer.activeSheetHtmlData） */
const SHELL_HTML_DATA = { listed: RENDER_CONFIG.sheets[1].html_data, soe: RENDER_CONFIG.sheets[2].html_data }
const RESPONSES = [
  { item_id: 'N2-disclosure-listed-conclusion', conclusion: null, remark: '上市结论' },
  { item_id: 'N2-disclosure-soe-offset-note', conclusion: null, remark: '抵销说明' },
  { item_id: 'N1-disclosure-listed-conclusion', conclusion: null, remark: '别的底稿' },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-n2', wpCode: 'N2' }
const SECTION = { listed: '五、41', soe: '八、41' } as const
const route = (url: string) => (url.includes('/render-config') ? RENDER_CONFIG : RESPONSES)

async function tabPayload(variant: 'listed' | 'soe') {
  const scope = effectScope(true)
  const { formData, tables } = scope.run(() => {
    const formData = useN2FormData({ wpId: ref('wp-n2'), projectId: ref('p1') })
    const tables = useN2DisclosureTables({
      variant,
      allResponses: formData.allResponses,
      renderPrefill: computed(() => SHELL_HTML_DATA[variant]?.adjudication_prefill),
    })
    return { formData, tables }
  })!
  await formData.loadData()
  tables.restore()
  await nextTick()
  const payload = tables.buildPayload({ wpId: 'wp-n2', year: 2025 })
  scope.stop()
  return payload
}

describe('n2HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockImplementation(async (url: string) => route(url))
    h.apiGet.mockImplementation(async (url: string) => route(url))
    h.post.mockResolvedValue({ rows_synced: 14 })
  })

  it.each(['listed', 'soe'] as const)('%s：载荷与 Tab 同一套代码逐字节相同，静默发出、不写底稿', async (variant) => {
    const out = await n2HeadlessProvider({ ...CTX, variant, applicableStandards: [`${variant}_standalone`] })
    expect(out).toEqual({ sections: [{ section: SECTION[variant], rows: 14, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-n2/render-config', expect.anything())
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    expect(h.put).not.toHaveBeenCalled()
    expect(JSON.stringify(sent)).toBe(JSON.stringify(await tabPayload(variant)))
    expect(h.apiPut).not.toHaveBeenCalled()
  })

  it('预填取本口径披露 sheet：上市增值税期末 150、国企期初带出', async () => {
    await n2HeadlessProvider({ ...CTX, variant: 'listed', applicableStandards: ['listed_standalone'] })
    const listed = h.post.mock.calls[0][1].sub_table_data[N2_SUB_TABLE_KEYS.listed.taxes] as Array<Record<string, unknown>>
    expect(listed.find((r) => r.label === '增值税')).toMatchObject({ end: 150, prior: 100 })
    expect(listed.at(-1)).toMatchObject({ end: 230, is_total: true })
    await n2HeadlessProvider({ ...CTX, variant: 'soe', applicableStandards: ['soe_standalone'] })
    const soe = h.post.mock.calls[1][1].sub_table_data[N2_SUB_TABLE_KEYS.soe.taxes] as Array<Record<string, unknown>>
    expect(soe.find((r) => r.label === '企业所得税')).toMatchObject({ opening: 50 })
  })

  it('Tab 的预填来自外壳 htmlData，同步走同一个 buildPayload', () => {
    for (const tab of ['N2TabDisclosureListed.vue', 'N2TabDisclosureSoe.vue']) {
      const src = readFileSync(resolve(__dirname, '../../n2/core', tab), 'utf-8')
      expect(src, tab).toMatch(/renderPrefill:\s*computed\(\(\)\s*=>\s*props\.htmlData\?\.adjudication_prefill\)/)
      expect(src, tab).toMatch(/tables\.buildPayload\(\{\s*wpId:\s*props\.wpId,\s*year:\s*syncYear\.value\s*\}\)/)
    }
  })
})
