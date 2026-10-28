/**
 * 能力快照请求静默（spec procedure-chain-hardening-and-java-contracts R10）：底稿打不开时由编辑器给一句中性提示，
 * 快照请求不再经全局拦截器另弹一条「资源不存在」；是否提示由调用方（useShellCapability）按状态码决定。
 */
import { describe, expect, it, vi } from 'vitest'

const get = vi.hoisted(() => vi.fn())
vi.mock('@/services/apiProxy', () => ({ api: { get } }))

import { fetchWorkpaperCapabilitySnapshot } from '../fetchCapabilitySnapshot'

describe('fetchWorkpaperCapabilitySnapshot', () => {
  it('静默请求', async () => {
    get.mockResolvedValue({ snapshotVersion: '1.0', ownerEpoch: 3 })
    const snap = await fetchWorkpaperCapabilitySnapshot({ wpId: 'w1', projectId: 'p1', ownerEpoch: 3 })
    expect(get).toHaveBeenCalledWith('/api/workpapers/w1/capability-snapshot?project_id=p1&ownerEpoch=3', { _silent: true })
    expect(snap?.ownerEpoch).toBe(3)
  })
})
