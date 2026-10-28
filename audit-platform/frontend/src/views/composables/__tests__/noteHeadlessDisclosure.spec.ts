/**
 * 附注页离屏同步编排（spec note-pull-header-formula-closure R2.3 / note-pull-followup-closure R1）：何时调 provider、
 * 逐章节回报、章节保护（从未由底稿同步、已有人工填写不覆盖；单章节刷新不写范围外章节）、失败隔离。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({ d2: vi.fn(), get: vi.fn() }))
// 编排用例只登记 D2（真实登记表随各组接入变长，不让本文件随之改）；登记表本身由 noteHeadlessProviders.spec 守
vi.mock('@/components/workpaper/headless/registry', () => ({ HEADLESS_PROVIDERS: { D2: async () => h.d2 } }))
vi.mock('@/utils/http', () => ({ default: { get: h.get } }))

import { headlessDisclosureWpCodes, loadWorkpaperResponses, runHeadlessDisclosure } from '../noteHeadlessDisclosure'
import type { NotePullResult } from '../noteWorkpaperPull'

function result(sections: Partial<NotePullResult['sections'][number]>[], extra: Partial<NotePullResult> = {}): NotePullResult {
  return {
    synced: 0, skipped: 0, skipped_never_synced: 0, variant: 'soe', applicable_standards: ['soe_standalone'],
    push: { ran: true, error: null, wp_codes: [], written: 0, kept: 0, skipped: 0, run_id: null, warnings: [] },
    sections: sections.map((s) => ({
      section: '八、5', wp_codes: ['D2'], wp_ids: { D2: 'wp-d2' }, push_wp_codes: [], unsupported_wp_codes: [],
      exists: true, synced_before: false, manual_values: 0, written: 0, unchanged: 0, kept: 0, skipped: 0, reasons: [],
      ...s,
    })),
    ...extra,
  }
}

const CTX = { projectId: 'p1', year: 2025 }

describe('runHeadlessDisclosure', () => {
  beforeEach(() => { h.d2.mockReset(); h.get.mockReset() })

  it('D2 已接入：按后端给的底稿 id 与项目准则调用 provider，逐章节回报', async () => {
    h.d2.mockResolvedValueOnce({ sections: [{ section: '八、5', rows: 22, kept: 2 }] })
    const { outcomes, pending } = await runHeadlessDisclosure(result([{}]), CTX)
    expect(h.d2).toHaveBeenCalledWith({
      projectId: 'p1', year: 2025, variant: 'soe', wpId: 'wp-d2', wpCode: 'D2', applicableStandards: ['soe_standalone'],
      sectionGuard: expect.any(Function),
    })
    expect(outcomes).toEqual([{ wpCode: 'D2', section: '八、5', status: 'synced', rows: 22, kept: 2 }])
    expect(pending).toEqual([])
  })

  it('章节保护：从未同步且已有人工填写不覆盖；同步过的照写；单章节刷新不写范围外章节', async () => {
    let guard: (s: string) => string | null = () => null
    h.d2.mockImplementation(async (ctx: any) => { guard = ctx.sectionGuard; return { sections: [] } })
    await runHeadlessDisclosure(result([{ manual_values: 3 }]), CTX)
    expect(guard('八、5')).toContain('附注 八、5 已有 3 格人工填写，未用底稿披露表覆盖')
    expect(guard('八、77')).toBe('')
    await runHeadlessDisclosure(result([{ manual_values: 3, synced_before: true }]), CTX)
    expect(guard('八、5')).toBeNull()
  })

  it('全部刷新：取数结果章节行之外的章节按 section_states 判，没有状态（附注还没有这一节）照写', async () => {
    let guard: (s: string) => string | null = () => null
    h.d2.mockImplementation(async (ctx: any) => { guard = ctx.sectionGuard; return { sections: [] } })
    const pull = result([{}], { section_states: {
      '八、77': { exists: true, synced_before: false, manual_values: 2 },
      '八、78': { exists: true, synced_before: true, manual_values: 9 },
    } })
    await runHeadlessDisclosure(pull, { ...CTX, allSections: true })
    expect(guard('八、77')).toContain('已有 2 格人工填写')
    expect(guard('八、78')).toBeNull()
    expect(guard('八、79')).toBeNull()
    expect(guard('八、5')).toBeNull()
  })

  it('一张底稿写多个章节：逐章节回报；静默跳过的不进提示，单章节失败只记这一节', async () => {
    h.d2.mockResolvedValueOnce({ sections: [
      { section: '八、5', rows: 3 },
      { section: '八、77', rows: 0, skipped: '' },
      { section: '八、78', rows: 0, skipped: '附注 八、78 已有 1 格人工填写' },
      { section: '八、79', rows: 0, error: '网络中断' },
    ] })
    const { outcomes } = await runHeadlessDisclosure(result([{}]), CTX)
    expect(outcomes).toEqual([
      { wpCode: 'D2', section: '八、5', status: 'synced', rows: 3, kept: 0 },
      { wpCode: 'D2', section: '八、78', status: 'skipped', message: '附注 八、78 已有 1 格人工填写' },
      { wpCode: 'D2', section: '八、79', status: 'failed', message: '网络中断' },
    ])
  })

  it('本项目口径没有这张底稿的披露表（builder 回空）→ 跳过并说明', async () => {
    h.d2.mockResolvedValueOnce({ sections: [] })
    const { outcomes } = await runHeadlessDisclosure(result([{}]), CTX)
    expect(outcomes).toEqual([{ wpCode: 'D2', section: '八、5', status: 'skipped', message: '本项目口径没有这张底稿的披露表' }])
  })

  it('本项目没有该底稿 → 跳过；未接入离屏同步且从未同步 → 点名待处理（同一底稿只算一次）', async () => {
    const out = await runHeadlessDisclosure(result([
      { wp_ids: {} },
      { section: '八、9', wp_codes: ['K1', 'G2'], wp_ids: { K1: 'wp-k1' } },
      { section: '八、10', wp_codes: ['K1'], wp_ids: { K1: 'wp-k1' } },
      { section: '八、1', wp_codes: ['E1'], wp_ids: { E1: 'wp-e1' }, synced_before: true },
    ]), CTX)
    expect(out.outcomes).toEqual([{ wpCode: 'D2', section: '八、5', status: 'skipped', message: '本项目没有 D2 底稿' }])
    expect(out.pending).toEqual(['K1'])
    expect(h.d2).not.toHaveBeenCalled()
  })

  it('同一底稿出现在多个章节行：provider 只调一次，底稿 id 取第一个给了 id 的章节', async () => {
    h.d2.mockResolvedValueOnce({ sections: [{ section: '八、5', rows: 1 }] })
    await runHeadlessDisclosure(result([{ wp_ids: {} }, { section: '八、77', wp_ids: { D2: 'wp-d2b' } }]), CTX)
    expect(h.d2).toHaveBeenCalledTimes(1)
    expect(h.d2.mock.calls[0][0].wpId).toBe('wp-d2b')
  })

  it('provider 失败只记这一张底稿，不抛', async () => {
    h.d2.mockRejectedValueOnce({ response: { data: { detail: { message: '当前项目准则不适用' } } } })
    const { outcomes } = await runHeadlessDisclosure(result([{}]), CTX)
    expect(outcomes).toEqual([{ wpCode: 'D2', section: '八、5', status: 'failed', message: '当前项目准则不适用' }])
  })

  it('已接入清单 = 登记表的编码', () => {
    expect(headlessDisclosureWpCodes()).toEqual(['D2'])
  })
})

describe('loadWorkpaperResponses', () => {
  it('只取本底稿前缀的条目（与底稿主入口同口径）；可给多个前缀', async () => {
    h.get.mockResolvedValue([
      { item_id: 'D2-detail-rows', remark: '[]', conclusion: null },
      { item_id: 'D2A-x', remark: '2' },
      { item_id: 'K1-x', remark: '1' },
    ])
    const map = await loadWorkpaperResponses('wp-d2', 'D2-')
    expect([...map.keys()]).toEqual(['D2-detail-rows'])
    expect(h.get.mock.calls[0][0]).toBe('/api/workpapers/wp-d2/checklist-responses')
    expect([...(await loadWorkpaperResponses('wp-d2', ['D2-', 'D2A-'])).keys()]).toEqual(['D2-detail-rows', 'D2A-x'])
  })
})
