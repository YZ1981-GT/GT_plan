// Feature: procedure-delegation-visibility-isolation — Task 12
//
// 验证底稿列表服务层消费 Task 8 分页 envelope（组件 C13）：
//  - listWorkpapersPaged / listMyLeadWorkpapers 返回完整 {items,total,stats,page,page_size}
//  - listWorkpapersAll 一次取完全部可见底稿（spec platform-perf-hotspots R5）；legacy listWorkpapers 基于它、过滤 nullable wp
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
  listWorkpapersAll,
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

describe('listWorkpapersAll — 全部可见底稿一次取完（spec platform-perf-hotspots R5）', () => {
  it('一次请求取完，不带分页参数（原先 100 条一页逐页拉）', async () => {
    const items = Array.from({ length: 250 }, (_, i) => envItem({ wp_index_id: `wi-${i}`, wp_id: `w-${i}` }))
    mockGet.mockResolvedValue({ data: { items, total: 250 } })
    const got = await listWorkpapersAll('p1')
    expect(got.length).toBe(250)
    expect(mockGet).toHaveBeenCalledTimes(1)
    const [url, cfg] = mockGet.mock.calls[0]
    expect(url).toBe('/api/projects/p1/working-papers-all')
    expect(cfg.params).toEqual({})
  })

  it('只带有值的过滤参数', async () => {
    mockGet.mockResolvedValue({ data: { items: [], total: 0 } })
    await listWorkpapersAll('p1', { audit_cycle: 'D', file_status: '', assigned_to: undefined })
    expect(mockGet.mock.calls[0][1].params).toEqual({ audit_cycle: 'D' })
  })

  it('同项目同过滤的并发调用共享一次请求，各自拿到独立的数组与项', async () => {
    let release!: (v: unknown) => void
    mockGet.mockReturnValue(new Promise((r) => { release = r }))
    const a = listWorkpapersAll('p1', { audit_cycle: 'D' })
    const b = listWorkpapersAll('p1', { audit_cycle: 'D' })
    expect(mockGet).toHaveBeenCalledTimes(1)
    release({ data: { items: [envItem()], total: 1 } })
    const [ra, rb] = await Promise.all([a, b])
    expect(ra).toEqual(rb)
    expect(ra).not.toBe(rb)
    ra[0].wp_code = '改过'
    expect(rb[0].wp_code).toBe('D2-1')
  })

  it('过滤不同各发各的；请求结束后不留缓存（再调重新取）', async () => {
    mockGet.mockResolvedValue({ data: { items: [], total: 0 } })
    await Promise.all([listWorkpapersAll('p1', { audit_cycle: 'D' }), listWorkpapersAll('p1', { audit_cycle: 'K' })])
    expect(mockGet).toHaveBeenCalledTimes(2)
    await listWorkpapersAll('p1', { audit_cycle: 'D' })
    expect(mockGet).toHaveBeenCalledTimes(3)
  })

  it('响应没有 items 数组时给空数组', async () => {
    mockGet.mockResolvedValue({ data: null })
    expect(await listWorkpapersAll('p1')).toEqual([])
  })
})

describe('legacy listWorkpapers — 基于全量清单 + nullable 过滤', () => {
  it('maps id from wp_id and status from file_status', async () => {
    mockGet.mockResolvedValue({ data: { items: [envItem({ wp_id: 'wp-9' })], total: 1 } })
    const rows = await listWorkpapers('p1')
    expect(rows.length).toBe(1)
    expect(rows[0].id).toBe('wp-9') // id 从 wp_id 映射
    expect(rows[0].status).toBe('draft') // file_status → status
    expect(mockGet.mock.calls[0][0]).toBe('/api/projects/p1/working-papers-all')
  })

  it('filters out nullable wp (wp_generated=false) for legacy consumers', async () => {
    mockGet.mockResolvedValue({
      data: {
        items: [envItem({ wp_index_id: 'a', wp_id: 'wp-a' }), envItem({ wp_index_id: 'b', wp_id: null, wp_generated: false })],
        total: 2,
      },
    })
    const rows = await listWorkpapers('p1')
    expect(rows.length).toBe(1)
    expect(rows[0].id).toBe('wp-a')
  })

  it('maps legacy `status` query param to index_status (Req 12.6)', async () => {
    mockGet.mockResolvedValue({ data: { items: [], total: 0 } })
    await listWorkpapers('p1', { status: 'archived' })
    const [, cfg] = mockGet.mock.calls[0]
    expect(cfg.params).toEqual({ index_status: 'archived' })
  })
})
