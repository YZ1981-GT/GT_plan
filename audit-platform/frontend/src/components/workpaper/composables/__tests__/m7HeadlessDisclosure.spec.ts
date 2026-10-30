/**
 * M7 专项储备披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 默认四行 / 读回原因与计提依据 / 按 M7-1 小计改期末原在两个 Tab 里内联，抽到 `mEquityDisclosureForm` 后 Tab 与离屏共用；
 * 取数口径与 Tab 的 useNoteAutoFill 同一个 `readNoteAutoFillValues`。判据：①挂载真实 Tab（经 useM7FormData 取回复、onMounted
 * 读回 + 取数），调它的同步函数截下载荷，与离屏载荷逐字节相同（上市 五、58；国企 八、61 带备注列）②取数门槛与 Tab 同
 * （合计、安全生产费都为 0 时不改期末）③只读 M7- 条目、离屏不写底稿 ④Tab 接线走共用函数。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), put: vi.fn(), apiGet: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn(),
}))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet, post: h.apiPost, put: h.apiPut } }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }), useRoute: () => ({ params: {}, query: {} }) }))
vi.mock('element-plus', async (importOriginal) => ({
  ...(await importOriginal<typeof import('element-plus')>()),
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), alert: vi.fn() },
}))

import M7TabDisclosureListed from '../../m7/core/M7TabDisclosureListed.vue'
import M7TabDisclosureSoe from '../../m7/core/M7TabDisclosureSoe.vue'
import { m7HeadlessProvider } from '../mEquityHeadlessDisclosure'
import { M_SYNC_URL, payloadFromMTab, type MResponseFixture } from './_mDisclosureTabHarness'

const J = JSON.stringify
const r = (item_id: string, remark: string | null, conclusion: string | null = null) => ({ item_id, remark, conclusion })

const LISTED_RESPONSES: MResponseFixture = [
  r('M7-1-safety-subtotal', '120000'),
  r('M7-1-maintenance-subtotal', null, '30000'),
  r('M7-1-other-subtotal', ''),
  r('M7-1-total-audited', '150000'),
  r('M7-disclosure-listed-row-0-reason', '按营业收入比例计提'),
  r('M7-disclosure-listed-note', '安全生产费按财资〔2022〕136号计提'),
  r('M7-disclosure-soe-row-0-policy', '国企依据（不进上市）'),
  r('M6-1-total-audited', '999'),
]
const SOE_RESPONSES: MResponseFixture = [
  r('M7-1-safety-subtotal', '0'),
  r('M7-1-maintenance-subtotal', '500'),
  r('M7-1-total-audited', '500'),
  r('M7-disclosure-soe-row-1-policy', '财企〔2012〕16号'),
  r('M7-disclosure-soe-note', '  维简费说明  '),
  r('M7-disclosure-listed-row-1-reason', '上市原因（不进国企）'),
]

const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-M7', wpCode: 'M7' }
const ctxOf = (variant: 'listed' | 'soe') => ({ ...CTX, variant, applicableStandards: [`${variant}_standalone`] })

async function tabPayload(variant: 'listed' | 'soe', responses: MResponseFixture) {
  const Comp = variant === 'listed' ? M7TabDisclosureListed : M7TabDisclosureSoe
  return payloadFromMTab(Comp, { apiGet: h.apiGet, post: h.post }, { wpId: 'wp-M7', responses })
}

async function headlessPayload(variant: 'listed' | 'soe', responses: MResponseFixture) {
  h.post.mockClear()
  h.get.mockResolvedValue(responses)
  const out = await m7HeadlessProvider(ctxOf(variant))
  expect(h.post).toHaveBeenCalledTimes(1)
  const [url, sent, cfg] = h.post.mock.calls[0]
  expect(url).toBe(M_SYNC_URL)
  expect(cfg).toMatchObject({ _silent: true })
  return { out, sent }
}

describe('m7HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.post.mockResolvedValue({ rows_synced: 4, push_kept: [] })
  })

  it('上市：按 M7-1 小计取期末（结论栏也认），载荷与挂载的 Tab 逐字节相同，静默写 五、58、不写底稿', async () => {
    const tabSent = await tabPayload('listed', LISTED_RESPONSES)
    const { out, sent } = await headlessPayload('listed', LISTED_RESPONSES)
    expect(out).toEqual({ sections: [{ section: '五、58', rows: 4, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-M7/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiPut).not.toHaveBeenCalled()
    expect(J(sent)).toBe(J(tabSent))
    expect(sent.sub_table_data['专项储备']).toEqual([
      { label: '安全生产费', begin_amount: 0, increase: 0, decrease: 0, end_amount: 120000 },
      { label: '维简费', begin_amount: 0, increase: 0, decrease: 0, end_amount: 30000 },
      { label: '其他专项储备', begin_amount: 0, increase: 0, decrease: 0, end_amount: 0 },
      { label: '合计', begin_amount: 0, increase: 0, decrease: 0, end_amount: 150000, is_total: true },
    ])
    expect(sent.sub_table_data._note_texts).toEqual([
      { section: 'm7-listed-note', title: '专项储备变动说明', text: '安全生产费按财资〔2022〕136号计提' },
    ])
  })

  it('国企：合计非 0 即取数（安全生产费 0 也照改），计提依据进备注列，与 Tab 逐字节相同', async () => {
    const tabSent = await tabPayload('soe', SOE_RESPONSES)
    const { out, sent } = await headlessPayload('soe', SOE_RESPONSES)
    expect(out.sections.map((s) => s.section)).toEqual(['八、61'])
    expect(J(sent)).toBe(J(tabSent))
    expect(sent.sub_table_data['专项储备']).toEqual([
      { label: '安全生产费', begin_amount: 0, increase: 0, decrease: 0, end_amount: 0, remark: '' },
      { label: '维简费', begin_amount: 0, increase: 0, decrease: 0, end_amount: 500, remark: '财企〔2012〕16号' },
      { label: '其他专项储备', begin_amount: 0, increase: 0, decrease: 0, end_amount: 0, remark: '' },
      { label: '合计', begin_amount: 0, increase: 0, decrease: 0, end_amount: 500, is_total: true, remark: '' },
    ])
    expect(sent.sub_table_data._note_texts?.[0]?.text).toBe('维简费说明')
  })

  it('合计与安全生产费都为 0：不改期末（与 Tab 同门槛），无说明', async () => {
    const list: MResponseFixture = [r('M7-1-safety-subtotal', '0'), r('M7-1-maintenance-subtotal', '700'), r('M7-1-total-audited', '0')]
    const tabSent = await tabPayload('listed', list)
    const { sent } = await headlessPayload('listed', list)
    expect(J(sent)).toBe(J(tabSent))
    expect((sent.sub_table_data['专项储备'] as any[]).every((x) => x.end_amount === 0)).toBe(true)
    expect(sent.sub_table_data._note_texts).toBeUndefined()
  })

  it('静态接线：两个 Tab 的默认行 / 读回 / 取数应用 / 快照都调共用函数', () => {
    const dir = resolve(__dirname, '../../m7/core')
    for (const [file, variant, create] of [
      ['M7TabDisclosureListed.vue', 'listed', 'createM7ListedDisclosureRows'],
      ['M7TabDisclosureSoe.vue', 'soe', 'createM7SoeDisclosureRows'],
    ] as const) {
      const src = readFileSync(resolve(dir, file), 'utf-8')
      expect(src, file).toContain(`>(${create}())`)
      expect(src, file).toContain('sources: M7_AUTO_FILL_SOURCES,')
      expect(src, file).toContain('if (applyM7AutoFill(disclosureRows.value, v)) {')
      expect(src, file).toContain(`restoreM7Disclosure(formData.allResponses.value, '${variant}', disclosureRows.value)`)
      expect(src, file).toContain(`buildM7TabSyncPayload(props.wpId, '${variant}', disclosureRows.value, disclosureNote.value)`)
      expect(src, file).not.toMatch(/buildMEquitySyncPayload\(|'M7-1-safety-subtotal'|row-\$\{i\}/)
    }
  })
})
