// Feature: procedure-delegation-visibility-isolation — Task 12
//
// 验证底稿列表服务层消费 Task 8 分页 envelope（组件 C13）：
//  - listWorkpapersPaged / listMyLeadWorkpapers 返回完整 {items,total,stats,page,page_size}
//  - legacy listWorkpapers 兼容 envelope（抽 items）并逐页拉取全集、过滤 nullable wp
//  - legacy `status` 查询参数映射到 index_status（Req 12.6）
//  - 两个独立视图打不同端点（Req 11.11/11.12：程序任务 vs 主编不串线）
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockGet = vi.fn()
vi.mock('@/utils/http', () => ({
  default: { get: (...a: any[]) => mockGet(...a) },
  downloadFile: vi.fn(),
}))

import {
  listWorkpapersPaged,
  listMyLeadWorkpapers,
  listWorkpapers,
} from '@/services/workpaperApi'

function envItem(over: Record<string, any> = {}) {
  return {
    wp_index_id: 'wi-1', project_id: 'p1', wp_id: 'wp-1', wp_code: 'D2-1',
    wp_name: '应收账款', audit_cycle: 'D', index_status: 'in_progress',
    file_status: 'draft', review_status: 'not_submitted', assigned_to: 'u1',
    reviewer: null, file_version: 1, file_path: '/x', source_type: 'template',
    prefill_stale: false, wp_generated: true, created_at: null, updated_at: null,
    ...over,
  }
}

beforeEach(() => {
  mockGet.mockReset()
})

describe('listWorkpapersPaged — 分页 envelope', () => {
  it('returns full envelope and forwards page/page_size', async () => {
    mockGet.mockResolvedValue({
      data: { items: [envItem()], total: 5, stats: { by_index_status: { in_progress: 5 }, by_file_status: { draft: 5 } }, page: 2, page_size: 10 },
    })
    const env = await listWorkpapersPaged('p1', { page: 2, page_size: 10, sort: 'wp_code' })
    expect(env.total).toBe(5)
    expect(env.page).toBe(2)
    expect(env.page_size).toBe(10)
    expect(env.items[0].wp_code).toBe('D2-1')
    expect(env.stats.by_index_status).toEqual({ in_progress: 5 })
    const [url, cfg] = mockGet.mock.calls[0]
    expect(url).toContain('/working-papers')
    expect(cfg.params.page).toBe(2)
    expect(cfg.params.page_size).toBe(10)
  })

  it('normalizes missing fields to a stable envelope', async () => {
    mockGet.mockResolvedValue({ data: { items: [envItem()] } })
    const env = await listWorkpapersPaged('p1')
    expect(env.total).toBe(1) // fallback to items.length
    expect(env.stats).toEqual({ by_index_status: {}, by_file_status: {} })
    expect(env.page).toBe(1)
  })
})

describe('listMyLeadWorkpapers — 独立主编视图端点', () => {
  it('hits the my-lead-workpapers endpoint (not the tasks endpoint)', async () => {
    mockGet.mockResolvedValue({ data: { items: [], total: 0, stats: { by_index_status: {}, by_file_status: {} }, page: 1, page_size: 20 } })
    await listMyLeadWorkpapers('p1', { page: 1 })
    const [url] = mockGet.mock.calls[0]
    expect(url).toContain('/my-lead-workpapers')
  })
})

describe('legacy listWorkpapers — envelope 兼容 + 全量分页 + nullable 过滤', () => {
  it('extracts items from a single-page envelope and maps id from wp_id', async () => {
    mockGet.mockResolvedValue({
      data: { items: [envItem({ wp_id: 'wp-9' })], total: 1, page: 1, page_size: 100, stats: {} },
    })
    const rows = await listWorkpapers('p1')
    expect(rows.length).toBe(1)
    expect(rows[0].id).toBe('wp-9') // id 从 wp_id 映射
    expect(rows[0].status).toBe('draft') // file_status → status
  })

  it('filters out nullable wp (wp_generated=false) for legacy consumers', async () => {
    mockGet.mockResolvedValue({
      data: {
        items: [envItem({ wp_index_id: 'a', wp_id: 'wp-a' }), envItem({ wp_index_id: 'b', wp_id: null, wp_generated: false })],
        total: 2, page: 1, page_size: 100, stats: {},
      },
    })
    const rows = await listWorkpapers('p1')
    expect(rows.length).toBe(1)
    expect(rows[0].id).toBe('wp-a')
  })

  it('paginates through all pages until total is covered', async () => {
    // 250 total across 3 pages of 100
    const page1 = Array.from({ length: 100 }, (_, i) => envItem({ wp_index_id: `p1-${i}`, wp_id: `w1-${i}` }))
    const page2 = Array.from({ length: 100 }, (_, i) => envItem({ wp_index_id: `p2-${i}`, wp_id: `w2-${i}` }))
    const page3 = Array.from({ length: 50 }, (_, i) => envItem({ wp_index_id: `p3-${i}`, wp_id: `w3-${i}` }))
    mockGet
      .mockResolvedValueOnce({ data: { items: page1, total: 250, page: 1, page_size: 100, stats: {} } })
      .mockResolvedValueOnce({ data: { items: page2, total: 250, page: 2, page_size: 100, stats: {} } })
      .mockResolvedValueOnce({ data: { items: page3, total: 250, page: 3, page_size: 100, stats: {} } })
    const rows = await listWorkpapers('p1')
    expect(rows.length).toBe(250)
    expect(mockGet).toHaveBeenCalledTimes(3)
  })

  it('maps legacy `status` query param to index_status (Req 12.6)', async () => {
    mockGet.mockResolvedValue({ data: { items: [], total: 0, page: 1, page_size: 100, stats: {} } })
    await listWorkpapers('p1', { status: 'archived' })
    const [, cfg] = mockGet.mock.calls[0]
    expect(cfg.params.index_status).toBe('archived')
    expect(cfg.params.status).toBeUndefined()
  })

  it('supports a plain legacy array response (un-upgraded backend)', async () => {
    mockGet.mockResolvedValue({ data: [{ id: 'old-1', wp_index_id: 'wi', status: 'reviewed' }] })
    const rows = await listWorkpapers('p1')
    expect(rows.length).toBe(1)
    expect(rows[0].id).toBe('old-1')
    expect(mockGet).toHaveBeenCalledTimes(1)
  })
})
