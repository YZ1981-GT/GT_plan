/**
 * I3 商誉披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①离屏请求体与「外壳 useI3CrossSheet → Tab 同参实例化 useI3Disclosure → 挂载 applyAutoFill → getSyncSnapshot →
 * builder」（外壳 GtI3Goodwill + Tab onMounted / syncToNotes 的同一步骤）逐字节相同；夹具有真实数据
 * ②没有已存矩阵时与 Tab 挂载同口径从 I3-2 明细取数；已存矩阵不被覆盖；连明细都没有时补合计行（Tab「矩阵都为空不同步」
 * 的拦截因此不会触发）③离屏不挂生命周期钩子、不订阅审定事件，组件内照旧订阅 ④只读 I3- 条目、静默发出、不写底稿
 * ⑤Tab / 外壳接线（静态）。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, defineComponent, effectScope, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), apiPost: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: h.apiPost } }))

import { i3HeadlessProvider } from '../i3HeadlessDisclosure'
import { useI3Disclosure } from '../useI3Disclosure'
import { useI3CrossSheet } from '../useI3CrossSheet'
import { buildI3ListedSyncPayloads, buildI3SoeSyncPayloads } from '../i3DisclosureSyncPayload'
import { I3_LISTED_SUBTABLE, I3_SOE_SUBTABLE } from '../i3NoteSectionMap'

const J = JSON.stringify
type Resp = { item_id: string; remark: string | null; conclusion: string | null }
const r = (item_id: string, remark: unknown): Resp => ({
  item_id, remark: typeof remark === 'string' ? remark : J(remark), conclusion: null,
})
const NOISE = [r('I30-2-rows', [{ investee: '别的底稿', costOpening: 9 }]), r('K1-unrelated', '999')]

const DETAIL = [
  { rowId: 'd1', investee: '甲公司', cguName: '甲资产组', costOpening: 1000, costIncrease: 200, costDecrease: 0, costEnding: 1200,
    mergerType: '非同一控制下企业合并', impOpening: 100, impIncrease: 50, impDecrease: 0, impEnding: 150, costAudited: 1200, impAudited: 150 },
  { rowId: 'd2', investee: '乙公司', cguName: '乙资产组', costOpening: 500, costIncrease: 0, costDecrease: 100, costEnding: 400,
    impOpening: 0, impIncrease: 0, impDecrease: 0, impEnding: 0, costAudited: 400, impAudited: 0 },
]
/** 上市：没有已存矩阵 ⇒ 挂载时从 I3-2 明细取数（含业绩承诺预填）；已存说明与关键假设 */
const LISTED = [
  r('I3-2-rows', DETAIL),
  r('I3-disc-listed-impairment_test_process-note', '采用预计未来现金流量现值法。'),
  r('I3-disc-listed-assumption-params', [{ rowId: 'ap1', label: '甲资产组', grossMargin: '28%', growthRate: '5%', discountRate: '12%' }]),
  ...NOISE,
]
/** 国企：已存矩阵 ⇒ 挂载取数不覆盖（I3-2 另有一行不同的明细） */
const SOE = [
  r('I3-disc-soe-book-value-matrix', [{ rowId: 'bv-1', investee: '丙公司', beginBalance: 800, increase: 0, decrease: 0, endBalance: 800, isAutoFilled: false }]),
  r('I3-disc-soe-impairment-matrix', [{ rowId: 'imp-1', investee: '丙公司', beginBalance: 0, increase: 80, decrease: 0, endBalance: 80, isAutoFilled: false }]),
  r('I3-disc-soe-key_assumptions-note', '折现率 11%。'),
  r('I3-2-rows', [{ rowId: 'd9', investee: '丁公司', costOpening: 999, costEnding: 999 }]),
  ...NOISE,
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-i3', wpCode: 'I3' }
const LISTED_CTX = { ...CTX, variant: 'listed' as const, applicableStandards: ['listed_standalone'] }
const SOE_CTX = { ...CTX, variant: 'soe' as const, applicableStandards: ['soe_standalone'] }
const SYNC_URL = '/api/projects/p1/disclosure-notes/sync-from-workpaper'
const WP = resolve(__dirname, '../..')

const own = (list: Resp[]) => new Map(list.filter((x) => x.item_id.startsWith('I3-')).map((x) => [x.item_id, { ...x }]))

/** Tab 路径：外壳算跨 sheet 取数 → Tab 同参实例化 → onMounted 的 applyAutoFill → syncToNotes 的快照与 builder */
async function tabSync(variant: 'listed' | 'soe', list: Resp[], stds: string[]) {
  const scope = effectScope(true)
  try {
    const disc = scope.run(() => {
      const allResponses = ref(own(list))
      const crossSheet = useI3CrossSheet(allResponses)
      return useI3Disclosure(ref('wp-i3'), ref('p1'), computed(() => allResponses.value) as any, {
        variant: ref(variant) as any,
        crossSheetAutoFill: computed(() => crossSheet.disclosureAutoFill.value ?? {}),
        onSave: () => {},
      })
    })!
    await nextTick()
    disc.applyAutoFill()
    const snap = disc.getSyncSnapshot()
    const blockedByEmpty = !snap.bookValueRows.length && !snap.impairmentRows.length
    const payloads = variant === 'listed'
      ? buildI3ListedSyncPayloads('wp-i3', stds || [], snap)
      : buildI3SoeSyncPayloads('wp-i3', stds || [], snap)
    return { blockedByEmpty, payloads }
  } finally {
    scope.stop()
  }
}

describe('i3HeadlessProvider', () => {
  let warn: ReturnType<typeof vi.spyOn>
  let listen: ReturnType<typeof vi.spyOn>
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.post.mockResolvedValue({ rows_synced: 12, push_kept: [] })
    warn = vi.spyOn(console, 'warn')
    listen = vi.spyOn(window, 'addEventListener')
  })
  afterEach(() => {
    warn.mockRestore()
    listen.mockRestore()
  })

  it('上市：没有已存矩阵 ⇒ 与 Tab 挂载同口径从 I3-2 取数，请求体与 Tab 逐字节相同，静默写 五、28、不写底稿', async () => {
    h.get.mockResolvedValue(LISTED)
    const out = await i3HeadlessProvider(LISTED_CTX)
    expect(out).toEqual({ sections: [{ section: '五、28', rows: 12, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-i3/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiPost).not.toHaveBeenCalled()
    expect(h.post).toHaveBeenCalledTimes(1)
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe(SYNC_URL)
    expect(cfg).toMatchObject({ _silent: true })
    const tab = await tabSync('listed', LISTED, LISTED_CTX.applicableStandards)
    expect(tab.blockedByEmpty).toBe(false)
    expect(J(sent)).toBe(J(tab.payloads[0]))
    const data = sent.sub_table_data
    expect(data[I3_LISTED_SUBTABLE.bookValue].map((x: any) => [x.label, x.期末余额])).toEqual([
      ['甲公司', 1200], ['乙公司', 400], ['合计', 1600],
    ])
    expect(data[I3_LISTED_SUBTABLE.impairment].at(-1)).toMatchObject({ label: '合计', 本期增加: 50, 期末余额: 150 })
    expect(data[I3_LISTED_SUBTABLE.performance]).toEqual([
      { label: '甲公司', 业绩承诺完成情况: '', 商誉减值金额: 50, row_type: 'data' },
      { label: '乙公司', 业绩承诺完成情况: '', 商誉减值金额: 0, row_type: 'data' },
    ])
    expect(data[I3_LISTED_SUBTABLE.assumptions]).toHaveLength(1)
    expect(data._note_texts).toEqual([{ section: 'listed-process', text: '采用预计未来现金流量现值法。' }])
  })

  it('国企：已存矩阵不被 I3-2 覆盖，请求体与 Tab 逐字节相同，写 八、29', async () => {
    h.get.mockResolvedValue(SOE)
    const out = await i3HeadlessProvider(SOE_CTX)
    expect(out.sections).toEqual([{ section: '八、29', rows: 12, kept: 0 }])
    const sent = h.post.mock.calls[0][1]
    expect(J(sent)).toBe(J((await tabSync('soe', SOE, SOE_CTX.applicableStandards)).payloads[0]))
    expect(sent.sub_table_data[I3_SOE_SUBTABLE.bookValue].map((x: any) => x.label)).toEqual(['丙公司', '合计'])
    expect(sent.sub_table_data[I3_SOE_SUBTABLE.impairment][0]).toMatchObject({ label: '丙公司', 本期增加: 80, 期末余额: 80 })
    expect(sent.sub_table_data._note_texts).toEqual([{ section: 'soe-impairment-method', text: '折现率 11%。' }])
  })

  it('既没有已存矩阵也没有 I3-2 明细：与 Tab 挂载同样补合计行（Tab 的「矩阵都为空」拦截不触发），载荷相同', async () => {
    const list = [r('I3-disc-soe-key_assumptions-note', '尚无商誉。')]
    h.get.mockResolvedValue(list)
    await i3HeadlessProvider(SOE_CTX)
    const tab = await tabSync('soe', list, SOE_CTX.applicableStandards)
    expect(tab.blockedByEmpty).toBe(false)
    expect(J(h.post.mock.calls[0][1])).toBe(J(tab.payloads[0]))
  })

  it('离屏不挂生命周期钩子、不订阅审定事件；组件内照旧订阅', async () => {
    h.get.mockResolvedValue(SOE)
    await i3HeadlessProvider(SOE_CTX)
    expect(listen.mock.calls.some(([type]) => type === 'substantive:adjudicated')).toBe(false)
    expect(warn.mock.calls.some((args) => String(args[0]).includes('no active component instance'))).toBe(false)

    const w = mount(defineComponent({
      setup() {
        useI3Disclosure(ref('wp-i3'), ref('p1'), ref(new Map()), { variant: ref('soe') as any })
        return () => null
      },
    }))
    expect(listen.mock.calls.some(([type]) => type === 'substantive:adjudicated')).toBe(true)
    w.unmount()
  })

  it('口径不适用（国企项目的上市版）：回空，不发请求', async () => {
    h.get.mockResolvedValue(LISTED)
    const out = await i3HeadlessProvider({ ...LISTED_CTX, applicableStandards: ['soe_standalone'] })
    expect(out).toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('静态接线：外壳跨 sheet 取数、Tab 挂载取数与同步快照都走共用 composable', () => {
    const shell = readFileSync(resolve(WP, 'GtI3Goodwill.vue'), 'utf-8')
    expect(shell).toContain('const crossSheet = useI3CrossSheet(allResponses)')
    expect(shell.match(/:cross-sheet-auto-fill="crossSheet\.disclosureAutoFill\.value"/g)).toHaveLength(2)
    for (const [file, variant] of [['I3TabDisclosureListed.vue', 'Listed'], ['I3TabDisclosureSoe.vue', 'Soe']] as const) {
      const src = readFileSync(resolve(WP, `i3/core/${file}`), 'utf-8')
      expect(src).toContain('crossSheetAutoFill: computed(() => props.crossSheetAutoFill ?? {}),')
      expect(src).toMatch(/onMounted\(\(\) => \{\s*applyAutoFill\(\)/)
      expect(src).toContain('const snap = getSyncSnapshot()')
      expect(src).toContain(`buildI3${variant}SyncPayloads(props.wpId, props.applicableStandards || [], snap)`)
    }
  })
})
