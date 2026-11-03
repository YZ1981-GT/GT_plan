/**
 * I5 其他非流动资产披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①离屏请求体与「Tab 同参实例化 useI5Disclosure → 调 Tab 的同步函数 `syncToNotes`（与 I5-2 明细有差额时先确认，
 * 这里按「仍要同步」）」经 Tab 通道发出的载荷逐字节相同；夹具有真实数据（账面余额 / 减值 / 账面价值两期 + 说明）
 * ②旧变动矩阵键与 Tab 同样迁移读 ③离屏不弹确认、不走 Tab 的 api 通道、不写底稿，只读 I5- 条目 ④离屏不挂生命周期钩子、
 * 不订阅审定事件，组件内照旧订阅 ⑤口径不适用回空 ⑥Tab 的同步就是 composable 的 syncToNotes，后者取 buildSyncPayloads。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, defineComponent, effectScope, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), apiPost: vi.fn(), confirm: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: h.apiPost } }))
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: h.confirm },
}))

import { i5HeadlessProvider } from '../i5HeadlessDisclosure'
import { useI5Disclosure } from '../useI5Disclosure'
import { I5_LISTED_SUBTABLE, I5_SOE_SUBTABLE } from '../i5NoteSectionMap'

const J = JSON.stringify
type Resp = { item_id: string; remark: string | null; conclusion: string | null }
const r = (item_id: string, remark: unknown): Resp => ({
  item_id, remark: typeof remark === 'string' ? remark : J(remark), conclusion: null,
})
const NOISE = [r('I50-disc-listed-rows', [{ item: '别的底稿', endGross: 9 }]), r('K1-unrelated', '999')]

const LISTED = [
  r('I5-disc-listed-rows', [
    { rowId: 'r1', item: '预付土地出让金', endGross: 100000, endImpairment: 0, priorGross: 80000, priorImpairment: 0 },
    { rowId: 'r2', item: '合同资产', endGross: 50000, endImpairment: 5000, priorGross: 40000, priorImpairment: 2000 },
  ]),
  r('I5-disc-listed-other-note', '其他非流动资产主要为预付土地款。'),
  // I5-2 明细与披露期末有差额 ⇒ Tab 同步前先确认
  r('I5-2-rows', [{ category: '预付土地出让金', endBalance: 90000, netValue: 90000, beginBalance: 80000 }]),
  ...NOISE,
]
/** 国企：只有旧版变动矩阵键（期初 / 增减 / 期末） */
const SOE_LEGACY = [
  r('I5-disc-soe-movement-matrix', [{ rowId: 'm1', item: '预付设备款', beginBalance: 300, increase: 100, decrease: 50, endBalance: 350 }]),
  r('I5-disc-soe-other-note', '国企其他非流动资产说明。'),
  ...NOISE,
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-i5', wpCode: 'I5' }
const LISTED_CTX = { ...CTX, variant: 'listed' as const, applicableStandards: ['listed_standalone'] }
const SOE_CTX = { ...CTX, variant: 'soe' as const, applicableStandards: ['soe_standalone'] }
const SYNC_URL = '/api/projects/p1/disclosure-notes/sync-from-workpaper'
const WP = resolve(__dirname, '../..')

const own = (list: Resp[]) => new Map(list.filter((x) => x.item_id.startsWith('I5-')).map((x) => [x.item_id, { ...x }]))

/** Tab 路径：Tab 同参实例化 → 调 Tab 的同步函数（composable 的 syncToNotes）→ 截下它经 Tab 通道发出的载荷 */
async function tabSent(variant: 'listed' | 'soe', list: Resp[], stds: string[]) {
  const map = own(list)
  const scope = effectScope(true)
  try {
    const disc = scope.run(() => useI5Disclosure(computed(() => 'wp-i5'), computed(() => 'p1'), computed(() => map), {
      variant: ref(variant),
      applicableStandards: () => stds,
      onSave: () => {},
    }))!
    await nextTick()
    h.apiPost.mockClear()
    await disc.syncToNotes()
    return h.apiPost.mock.calls.filter(([url]) => url === SYNC_URL).map(([, body]) => body)
  } finally {
    scope.stop()
  }
}

describe('i5HeadlessProvider', () => {
  let listen: ReturnType<typeof vi.spyOn>
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.post.mockResolvedValue({ rows_synced: 3, push_kept: [] })
    h.apiPost.mockResolvedValue({ rows_synced: 3 })
    h.confirm.mockResolvedValue('confirm')
    listen = vi.spyOn(window, 'addEventListener')
  })
  afterEach(() => listen.mockRestore())

  it('上市：请求体与 Tab 同步（差额确认后）逐字节相同，静默写 五、31，不弹确认、不写底稿', async () => {
    h.get.mockResolvedValue(LISTED)
    const out = await i5HeadlessProvider(LISTED_CTX)
    expect(out).toEqual({ sections: [{ section: '五、31', rows: 3, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-i5/checklist-responses', expect.anything())
    expect(h.confirm).not.toHaveBeenCalled()
    expect(h.apiPost).not.toHaveBeenCalled()
    expect(h.put).not.toHaveBeenCalled()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe(SYNC_URL)
    expect(cfg).toMatchObject({ _silent: true })
    const bodies = await tabSent('listed', LISTED, LISTED_CTX.applicableStandards)
    expect(h.confirm).toHaveBeenCalledTimes(1)
    expect(bodies).toHaveLength(1)
    expect(J(sent)).toBe(J(bodies[0]))
    const rows = sent.sub_table_data[I5_LISTED_SUBTABLE.main] as Array<Record<string, unknown>>
    expect(rows.find((x) => x.label === '合同资产')).toMatchObject({ end_book: 50000, end_impair: 5000, end_carrying: 45000, prior_carrying: 38000 })
    expect(rows.at(-1)).toMatchObject({ label: '合计', end_carrying: 145000, prior_carrying: 118000, is_total: true })
    expect(sent.sub_table_data._note_texts).toEqual([
      { section: 'listed-other', title: '其他非流动资产说明', text: '其他非流动资产主要为预付土地款。' },
    ])
  })

  it('国企·旧变动矩阵键：与 Tab 同样迁移读，请求体与 Tab 逐字节相同，写 八、32', async () => {
    h.get.mockResolvedValue(SOE_LEGACY)
    const out = await i5HeadlessProvider(SOE_CTX)
    expect(out.sections).toEqual([{ section: '八、32', rows: 3, kept: 0 }])
    const sent = h.post.mock.calls[0][1]
    expect(J(sent)).toBe(J((await tabSent('soe', SOE_LEGACY, SOE_CTX.applicableStandards))[0]))
    expect(sent.sub_table_data[I5_SOE_SUBTABLE.main][0]).toMatchObject({ label: '预付设备款', 期末余额: 350, 年初余额: 300 })
  })

  it('离屏不挂生命周期钩子、不订阅审定事件；组件内照旧订阅', async () => {
    const warn = vi.spyOn(console, 'warn')
    h.get.mockResolvedValue(SOE_LEGACY)
    await i5HeadlessProvider(SOE_CTX)
    expect(listen.mock.calls.some(([type]) => type === 'substantive:adjudicated')).toBe(false)
    expect(warn.mock.calls.some((args) => String(args[0]).includes('no active component instance'))).toBe(false)
    warn.mockRestore()
    const w = mount(defineComponent({
      setup() {
        useI5Disclosure(ref('wp-i5'), ref('p1'), ref(new Map()), { variant: 'soe' })
        return () => null
      },
    }))
    expect(listen.mock.calls.some(([type]) => type === 'substantive:adjudicated')).toBe(true)
    w.unmount()
  })

  it('口径不适用（国企项目的上市版）：回空，不发请求', async () => {
    h.get.mockResolvedValue(LISTED)
    const out = await i5HeadlessProvider({ ...LISTED_CTX, applicableStandards: ['soe_standalone'] })
    expect(out).toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('静态接线：Tab 同步调 composable 的 syncToNotes，后者取 buildSyncPayloads', () => {
    for (const [file, variant] of [['I5TabDisclosureListed.vue', 'listed'], ['I5TabDisclosureSoe.vue', 'soe']] as const) {
      const src = readFileSync(resolve(WP, `i5/core/${file}`), 'utf-8')
      expect(src).toContain(`const variant = ref<'${variant}'>('${variant}')`)
      expect(src).toMatch(/useI5Disclosure\(\s*computed\(\(\) => props\.wpId\),\s*computed\(\(\) => props\.projectId\),\s*computed\(\(\) => props\.allResponses\),\s*\{\s*variant,\s*applicableStandards: \(\) => props\.applicableStandards,/)
      expect(src).toContain('await disc.syncToNotes()')
    }
    const composable = readFileSync(resolve(__dirname, '../useI5Disclosure.ts'), 'utf-8')
    const body = composable.slice(composable.indexOf('async function syncToNotes'), composable.indexOf('async function generateNoteText'))
    expect(body).toContain('const payloads = buildSyncPayloads()')
    expect(body).not.toContain('buildI5ListedSyncPayloads(')
  })
})
