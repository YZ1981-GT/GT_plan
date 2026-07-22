/**
 * GtAProgramConsoleA17Seq5.spec.ts — A17 seq5 核对表选版 UI
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useAProgramReview } from '@/composables/useAProgramReview'

const mockApiGet = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: unknown[]) => mockApiGet(...args),
    post: vi.fn().mockResolvedValue({}),
  },
}))

const a17Seq5Row = {
  linked_workpapers: 'A17-5-1,A17-5-2,A17-5-3,A17-5-4,A17-5-5',
}

function parseLinkedWorkpapers(value: string): string[] {
  return value.split(',').map(s => s.trim()).filter(Boolean)
}

describe('GtAProgramConsole — A17 seq5 核对表选版', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApiGet.mockImplementation((url: string) => {
      if (url.includes('/a17/applicable-versions')) {
        return Promise.resolve([
          { wp_code: 'A17-5-1', applicable: true, mandatory: true },
          { wp_code: 'A17-5-2', applicable: false, mandatory: true },
          { wp_code: 'A17-5-3', applicable: false, mandatory: true },
          { wp_code: 'A17-5-4', applicable: false, mandatory: true },
          { wp_code: 'A17-5-5', applicable: true, mandatory: false },
        ])
      }
      return Promise.resolve([])
    })
  })

  it('仅展示适用核对表 chip（A17-5-1 + A17-5-5）', async () => {
    const projectId = ref('proj-001')
    const review = useAProgramReview({
      sheetName: () => '重大事项概要程序表A17',
      projectId,
      parseLinkedWorkpapers,
    })

    await review.fetchA17ApplicableVersions()

    const applicable = review.a17ApplicableRefs(a17Seq5Row)
    expect(applicable).toContain('A17-5-1')
    expect(applicable).toContain('A17-5-5')
    expect(applicable).not.toContain('A17-5-3')
  })

  it('必做/推荐 badge 正确显示', async () => {
    const projectId = ref('proj-001')
    const review = useAProgramReview({
      sheetName: () => '重大事项概要程序表A17',
      projectId,
      parseLinkedWorkpapers,
    })

    await review.fetchA17ApplicableVersions()

    expect(review.a17_5Badge('A17-5-1')).toBe('必做')
    expect(review.a17_5Badge('A17-5-5')).toBe('推荐')
  })

  it('不适用版本默认折叠，展开后灰显', async () => {
    const projectId = ref('proj-001')
    const review = useAProgramReview({
      sheetName: () => '重大事项概要程序表A17',
      projectId,
      parseLinkedWorkpapers,
    })

    await review.fetchA17ApplicableVersions()

    const inapplicable = review.a17InapplicableRefs(a17Seq5Row)
    expect(inapplicable).toContain('A17-5-3')
    expect(review.isA17_5ChipDisabled('A17-5-3')).toBe(true)
  })
})
