/**
 * 粗裁 apply 的确认标记（spec procedure-trim-generation-delegation-chain 需求 3.2）：用户确认把有编制内容的
 * 已生成底稿移入回收站时，请求体带 `confirm_substantive_recycle: true`；不传 / 传 false 时请求体与原来一致
 * （后端没收到确认而有这类底稿 ⇒ 409、零副作用）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ put: vi.fn(), post: vi.fn(), get: vi.fn(), delete: vi.fn(), patch: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: http }))

import { canonicalTrimApply, type CanonicalTrimScopeEntry } from '../commonApi'

const URL = '/api/projects/p1/procedure-trim/apply'
const ENTRIES: CanonicalTrimScopeEntry[] = [
  { kind: 'scope', cycle: 'H', wp_index_code: 'H3', target_status: 'not_applicable', skip_reason: '本期无投资性房地产' },
]

beforeEach(() => {
  vi.clearAllMocks()
  http.post.mockResolvedValue({ data: { applied: 2 } })
})

describe('canonicalTrimApply', () => {
  it('不传确认：请求体只有 entries / 凭证 / 请求号', async () => {
    expect(await canonicalTrimApply('p1', ENTRIES, 'pv', 'rq')).toEqual({ applied: 2 })
    expect(http.post).toHaveBeenCalledWith(URL, { entries: ENTRIES, preview_id: 'pv', request_id: 'rq' })
  })

  it('确认移入回收站：多出 confirm_substantive_recycle；传 false 不带这个键', async () => {
    await canonicalTrimApply('p1', ENTRIES, 'pv', 'rq', { confirmSubstantiveRecycle: true })
    expect(http.post.mock.calls[0]).toEqual([
      URL, { entries: ENTRIES, preview_id: 'pv', request_id: 'rq', confirm_substantive_recycle: true },
    ])
    await canonicalTrimApply('p1', ENTRIES, 'pv', 'rq', { confirmSubstantiveRecycle: false })
    expect(http.post.mock.calls[1][1]).not.toHaveProperty('confirm_substantive_recycle')
  })
})
