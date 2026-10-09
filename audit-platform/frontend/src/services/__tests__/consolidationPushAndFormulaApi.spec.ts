import { beforeEach, describe, expect, it, vi } from 'vitest'

const { api } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}))
vi.mock('@/services/apiProxy', () => ({ api }))

import {
  createConsolNoteFormula,
  deleteConsolNoteFormula,
  getConsolPushRuns,
  getConsolPushStatus,
  listConsolNoteFormulas,
  pushConsolidation,
  reseedConsolNoteFormulas,
  updateConsolNoteFormula,
} from '@/services/consolidationApi'

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset())
})

describe('合并推送 API 契约', () => {
  it('默认/公式变更 trigger 精确发送，排队回执原样返回', async () => {
    const ack = { queued: false, message: '已有推送在排队，本次请求已并入', project_id: 'p1', year: 2025 }
    api.post.mockResolvedValue(ack)
    await expect(pushConsolidation('p1', 2025)).resolves.toEqual(ack)
    expect(api.post).toHaveBeenLastCalledWith('/api/consolidation/p1/2025/push', { trigger: 'manual' })
    await pushConsolidation('p1', 2025, 'formula_changed')
    expect(api.post).toHaveBeenLastCalledWith('/api/consolidation/p1/2025/push', { trigger: 'formula_changed' })
  })

  it('运行列表主动解包 runs，limit 与 status 路径正确', async () => {
    api.get.mockResolvedValueOnce({ runs: [{ id: 'r1' }] }).mockResolvedValueOnce({ last_run: null, is_stale: false, stale_rows: 0 })
    await expect(getConsolPushRuns('p1', 2025, 10)).resolves.toEqual([{ id: 'r1' }])
    expect(api.get).toHaveBeenNthCalledWith(1, '/api/consolidation/p1/2025/push-runs', { params: { limit: 10 } })
    await expect(getConsolPushStatus('p1', 2025)).resolves.toMatchObject({ is_stale: false })
    expect(api.get).toHaveBeenNthCalledWith(2, '/api/consolidation/p1/2025/push-status')
  })
})

describe('合并附注公式 API 契约', () => {
  const payload = {
    template_type: 'soe' as const, section_id: '五-1-1', row_index: 0, col_index: 1,
    formula: "TB('1001','期末余额')", description: '说明',
  }

  it('列表按模板/章节查询，新增路径与 body 正确', async () => {
    api.get.mockResolvedValue({ template_type: 'soe', count: 0, sections: [] })
    api.post.mockResolvedValue({ id: 'n1' })
    await listConsolNoteFormulas('soe', '五-1-1')
    expect(api.get).toHaveBeenCalledWith('/api/consol-note-formulas', {
      params: { template_type: 'soe', section_id: '五-1-1' },
    })
    await createConsolNoteFormula(payload)
    expect(api.post).toHaveBeenCalledWith('/api/consol-note-formulas', payload)
  })

  it('修改、删除与重新种子化使用公式 ID / 模板参数', async () => {
    api.put.mockResolvedValue({ id: 'n1' })
    api.delete.mockResolvedValue({ id: 'n1', deleted: true })
    api.post.mockResolvedValue({ inserted: 1 })
    await updateConsolNoteFormula('n1', { formula: 'REPORT(\'BS-002\')', description: null })
    expect(api.put).toHaveBeenCalledWith('/api/consol-note-formulas/n1', { formula: "REPORT('BS-002')", description: null })
    await deleteConsolNoteFormula('n1')
    expect(api.delete).toHaveBeenCalledWith('/api/consol-note-formulas/n1')
    await reseedConsolNoteFormulas('listed')
    expect(api.post).toHaveBeenCalledWith('/api/consol-note-formulas/seed?template_type=listed')
  })
})
