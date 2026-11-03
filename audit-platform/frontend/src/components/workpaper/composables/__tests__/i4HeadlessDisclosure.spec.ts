/**
 * I4 长期待摊费用披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①离屏请求体与「Tab 同参实例化 useI4Disclosure → 调 Tab 的同步函数 `syncToNotes`（披露期末与 I4-2 明细有差额时
 * 先确认，这里按「仍要同步」）」经 Tab 通道发出的载荷逐字节相同；夹具有真实数据（滚动行 / 一年内到期脚注 / 补充说明）
 * ②离屏不弹确认、不走 Tab 的 api 通道、不写底稿，只读 I4- 条目 ③离屏不挂生命周期钩子、不订阅审定事件，组件内照旧订阅
 * ④口径不适用回空 ⑤Tab 的同步就是 composable 的 syncToNotes，后者取 buildSyncPayloads（静态接线）。
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

import { i4HeadlessProvider } from '../i4HeadlessDisclosure'
import { useI4Disclosure } from '../useI4Disclosure'
import { I4_LISTED_SUBTABLE, I4_SOE_SUBTABLE } from '../i4NoteSectionMap'

const J = JSON.stringify
type Resp = { item_id: string; remark: string | null; conclusion: string | null }
const r = (item_id: string, remark: unknown): Resp => ({
  item_id, remark: typeof remark === 'string' ? remark : J(remark), conclusion: null,
})
const NOISE = [r('I40-disc-listed-rows', [{ item: '别的底稿', beginBalance: 9 }]), r('K1-unrelated', '999')]

const LISTED = [
  r('I4-disc-listed-rows', [
    { rowId: 'r1', item: '使用权资产改良及维护支出', beginBalance: 100, increase: 20, amortization: 15, otherDecrease: 5 },
    { rowId: 'r2', item: '开办费', beginBalance: 50, increase: 0, amortization: 10, otherDecrease: 0 },
  ]),
  r('I4-disc-listed-current-portion', '8'),
  r('I4-disc-listed-other-note', '长期待摊费用主要为装修改良。'),
  // I4-2 明细与披露期末有差额 ⇒ Tab 同步前先确认
  r('I4-2-rows', [{ expenseType: '开办费', auditedOpening: 50, auditedAmortization: 20, remainingMonths: 6, auditedEnding: 30 }]),
  ...NOISE,
]
const SOE = [
  r('I4-disc-soe-rows', [
    { rowId: 's1', item: '固定资产大修理支出', beginBalance: 300, increase: 0, amortization: 60, otherDecrease: 40, otherDecreaseReason: '处置转销' },
  ]),
  r('I4-disc-soe-other-note', '国企补充说明。'),
  ...NOISE,
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-i4', wpCode: 'I4' }
const LISTED_CTX = { ...CTX, variant: 'listed' as const, applicableStandards: ['listed_standalone'] }
const SOE_CTX = { ...CTX, variant: 'soe' as const, applicableStandards: ['soe_standalone'] }
const SYNC_URL = '/api/projects/p1/disclosure-notes/sync-from-workpaper'
const WP = resolve(__dirname, '../..')

const own = (list: Resp[]) => new Map(list.filter((x) => x.item_id.startsWith('I4-')).map((x) => [x.item_id, { ...x }]))

/** Tab 路径：Tab 同参实例化 → 调 Tab 的同步函数（composable 的 syncToNotes）→ 截下它经 Tab 通道发出的载荷 */
async function tabSent(variant: 'listed' | 'soe', list: Resp[], stds: string[]) {
  const saves: string[] = []
  const map = own(list)
  const scope = effectScope(true)
  try {
    const disc = scope.run(() => useI4Disclosure(computed(() => 'wp-i4'), computed(() => 'p1'), computed(() => map), {
      variant: ref(variant),
      applicableStandards: () => stds,
      onSave: (itemId) => { saves.push(itemId) },
    }))!
    await nextTick()
    h.apiPost.mockClear()
    await disc.syncToNotes()
    return { bodies: h.apiPost.mock.calls.filter(([url]) => url === SYNC_URL).map(([, body]) => body), saves }
  } finally {
    scope.stop()
  }
}

describe('i4HeadlessProvider', () => {
  let listen: ReturnType<typeof vi.spyOn>
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.post.mockResolvedValue({ rows_synced: 3, push_kept: [] })
    h.apiPost.mockResolvedValue({ rows_synced: 3 })
    h.confirm.mockResolvedValue('confirm')
    listen = vi.spyOn(window, 'addEventListener')
  })
  afterEach(() => listen.mockRestore())

  it('上市：请求体与 Tab 同步（差额确认后）逐字节相同，静默写 五、29，不弹确认、不写底稿', async () => {
    h.get.mockResolvedValue(LISTED)
    const out = await i4HeadlessProvider(LISTED_CTX)
    expect(out).toEqual({ sections: [{ section: '五、29', rows: 3, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-i4/checklist-responses', expect.anything())
    expect(h.confirm).not.toHaveBeenCalled()
    expect(h.apiPost).not.toHaveBeenCalled()
    expect(h.put).not.toHaveBeenCalled()
    expect(h.post).toHaveBeenCalledTimes(1)
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe(SYNC_URL)
    expect(cfg).toMatchObject({ _silent: true })
    const tab = await tabSent('listed', LISTED, LISTED_CTX.applicableStandards)
    expect(h.confirm).toHaveBeenCalledTimes(1)
    expect(tab.saves).toEqual([])
    expect(tab.bodies).toHaveLength(1)
    expect(J(sent)).toBe(J(tab.bodies[0]))
    const rows = sent.sub_table_data[I4_LISTED_SUBTABLE.movement] as Array<Record<string, unknown>>
    expect(rows.map((x) => [x.label, x.期末余额])).toEqual([['使用权资产改良及维护支出', 100], ['开办费', 40], ['合计', 140]])
    expect((sent.sub_table_data._note_texts as Array<{ section: string; text: string }>).map((n) => n.section))
      .toEqual(['listed-current-portion', 'listed-other'])
    expect(sent.sub_table_data._note_texts[0].text).toContain('8.00')
  })

  it('国企：请求体与 Tab 同步逐字节相同，写 八、30（摊销 / 其他减少分列 + 原因）', async () => {
    h.get.mockResolvedValue(SOE)
    const out = await i4HeadlessProvider(SOE_CTX)
    expect(out.sections).toEqual([{ section: '八、30', rows: 3, kept: 0 }])
    const sent = h.post.mock.calls[0][1]
    const tab = await tabSent('soe', SOE, SOE_CTX.applicableStandards)
    expect(J(sent)).toBe(J(tab.bodies[0]))
    expect(sent.sub_table_data[I4_SOE_SUBTABLE.movement][0]).toMatchObject({
      label: '固定资产大修理支出', 本期摊销额: 60, 其他减少额: 40, 期末余额: 200, 其他减少的原因: '处置转销',
    })
  })

  it('离屏不挂生命周期钩子、不订阅审定事件；组件内照旧订阅', async () => {
    const warn = vi.spyOn(console, 'warn')
    h.get.mockResolvedValue(SOE)
    await i4HeadlessProvider(SOE_CTX)
    expect(listen.mock.calls.some(([type]) => type === 'substantive:adjudicated')).toBe(false)
    expect(warn.mock.calls.some((args) => String(args[0]).includes('no active component instance'))).toBe(false)
    warn.mockRestore()
    const w = mount(defineComponent({
      setup() {
        useI4Disclosure(ref('wp-i4'), ref('p1'), ref(new Map()), { variant: 'soe' })
        return () => null
      },
    }))
    expect(listen.mock.calls.some(([type]) => type === 'substantive:adjudicated')).toBe(true)
    w.unmount()
  })

  it('口径不适用（上市项目的国企版）：回空，不发请求', async () => {
    h.get.mockResolvedValue(SOE)
    const out = await i4HeadlessProvider({ ...SOE_CTX, applicableStandards: ['listed_standalone'] })
    expect(out).toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('静态接线：Tab 同步调 composable 的 syncToNotes，后者取 buildSyncPayloads', () => {
    for (const [file, variant] of [['I4TabDisclosureListed.vue', 'listed'], ['I4TabDisclosureSoe.vue', 'soe']] as const) {
      const src = readFileSync(resolve(WP, `i4/core/${file}`), 'utf-8')
      expect(src).toContain(`const variant = ref<'${variant}'>('${variant}')`)
      expect(src).toMatch(/useI4Disclosure\(\s*computed\(\(\) => props\.wpId\),\s*computed\(\(\) => props\.projectId\),\s*computed\(\(\) => props\.allResponses\),\s*\{\s*variant,\s*applicableStandards: \(\) => props\.applicableStandards,/)
      expect(src).toContain('await disc.syncToNotes()')
    }
    const composable = readFileSync(resolve(__dirname, '../useI4Disclosure.ts'), 'utf-8')
    const body = composable.slice(composable.indexOf('async function syncToNotes'), composable.indexOf('async function generateNoteText'))
    expect(body).toContain('const payloads = buildSyncPayloads()')
    expect(body).not.toContain('buildI4ListedSyncPayloads(')
  })
})
