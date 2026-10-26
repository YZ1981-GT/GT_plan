/**
 * 委派扩权重试的 API 层（spec procedure-trim-generation-delegation-chain 任务 13）：`expand_scope` / `scope_reason`
 * 并进请求体、`silent` 转成 `_silent` 请求配置；不传选项时请求与原来一致（不多字段、不静默）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ put: vi.fn(), post: vi.fn(), get: vi.fn(), delete: vi.fn(), patch: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: http }))

import { applyProcedureDelegation, assignProcedures, previewProcedureDelegation } from '../commonApi'

beforeEach(() => {
  vi.clearAllMocks()
  http.put.mockResolvedValue({ data: { updated: 1 } })
  http.post.mockResolvedValue({ data: { applied: 1 } })
})

const BODY = { selector: { kind: 'row' as const, task_ids: ['t1'] }, assignee_staff_id: 's1' }

describe('assignProcedures', () => {
  it('不传选项：只发 assignments，不静默', async () => {
    await assignProcedures('p1', [{ procedure_id: 'x', staff_id: 's1' }])
    expect(http.put).toHaveBeenCalledWith('/api/projects/p1/workpaper-leads',
      { assignments: [{ procedure_id: 'x', staff_id: 's1' }] }, {})
  })

  it('带扩权选项：理由并进请求体，silent 转为 _silent', async () => {
    await assignProcedures('p1', [{ procedure_id: 'x', staff_id: 's1' }],
      { expand_scope: true, scope_reason: '支援', silent: true })
    expect(http.put).toHaveBeenCalledWith('/api/projects/p1/workpaper-leads',
      { assignments: [{ procedure_id: 'x', staff_id: 's1' }], expand_scope: true, scope_reason: '支援' },
      { _silent: true })
  })
})

describe('previewProcedureDelegation（spec procedure-chain-hardening-and-java-contracts R12.3）', () => {
  it('不传选项：不静默；silent ⇒ _silent（422 只由调用方提示一次，浏览器实测原先弹两条）', async () => {
    http.post.mockResolvedValue({ data: { preview_id: 'pv' } })
    expect(await previewProcedureDelegation('p1', BODY)).toEqual({ preview_id: 'pv' })
    expect(http.post).toHaveBeenLastCalledWith('/api/projects/p1/procedure-delegations/preview', BODY, {})
    await previewProcedureDelegation('p1', BODY, { silent: true })
    expect(http.post).toHaveBeenLastCalledWith('/api/projects/p1/procedure-delegations/preview', BODY, { _silent: true })
  })
})

describe('applyProcedureDelegation', () => {
  it('不传选项：请求体 = 预览 body + 凭证 + 请求号', async () => {
    await applyProcedureDelegation('p1', 'pv', 'rq', BODY)
    expect(http.post).toHaveBeenCalledWith('/api/projects/p1/procedure-delegations/apply',
      { ...BODY, preview_id: 'pv', request_id: 'rq' }, {})
  })

  it('带扩权选项：同一凭证与请求号，多出 expand_scope / scope_reason，静默', async () => {
    await applyProcedureDelegation('p1', 'pv', 'rq', BODY, { expand_scope: true, scope_reason: '支援', silent: true })
    expect(http.post).toHaveBeenCalledWith('/api/projects/p1/procedure-delegations/apply',
      { ...BODY, expand_scope: true, scope_reason: '支援', preview_id: 'pv', request_id: 'rq' }, { _silent: true })
  })
})
