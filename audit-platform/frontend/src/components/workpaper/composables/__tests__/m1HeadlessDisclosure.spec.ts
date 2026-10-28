/**
 * M1 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①挂载真实的两个披露 Tab（onMounted 经 useM1FormData 取回复、读回表格），调 Tab 的同步函数，截下它发出的
 * 载荷，与离屏 provider 发出的逐字节相同；夹具有真实金额 ②快照缺陷修复后的值（原值见各用例注释）③只读 M1- 条目
 * （M10- / K3- 噪声不进）、离屏不写底稿 ④两口径分别写 八、42 / 五、42，只推「应付股利」表、不带 _removed_table_keys
 * （与 K3 / L2 共用章节，不删别人的子表）⑤章节保护命中不发请求 ⑥Tab 接线：默认行 / 读回 / 快照都走 m1DisclosureForm。
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
}))

import M1TabDisclosureListed from '../../m1/core/M1TabDisclosureListed.vue'
import M1TabDisclosureSoe from '../../m1/core/M1TabDisclosureSoe.vue'
import { m1HeadlessProvider } from '../m1HeadlessDisclosure'
import { M1_SOE_SUBTABLES, M1_LISTED_SUBTABLES } from '../m1NoteSectionMap'
import { M_SYNC_URL, payloadFromMTab, type MResponseFixture } from './_mDisclosureTabHarness'

const J = JSON.stringify
const r = (item_id: string, remark: string | null) => ({ item_id, remark, conclusion: null })
const NOISE = [
  r('M10-disclosure-soe-0-endBalance', '777'),
  r('M10-disclosure-listed-0-endAmount', '777'),
  r('K3-disclosure-soe-rows', '[]'),
]
/** 国企：第 0 行两列、第 1 行期末、第 2 行期初是非数字（读回按 0）、合计输入行手填了 9999；另有说明文本（不进载荷） */
const SOE_RESPONSES: MResponseFixture = [
  r('M1-disclosure-soe-0-beginBalance', '1200'),
  r('M1-disclosure-soe-0-endBalance', '1500.5'),
  r('M1-disclosure-soe-1-endBalance', '300'),
  r('M1-disclosure-soe-2-beginBalance', 'abc'),
  r('M1-disclosure-soe-3-endBalance', '9999'),
  r('M1-disclosure-soe-capital', '国有资本经营收益上缴说明'),
  ...NOISE,
]
/** 上市：股东A 两列、股东C 期末、合计输入行手填了 5000 */
const LISTED_RESPONSES: MResponseFixture = [
  r('M1-disclosure-listed-0-endAmount', '800'),
  r('M1-disclosure-listed-0-priorYearEnd', '650'),
  r('M1-disclosure-listed-2-endAmount', '120'),
  r('M1-disclosure-listed-4-endAmount', '5000'),
  r('M1-disclosure-listed-policy', '分红政策说明'),
  ...NOISE,
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-m1', wpCode: 'M1' }
const SOE = { ...CTX, variant: 'soe' as const, applicableStandards: ['soe_standalone'] }
const LISTED = { ...CTX, variant: 'listed' as const, applicableStandards: ['listed_standalone'] }

async function tabPayload(variant: 'soe' | 'listed', responses: MResponseFixture): Promise<any> {
  const Comp = variant === 'soe' ? M1TabDisclosureSoe : M1TabDisclosureListed
  return payloadFromMTab(Comp, { apiGet: h.apiGet, post: h.post }, { wpId: 'wp-m1', responses })
}

describe('m1HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.post.mockResolvedValue({ rows_synced: 4, push_kept: [] })
  })

  it('国企：载荷与挂载的 Tab 逐字节相同，静默写 八、42、只读 M1- 条目、不写底稿', async () => {
    const tabSent = await tabPayload('soe', SOE_RESPONSES)
    h.post.mockClear()
    h.get.mockResolvedValue(SOE_RESPONSES)
    const out = await m1HeadlessProvider(SOE)
    expect(out).toEqual({ sections: [{ section: '八、42', rows: 4, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-m1/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiPut).not.toHaveBeenCalled()
    expect(h.post).toHaveBeenCalledTimes(1)
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe(M_SYNC_URL)
    expect(cfg).toMatchObject({ _silent: true })
    expect(J(sent)).toBe(J(tabSent))
    expect(sent).toMatchObject({ wp_id: 'wp-m1', section_id: '八、42', current_standard: 'soe_standalone' })
    // 修复后的值。原快照读不存在的 endAmount / priorAmount ⇒ 两列恒 0，且表格的「合计」输入行（9999）被当明细
    // 发出、builder 再追加自算合计（= 明细 + 9999）⇒ 附注里两行合计
    expect(sent.sub_table_data[M1_SOE_SUBTABLES.dividend]).toEqual([
      { label: '应付国有股东股利', end_amount: 1500.5, prior_amount: 1200 },
      { label: '应付法人股东股利', end_amount: 300, prior_amount: 0 },
      { label: '应付其他股东股利', end_amount: 0, prior_amount: 0 },
      { label: '合计', end_amount: 1800.5, prior_amount: 1200, is_total: true },
    ])
    expect(Object.keys(sent.sub_table_data)).toEqual([M1_SOE_SUBTABLES.dividend])
    expect(Object.keys(sent.columns)).toEqual([M1_SOE_SUBTABLES.dividend])
  })

  it('上市：载荷与挂载的 Tab 逐字节相同，写 五、42；上年年末余额按 priorYearEnd 取（原值恒 0）', async () => {
    const tabSent = await tabPayload('listed', LISTED_RESPONSES)
    h.post.mockClear()
    h.get.mockResolvedValue(LISTED_RESPONSES)
    const out = await m1HeadlessProvider(LISTED)
    expect(out.sections.map((s) => s.section)).toEqual(['五、42'])
    const sent = h.post.mock.calls[0][1]
    expect(J(sent)).toBe(J(tabSent))
    // 原快照：上年年末余额读不存在的 priorAmount ⇒ 恒 0；合计输入行（5000）重复发出，自算合计 = 920 + 5000
    expect(sent.sub_table_data[M1_LISTED_SUBTABLES.dividend]).toEqual([
      { label: '股东A（境内法人）', end_amount: 800, prior_amount: 650 },
      { label: '股东B（境内自然人）', end_amount: 0, prior_amount: 0 },
      { label: '股东C（境外法人）', end_amount: 120, prior_amount: 0 },
      { label: '股东D（其他）', end_amount: 0, prior_amount: 0 },
      { label: '合计', end_amount: 920, prior_amount: 650, is_total: true },
    ])
    // 「超过1年未支付」表暂无录入区块 ⇒ 不推、也不进 _removed_table_keys（不删 K3 写的同名表）
    expect(Object.keys(sent.sub_table_data)).toEqual([M1_LISTED_SUBTABLES.dividend])
    expect(sent.sub_table_data._removed_table_keys).toBeUndefined()
  })

  it('没有任何回复：按默认行发出（金额全 0 + 合计），与 Tab 相同', async () => {
    const tabSent = await tabPayload('soe', NOISE)
    h.post.mockClear()
    h.get.mockResolvedValue(NOISE)
    await m1HeadlessProvider(SOE)
    const sent = h.post.mock.calls[0][1]
    expect(J(sent)).toBe(J(tabSent))
    expect(sent.sub_table_data[M1_SOE_SUBTABLES.dividend].at(-1)).toEqual(
      { label: '合计', end_amount: 0, prior_amount: 0, is_total: true },
    )
  })

  it('章节保护命中：不发请求，原因随结果回报', async () => {
    h.get.mockResolvedValue(SOE_RESPONSES)
    const out = await m1HeadlessProvider({ ...SOE, sectionGuard: () => '附注 八、42 已有 2 格人工填写' })
    expect(h.post).not.toHaveBeenCalled()
    expect(out).toEqual({ sections: [{ section: '八、42', rows: 0, skipped: '附注 八、42 已有 2 格人工填写' }] })
  })

  it('Tab 接线：默认行 / 读回 / 快照都调 m1DisclosureForm，组件内不再自拼', () => {
    const dir = resolve(__dirname, '../../m1/core')
    for (const [file, v] of [['M1TabDisclosureSoe.vue', 'Soe'], ['M1TabDisclosureListed.vue', 'Listed']] as const) {
      const src = readFileSync(resolve(dir, file), 'utf-8')
      expect(src, file).toContain(`const detailRows = ref(createM1${v}DisclosureRows())`)
      expect(src, file).toContain(`restoreM1${v}DisclosureRows(responses, detailRows.value)`)
      const sync = src.slice(src.indexOf('async function syncToDisclosureNotes'))
      expect(sync, file).toMatch(new RegExp(`const payload = buildM1${v}TabSyncPayload\\(props\\.wpId, detailRows\\.value\\)`))
      expect(src, file).not.toMatch(/buildM1SyncPayload\(|r\.priorAmount|M1DividendRow/)
    }
  })
})
