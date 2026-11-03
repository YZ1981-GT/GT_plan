/**
 * 联动影响分析的年度（spec post-push-residual-defect-closure 6.5.3）：
 * 端点 year 必填；原先缺年度时兜底今年 ⇒ 标的是别的年度的下游。现在缺年度不发。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const post = vi.fn()
vi.mock('@/utils/http', () => ({ default: { post: (...a: unknown[]) => post(...a), get: vi.fn() } }))
vi.mock('@/utils/logger', () => ({ logger: { log: vi.fn(), warn: vi.fn(), error: vi.fn() } }))

import { useStaleImpact } from '../useStaleImpact'

beforeEach(() => {
  post.mockReset().mockResolvedValue({ data: { affected: [], total: 0 } })
})

describe('useStaleImpact.notify 年度', () => {
  it('带项目年度：按它分析', async () => {
    await useStaleImpact('D2').notify({ sheet: 'S1', project_id: 'p1', year: 2025 })
    expect(post).toHaveBeenCalledTimes(1)
    expect(post.mock.calls[0][1]).toMatchObject({ project_id: 'p1', year: 2025 })
  })

  it.each([[null], [undefined]])('年度缺失（%s）：不发请求', async (y) => {
    const r = await useStaleImpact('D2').notify({ sheet: 'S1', project_id: 'p1', year: y as null | undefined })
    expect(r).toBeNull()
    expect(post).not.toHaveBeenCalled()
  })
})
