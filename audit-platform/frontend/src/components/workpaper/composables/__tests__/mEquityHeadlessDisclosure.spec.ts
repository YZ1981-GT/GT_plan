/**
 * M4 资本公积 / M5 盈余公积披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据（按「编码 × 口径」逐个 Tab）：①挂载真实的披露 Tab（onMounted 经 useM{n}FormData 取回复、读回金额与说明），调 Tab 的
 * 同步函数，截下它发出的载荷，与离屏 provider 发出的逐字节相同；夹具有真实数据（含空串 / 非数字金额、空说明、别的口径与
 * 别的编码的同形条目）②只读本底稿前缀条目、离屏不写底稿 ③按口径写各自章节 ④没有已保存数据时按默认行（与 Tab 同）
 * ⑤章节保护命中不发请求 ⑥Tab 接线：默认行 / 读回 / 快照都走 mEquityDisclosureForm。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), put: vi.fn(), apiGet: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn(),
}))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet, post: h.apiPost, put: h.apiPut } }))
vi.mock('element-plus', async (importOriginal) => ({
  ...(await importOriginal<typeof import('element-plus')>()),
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), alert: vi.fn() },
}))

import M4TabDisclosureListed from '../../m4/core/M4TabDisclosureListed.vue'
import M4TabDisclosureSoe from '../../m4/core/M4TabDisclosureSoe.vue'
import M5TabDisclosureListed from '../../m5/core/M5TabDisclosureListed.vue'
import M5TabDisclosureSoe from '../../m5/core/M5TabDisclosureSoe.vue'
import { m4HeadlessProvider, m5HeadlessProvider } from '../mEquityHeadlessDisclosure'
import type { HeadlessDisclosureProvider } from '@/components/workpaper/headless/headlessFramework'
import { M_SYNC_URL, payloadFromMTab, type MResponseFixture } from './_mDisclosureTabHarness'

const J = JSON.stringify
const r = (item_id: string, remark: string | null) => ({ item_id, remark, conclusion: null })

interface TabCase {
  code: 'M4' | 'M5'
  variant: 'listed' | 'soe'
  Comp: unknown
  provider: HeadlessDisclosureProvider
  section: string
  table: string
  /** 别的口径 / 别的编码的同形条目（不得进载荷） */
  noise: MResponseFixture
  responses: MResponseFixture
  rows: Array<Record<string, unknown>>
  note: string
}

const CASES: TabCase[] = [
  {
    code: 'M4', variant: 'listed', Comp: M4TabDisclosureListed, provider: m4HeadlessProvider,
    section: '五、55', table: '资本公积',
    noise: [r('M4-disclosure-soe-0-beginBalance', '999'), r('M5-disclosure-listed-0-beginBalance', '888')],
    responses: [
      r('M4-disclosure-listed-0-beginBalance', '5000000'),
      r('M4-disclosure-listed-0-increase', '2000000'),
      r('M4-disclosure-listed-0-decrease', ''),
      r('M4-disclosure-listed-1-beginBalance', '300000'),
      r('M4-disclosure-listed-1-increase', '不是数字'),
      r('M4-disclosure-listed-1-decrease', '100000'),
      r('M4-disclosure-listed-premium-note', '本期因增资产生资本溢价'),
      r('M4-disclosure-listed-other-note', ''),
    ],
    rows: [
      { label: '资本溢价（股本溢价）', begin_amount: 5000000, increase: 2000000, decrease: 0, end_amount: 7000000 },
      { label: '其他资本公积', begin_amount: 300000, increase: 0, decrease: 100000, end_amount: 200000 },
      { label: '合计', begin_amount: 5300000, increase: 2000000, decrease: 100000, end_amount: 7200000, is_total: true },
    ],
    note: '本期因增资产生资本溢价',
  },
  {
    code: 'M4', variant: 'soe', Comp: M4TabDisclosureSoe, provider: m4HeadlessProvider,
    section: '八、60', table: '资本公积',
    noise: [r('M4-disclosure-listed-0-beginBalance', '999'), r('M5-disclosure-soe-0-beginBalance', '888')],
    responses: [
      r('M4-disclosure-soe-0-beginBalance', '8000000'),
      r('M4-disclosure-soe-0-increase', '1000000'),
      r('M4-disclosure-soe-1-decrease', '50000'),
      r('M4-disclosure-soe-premium-note', '国有资本投入超注册资本部分'),
      r('M4-disclosure-soe-other-note', '权益法调整'),
    ],
    rows: [
      { label: '国有资本溢价', begin_amount: 8000000, increase: 1000000, decrease: 0, end_amount: 9000000 },
      { label: '其他资本公积', begin_amount: 0, increase: 0, decrease: 50000, end_amount: -50000 },
      { label: '合计', begin_amount: 8000000, increase: 1000000, decrease: 50000, end_amount: 8950000, is_total: true },
    ],
    note: '国有资本投入超注册资本部分\n权益法调整',
  },
  {
    code: 'M5', variant: 'listed', Comp: M5TabDisclosureListed, provider: m5HeadlessProvider,
    section: '五、59', table: '盈余公积',
    noise: [r('M5-disclosure-soe-0-beginBalance', '999'), r('M4-disclosure-listed-0-beginBalance', '888'), r('M5-disclosure-soe-special-note', '国企专项')],
    responses: [
      r('M5-disclosure-listed-0-beginBalance', '1200000'),
      r('M5-disclosure-listed-0-increase', '300000'),
      r('M5-disclosure-listed-1-beginBalance', '400000'),
      r('M5-disclosure-listed-1-decrease', '50000'),
      r('M5-disclosure-listed-1-increase', 'abc'),
      r('M5-disclosure-listed-statutory-note', '按净利润 10% 计提法定盈余公积'),
      r('M5-disclosure-listed-discretionary-note', '经股东大会决议提取任意盈余公积'),
    ],
    rows: [
      { label: '法定盈余公积', begin_amount: 1200000, increase: 300000, decrease: 0, end_amount: 1500000 },
      { label: '任意盈余公积', begin_amount: 400000, increase: 0, decrease: 50000, end_amount: 350000 },
      { label: '合计', begin_amount: 1600000, increase: 300000, decrease: 50000, end_amount: 1850000, is_total: true },
    ],
    note: '按净利润 10% 计提法定盈余公积\n经股东大会决议提取任意盈余公积',
  },
  {
    code: 'M5', variant: 'soe', Comp: M5TabDisclosureSoe, provider: m5HeadlessProvider,
    section: '八、62', table: '盈余公积',
    noise: [r('M5-disclosure-listed-0-beginBalance', '999'), r('M4-disclosure-soe-0-beginBalance', '888')],
    responses: [
      r('M5-disclosure-soe-0-beginBalance', '2000000'),
      r('M5-disclosure-soe-0-increase', '500000'),
      r('M5-disclosure-soe-1-increase', '100000'),
      r('M5-disclosure-soe-statutory-note', ''),
      r('M5-disclosure-soe-discretionary-note', '提取任意盈余公积'),
      r('M5-disclosure-soe-special-note', '按国资委要求计提'),
    ],
    rows: [
      { label: '法定盈余公积', begin_amount: 2000000, increase: 500000, decrease: 0, end_amount: 2500000 },
      { label: '任意盈余公积', begin_amount: 0, increase: 100000, decrease: 0, end_amount: 100000 },
      { label: '合计', begin_amount: 2000000, increase: 600000, decrease: 0, end_amount: 2600000, is_total: true },
    ],
    note: '提取任意盈余公积\n按国资委要求计提',
  },
]

function ctxOf(c: TabCase) {
  return {
    projectId: 'p1', year: 2025, wpId: `wp-${c.code}`, wpCode: c.code,
    variant: c.variant, applicableStandards: [`${c.variant}_standalone`],
  }
}

async function tabPayload(c: TabCase, responses: MResponseFixture): Promise<any> {
  return payloadFromMTab(c.Comp, { apiGet: h.apiGet, post: h.post }, { wpId: `wp-${c.code}`, responses })
}

describe.each(CASES.map((c) => [`${c.code} ${c.variant}`, c] as const))('%s 离屏同步', (_name, c) => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.post.mockResolvedValue({ rows_synced: 3, push_kept: [] })
  })

  it('载荷与挂载的 Tab 逐字节相同，静默写本口径章节、只读本底稿条目、不写底稿', async () => {
    const fixture = [...c.responses, ...c.noise]
    const tabSent = await tabPayload(c, fixture)
    h.post.mockClear()
    h.get.mockResolvedValue(fixture)
    const out = await c.provider(ctxOf(c))
    expect(out).toEqual({ sections: [{ section: c.section, rows: 3, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith(`/api/workpapers/wp-${c.code}/checklist-responses`, expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiPut).not.toHaveBeenCalled()
    expect(h.post).toHaveBeenCalledTimes(1)
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe(M_SYNC_URL)
    expect(cfg).toMatchObject({ _silent: true })
    expect(J(sent)).toBe(J(tabSent))
    expect(sent).toMatchObject({ wp_id: `wp-${c.code}`, section_id: c.section, current_standard: `${c.variant}_standalone` })
    expect(sent.sub_table_data[c.table]).toEqual(c.rows)
    expect(sent.sub_table_data._note_texts).toEqual([
      { section: `${c.code.toLowerCase()}-${c.variant}-note`, title: `${c.table}变动说明`, text: c.note },
    ])
    expect(sent.sub_table_data._removed_table_keys).toBeUndefined()
  })

  it('没有已保存数据：按默认行发出（与 Tab 相同），不带说明', async () => {
    const tabSent = await tabPayload(c, c.noise)
    h.post.mockClear()
    h.get.mockResolvedValue(c.noise)
    await c.provider(ctxOf(c))
    const sent = h.post.mock.calls[0][1]
    expect(J(sent)).toBe(J(tabSent))
    const rows = sent.sub_table_data[c.table] as any[]
    expect(rows.map((x) => x.label)).toEqual([...c.rows.map((x) => x.label)])
    expect(rows.every((x) => x.begin_amount === 0 && x.end_amount === 0)).toBe(true)
    expect(sent.sub_table_data._note_texts).toBeUndefined()
  })

  it('章节保护命中：不发请求，原因随结果回报', async () => {
    h.get.mockResolvedValue(c.responses)
    const why = `附注 ${c.section} 已有 1 格人工填写`
    const out = await c.provider({ ...ctxOf(c), sectionGuard: () => why })
    expect(h.post).not.toHaveBeenCalled()
    expect(out).toEqual({ sections: [{ section: c.section, rows: 0, skipped: why }] })
  })
})

describe('Tab 接线', () => {
  it('四个 Tab 的默认行 / 读回 / 快照都调 mEquityDisclosureForm，组件内不再自拼', () => {
    const wp = resolve(__dirname, '../..')
    for (const c of CASES) {
      const file = `${c.code.toLowerCase()}/core/${c.code}TabDisclosure${c.variant === 'soe' ? 'Soe' : 'Listed'}.vue`
      const src = readFileSync(resolve(wp, file), 'utf-8')
      expect(src, file).toContain(`const FORM = ${c.code}_DISCLOSURE_FORM.${c.variant}`)
      expect(src, file).toContain('const dataRows = ref<DisclosureRow[]>(createMEquityDisclosureRows(FORM))')
      expect(src, file).toContain('restoreMEquityDisclosure(formData.allResponses.value, FORM, disclosureState())')
      const sync = src.slice(src.indexOf('async function syncToDisclosureNotes'))
      expect(sync, file).toMatch(/const payload = buildMEquityTabSyncPayload\(props\.wpId, FORM, disclosureState\(\)\)/)
      expect(src, file).not.toMatch(/buildMEquitySyncPayload\(|-disclosure-(?:listed|soe)-\$\{i\}|interface DisclosureRow/)
    }
  })
})
