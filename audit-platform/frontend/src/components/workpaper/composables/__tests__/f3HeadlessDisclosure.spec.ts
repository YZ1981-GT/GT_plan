/**
 * F3 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①两版离屏载荷与「Tab 同样参数实例化 composable → Tab 同一个载荷函数」逐字节相同 ②抽出的载荷函数与抽出前 Tab
 * 内联的写法逐字节相同（Tab 行为不变）③Tab 源码确实调用该函数 ④只读 F3 条目、不写底稿、离屏结束不留窗口监听。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))

import { f3HeadlessProvider } from '../f3HeadlessDisclosure'
import { useF3DisclosureListed } from '../useF3DisclosureListed'
import { useF3DisclosureSoe } from '../useF3DisclosureSoe'
import { buildF3SyncPayload, buildF3SyncPayloadFromDisclosure, F3_SUBTABLE_BY_VARIANT } from '../f3NoteSectionMap'

const ADJ = [
  { rowKey: 'bank', openingUnadjusted: 500, openingAje: 0, openingRje: 0, periodCredit: 300, periodDebit: 100, closingAje: 0, closingRje: 0 },
  { rowKey: 'commercial', openingUnadjusted: 200, openingAje: 10, openingRje: 0, periodCredit: 50, periodDebit: 20, closingAje: 5, closingRje: 0 },
]
const RESPONSES = [
  { item_id: 'F3-1-adj-rows', conclusion: null, remark: JSON.stringify(ADJ) },
  { item_id: 'F3-note-listed-note', conclusion: null, remark: '本期末已到期未支付的应付票据总额为0元' },
  { item_id: 'F3-note-soe-note', conclusion: null, remark: '国企说明' },
  { item_id: 'K1-unrelated', conclusion: null, remark: '999' },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-f3', wpCode: 'F3' }
const SECTION = { listed: '五、36', soe: '八、36' } as const

function instantiate(variant: 'listed' | 'soe', standards: string[]) {
  const map = new Map(RESPONSES.filter((r) => r.item_id.startsWith('F3-')).map((r) => [r.item_id, r]))
  const options = { allResponses: ref(map), isReadonly: ref(false), applicableStandards: ref(standards) }
  const scope = effectScope(true)
  const disclosure = scope.run(() => (variant === 'listed' ? useF3DisclosureListed(options) : useF3DisclosureSoe(options)))!
  return { scope, disclosure }
}

describe('f3HeadlessProvider', () => {
  let adjudicatedListeners = 0
  const add = window.addEventListener.bind(window)
  const remove = window.removeEventListener.bind(window)

  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 3 })
    adjudicatedListeners = 0
    vi.spyOn(window, 'addEventListener').mockImplementation((type: string, ...rest: any[]) => {
      if (type === 'substantive:adjudicated') adjudicatedListeners += 1
      return (add as any)(type, ...rest)
    })
    vi.spyOn(window, 'removeEventListener').mockImplementation((type: string, ...rest: any[]) => {
      if (type === 'substantive:adjudicated') adjudicatedListeners -= 1
      return (remove as any)(type, ...rest)
    })
  })
  afterEach(() => vi.restoreAllMocks())

  it.each(['listed', 'soe'] as const)('%s：载荷与 Tab 同一套代码逐字节相同，静默发出、不写底稿、不留窗口监听', async (variant) => {
    const standards = [`${variant}_standalone`]
    const out = await f3HeadlessProvider({ ...CTX, variant, applicableStandards: standards })
    expect(out).toEqual({ sections: [{ section: SECTION[variant], rows: 3, kept: 0 }] })
    expect(adjudicatedListeners).toBe(0)
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-f3/checklist-responses', expect.anything())
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    expect(h.put).not.toHaveBeenCalled()

    const { scope, disclosure } = instantiate(variant, standards)
    await nextTick()
    expect(JSON.stringify(sent)).toBe(JSON.stringify(
      buildF3SyncPayloadFromDisclosure(variant, 'wp-f3', standards, disclosure),
    ))
    // 抽出前 Tab 内联的写法（行为不变的判据）
    const inline = buildF3SyncPayload(
      variant, 'wp-f3', standards,
      disclosure.section1Rows.value.map((r) => ({ label: r.label, endAmount: r.endAmount, priorAmount: r.priorAmount })),
      { label: '合计', endAmount: disclosure.section1Subtotal.value.endAmount, priorAmount: disclosure.section1Subtotal.value.priorAmount },
      disclosure.noteText.value,
    )
    expect(JSON.stringify(sent)).toBe(JSON.stringify(inline))
    scope.stop()
    expect(adjudicatedListeners).toBe(0)
  })

  it('载荷带真实数据：期末 = 期初未审 + 贷方 − 借方 + 调整，合计与附注说明都在', async () => {
    await f3HeadlessProvider({ ...CTX, variant: 'listed', applicableStandards: ['listed_standalone'] })
    const sent = h.post.mock.calls[0][1]
    const rows = sent.sub_table_data[F3_SUBTABLE_BY_VARIANT.listed.notesPayable] as Array<Record<string, unknown>>
    expect(rows.find((r) => r.label === '银行承兑汇票')).toMatchObject({ end_amount: 700, prior_amount: 500 })
    expect(rows.find((r) => r.label === '商业承兑汇票')).toMatchObject({ end_amount: 235, prior_amount: 210 })
    expect(rows.at(-1)).toMatchObject({ label: '合计', end_amount: 935, prior_amount: 710, is_total: true })
    expect(sent.sub_table_data._note_texts[0].text).toBe('本期末已到期未支付的应付票据总额为0元')
  })

  it('两版 Tab 的同步调用同一个载荷函数', () => {
    for (const [tab, variant] of [['F3TabDisclosureListed.vue', 'listed'], ['F3TabDisclosureSOE.vue', 'soe']] as const) {
      const src = readFileSync(resolve(__dirname, '../../f3-notes-payable', tab), 'utf-8')
      expect(src, tab).toMatch(new RegExp(
        `buildF3SyncPayloadFromDisclosure\\('${variant}', props\\.wpId, props\\.applicableStandards, \\{\\s*section1Rows, section1Subtotal, noteText,\\s*\\}\\)`,
      ))
      expect(src, tab).not.toMatch(/buildF3SyncPayload\(/)
    }
  })
})
