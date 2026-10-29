/**
 * RV9.1-02 守卫：起点身份算不出时，照实告诉用户「未能分析下游影响」
 *
 * 判据（design §10.2）：
 * 1. useStaleImpact 暴露 unresolvedReason，取后端 unresolved_reason；能分析时为空。
 * 2. 每次通知先清掉上一次的原因：本次没发请求或请求失败时不留旧原因（T31 返工）。
 * 3. 同一会话同一 (底稿, sheet) 只提示一次、换 sheet 再提示、后端能分析时不提示 —— 这三条走真实保存流程，
 *    用例在 useEditorSave.spec.ts（原先在本文件里复刻了一份判定再测，改坏生产代码也照样绿）。
 *
 * 变异：notify 不再读 unresolved_reason，或开头不清旧原因 → 本文件对应用例红。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// vi.mock 的工厂会被提升到文件顶部，桩必须用 vi.hoisted 才能被它引用
const { post } = vi.hoisted(() => ({ post: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { post, get: vi.fn() } }))
vi.mock('@/utils/logger', () => ({ logger: { log: vi.fn(), warn: vi.fn() } }))
vi.mock('@/services/apiPaths', () => ({
  linkageBus: { impact: '/api/linkage-bus/impact' },
  addressRegistry: { v2: { staleImpact: '/api/address-registry/v2/stale-impact' } },
}))

import { useStaleImpact } from '../useStaleImpact'

describe('useStaleImpact.unresolvedReason', () => {
  beforeEach(() => {
    post.mockReset()
  })

  it('后端算不出起点身份时暴露中文原因', async () => {
    post.mockResolvedValue({
      data: {
        unresolved_code: 'label_not_a1',
        unresolved_reason: '引用末段是语义标签、不是 A1 单元格坐标',
        affected: [],
        total: 0,
      },
    })
    const s = useStaleImpact('D2')
    await s.notify({ sheet: '审定表D2-1', cell: '期末余额', project_id: 'p1', year: 2025 })
    expect(s.unresolvedReason.value).toBe('引用末段是语义标签、不是 A1 单元格坐标')
  })

  it('能分析时原因为空', async () => {
    post.mockResolvedValue({ data: { affected: ['WP:D3:审定表D3-1:C10'], total: 1 } })
    const s = useStaleImpact('D2')
    await s.notify({ sheet: '审定表D2-1', cell: 'C10', project_id: 'p1', year: 2025 })
    expect(s.unresolvedReason.value).toBe('')
    expect(s.totalAffected.value).toBe(1)
  })

  it('clear 会清掉原因', async () => {
    post.mockResolvedValue({ data: { unresolved_reason: 'x', affected: [], total: 0 } })
    const s = useStaleImpact('D2')
    await s.notify({ sheet: 's', cell: 'c', project_id: 'p1', year: 2025 })
    expect(s.unresolvedReason.value).toBe('x')
    s.clear()
    expect(s.unresolvedReason.value).toBe('')
  })
})

describe('useStaleImpact.unresolvedReason 不留上一次的原因', () => {
  beforeEach(() => {
    post.mockReset()
  })

  async function withReason() {
    post.mockResolvedValueOnce({ data: { unresolved_reason: '上一次的原因', affected: [], total: 0 } })
    const s = useStaleImpact('D2')
    await s.notify({ sheet: '审定表D2-1', cell: 'C10', project_id: 'p1', year: 2025 })
    expect(s.unresolvedReason.value).toBe('上一次的原因')
    return s
  }

  it('下一次因年度为空没有发请求 → 原因清空', async () => {
    const s = await withReason()
    await s.notify({ sheet: '明细表D2-2', cell: 'C10', project_id: 'p1', year: null })
    expect(post).toHaveBeenCalledTimes(1)
    expect(s.unresolvedReason.value).toBe('')
  })

  it('下一次请求被拒（403）→ 原因清空', async () => {
    const s = await withReason()
    post.mockRejectedValueOnce({ response: { status: 403 } })
    await s.notify({ sheet: '明细表D2-2', cell: 'C10', project_id: 'p1', year: 2025 })
    expect(s.unresolvedReason.value).toBe('')
  })
})

// 保存流程「同一 (底稿, sheet) 只提示一次」的行为用例在 useEditorSave.spec.ts（走真实 onSave，不复刻判定）。
