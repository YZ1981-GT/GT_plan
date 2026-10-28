/**
 * I1 无形资产披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①离屏请求体与「Tab 同参实例化 useI1Listed/SoeDisclosure → persist → buildSyncSnapshot → builder」（Tab
 * `syncToNotes` 的同一步骤）逐字节相同；夹具有真实数据（变动表 / 数据资源 / 未办妥权属 / 摊销归属 / 说明都非空）
 * ②有阻断项（期末账面价值为负）时与 Tab 同样不写，逐章节回报 Tab 同一条阻断原因；只有编制提示时按 Tab 确认后的同一
 * 载荷写入 ③只读 I1- 条目、静默发出、不写底稿 ④口径不适用回空 ⑤Tab 同步调的就是共用快照（静态接线）。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))

import { i1HeadlessProvider } from '../i1HeadlessDisclosure'
import { useI1ListedDisclosure, useI1SoeDisclosure } from '../useI1Disclosure'
import { buildI1ListedSyncPayloads, buildI1SoeSyncPayloads } from '../i1DisclosureSyncPayload'
import { I1_LISTED_SUBTABLE, I1_SOE_SUBTABLE } from '../i1NoteSectionMap'

const J = JSON.stringify
type Resp = { item_id: string; remark: string | null; conclusion: string | null }
const r = (item_id: string, remark: unknown): Resp => ({
  item_id, remark: typeof remark === 'string' ? remark : J(remark), conclusion: null,
})
const NOISE = [r('I10-listed-movement', { cost_begin: { software: 9 } }), r('K1-unrelated', '999')]

const LISTED_MOVEMENT = {
  cost_begin: { software: 1000, land: 5000 },
  cost_inc_purchase: { software: 200 },
  amort_begin: { software: 100, land: 500 },
  amort_inc_provision: { software: 40, land: 100 },
}
const LISTED = [
  r('I1-listed-movement', LISTED_MOVEMENT),
  r('I1-listed-note-rd-ratio', '本期通过内部研发形成的无形资产占比 12.50%。'),
  r('I1-listed-title-cert-rows', [{ rowId: 'tc-1', name: '厂区土地', bookValue: 3000, reason: '正在办理' }]),
  r('I1-listed-important-rows', [{ rowId: 'imp-1', name: 'ERP 系统', bookValue: 800, remainingAmortMonths: 36 }]),
  r('I1-listed-data-resource', { costBegin: 80, costIncPurchase: 20, amortBegin: 10, note: '数据资源按暂行规定披露。' }),
  r('I1-listed-amort-alloc', { management: 100, rd: 40, total: 140 }),
  ...NOISE,
]
const SOE = [
  r('I1-soe-layers', [
    { layer: 'cost', categories: [
      { key: 'software', begin: 1000, increase: 200, decrease: 0, end: 0 },
      { key: 'land', begin: 5000, increase: 0, decrease: 0, end: 0 },
    ] },
    { layer: 'amort', categories: [{ key: 'software', begin: 100, increase: 40, decrease: 0, end: 0 }] },
    { layer: 'impair', categories: [] },
    { layer: 'carrying', categories: [] },
  ]),
  r('I1-soe-note-indefinite', '商标权使用寿命不确定，每年进行减值测试。'),
  r('I1-soe-amort-alloc', { management: 140, total: 140 }),
  ...NOISE,
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-i1', wpCode: 'I1' }
const LISTED_CTX = { ...CTX, variant: 'listed' as const, applicableStandards: ['listed_standalone'] }
const SOE_CTX = { ...CTX, variant: 'soe' as const, applicableStandards: ['soe_standalone'] }
const SYNC_URL = '/api/projects/p1/disclosure-notes/sync-from-workpaper'
const WP = resolve(__dirname, '../..')

const own = (list: Resp[]) => new Map(list.filter((x) => x.item_id.startsWith('I1-')).map((x) => [x.item_id, { ...x }]))

/** Tab 路径：Tab `syncToNotes` 的同一步骤（同参实例化 → 校验 → persist → buildSyncSnapshot → builder） */
async function tabSync(variant: 'listed' | 'soe', list: Resp[], stds: string[]) {
  const saves: string[] = []
  const params = { allResponses: ref(own(list)), onSave: (id: string) => { saves.push(id) } }
  const scope = effectScope(true)
  try {
    if (variant === 'listed') {
      const disc = scope.run(() => useI1ListedDisclosure(params))!
      await nextTick()
      const prep = { ...disc.prepValidation.value }
      disc.persist()
      return { prep, saves, payloads: buildI1ListedSyncPayloads('wp-i1', stds || [], disc.buildSyncSnapshot()) }
    }
    const disc = scope.run(() => useI1SoeDisclosure(params))!
    await nextTick()
    const prep = { ...disc.prepValidation.value }
    disc.persist()
    return { prep, saves, payloads: buildI1SoeSyncPayloads('wp-i1', stds || [], disc.buildSyncSnapshot()) }
  } finally {
    scope.stop()
  }
}

describe('i1HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.post.mockResolvedValue({ rows_synced: 30, push_kept: [{ table: '无形资产情况' }] })
  })

  it('上市：请求体与 Tab 同步逐字节相同，静默写 五、26、只读 I1- 条目、不写底稿', async () => {
    h.get.mockResolvedValue(LISTED)
    const out = await i1HeadlessProvider(LISTED_CTX)
    expect(out).toEqual({ sections: [{ section: '五、26', rows: 30, kept: 1 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-i1/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.post).toHaveBeenCalledTimes(1)
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe(SYNC_URL)
    expect(cfg).toMatchObject({ _silent: true })
    const tab = await tabSync('listed', LISTED, LISTED_CTX.applicableStandards)
    expect(tab.prep.blocking).toEqual([])
    expect(tab.prep.warnings).toEqual([])
    expect(tab.payloads).toHaveLength(1)
    expect(J(sent)).toBe(J(tab.payloads[0]))
    // 夹具有真实数据：变动表合计、子表、说明都在
    const movement = sent.sub_table_data[I1_LISTED_SUBTABLE.movement] as Array<Record<string, unknown>>
    expect(movement.find((x) => x.label === '1.期末账面价值')?.['合计']).toBe(5460)
    expect(sent.sub_table_data[I1_LISTED_SUBTABLE.titleCert]).toEqual([
      { label: '厂区土地', 账面价值: 3000, 未办妥产权证书原因: '正在办理' },
    ])
    expect(sent.sub_table_data[I1_LISTED_SUBTABLE.important]).toHaveLength(1)
    expect(sent.sub_table_data[I1_LISTED_SUBTABLE.dataResource]).toBeTruthy()
    expect(sent.sub_table_data['本期摊销费用归属']?.[0]).toMatchObject({ 管理费用: 100, 研发费用: 40, 合计: 140 })
    const sections = (sent.sub_table_data._note_texts as Array<{ section: string }>).map((n) => n.section)
    expect(sections).toEqual(['listed-rd-ratio', 'listed-data-resource', 'listed-amort-alloc'])
  })

  it('国企：请求体与 Tab 同步逐字节相同，写 八、27', async () => {
    h.get.mockResolvedValue(SOE)
    const out = await i1HeadlessProvider(SOE_CTX)
    expect(out.sections).toEqual([{ section: '八、27', rows: 30, kept: 1 }])
    const sent = h.post.mock.calls[0][1]
    const tab = await tabSync('soe', SOE, SOE_CTX.applicableStandards)
    expect(tab.prep.blocking).toEqual([])
    expect(J(sent)).toBe(J(tab.payloads[0]))
    const rows = sent.sub_table_data[I1_SOE_SUBTABLE.movement] as Array<Record<string, unknown>>
    expect(rows.find((x) => x.layer === 'cost' && x.is_total)?.end).toBe(6200)
    expect(rows.find((x) => x.layer === 'carrying' && x.is_total)?.end).toBe(6060)
    const notes = (sent.sub_table_data._note_texts as Array<{ section: string }>).map((n) => n.section)
    expect(notes).toEqual(['soe-indefinite', 'soe-amort-alloc'])
    expect(h.put).not.toHaveBeenCalled()
  })

  it('有阻断项（期末账面价值为负）：与 Tab 同样不写，回报 Tab 的同一条阻断原因', async () => {
    const list = [r('I1-listed-movement', { cost_begin: { software: 100 }, amort_begin: { software: 300 } })]
    h.get.mockResolvedValue(list)
    const tab = await tabSync('listed', list, LISTED_CTX.applicableStandards)
    expect(tab.prep.blocking.length).toBeGreaterThan(0)
    const out = await i1HeadlessProvider(LISTED_CTX)
    expect(h.post).not.toHaveBeenCalled()
    expect(out).toEqual({ sections: [{
      section: '五、26',
      rows: 0,
      skipped: `底稿披露表校验未通过：${tab.prep.blocking[0]}，未写入（请在底稿附注披露页修正后同步）`,
    }] })
  })

  it('只有编制提示（未办妥权属未填原因）：按 Tab 确认后的同一载荷写入', async () => {
    const list = LISTED.map((x) => (x.item_id === 'I1-listed-title-cert-rows'
      ? r(x.item_id, [{ rowId: 'tc-1', name: '厂区土地', bookValue: 3000, reason: '' }])
      : x))
    h.get.mockResolvedValue(list)
    const tab = await tabSync('listed', list, LISTED_CTX.applicableStandards)
    expect(tab.prep.blocking).toEqual([])
    expect(tab.prep.warnings).toEqual(['未办妥权属「厂区土地」未填原因'])
    const out = await i1HeadlessProvider(LISTED_CTX)
    expect(out.sections).toEqual([{ section: '五、26', rows: 30, kept: 1 }])
    expect(J(h.post.mock.calls[0][1])).toBe(J(tab.payloads[0]))
  })

  it('口径不适用（国企项目的上市版）：回空，不发请求', async () => {
    h.get.mockResolvedValue(LISTED)
    const out = await i1HeadlessProvider({ ...LISTED_CTX, applicableStandards: ['soe_standalone'] })
    expect(out).toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('章节保护命中：不发请求，原因随结果回报', async () => {
    h.get.mockResolvedValue(SOE)
    const out = await i1HeadlessProvider({ ...SOE_CTX, sectionGuard: () => '附注 八、27 已有 2 格人工填写' })
    expect(h.post).not.toHaveBeenCalled()
    expect(out).toEqual({ sections: [{ section: '八、27', rows: 0, skipped: '附注 八、27 已有 2 格人工填写' }] })
  })

  it('静态接线：两个 Tab 的同步调共用快照 buildSyncSnapshot，组件内不再自拼快照', () => {
    const listed = readFileSync(resolve(WP, 'i1/core/I1TabDisclosureListed.vue'), 'utf-8')
    const soe = readFileSync(resolve(WP, 'i1/core/I1TabDisclosureSoe.vue'), 'utf-8')
    expect(listed).toContain('buildI1ListedSyncPayloads(props.wpId, props.applicableStandards || [], buildSyncSnapshot())')
    expect(soe).toContain('buildI1SoeSyncPayloads(props.wpId, props.applicableStandards || [], buildSyncSnapshot())')
    for (const src of [listed, soe]) {
      expect(src).toContain('if (prepValidation.value.blocking.length) {')
      expect(src).not.toMatch(/noteIndefinite:\s*noteIndefinite\.value/)
    }
    const composable = readFileSync(resolve(__dirname, '../useI1Disclosure.ts'), 'utf-8')
    expect(composable.match(/function buildSyncSnapshot\(\)/g)).toHaveLength(2)
  })
})
