/**
 * 底稿披露同步「以试算表审定数为准」提示（spec note-pull-followup-closure R3）。
 *
 * - 三个写附注的同步端点（单章节 / 批量 / HTML）响应里有 `push_kept` ⇒ 每个章节提示一次，写明行名与期间；
 * - 请求带 `_silent`（附注页离屏同步自己汇总）不弹；别的端点不弹；没有保持推送值的格不弹；
 * - main.ts 装在全局 http 实例上（否则 90 多个披露 Tab 都看不到）。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it, vi } from 'vitest'

vi.mock('element-plus', () => ({ ElMessage: vi.fn() }))

import {
  installPushKeptNotice,
  isDisclosureSyncUrl,
  pushKeptGroups,
  pushKeptMessage,
} from '../disclosureSyncPushNotice'

const CELL = { table: '货币资金', row: '库存现金', period: 'end', field: 'end_amount', kind: 'cell', pushed: 390, incoming: 999 }
const TOTAL = { ...CELL, row: '合计', kind: 'total', pushed: 515, incoming: 1500 }

function fakeHttp() {
  const handlers: Array<(r: any) => any> = []
  return {
    interceptors: {
      response: {
        use: vi.fn((ok: (r: any) => any) => { handlers.push(ok); return handlers.length - 1 }),
        eject: vi.fn(),
      },
    },
    respond: (url: string, data: unknown, extra: Record<string, unknown> = {}) =>
      handlers.reduce((r, h) => h(r), { config: { url, ...extra }, data } as any),
  }
}

describe('同步端点识别', () => {
  it('单章节 / 批量 / HTML 三个入口；别的附注端点不算', () => {
    expect(isDisclosureSyncUrl('/api/projects/p1/disclosure-notes/sync-from-workpaper')).toBe(true)
    expect(isDisclosureSyncUrl('/api/projects/p1/disclosure-notes/sync-batch-from-workpaper')).toBe(true)
    expect(isDisclosureSyncUrl('/api/wp-disclosure-sync/w1/sync-html?force=true')).toBe(true)
    expect(isDisclosureSyncUrl('/api/disclosure-notes/p1/2025/pull-from-workpapers')).toBe(false)
    expect(isDisclosureSyncUrl(undefined)).toBe(false)
  })
})

describe('提示文案', () => {
  it('按章节分组，批量同步逐项读；合计重算格不点名（点名的是被保持的数据格）', () => {
    expect(pushKeptGroups({ section_id: '五、1', push_kept: [CELL, TOTAL] })).toEqual([
      { section: '五、1', cells: [CELL, TOTAL] }])
    expect(pushKeptGroups({ results: [{ section_id: '五、1', push_kept: [CELL] }, { section_id: '五、2', push_kept: [] }] }))
      .toEqual([{ section: '五、1', cells: [CELL] }])
    const msg = pushKeptMessage({ section: '五、1', cells: [CELL, TOTAL] })!
    expect(msg).toContain('附注 五、1')
    expect(msg).toContain('「库存现金」期末')
    expect(msg).toContain('以试算表审定数为准')
    expect(msg).not.toContain('合计')
    const many = pushKeptMessage({ section: '五、1', cells: [1, 2, 3, 4].map((i) => ({ ...CELL, row: `行${i}` })) })!
    expect(many).toContain('等 4 格')
    expect(pushKeptMessage({ section: '五、1', cells: [] })).toBeNull()
    expect(pushKeptGroups(null)).toEqual([])
    expect(pushKeptGroups({ push_kept: 'x' })).toEqual([])
  })
})

describe('拦截器', () => {
  it('同步响应有 push_kept 才提示；_silent / 别的端点 / 空列表不提示；响应原样返回', () => {
    const http = fakeHttp()
    const notify = vi.fn()
    const uninstall = installPushKeptNotice(http as any, notify)
    const url = '/api/projects/p1/disclosure-notes/sync-from-workpaper'
    const res = http.respond(url, { section_id: '五、1', push_kept: [CELL] })
    expect(res.data.push_kept).toEqual([CELL])
    expect(notify).toHaveBeenCalledTimes(1)
    http.respond(url, { section_id: '五、1', push_kept: [CELL] }, { _silent: true })
    http.respond('/api/projects/p1/notes', { section_id: '五、1', push_kept: [CELL] })
    http.respond(url, { section_id: '五、1', push_kept: [] })
    expect(notify).toHaveBeenCalledTimes(1)
    uninstall()
    expect(http.interceptors.response.eject).toHaveBeenCalledWith(0)
  })

  it('main.ts 装在全局 http 实例上', () => {
    const main = readFileSync(resolve(__dirname, '../../main.ts'), 'utf-8')
    expect(main).toContain("import { installPushKeptNotice } from './utils/disclosureSyncPushNotice'")
    expect(main).toMatch(/^installPushKeptNotice\(http\)$/m)
  })
})
