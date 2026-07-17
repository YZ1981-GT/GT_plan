// @vitest-environment jsdom
/**
 * syncHubFromSummary — transition 携带 wp_code/year 契约（P0-2）。
 * 锁定：终态推进时把源循环码与年度传给后端 /transition，供其发布
 * CONFIRMATION_RECEIVED → 下游 stale 路由。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/http', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
}))

import api from '@/utils/http'
import { syncHubFromSummary } from '../syncHubFromSummary'
import type { ConfirmationRow } from '../../confirmationTypes'

describe('syncHubFromSummary transition payload', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('创建后终态推进的 /transition 携带 wp_code 与 year', async () => {
    ;(api.get as any).mockResolvedValue({ items: [] }) // 无既有 Hub
    const transitionBodies: any[] = []
    ;(api.post as any).mockImplementation((url: string, body: any) => {
      if (url.endsWith('/transition')) {
        transitionBodies.push(body)
        return Promise.resolve({ id: 'h1', status: body.target_status })
      }
      // create
      return Promise.resolve({ id: 'h1', status: 'pending' })
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
    // pending → sent → returned → matched，共 3 步 transition
    expect(transitionBodies.length).toBe(3)
    for (const b of transitionBodies) {
      expect(b.wp_code).toBe('D0')
      expect(b.year).toBe(2026)
      expect(['sent', 'returned', 'matched']).toContain(b.target_status)
    }
  })
})
