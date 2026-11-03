/**
 * N1 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①两版离屏载荷与 Tab 路径逐字节相同 —— Tab 路径就是 Tab 自己的加载器 `useN1FormData.loadData()`（自取渲染配置与
 * 回复）→ `useN1DisclosureTables`（预填照 Tab 传 `formData.*Prefill`）→ restore → buildPayload ②渲染配置的四表预填
 * 真的进了载荷（未持久化的表 1 两段按预填带出递延税额）③只读 N1 条目、不写底稿。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), apiGet: vi.fn(), apiPut: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet, put: h.apiPut, post: vi.fn() } }))

import { n1HeadlessProvider } from '../n1HeadlessDisclosure'
import { useN1DisclosureTables } from '../useN1DisclosureTables'
import { useN1FormData } from '../useN1FormData'
import { N1_SUB_TABLE_KEYS } from '../n1NoteSectionMap'

const RENDER_CONFIG = {
  sheets: [
    { sheet_name: '底稿目录', html_data: {} },
    {
      sheet_name: '审定表N1-1',
      html_data: {
        trial_balance: { begin_balance: 100, debit_amount: 40, credit_amount: 10, end_balance: 130 },
        adjudication_prefill: { 资产减值准备: { opening: 50, closing: 80 }, 可抵扣亏损: { opening: 20, closing: 30 } },
        liability_prefill: { depreciation: { opening: 7, closing: 9 } },
      },
    },
  ],
}
const RESPONSES = [
  { item_id: 'N1-disclosure-listed-unrecognized', conclusion: JSON.stringify([{ item: '可抵扣暂时性差异', end: 400, prior: 300 }, { item: '可抵扣亏损', end: 200, prior: null }]), remark: null },
  { item_id: 'N1-disclosure-listed-conclusion', conclusion: null, remark: '上市结论' },
  { item_id: 'N1-disclosure-soe-conclusion', conclusion: null, remark: '国企结论' },
  { item_id: 'N2-disclosure-listed-taxes', conclusion: '[]', remark: null },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-n1', wpCode: 'N1' }
const SECTION = { listed: '五、30', soe: '八、31' } as const

const route = (url: string) => (url.includes('/render-config') ? RENDER_CONFIG : RESPONSES)

/** Tab 路径：Tab 自己的加载器（useN1FormData）+ 同样参数的 useN1DisclosureTables → restore → buildPayload */
async function tabPayload(variant: 'listed' | 'soe') {
  const scope = effectScope(true)
  const { formData, tables } = scope.run(() => {
    const formData = useN1FormData({ wpId: ref('wp-n1'), projectId: ref('p1') })
    const tables = useN1DisclosureTables({
      variant,
      allResponses: formData.allResponses,
      auditYear: ref<number | null>(2025),
      adjudicationPrefill: formData.adjudicationPrefill,
      liabilityPrefill: formData.liabilityPrefill,
    })
    return { formData, tables }
  })!
  await formData.loadData()
  tables.restore()
  await nextTick()
  const payload = tables.buildPayload({ wpId: 'wp-n1', year: 2025 })
  scope.stop()
  return payload
}

describe('n1HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockImplementation(async (url: string) => route(url))
    h.apiGet.mockImplementation(async (url: string) => route(url))
    h.post.mockResolvedValue({ rows_synced: 21 })
  })

  it.each(['listed', 'soe'] as const)('%s：载荷与 Tab 同一套代码逐字节相同，静默发出、不写底稿', async (variant) => {
    const out = await n1HeadlessProvider({ ...CTX, variant, applicableStandards: [`${variant}_standalone`] })
    expect(out).toEqual({ sections: [{ section: SECTION[variant], rows: 21, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-n1/checklist-responses', expect.anything())
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-n1/render-config', expect.anything())
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    expect(h.put).not.toHaveBeenCalled()
    expect(JSON.stringify(sent)).toBe(JSON.stringify(await tabPayload(variant)))
    expect(h.apiPut).not.toHaveBeenCalled()
  })

  it('渲染配置的四表预填进了载荷：未持久化的表 1 按预填带出递延税额', async () => {
    await n1HeadlessProvider({ ...CTX, variant: 'listed', applicableStandards: ['listed_standalone'] })
    const sent = h.post.mock.calls[0][1]
    const unoffset = sent.sub_table_data[N1_SUB_TABLE_KEYS.listed.unoffset] as Array<Record<string, unknown>>
    expect(unoffset.find((r) => r.label === '资产减值准备')).toMatchObject({ end_tax: 80, prior_tax: 50 })
    expect(unoffset.find((r) => r.label === '购入摊销年限大于税法规定的资产')).toMatchObject({ end_tax: 9, prior_tax: 7 })
    const unrec = sent.sub_table_data[N1_SUB_TABLE_KEYS.listed.unrecognized] as Array<Record<string, unknown>>
    expect(unrec.at(-1)).toMatchObject({ end: 600, is_total: true })
  })

  it('取不到渲染配置：按 Tab 加载失败同一兜底（没有预填，表 1 留空）', async () => {
    h.get.mockImplementation(async (url: string) => {
      if (url.includes('/render-config')) throw new Error('offline')
      return RESPONSES
    })
    await n1HeadlessProvider({ ...CTX, variant: 'listed', applicableStandards: ['listed_standalone'] })
    const unoffset = h.post.mock.calls[0][1].sub_table_data[N1_SUB_TABLE_KEYS.listed.unoffset] as Array<Record<string, unknown>>
    expect(unoffset.find((r) => r.label === '资产减值准备')?.end_tax ?? null).toBeNull()
  })

  it('Tab 的同步走的是同一个 buildPayload，预填来自 useN1FormData', () => {
    for (const tab of ['N1TabDisclosureListed.vue', 'N1TabDisclosureSoe.vue']) {
      const src = readFileSync(resolve(__dirname, '../../n1/core', tab), 'utf-8')
      expect(src, tab).toMatch(/adjudicationPrefill:\s*formData\.adjudicationPrefill/)
      expect(src, tab).toMatch(/tables\.buildPayload\(\{\s*wpId:\s*props\.wpId,\s*year:\s*syncYear\.value\s*\}\)/)
    }
  })
})
