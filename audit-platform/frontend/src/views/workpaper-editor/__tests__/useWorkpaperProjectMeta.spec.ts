/**
 * useWorkpaperProjectMeta —— 底稿编辑页取项目信息 / 审计年度
 *
 * 年度缺失时整页不渲染底稿，所以「没取到」（被 GET 去重取消 / 4xx / 5xx / 断网）必须与「项目没填年度」分开：
 * 2026-10-26 浏览器实测重药安徽（审计年度 2025）打开 J1A 整页显示「未设置审计年度」——同页另一组件同址 GET
 * 把编辑页这一发取消了，catch 里只给场景默认值、年度留空。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockGet = vi.fn()
vi.mock('@/services/apiProxy', () => ({ api: { get: (...args: any[]) => mockGet(...args) } }))

import { useWorkpaperProjectMeta } from '../useWorkpaperProjectMeta'

type Settle = { resolve: (v: any) => void; reject: (e: unknown) => void }

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

describe('useWorkpaperProjectMeta', () => {
  beforeEach(() => {
    mockGet.mockReset()
  })

  it('取到项目：年度取 audit_year，场景等照填，不算失败', async () => {
    mockGet.mockResolvedValue({ audit_year: 2025, scenario: 'ipo', has_foreign_currency: true, measurement_model: 'fair' })
    const m = useWorkpaperProjectMeta('p1')
    await m.loadProjectMeta()
    expect(m.projectYear.value).toBe(2025)
    expect(m.projectMeta.value).toEqual({ scenario: 'ipo', has_foreign_currency: true, measurement_model: 'fair' })
    expect(m.projectMetaFailed.value).toBe(false)
  })

  it('请求不参与 GET 去重、不弹全局提示、不把 4xx/5xx 当成功', async () => {
    mockGet.mockResolvedValue({ audit_year: 2025 })
    await useWorkpaperProjectMeta('p1').loadProjectMeta()
    expect(mockGet).toHaveBeenCalledTimes(1)
    const [url, config] = mockGet.mock.calls[0]
    expect(url).toBe('/api/projects/p1')
    expect(config).toMatchObject({ _dedupe: false, _silent: true })
    expect(config).not.toHaveProperty('validateStatus')
  })

  it('项目真没填年度：年度为空、不算失败（页面显示「未设置审计年度」）', async () => {
    mockGet.mockResolvedValue({ name: '无年度项目', audit_year: null, audit_period_end: null })
    const m = useWorkpaperProjectMeta('p1')
    await m.loadProjectMeta()
    expect(m.projectYear.value).toBeNull()
    expect(m.projectMeta.value).not.toBeNull()
    expect(m.projectMetaFailed.value).toBe(false)
  })

  it.each([
    ['被取消（GET 去重 / 切页）', Object.assign(new Error('canceled'), { name: 'CanceledError', code: 'ERR_CANCELED' })],
    ['服务端 500', Object.assign(new Error('Request failed with status code 500'), { response: { status: 500 } })],
    ['无权访问 403', Object.assign(new Error('Request failed with status code 403'), { response: { status: 403 } })],
  ])('%s：算失败，不当成「没填年度」', async (_label, error) => {
    mockGet.mockRejectedValue(error)
    const m = useWorkpaperProjectMeta('p1')
    await m.loadProjectMeta()
    expect(m.projectMetaFailed.value).toBe(true)
    expect(m.projectYear.value).toBeNull()
    expect(m.projectMeta.value).toBeNull()
  })

  it('重试成功后清掉失败标记', async () => {
    mockGet.mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce({ audit_year: 2024 })
    const m = useWorkpaperProjectMeta('p1')
    await m.loadProjectMeta()
    expect(m.projectMetaFailed.value).toBe(true)
    await m.loadProjectMeta()
    expect(m.projectMetaFailed.value).toBe(false)
    expect(m.projectYear.value).toBe(2024)
  })

  it.each([
    ['晚到的失败', (d: Settle) => d.reject(new Error('late failure'))],
    ['晚到的成功（旧数据）', (d: Settle) => d.resolve({ audit_year: 2019, scenario: 'old' })],
  ])('先发的请求%s不覆盖后发请求的结果', async (_label, settleFirst) => {
    const first = deferred<any>()
    const second = deferred<any>()
    mockGet.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const m = useWorkpaperProjectMeta('p1')
    const p1 = m.loadProjectMeta()
    const p2 = m.loadProjectMeta()
    second.resolve({ audit_year: 2025, scenario: 'normal' })
    await p2
    settleFirst(first)
    await p1
    expect(m.projectYear.value).toBe(2025)
    expect(m.projectMeta.value?.scenario).toBe('normal')
    expect(m.projectMetaFailed.value).toBe(false)
  })
})
