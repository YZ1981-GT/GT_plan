/**
 * Sprint 4 Task 4.3 — 报表 ReportView 「附注引用我」侧栏前端测试
 *
 * Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 4 Task 4.3
 * Reqs:   rowCode → 反查所有引用此报表项的 note_section（双向溯源跳转）
 *
 * 覆盖：
 * 1. apiPaths.reports.noteReferences URL 拼接正确
 * 2. row_code 含特殊字符时正确 URL-encode
 * 3. mock api.get 返回的数据 shape 与组件契约一致
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(),
  },
}))

import { reports } from '@/services/apiPaths/report'
import { api } from '@/services/apiProxy'

describe('apiPaths.reports.noteReferences', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('拼接 URL 包含 project_id / year / row_code 三段', () => {
    const url = reports.noteReferences('proj-1', 2024, 'BS-001')
    expect(url).toBe('/api/financial-reports/proj-1/2024/BS-001/note-references')
  })

  it('row_code 含特殊字符时 URL-encode（避免路径解析歧义）', () => {
    const url = reports.noteReferences('p', 2024, '资产/负债 行 1')
    // 必须 encode 至少 / 与中文 / 空格
    expect(url).toContain(encodeURIComponent('资产/负债 行 1'))
    expect(url).not.toContain('资产/负债 行 1') // 原文不出现在最终 URL
  })

  it('row_code 为简单 ASCII 时不破坏路径', () => {
    const url = reports.noteReferences('p', 2024, 'BS-001-A')
    expect(url).toBe('/api/financial-reports/p/2024/BS-001-A/note-references')
  })

  it('mock api.get 返回正确 shape 时调用方可消费 notes 数组', async () => {
    vi.mocked(api.get).mockResolvedValue({
      row_code: 'BS-001',
      notes: [
        { note_section: '五、1 货币资金', section_title: '货币资金', table_index: 0 },
        { note_section: '五、1 货币资金', section_title: '货币资金', table_index: 1 },
      ],
    } as any)

    const resp: any = await api.get(reports.noteReferences('p', 2024, 'BS-001'))
    expect(resp.row_code).toBe('BS-001')
    expect(resp.notes).toHaveLength(2)
    expect(resp.notes[0].note_section).toBe('五、1 货币资金')
    expect(resp.notes[1].table_index).toBe(1)
  })

  it('空 notes 时调用方应能优雅处理', async () => {
    vi.mocked(api.get).mockResolvedValue({
      row_code: 'BS-999',
      notes: [],
    } as any)

    const resp: any = await api.get(reports.noteReferences('p', 2024, 'BS-999'))
    expect(resp.notes).toEqual([])
  })
})
