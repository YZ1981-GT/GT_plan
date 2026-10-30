/**
 * M8 一般风险准备披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 默认三行 / 逐格读回 / 期初取 M8-2 明细期初合计 / 同步快照原在两个 Tab 里内联，抽到 `mEquityDisclosureForm` 后 Tab 与离屏共用。
 * 判据：①挂载真实 Tab（经 useM8FormData 取回复、onMounted 读回），调它的同步函数截下载荷，与离屏载荷逐字节相同（上市 五、60 /
 * 国企 八、94）②快照按表格行字段取值（原按不存在的 beginAmount / increaseAmount / decreaseAmount 取 ⇒ 恒 0）③M8-2 期初合计
 * 只在首行期初为 0 时带入（取 conclusion，与 getField 同口径）④国企专项说明不进载荷 ⑤只读 M8- 条目、离屏不写底稿 ⑥Tab 接线。
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

import M8TabDisclosureListed from '../../m8/core/M8TabDisclosureListed.vue'
import M8TabDisclosureSoe from '../../m8/core/M8TabDisclosureSoe.vue'
import { m8HeadlessProvider } from '../mEquityHeadlessDisclosure'
import { M_SYNC_URL, payloadFromMTab, type MResponseFixture } from './_mDisclosureTabHarness'

const J = JSON.stringify
const r = (item_id: string, remark: string | null, conclusion: string | null = null) => ({ item_id, remark, conclusion })

const LISTED: MResponseFixture = [
  r('M8-disclosure-listed-row-0-beginBalance', '100000'),
  r('M8-disclosure-listed-row-0-currentIncrease', '20000'),
  r('M8-disclosure-listed-row-1-currentDecrease', '5000'),
  r('M8-disclosure-listed-row-2-currentIncrease', '不是数字'),
  r('M8-2-total-beginBalance', null, '999999'),
  r('M8-disclosure-listed-note', '按风险资产期末余额 1.5% 计提'),
  r('M8-disclosure-soe-row-0-beginBalance', '777'),
]
const SOE: MResponseFixture = [
  r('M8-disclosure-soe-row-1-beginBalance', '40000'),
  r('M8-disclosure-soe-row-1-currentIncrease', '6000'),
  r('M8-2-total-beginBalance', null, '30000'),
  r('M8-disclosure-soe-note', '一般风险准备说明（国企）'),
  r('M8-disclosure-soe-special', '国资委专项说明（不进附注）'),
  r('M8-disclosure-listed-row-1-beginBalance', '888'),
]

const ctxOf = (variant: 'listed' | 'soe') => ({
  projectId: 'p1', year: 2025, wpId: 'wp-M8', wpCode: 'M8', variant, applicableStandards: [`${variant}_standalone`],
})

async function both(variant: 'listed' | 'soe', responses: MResponseFixture) {
  const Comp = variant === 'listed' ? M8TabDisclosureListed : M8TabDisclosureSoe
  const tabSent = await payloadFromMTab(Comp, { apiGet: h.apiGet, post: h.post }, { wpId: 'wp-M8', responses })
  h.post.mockClear()
  h.get.mockResolvedValue(responses)
  const out = await m8HeadlessProvider(ctxOf(variant))
  expect(h.post).toHaveBeenCalledTimes(1)
  const [url, sent, cfg] = h.post.mock.calls[0]
  expect(url).toBe(M_SYNC_URL)
  expect(cfg).toMatchObject({ _silent: true })
  return { tabSent, out, sent }
}

describe('m8HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.post.mockResolvedValue({ rows_synced: 4, push_kept: [] })
  })

  it('上市：按表格行字段取值（不再恒 0），首行已有期初时不带入 M8-2 合计；与挂载的 Tab 逐字节相同、不写底稿', async () => {
    const { tabSent, out, sent } = await both('listed', LISTED)
    expect(out).toEqual({ sections: [{ section: '五、60', rows: 4, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-M8/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiPut).not.toHaveBeenCalled()
    expect(J(sent)).toBe(J(tabSent))
    expect(sent.sub_table_data['一般风险准备']).toEqual([
      { label: '一般风险准备—信贷资产', begin_amount: 100000, increase: 20000, decrease: 0, end_amount: 120000 },
      { label: '一般风险准备—投资资产', begin_amount: 0, increase: 0, decrease: 5000, end_amount: -5000 },
      { label: '一般风险准备—其他', begin_amount: 0, increase: 0, decrease: 0, end_amount: 0 },
      { label: '合计', begin_amount: 100000, increase: 20000, decrease: 5000, end_amount: 115000, is_total: true },
    ])
    expect(sent.sub_table_data._note_texts).toEqual([
      { section: 'm8-listed-note', title: '一般风险准备说明', text: '按风险资产期末余额 1.5% 计提' },
    ])
  })

  it('国企：首行期初为 0 ⇒ 带入 M8-2 期初合计；专项说明不进载荷；与 Tab 逐字节相同', async () => {
    const { tabSent, out, sent } = await both('soe', SOE)
    expect(out.sections.map((s) => s.section)).toEqual(['八、94'])
    expect(J(sent)).toBe(J(tabSent))
    const rows = sent.sub_table_data['一般风险准备'] as any[]
    expect(rows[0]).toEqual({ label: '一般风险准备—信贷资产', begin_amount: 30000, increase: 0, decrease: 0, end_amount: 30000 })
    expect(rows[1]).toEqual({ label: '一般风险准备—投资资产', begin_amount: 40000, increase: 6000, decrease: 0, end_amount: 46000 })
    expect(J(sent)).not.toContain('国资委专项说明')
    expect(sent.sub_table_data._note_texts?.[0]?.text).toBe('一般风险准备说明（国企）')
  })

  it('静态接线：两个 Tab 的默认行 / 读回 / 快照都调共用函数，不再按不存在的字段取值', () => {
    const dir = resolve(__dirname, '../../m8/core')
    for (const [file, variant] of [['M8TabDisclosureListed.vue', 'listed'], ['M8TabDisclosureSoe.vue', 'soe']] as const) {
      const src = readFileSync(resolve(dir, file), 'utf-8')
      expect(src, file).toContain('const dataRows = ref<DisclosureDataRow[]>(createM8DisclosureRows())')
      expect(src.replace(/\(\s+/g, '(').replace(/\s+/g, ' '), file).toContain(
        `restoreM8Disclosure(formData.allResponses.value, '${variant}', dataRows.value, formData.getField('2', 'total-beginBalance'),`,
      )
      expect(src, file).toContain(`buildM8TabSyncPayload(props.wpId, '${variant}', dataRows.value, disclosureNote.value)`)
      expect(src, file).not.toMatch(/beginAmount|increaseAmount|decreaseAmount|buildM8SyncPayload\(/)
    }
  })
})
