/**
 * 附注刷新从底稿取数：后端结果与离屏同步结果并入刷新提示（spec note-pull-header-formula-closure R2.2）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({ post: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { post: h.post } }))

import { describeWorkpaperPull, pullFromWorkpapers, type NotePullResult } from '../noteWorkpaperPull'

function pull(overrides: Partial<NotePullResult['push']> = {}, sections: Partial<NotePullResult['sections'][number]>[] = []): NotePullResult {
  return {
    synced: 0, skipped: 0, skipped_never_synced: 0, variant: 'soe', applicable_standards: ['soe_standalone'],
    push: { ran: true, error: null, wp_codes: ['D2'], written: 0, kept: 0, skipped: 0, run_id: 'r1', warnings: [], ...overrides },
    sections: sections.map((s) => ({
      section: '八、5', wp_codes: ['D2'], wp_ids: {}, push_wp_codes: ['D2'], unsupported_wp_codes: [],
      exists: true, synced_before: false, manual_values: 0, written: 0, unchanged: 0, kept: 0, skipped: 0, reasons: [],
      ...s,
    })),
  }
}

describe('pullFromWorkpapers', () => {
  beforeEach(() => { h.post.mockReset() })

  it('带章节参数、静默请求，返回后端结果', async () => {
    h.post.mockResolvedValueOnce(pull({}, [{}]))
    const { result, error } = await pullFromWorkpapers('p1', 2025, '八、5')
    expect(error).toBeNull()
    expect(result?.sections[0].section).toBe('八、5')
    const [url, body, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/disclosure-notes/p1/2025/pull-from-workpapers')
    expect(body).toBeNull()
    expect(cfg).toMatchObject({ params: { note_section: '八、5', phase: 'all' }, _silent: true })
  })

  it('请求失败不抛：回中文原因（不再静默吞掉）', async () => {
    h.post.mockRejectedValueOnce({ response: { data: { detail: '项目不存在' } } })
    const { result, error } = await pullFromWorkpapers('p1', 2025, null)
    expect(result).toBeNull()
    expect(error).toBe('从底稿取数失败：项目不存在')
    expect(h.post.mock.calls[0][2]).toMatchObject({ params: { phase: 'all' } })
  })
})

describe('describeWorkpaperPull', () => {
  it('推送写入与保留人工都写进提示，点名写入的章节', () => {
    const { lines, warn } = describeWorkpaperPull(
      pull({ written: 3, kept: 1 }, [{ section: '八、1', written: 3 }, { section: '八、5' }]), null, [],
    )
    expect(lines).toEqual(['公式推送按审定数写入 3 格（八、1）', '保留人工 / 锁定 1 格'])
    expect(warn).toBe(false)
  })

  it('推送被拒（审计年度不符）与请求失败都是告警', () => {
    expect(describeWorkpaperPull(pull({ ran: false, error: '只作用于项目审计年度' }), null, [])).toEqual({
      lines: ['公式推送未执行：只作用于项目审计年度'], warn: true,
    })
    expect(describeWorkpaperPull(null, '从底稿取数失败：x', [])).toEqual({ lines: ['从底稿取数失败：x'], warn: true })
  })

  it('离屏同步：成功列出行数、失败告警、跳过写明原因、未接入底稿点名', () => {
    const { lines, warn } = describeWorkpaperPull(pull(), null, [
      { wpCode: 'D2', section: '八、5', status: 'synced', rows: 22 },
      { wpCode: 'K1', section: '八、9', status: 'failed', message: '网络中断' },
      { wpCode: 'D1', section: '八、4', status: 'skipped', message: '附注已有人工填写' },
    ], { pendingWpCodes: ['E1', 'F2'] })
    expect(lines).toEqual([
      '已从底稿披露表同步：D2→八、5（22 行）',
      'D1：附注已有人工填写',
      '底稿披露表同步失败：K1→八、9（网络中断）',
      '底稿 E1、F2 的明细表需在底稿附注披露页保存一次后同步',
    ])
    expect(warn).toBe(true)
  })

  it('离屏同步逐章节回报：推送保持的格汇总一句，条目多时截断并写总数（spec note-pull-followup-closure R1）', () => {
    const synced = Array.from({ length: 8 }, (_, i) => ({
      wpCode: `G${i + 1}`, section: `八、${i + 10}`, status: 'synced' as const, rows: i, kept: i === 0 ? 2 : i === 3 ? 1 : 0,
    }))
    const skipped = Array.from({ length: 5 }, (_, i) => ({
      wpCode: 'H1', section: `八、${i + 30}`, status: 'skipped' as const, message: `附注 八、${i + 30} 已有 1 格人工填写`,
    }))
    const { lines, warn } = describeWorkpaperPull(pull(), null, [...synced, ...skipped])
    expect(lines[0]).toBe('已从底稿披露表同步：G1→八、10（0 行）、G2→八、11（1 行）、G3→八、12（2 行）、G4→八、13（3 行）、'
      + 'G5→八、14（4 行）、G6→八、15（5 行） 等 8 项')
    expect(lines[1]).toBe('其中 3 格由公式推送维护，已保持试算表审定数（八、10、八、13）')
    expect(lines.slice(2)).toEqual([
      'H1：附注 八、30 已有 1 格人工填写', 'H1：附注 八、31 已有 1 格人工填写', 'H1：附注 八、32 已有 1 格人工填写',
      '另有 2 个章节未写入（原因同上类）',
    ])
    expect(warn).toBe(false)
  })
})
