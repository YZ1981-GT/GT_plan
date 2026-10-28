/**
 * I6 研发费用披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①离屏请求体与「Tab 同参实例化 useI6Disclosure → 打开后静置（越过 300ms 防抖）→ 调 Tab 的同步函数 `syncToNotes`
 * （分项差异先确认，这里按「仍要同步」）」经 Tab 通道发出的载荷逐字节相同 ②不跑「从 I6-2 静默刷新」：I6-2 明细与已存披露行
 * 不一致时，Tab 打开时看到的就是已存行（`I6-2-detail-rows` 的 watcher 不是 immediate，静态钉住），离屏同此
 * ③离屏不弹确认、不走 Tab 的 api 通道、不写底稿，只读 I6- 条目 ④离屏不挂生命周期钩子、不订阅审定 / 调整回写事件，组件内照旧
 * ⑤口径不适用回空 ⑥Tab 的同步就是 composable 的 syncToNotes，后者取 buildSyncPayloads（静态接线）。
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

import { i6HeadlessProvider } from '../i6HeadlessDisclosure'
import { useI6Disclosure } from '../useI6Disclosure'
import { I6_LISTED_SUBTABLE, I6_SOE_SUBTABLE } from '../i6NoteSectionMap'

const J = JSON.stringify
type Resp = { item_id: string; remark: string | null; conclusion: string | null }
const r = (item_id: string, remark: unknown): Resp => ({
  item_id, remark: typeof remark === 'string' ? remark : J(remark), conclusion: null,
})
const NOISE = [r('I60-disc-listed-rows', [{ item: '别的底稿', currentAmount: 9 }]), r('K1-unrelated', '999')]

const LISTED = [
  r('I6-disc-listed-rows', [
    { rowId: 'a1', item: '人工费', currentAmount: 100000, priorAmount: 80000, isAutoFilled: true },
    { rowId: 'a2', item: '材料费', currentAmount: 50000, priorAmount: 40000, isAutoFilled: false },
  ]),
  r('I6-disc-L-capitalization', '本期研发支出资本化比例 10%。'),
  r('I6-disc-L-projects', '重要研发项目为 X 平台。'),
  // I6-2 明细与已存披露行不一致：若跑了静默刷新，自动行「人工费」会变成 150000
  r('I6-2-detail-rows', [{ expenseNature: '人工费', auditedAmount: 150000, priorAudited: 80000 }]),
  ...NOISE,
]
const SOE = [
  r('I6-disc-soe-rows', [{ rowId: 's1', item: '委外研发费', currentAmount: 30000, priorAmount: 20000 }]),
  r('I6-disc-S-supplement', '国企研发费用补充说明。'),
  ...NOISE,
]
/** 国企旧键（`I6-disc-S-categories`，字段是旧名 项目 / 本期发生额 / 上期发生额） */
const SOE_LEGACY = [r('I6-disc-S-categories', [{ rowId: 'o1', 项目: '设计费', 本期发生额: 7000, 上期发生额: 5000 }]), ...NOISE]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-i6', wpCode: 'I6' }
const LISTED_CTX = { ...CTX, variant: 'listed' as const, applicableStandards: ['listed_standalone'] }
const SOE_CTX = { ...CTX, variant: 'soe' as const, applicableStandards: ['soe_standalone'] }
const SYNC_URL = '/api/projects/p1/disclosure-notes/sync-from-workpaper'
const WP = resolve(__dirname, '../..')

const own = (list: Resp[]) => new Map(list.filter((x) => x.item_id.startsWith('I6-')).map((x) => [x.item_id, { ...x }]))

/** Tab 路径：Tab 同参实例化 → 静置越过防抖 → 调 Tab 的同步函数（composable 的 syncToNotes）→ 截下 Tab 通道发出的载荷 */
async function tabSent(variant: 'listed' | 'soe', list: Resp[], stds: string[]) {
  const saves: string[] = []
  const map = own(list)
  const scope = effectScope(true)
  try {
    const disc = scope.run(() => useI6Disclosure(computed(() => 'wp-i6'), computed(() => 'p1'), computed(() => map), {
      variant: ref(variant),
      applicableStandards: () => stds,
      onSave: (itemId) => { saves.push(itemId) },
    }))!
    await nextTick()
    await new Promise((done) => setTimeout(done, 350))
    h.apiPost.mockClear()
    await disc.syncToNotes()
    return { bodies: h.apiPost.mock.calls.filter(([url]) => url === SYNC_URL).map(([, body]) => body), saves }
  } finally {
    scope.stop()
  }
}

describe('i6HeadlessProvider', () => {
  let listen: ReturnType<typeof vi.spyOn>
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.post.mockResolvedValue({ rows_synced: 3, push_kept: [] })
    h.apiPost.mockResolvedValue({ rows_synced: 3 })
    h.confirm.mockResolvedValue('confirm')
    listen = vi.spyOn(window, 'addEventListener')
  })
  afterEach(() => listen.mockRestore())

  it('上市：已存披露行（不按 I6-2 静默刷新），请求体与 Tab 同步逐字节相同，静默写 五、66，不弹确认、不写底稿', async () => {
    h.get.mockResolvedValue(LISTED)
    const out = await i6HeadlessProvider(LISTED_CTX)
    expect(out).toEqual({ sections: [{ section: '五、66', rows: 3, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-i6/checklist-responses', expect.anything())
    expect(h.confirm).not.toHaveBeenCalled()
    expect(h.apiPost).not.toHaveBeenCalled()
    expect(h.put).not.toHaveBeenCalled()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe(SYNC_URL)
    expect(cfg).toMatchObject({ _silent: true })
    const tab = await tabSent('listed', LISTED, LISTED_CTX.applicableStandards)
    expect(tab.saves, 'Tab 打开静置期间不应静默刷新并保存').toEqual([])
    expect(h.confirm).toHaveBeenCalledTimes(1)
    expect(J(sent)).toBe(J(tab.bodies[0]))
    expect(sent.sub_table_data[I6_LISTED_SUBTABLE.expenseByNature]).toEqual([
      { label: '人工费', 本期发生额: 100000, 上期发生额: 80000, row_type: 'data' },
      { label: '材料费', 本期发生额: 50000, 上期发生额: 40000, row_type: 'data' },
      { label: '合计', 本期发生额: 150000, 上期发生额: 120000, row_type: 'total' },
    ])
    expect((sent.sub_table_data._note_texts as Array<{ section: string }>).map((n) => n.section))
      .toEqual(['listed-capitalization', 'listed-projects'])
  })

  it('国企：请求体与 Tab 同步逐字节相同，写 八、67；旧键同样兼容读', async () => {
    h.get.mockResolvedValue(SOE)
    const out = await i6HeadlessProvider(SOE_CTX)
    expect(out.sections).toEqual([{ section: '八、67', rows: 3, kept: 0 }])
    const sent = h.post.mock.calls[0][1]
    expect(J(sent)).toBe(J((await tabSent('soe', SOE, SOE_CTX.applicableStandards)).bodies[0]))
    expect(sent.sub_table_data[I6_SOE_SUBTABLE.expenseByNature][0]).toMatchObject({ label: '委外研发费', 本期发生额: 30000 })
    expect(sent.sub_table_data._note_texts).toEqual([
      { section: 'soe-supplement', title: '研发费用补充说明', text: '国企研发费用补充说明。' },
    ])

    h.post.mockClear()
    h.get.mockResolvedValue(SOE_LEGACY)
    await i6HeadlessProvider(SOE_CTX)
    const legacy = h.post.mock.calls[0][1]
    expect(J(legacy)).toBe(J((await tabSent('soe', SOE_LEGACY, SOE_CTX.applicableStandards)).bodies[0]))
    expect(legacy.sub_table_data[I6_SOE_SUBTABLE.expenseByNature][0]).toMatchObject({ label: '设计费', 本期发生额: 7000, 上期发生额: 5000 })
  })

  it('离屏不挂生命周期钩子、不订阅审定 / 调整回写事件；组件内照旧订阅', async () => {
    const warn = vi.spyOn(console, 'warn')
    h.get.mockResolvedValue(LISTED)
    await i6HeadlessProvider(LISTED_CTX)
    const types = () => listen.mock.calls.map(([type]) => type)
    expect(types()).not.toContain('substantive:adjudicated')
    expect(types()).not.toContain('i6:adjustment-writeback')
    expect(warn.mock.calls.some((args) => String(args[0]).includes('no active component instance'))).toBe(false)
    warn.mockRestore()
    const w = mount(defineComponent({
      setup() {
        useI6Disclosure(ref('wp-i6'), ref('p1'), ref(new Map()), { variant: 'listed' })
        return () => null
      },
    }))
    expect(types()).toContain('substantive:adjudicated')
    expect(types()).toContain('i6:adjustment-writeback')
    w.unmount()
  })

  it('口径不适用（国企项目的上市版）：回空，不发请求', async () => {
    h.get.mockResolvedValue(LISTED)
    const out = await i6HeadlessProvider({ ...LISTED_CTX, applicableStandards: ['soe_standalone'] })
    expect(out).toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('静态接线：Tab 同步调 composable 的 syncToNotes（取 buildSyncPayloads）；I6-2 明细 watcher 仍非 immediate', () => {
    for (const [file, variant] of [['I6TabDisclosureListed.vue', 'listed'], ['I6TabDisclosureSoe.vue', 'soe']] as const) {
      const src = readFileSync(resolve(WP, `i6/core/${file}`), 'utf-8')
      expect(src).toContain(`const variant = ref<'${variant}'>('${variant}')`)
      expect(src).toMatch(/useI6Disclosure\(\s*computed\(\(\) => props\.wpId\),\s*computed\(\(\) => props\.projectId\),\s*computed\(\(\) => props\.allResponses\),\s*\{\s*variant,\s*applicableStandards: \(\) => props\.applicableStandards,/)
      expect(src).toContain('await disc.syncToNotes()')
    }
    const composable = readFileSync(resolve(__dirname, '../useI6Disclosure.ts'), 'utf-8')
    const body = composable.slice(composable.indexOf('async function syncToNotes'), composable.indexOf('async function generateNoteText'))
    expect(body).toContain('const payloads = buildSyncPayloads()')
    expect(body).not.toContain('buildI6ListedSyncPayloads(')
    const watcher = composable.match(
      /watch\(\s*\(\) => allResponses\.value\.get\('I6-2-detail-rows'\)\?\.remark,\s*\(\) => \{[\s\S]*?_autoRefreshFromWorkpaper\(\), 300\)\s*\},\s*\)/,
    )
    expect(watcher, '找不到 I6-2 明细 watcher（写法变了先核对离屏是否要显式刷新）').toBeTruthy()
    expect(watcher![0]).not.toContain('immediate')
  })
})
