/**
 * I2 开发支出披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①离屏请求体与「Tab 同参实例化 useI2Disclosure → persistAll → getListedSnapshot / getSoeSnapshot → builder」
 * （Tab `syncToNotes` 的同一步骤）逐字节相同；夹具有真实数据（按性质 / 滚动 / 资本化续表 / 重要项目 / 减值 / 说明）
 * ②旧单表键（`I2-disc-*-rows`）与 Tab 同样兼容读 ③只读 I2- 条目、静默发出、不写底稿 ④口径不适用回空
 * ⑤Tab 同步调的就是 composable 的快照函数（静态接线）。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))

import { i2HeadlessProvider } from '../i2HeadlessDisclosure'
import { useI2Disclosure } from '../useI2Disclosure'
import { buildI2ListedSyncPayloads, buildI2SoeSyncPayloads } from '../i2DisclosureSyncPayload'
import { I2_LISTED_SUBTABLE, I2_SOE_SUBTABLE } from '../i2NoteSectionMap'

const J = JSON.stringify
type Resp = { item_id: string; remark: string | null; conclusion: string | null }
const r = (item_id: string, remark: unknown): Resp => ({
  item_id, remark: typeof remark === 'string' ? remark : J(remark), conclusion: null,
})
const NOISE = [r('I20-disc-listed-movement', [{ name: '别的底稿', beginBalance: 9 }]), r('K1-unrelated', '999')]

const LISTED = [
  r('I2-disc-listed-nature', [
    { rowId: 'n1', name: '人工费', currentExpensed: 300, currentCapitalized: 120, priorExpensed: 250, priorCapitalized: 80 },
    { rowId: 'n2', name: '材料费', currentExpensed: 50, currentCapitalized: 30, priorExpensed: 0, priorCapitalized: 0 },
  ]),
  r('I2-disc-listed-movement', [{
    rowId: 'm1', name: 'A 项目', beginBalance: 500, increaseInternal: 150, increaseOther: 0,
    decreaseToIntangible: 200, decreaseToExpense: 0, capStartDate: '2024-03-01', capBasis: '技术可行性评审通过', progress: '80%',
  }]),
  r('I2-disc-listed-important', [{
    rowId: 'i1', name: 'A 项目', progress: '80%', expectedCompletion: '2026-06', economicBenefit: '对外销售',
    capStartDate: '2024-03-01', capBasis: '评审通过',
  }]),
  r('I2-disc-listed-impairment', [{ rowId: 'p1', name: 'B 项目', beginBalance: 0, provision: 30, decrease: 0 }]),
  r('I2-disc-listed-note', '开发支出主要为 A 项目。'),
  r('I2-disc-listed-note-purchased', '本期无购买式研发。'),
  ...NOISE,
]
const SOE = [
  r('I2-disc-soe-movement', [{
    rowId: 'm1', name: 'C 项目', beginBalance: 300, increaseInternal: 100, increaseOther: 0,
    decreaseToIntangible: 50, decreaseToExpense: 20, decreaseOther: 10,
  }]),
  r('I2-disc-soe-note', '国企开发支出说明。'),
  ...NOISE,
]
/** 旧版单表（只有 `I2-disc-soe-rows`，字段是旧名 increase / decrease） */
const SOE_LEGACY = [
  r('I2-disc-soe-rows', [{ rowId: 'old1', projectName: 'D 项目', capBeginAmount: 80, increase: 40, decrease: 30 }]),
  ...NOISE,
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-i2', wpCode: 'I2' }
const LISTED_CTX = { ...CTX, variant: 'listed' as const, applicableStandards: ['listed_standalone'] }
const SOE_CTX = { ...CTX, variant: 'soe' as const, applicableStandards: ['soe_standalone'] }
const SYNC_URL = '/api/projects/p1/disclosure-notes/sync-from-workpaper'
const WP = resolve(__dirname, '../..')

const own = (list: Resp[]) => new Map(list.filter((x) => x.item_id.startsWith('I2-')).map((x) => [x.item_id, { ...x }]))

/** Tab 路径：Tab `syncToNotes` 的同一步骤（同参实例化 → persistAll → 快照 → builder） */
async function tabPayloads(variant: 'listed' | 'soe', list: Resp[], stds: string[]) {
  const saved: string[] = []
  const scope = effectScope(true)
  try {
    const disc = scope.run(() => useI2Disclosure(ref(own(list)), {
      variant,
      saveResponse: async (sheetCode) => { saved.push(sheetCode) },
      applicableStandards: ref(stds),
    }))!
    await nextTick()
    await disc.persistAll()
    const payloads = variant === 'listed'
      ? buildI2ListedSyncPayloads('wp-i2', stds, disc.getListedSnapshot())
      : buildI2SoeSyncPayloads('wp-i2', stds, disc.getSoeSnapshot())
    return { payloads, saved }
  } finally {
    scope.stop()
  }
}

describe('i2HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.post.mockResolvedValue({ rows_synced: 9, push_kept: [] })
  })

  it('上市：请求体与 Tab 同步逐字节相同，静默写 五、27、只读 I2- 条目、不写底稿', async () => {
    h.get.mockResolvedValue(LISTED)
    const out = await i2HeadlessProvider(LISTED_CTX)
    expect(out).toEqual({ sections: [{ section: '五、27', rows: 9, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-i2/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.post).toHaveBeenCalledTimes(1)
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe(SYNC_URL)
    expect(cfg).toMatchObject({ _silent: true })
    const tab = await tabPayloads('listed', LISTED, LISTED_CTX.applicableStandards)
    expect(tab.saved).toEqual(['disc-listed'])
    expect(J(sent)).toBe(J(tab.payloads[0]))
    // 夹具有真实数据：各子表与说明都在
    const data = sent.sub_table_data
    expect(data[I2_LISTED_SUBTABLE.nature].at(-1)).toMatchObject({ 项目: '合计', cur_expense: 350, cur_capitalize: 150 })
    expect(data[I2_LISTED_SUBTABLE.movement][0]).toMatchObject({ label: 'A 项目', 期初余额: 500, 期末余额: 450 })
    expect(data[I2_LISTED_SUBTABLE.capDetail]).toEqual([
      { label: 'A 项目', 资本化开始时点: '2024-03-01', 资本化的具体依据: '技术可行性评审通过', 截至期末的研发进度: '80%' },
    ])
    expect(data[I2_LISTED_SUBTABLE.important]).toHaveLength(1)
    expect(data[I2_LISTED_SUBTABLE.impairment].at(-1)).toMatchObject({ label: '合计', 期末余额: 30 })
    expect((data._note_texts as Array<{ section: string }>).map((n) => n.section)).toEqual(['listed-main', 'listed-purchased-rd'])
  })

  it('国企：请求体与 Tab 同步逐字节相同，写 八、28', async () => {
    h.get.mockResolvedValue(SOE)
    const out = await i2HeadlessProvider(SOE_CTX)
    expect(out.sections).toEqual([{ section: '八、28', rows: 9, kept: 0 }])
    const sent = h.post.mock.calls[0][1]
    expect(J(sent)).toBe(J((await tabPayloads('soe', SOE, SOE_CTX.applicableStandards)).payloads[0]))
    expect(sent.sub_table_data[I2_SOE_SUBTABLE.movement][0]).toMatchObject({ label: 'C 项目', 本期减少_其他: 10, 期末余额: 320 })
    expect(sent.sub_table_data._note_texts).toEqual([{ section: 'soe-main', title: '开发支出说明', text: '国企开发支出说明。' }])
    expect(h.put).not.toHaveBeenCalled()
  })

  it('旧单表键：与 Tab 同样兼容读（旧字段名换算后进滚动表）', async () => {
    h.get.mockResolvedValue(SOE_LEGACY)
    await i2HeadlessProvider(SOE_CTX)
    const sent = h.post.mock.calls[0][1]
    expect(J(sent)).toBe(J((await tabPayloads('soe', SOE_LEGACY, SOE_CTX.applicableStandards)).payloads[0]))
    expect(sent.sub_table_data[I2_SOE_SUBTABLE.movement][0]).toMatchObject({
      label: 'D 项目', 期初余额: 80, 本期增加_内部开发支出: 40, 本期减少_确认为无形资产: 30, 期末余额: 90,
    })
  })

  it('口径不适用（上市项目的国企版）：回空，不发请求', async () => {
    h.get.mockResolvedValue(SOE)
    const out = await i2HeadlessProvider({ ...SOE_CTX, applicableStandards: ['listed_standalone'] })
    expect(out).toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('静态接线：两个 Tab 的同步先保存、再调 composable 的快照函数 + 同一 builder', () => {
    const listed = readFileSync(resolve(WP, 'i2/core/I2TabDisclosureListed.vue'), 'utf-8')
    const soe = readFileSync(resolve(WP, 'i2/core/I2TabDisclosureSoe.vue'), 'utf-8')
    expect(listed).toContain('buildI2ListedSyncPayloads(props.wpId, props.applicableStandards, getListedSnapshot())')
    expect(soe).toContain('buildI2SoeSyncPayloads(props.wpId, props.applicableStandards, getSoeSnapshot())')
    for (const src of [listed, soe]) {
      expect(src).toMatch(/const disc = useI2Disclosure\(allResponsesRef, \{\s*variant: '(listed|soe)',\s*saveResponse: props\.saveResponse,\s*applicableStandards: standardsRef,\s*\}\)/)
      expect(src).not.toMatch(/movementRows:\s*movementRows\.value/)
    }
  })
})
