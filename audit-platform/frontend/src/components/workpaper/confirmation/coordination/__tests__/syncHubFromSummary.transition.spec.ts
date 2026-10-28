// @vitest-environment jsdom
/**
 * syncHubFromSummary — transition 携带 wp_code/year 契约（P0-2）。
 * 锁定：终态推进时把源循环码与年度传给后端 /transition，供其发布
 * CONFIRMATION_RECEIVED → 下游 stale 路由。
 *
 * 🔴 桩按真实形状返回 AxiosResponse（业务数据在 `.data`，拦截器已解掉 `{code, message, data}` 信封）。
 *    原先桩直接返回业务数据，掩盖了生产上 `res.items` / `created.id` 恒 undefined 的缺陷
 *    （spec attachment-confirmation-evidence-loop 需求 1.5）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/http', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
}))

import http from '@/utils/http'
import { syncHubFromSummary } from '../syncHubFromSummary'
import type { ConfirmationRow } from '../../confirmationTypes'

const axiosLike = (data: unknown) => Promise.resolve({ data, status: 200 })

describe('syncHubFromSummary transition payload', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('创建后终态推进的 /transition 携带 wp_code 与 year', async () => {
    ;(http.get as any).mockImplementation(() => axiosLike({ items: [] })) // 无既有 Hub
    const transitionBodies: any[] = []
    ;(http.post as any).mockImplementation((url: string, body: any) => {
      if (url.endsWith('/transition')) {
        transitionBodies.push(body)
        return axiosLike({ id: 'h1', status: body.target_status })
      }
      // create
      return axiosLike({ id: 'h1', status: 'pending' })
    })

    const rows: ConfirmationRow[] = [
      { entity_name: '甲公司', account_type: '应收账款', is_replied: true, match_status: '相符', amount: 1000, reply_amount: 1000 } as any,
    ]

    const res = await syncHubFromSummary({
      projectId: 'proj-1',
      wpId: 'wp-1',
      sourceWpCode: 'D0-1',
      wpCode: 'D0',
      year: 2026,
      rows,
    })

    expect(res.created).toBe(1)
    expect(rows[0]._hub_confirmation_id).toBe('h1') // id 写回行上（汇总表计数列靠它）
    expect(res.remapped).toBe(1) // 调用方据此持久化本表
    // pending → sent → returned → matched，共 3 步 transition
    expect(transitionBodies.length).toBe(3)
    for (const b of transitionBodies) {
      expect(b.wp_code).toBe('D0')
      expect(b.year).toBe(2026)
      expect(['sent', 'returned', 'matched']).toContain(b.target_status)
    }
  })

  it('已有台账按名称 + 类型命中时更新而不是重复新建', async () => {
    ;(http.get as any).mockImplementation(() =>
      axiosLike({ items: [{ id: 'h9', confirm_type: 'receivable', counterparty: '乙公司', status: 'sent' }] }))
    ;(http.put as any).mockImplementation(() => axiosLike({ id: 'h9' }))
    ;(http.post as any).mockImplementation(() => axiosLike({ id: 'h9', status: 'sent' }))

    const rows: ConfirmationRow[] = [
      { entity_name: '乙公司', account_type: '应收账款', send_date: '2026-01-05', amount: 50 } as any,
    ]
    const res = await syncHubFromSummary({ projectId: 'proj-1', wpId: 'wp-1', rows })

    expect([res.created, res.updated]).toEqual([0, 1])
    const creates = (http.post as any).mock.calls.filter(([url]: [string]) => url.endsWith('/confirmations'))
    expect(creates).toEqual([])
    expect(rows[0]._hub_confirmation_id).toBe('h9')
    expect(res.remapped).toBe(1)
  })

  it('行上已是同一个函证 id：只更新台账，不算改动（不触发持久化）', async () => {
    ;(http.get as any).mockImplementation(() =>
      axiosLike({ items: [{ id: 'h9', confirm_type: 'receivable', counterparty: '乙公司', status: 'sent' }] }))
    ;(http.put as any).mockImplementation(() => axiosLike({ id: 'h9' }))
    const rows: ConfirmationRow[] = [
      { entity_name: '乙公司', account_type: '应收账款', send_date: '2026-01-05', _hub_confirmation_id: 'h9' } as any,
    ]
    const res = await syncHubFromSummary({ projectId: 'proj-1', wpId: 'wp-1', rows })
    expect([res.updated, res.remapped]).toEqual([1, 0])
  })
})
