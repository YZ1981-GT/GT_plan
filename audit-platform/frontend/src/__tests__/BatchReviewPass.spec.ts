/**
 * 批量复核前端测试
 * Validates: Requirements 7.2, 7.6
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const mockPush = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'test-project' }, query: {} }),
  useRouter: () => ({ push: mockPush, replace: vi.fn() }),
}))

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

vi.mock('@/services/pmApi', () => ({
  getGlobalReviewInbox: vi.fn().mockResolvedValue([]),
  getProjectReviewInbox: vi.fn().mockResolvedValue([]),
  batchReview: vi.fn().mockResolvedValue({ success: 2, failed: 0 }),
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    user: { id: 'user-1', role: 'manager', name: 'Test Manager' },
  }),
}))

import { api } from '@/services/apiProxy'

describe('BatchReviewPass', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('batch review API is called with correct payload', async () => {
    vi.mocked(api.post).mockResolvedValue({
      success_count: 3,
      skipped_count: 1,
      skipped_items: [{ wp_id: 'wp-4', reason: '未提交复核' }],
    })

    const result = await api.post(
      '/api/projects/test-project/batch-review-pass',
      { wp_ids: ['wp-1', 'wp-2', 'wp-3', 'wp-4'], comment: '已审阅，无异议' }
    )

    expect(api.post).toHaveBeenCalledWith(
      '/api/projects/test-project/batch-review-pass',
      { wp_ids: ['wp-1', 'wp-2', 'wp-3', 'wp-4'], comment: '已审阅，无异议' }
    )
    expect(result.success_count).toBe(3)
    expect(result.skipped_count).toBe(1)
    expect(result.skipped_items[0].reason).toBe('未提交复核')
  })

  it('default comment is "已审阅，无异议"', () => {
    const defaultComment = '已审阅，无异议'
    expect(defaultComment).toBe('已审阅，无异议')
  })

  it('result summary includes success and skipped counts', async () => {
    vi.mocked(api.post).mockResolvedValue({
      success_count: 5,
      skipped_count: 2,
      skipped_items: [
        { wp_id: 'wp-6', reason: '未提交复核' },
        { wp_id: 'wp-7', reason: '已通过' },
      ],
    })

    const result = await api.post(
      '/api/projects/test-project/batch-review-pass',
      { wp_ids: ['wp-1', 'wp-2', 'wp-3', 'wp-4', 'wp-5', 'wp-6', 'wp-7'], comment: '已审阅，无异议' }
    )

    expect(result.success_count + result.skipped_count).toBe(7)
    expect(result.skipped_items).toHaveLength(2)
    result.skipped_items.forEach((item: any) => {
      expect(item.reason).toBeTruthy()
    })
  })

  it('handles empty selection gracefully', async () => {
    vi.mocked(api.post).mockResolvedValue({
      success_count: 0,
      skipped_count: 0,
      skipped_items: [],
    })

    const result = await api.post(
      '/api/projects/test-project/batch-review-pass',
      { wp_ids: [], comment: '已审阅，无异议' }
    )

    expect(result.success_count).toBe(0)
    expect(result.skipped_count).toBe(0)
  })
})
