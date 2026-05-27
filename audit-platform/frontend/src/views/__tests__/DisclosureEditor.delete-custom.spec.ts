/**
 * DisclosureEditor — 删除自定义章节 + 新增章节（Sprint 3 Task 3.5 / 3.1）
 *
 * Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 3 Task 3.5 + 3.1
 * Reqs:   R4.1 验收 32（删除自定义条目 + 30 天保留期） + R4.3 验收 36
 *
 * 通过 useNoteCustomTemplate 薄层封装单测覆盖 DisclosureEditor 的：
 * - 新增章节 → POST /api/projects/{pid}/note-template/save 携带 union sections
 * - 删除自定义章节 → POST 同上端点，sections 中移除目标 section_number
 * - 30 天保留语义：删除产生新版本，旧版本作为不可变快照保留（D8 storage）
 *
 * 用例：
 * 1. addOrUpdateCustomSection: 当前为空 → 新增一条，POST 携带单元素 sections 数组
 * 2. addOrUpdateCustomSection: 同 section_number 覆盖（不重复追加）
 * 3. removeCustomSection: 移除指定章节 → POST sections 不含该章节
 * 4. removeCustomSection: 当前不包含该章节 → 返回 null，不发起 POST
 *
 * **Validates: Requirements R4.1, R4.3**
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// ─── Mock apiProxy ─────────────────────────────────────────────────────────

const mockGet = vi.fn()
const mockPost = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  default: {
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
  },
  api: {
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
  },
}))

import {
  loadCurrentCustomTemplate,
  addOrUpdateCustomSection,
  removeCustomSection,
} from '@/composables/useNoteCustomTemplate'

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
})

describe('DisclosureEditor — Sprint 3 Task 3.1: 新增章节', () => {
  it('用例 1 — 当前为空 → POST 携带单元素 sections 数组', async () => {
    mockGet.mockResolvedValue({})  // 主文件不存在 / 为空
    mockPost.mockResolvedValue({
      version: 1,
      updated_at: '2026-05-27T10:00:00Z',
      history: [{ version: 1, snapshot_path: 'v1.json', updated_at: '2026-05-27T10:00:00Z' }],
    })

    const result = await addOrUpdateCustomSection('proj-A', {
      section_number: '五、X1',
      section_title: '递延收益',
      account_name: '递延收益',
      sort_order: 9000,
    })

    expect(mockPost).toHaveBeenCalledWith(
      '/api/projects/proj-A/note-template/save',
      expect.objectContaining({
        sections: [
          expect.objectContaining({
            section_number: '五、X1',
            section_title: '递延收益',
            _custom: true,
          }),
        ],
      }),
    )
    expect(result.version).toBe(1)
  })

  it('用例 2 — 已存在同 section_number 时覆盖（不重复追加）', async () => {
    const existing = {
      version: 2,
      sections: [
        { section_number: '五、X1', section_title: '旧标题', _custom: true },
        { section_number: '五、X2', section_title: '其他自定义', _custom: true },
      ],
    }
    mockGet.mockResolvedValue(existing)
    mockPost.mockResolvedValue({ version: 3, updated_at: '...', history: [] })

    await addOrUpdateCustomSection('proj-A', {
      section_number: '五、X1',
      section_title: '新标题',
      sort_order: 9100,
    })

    const sentBody = mockPost.mock.calls[0][1]
    // 仍是 2 条（覆盖而非追加）
    expect(sentBody.sections).toHaveLength(2)
    const x1 = sentBody.sections.find((s: any) => s.section_number === '五、X1')
    expect(x1.section_title).toBe('新标题')
    expect(x1.sort_order).toBe(9100)
    // X2 保持不动
    const x2 = sentBody.sections.find((s: any) => s.section_number === '五、X2')
    expect(x2.section_title).toBe('其他自定义')
  })
})

describe('DisclosureEditor — Sprint 3 Task 3.5: 删除自定义章节', () => {
  it('用例 3 — 移除指定章节 → POST sections 不含该章节（30 天回收期由后端 D8 v{N}.json 提供）', async () => {
    const existing = {
      version: 5,
      sections: [
        { section_number: '五、X1', section_title: 'A', _custom: true },
        { section_number: '五、X2', section_title: 'B', _custom: true },
        { section_number: '五、X3', section_title: 'C', _custom: true },
      ],
    }
    mockGet.mockResolvedValue(existing)
    mockPost.mockResolvedValue({ version: 6, updated_at: '...', history: [] })

    const result = await removeCustomSection('proj-A', '五、X2')

    expect(mockPost).toHaveBeenCalledWith(
      '/api/projects/proj-A/note-template/save',
      expect.objectContaining({
        sections: expect.arrayContaining([
          expect.objectContaining({ section_number: '五、X1' }),
          expect.objectContaining({ section_number: '五、X3' }),
        ]),
      }),
    )
    const sentSections = mockPost.mock.calls[0][1].sections
    expect(sentSections).toHaveLength(2)
    expect(sentSections.find((s: any) => s.section_number === '五、X2')).toBeUndefined()
    expect(result?.version).toBe(6)
  })

  it('用例 4 — 当前不包含该章节 → 返回 null，不发起 POST', async () => {
    mockGet.mockResolvedValue({
      version: 1,
      sections: [
        { section_number: '五、X1', section_title: 'A', _custom: true },
      ],
    })

    const result = await removeCustomSection('proj-A', '五、X9')

    expect(result).toBeNull()
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('用例 5 — sectionNumber 为空字符串 → 抛错', async () => {
    await expect(removeCustomSection('proj-A', '')).rejects.toThrow(/sectionNumber/)
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('用例 6 — loadCurrentCustomTemplate 容错：API 错误返回空 sections', async () => {
    mockGet.mockRejectedValue(new Error('500'))
    const payload = await loadCurrentCustomTemplate('proj-A')
    expect(payload.sections).toEqual([])
    expect(payload.version).toBe(0)
  })
})
