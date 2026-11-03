/**
 * useStaleImpact.notify — 写 stale 请求的前端分支（acnr-foundation-defect-closure T23 / D8，段四审计 F4-14）
 *
 * - 无项目上下文 → 不发请求（后端 /impact 要求项目鉴权，裸发必 403）；
 * - 正常 → body 带 project_id；未给年度时不带 year（由后端按项目审计年度补齐，不用日历年兜底）；
 * - 403 / 503 → 返回 null、不抛出、不阻断保存，本 composable 只记日志、不另行弹错。
 *   说明：请求未带 `_silent`，全局 http 拦截器对 403 仍会给出既有的非阻塞提示，
 *   这与 design §11.2「403 按现有非阻塞告警处理」一致；本用例只钉 composable 自身的分支。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const h = vi.hoisted(() => ({
  post: vi.fn(),
  get: vi.fn(),
  log: vi.fn(),
}))

vi.mock('@/utils/http', () => ({ default: { post: h.post, get: h.get } }))
vi.mock('@/utils/logger', () => ({ logger: { log: h.log, warn: vi.fn(), error: vi.fn() } }))

import { useStaleImpact } from '@/composables/useStaleImpact'
import { linkageBus } from '@/services/apiPaths'

let warnSpy: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  h.post.mockReset()
  h.get.mockReset()
  h.log.mockReset()
  warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
})

afterEach(() => {
  warnSpy.mockRestore()
})

function httpError(status: number) {
  return Object.assign(new Error(`HTTP ${status}`), { response: { status } })
}

describe('useStaleImpact.notify', () => {
  it('没有 project_id 时不发请求', async () => {
    const { notify } = useStaleImpact('D2')
    const res = await notify({ sheet: '审定表D2-1', cell: 'C10' })
    expect(res).toBeUndefined()
    expect(h.post).not.toHaveBeenCalled()
  })

  it('底稿编码为空时不发请求', async () => {
    const { notify } = useStaleImpact('')
    await notify({ sheet: '审定表D2-1', cell: 'C10', project_id: 'p-1' })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('正常发送：body 带 project_id，未给年度时不带 year', async () => {
    h.post.mockResolvedValue({ data: { affected: ['WP:D3:审定表D3-1:C10'], total: 1 } })
    const { notify, affected, totalAffected } = useStaleImpact('D2')
    await notify({ sheet: '审定表D2-1', cell: 'C10', project_id: 'p-1' })
    expect(h.post).toHaveBeenCalledTimes(1)
    const [url, body] = h.post.mock.calls[0]
    expect(url).toBe(linkageBus.impact)
    expect(body).toEqual({ source_uri: 'WP:D2:审定表D2-1:C10', project_id: 'p-1' })
    expect('year' in body).toBe(false)
    expect(totalAffected.value).toBe(1)
    expect(affected.value[0].wp_code).toBe('D3')
  })

  it('给了年度才带 year', async () => {
    h.post.mockResolvedValue({ data: { affected: [], total: 0 } })
    const { notify } = useStaleImpact('D2')
    await notify({ sheet: '审定表D2-1', cell: 'C10', project_id: 'p-1', year: 2025 })
    expect(h.post.mock.calls[0][1]).toEqual({
      source_uri: 'WP:D2:审定表D2-1:C10', project_id: 'p-1', year: 2025,
    })
  })

  it('403：返回 null、不抛出、只记日志不另行告警', async () => {
    h.post.mockRejectedValue(httpError(403))
    const { notify, loading } = useStaleImpact('D2')
    await expect(notify({ sheet: '审定表D2-1', cell: 'C10', project_id: 'p-1' })).resolves.toBeNull()
    expect(loading.value).toBe(false)
    expect(h.log).toHaveBeenCalledTimes(1)
    expect(String(h.log.mock.calls[0][0])).toContain('403')
    expect(warnSpy).not.toHaveBeenCalled()
  })

  it('503：降级静默返回 null', async () => {
    h.post.mockRejectedValue(httpError(503))
    const { notify } = useStaleImpact('D2')
    await expect(notify({ sheet: '审定表D2-1', cell: 'C10', project_id: 'p-1' })).resolves.toBeNull()
    expect(String(h.log.mock.calls[0][0])).toContain('503')
    expect(warnSpy).not.toHaveBeenCalled()
  })

  it('其他错误：返回 null 并 console.warn（不阻断保存）', async () => {
    h.post.mockRejectedValue(httpError(500))
    const { notify } = useStaleImpact('D2')
    await expect(notify({ sheet: '审定表D2-1', cell: 'C10', project_id: 'p-1' })).resolves.toBeNull()
    expect(warnSpy).toHaveBeenCalledTimes(1)
  })
})
