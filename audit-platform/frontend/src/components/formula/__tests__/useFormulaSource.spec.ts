/**
 * useFormulaSource.spec.ts — 公式三来源 composable 单元测试
 *
 * spec formula-management-library Task 21.2（Req 25.1-25.6）
 *
 * 覆盖：
 *  ③ custom 恢复预设调 restore 端点 —— restorePreset 调
 *     DELETE /api/workpapers/{wpId}/user-formulas/{cell_key}（复用既有端点，不重写）
 *  - reference 候选源加载 —— loadReferenceCandidates 调 GET /api/workpapers/{wpId}/formulas
 *    并归一化为 ReferenceCandidate[]
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const { mockGet, mockDelete } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockDelete: vi.fn(),
}))

vi.mock('@/utils/http', () => ({
  default: { get: mockGet, delete: mockDelete },
}))

import { useFormulaSource } from '../useFormulaSource'

describe('useFormulaSource — 公式三来源数据源（Req 25.4/25.5）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ── ③ custom 恢复预设调 restore 端点（Req 25.4） ─────────────────────────────
  it('restorePreset 调 DELETE user-formulas 端点（cell_key 经 encodeURIComponent）', async () => {
    mockDelete.mockResolvedValue({ data: { status: 'ok' } })
    const api = useFormulaSource()

    const ok = await api.restorePreset('wp-1', '货币资金审定表E1-1!B7')

    expect(ok).toBe(true)
    expect(mockDelete).toHaveBeenCalledWith(
      '/api/workpapers/wp-1/user-formulas/' +
        encodeURIComponent('货币资金审定表E1-1!B7'),
    )
  })

  it('restorePreset 缺 wpId/cellKey → 不发请求，返回 false', async () => {
    const api = useFormulaSource()
    expect(await api.restorePreset('', 'B7')).toBe(false)
    expect(await api.restorePreset('wp-1', '')).toBe(false)
    expect(mockDelete).not.toHaveBeenCalled()
  })

  it('restorePreset 端点报错 → 返回 false 且不抛异常', async () => {
    mockDelete.mockRejectedValue(new Error('500'))
    const api = useFormulaSource()
    expect(await api.restorePreset('wp-1', 'B7')).toBe(false)
  })

  // ── reference 候选源加载（Req 25.5） ─────────────────────────────────────────
  it('loadReferenceCandidates 调 GET formulas 并归一化候选源公式', async () => {
    mockGet.mockResolvedValue({
      data: {
        items: [
          {
            id: 'f1',
            sheet_name: '审定表',
            target_cell: 'B7',
            expression: "TB('1001','审定数')",
            formula_type: 'auto_calc',
          },
          { id: 'f2', target_cell: 'C3', expression: "ROW('BS-001')" },
        ],
      },
    })
    const api = useFormulaSource()

    await api.loadReferenceCandidates('wp-1')

    expect(mockGet).toHaveBeenCalledWith('/api/workpapers/wp-1/formulas')
    expect(api.candidates.value).toHaveLength(2)
    expect(api.candidates.value[0]).toEqual({
      id: 'f1',
      sheet_name: '审定表',
      target_cell: 'B7',
      expression: "TB('1001','审定数')",
      formula_type: 'auto_calc',
    })
    // 缺失字段回退默认
    expect(api.candidates.value[1].formula_type).toBe('auto_calc')
    expect(api.candidates.value[1].sheet_name).toBe('')
  })

  it('loadReferenceCandidates 缺 wpId → 不发请求', async () => {
    const api = useFormulaSource()
    await api.loadReferenceCandidates('')
    expect(mockGet).not.toHaveBeenCalled()
  })

  it('loadReferenceCandidates 端点报错 → candidates 置空且不抛异常', async () => {
    mockGet.mockRejectedValue(new Error('boom'))
    const api = useFormulaSource()
    await api.loadReferenceCandidates('wp-1')
    expect(api.candidates.value).toEqual([])
  })
})
