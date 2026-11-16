/**
 * `updateReviewStatus` 必须带 `_silent`（缺陷修复 2026-11-16）。
 *
 * 为什么：调用方 `ReviewWorkbench` 的 catch 已调 `handleApiError` 统一处理错误。
 * 不带 `_silent` 时 `http.ts` 拦截器会先弹一次（显示后端中文原因），`handleApiError`
 * 再弹一次 ⇒ 同一次失败出现两条 toast（走查实测）。
 *
 * 这条守卫钉的是「错误提示只由调用方那一层负责」这一约定，不是实现细节：
 * 若将来改成由拦截器统一弹，必须同时删掉调用方的 handleApiError，否则又变两条。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'

const put = vi.fn()
vi.mock('@/utils/http', () => ({
  __esModule: true,
  default: {
    put: (...a: unknown[]) => put(...a),
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}))

import { updateReviewStatus } from '../workpaperApi'

beforeEach(() => {
  put.mockReset().mockResolvedValue({ data: { ok: true } })
})

describe('updateReviewStatus 错误提示归属', () => {
  it('请求带 _silent（避免拦截器与调用方各弹一次）', async () => {
    await updateReviewStatus('p1', 'wp1', 'level1_rejected', '原因')
    expect(put).toHaveBeenCalledTimes(1)
    const [url, body, config] = put.mock.calls[0]
    expect(String(url)).toContain('/review-status')
    expect(body).toEqual({ review_status: 'level1_rejected', reason: '原因' })
    expect(config, '必须显式传配置对象').toBeTruthy()
    expect((config as any)._silent, '缺少 _silent 会导致同一次失败弹两条 toast').toBe(true)
  })

  it('不传 reason 时请求体不带 reason 键', async () => {
    await updateReviewStatus('p1', 'wp1', 'level1_passed')
    const [, body] = put.mock.calls[0]
    expect(body).toEqual({ review_status: 'level1_passed' })
    expect('reason' in (body as Record<string, unknown>)).toBe(false)
  })
})
