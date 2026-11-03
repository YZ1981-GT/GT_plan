/**
 * A30「按项目底稿建议」只填空项（spec attachment-archive-and-a-class-evidence 需求 8.2、8.3）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn() },
  ElMessageBox: { alert: vi.fn(() => Promise.resolve()) },
}))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))

import { api } from '@/services/apiProxy'
import { ElMessageBox } from 'element-plus'
import { planSuggestions, suggestionsPath, useArchiveChecklistSuggest } from '../useArchiveChecklistSuggest'

describe('planSuggestions', () => {
  it('只填空项；已填与建议相反才算冲突；不适用不算冲突', () => {
    const current: Record<string, string> = { 'A30-D2': '否', 'A30-E1': '是', 'A30-F1': '不适用', 'A30-G1': '  ' }
    const plan = planSuggestions(
      { 'A30-D2': '是', 'A30-E1': '是', 'A30-F1': '是', 'A30-G1': '否', 'A30-H1': '是' },
      (id) => current[id] || '',
    )
    expect(plan.fill).toEqual([['A30-G1', '否'], ['A30-H1', '是']])
    expect(plan.conflicts).toEqual([{ itemId: 'A30-D2', current: '否', suggested: '是' }])
  })
})

describe('useArchiveChecklistSuggest', () => {
  const answers: Record<string, string | null> = {}
  const updateConclusion = vi.fn((id: string, v: string) => { answers[id] = v })
  const base = {
    projectId: () => 'p1', wpId: () => 'w1', wpCode: () => 'A30', readonly: () => false,
    getResponse: (id: string) => ({ conclusion: answers[id] ?? null }), updateConclusion,
  }

  beforeEach(() => {
    vi.clearAllMocks()
    for (const k of Object.keys(answers)) delete answers[k]
  })

  it('只对 A30 且非只读可用', () => {
    expect(useArchiveChecklistSuggest(base).available.value).toBe(true)
    expect(useArchiveChecklistSuggest({ ...base, wpCode: () => 'A17-5-1' }).available.value).toBe(false)
    expect(useArchiveChecklistSuggest({ ...base, readonly: () => true }).available.value).toBe(false)
  })

  it('取建议后只写空项，冲突项提示不改', async () => {
    answers['A30-D2'] = '否'
    vi.mocked(api.get).mockResolvedValue({ suggestions: { 'A30-D2': '是', 'A30-E1': '是' }, total: 2, present: 2 })
    const s = useArchiveChecklistSuggest({ ...base, itemLabel: (id) => id.replace(/^A30-/, '') })
    const result = await s.applySuggestions()
    expect(api.get).toHaveBeenCalledWith(suggestionsPath('p1', 'w1'))
    expect(suggestionsPath('p1', 'w1')).toBe('/api/projects/p1/workpapers/w1/archive-checklist/suggestions')
    expect(updateConclusion).toHaveBeenCalledTimes(1)
    expect(updateConclusion).toHaveBeenCalledWith('A30-E1', '是')
    expect(answers['A30-D2']).toBe('否')
    expect(result?.conflicts).toHaveLength(1)
    expect(vi.mocked(ElMessageBox.alert).mock.calls[0][0]).toContain('D2：已填「否」，项目底稿显示「是」')
  })

  it('只读时不请求', async () => {
    const s = useArchiveChecklistSuggest({ ...base, readonly: () => true })
    expect(await s.applySuggestions()).toBeNull()
    expect(api.get).not.toHaveBeenCalled()
  })
})
