/**
 * resolveLinkageRoute 路由解析测试
 * 覆盖: workpaper (UUID/wp_code), report, note, trial_balance
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { resolveLinkageRoute } from '@/composables/useResolveLinkageRoute'
import type { LinkageContract } from '@/types/linkageContract'

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(),
  },
}))

import { api } from '@/services/apiProxy'
const mockGet = vi.mocked(api.get)

const PROJECT_ID = 'proj-test-001'

function makeContract(overrides: Partial<LinkageContract>): LinkageContract {
  return {
    source_type: 'trial_balance',
    source_id: 'src-1',
    target_type: 'workpaper',
    target_id: 'tgt-1',
    status: 'current',
    confidence: 'system',
    ...overrides,
  }
}

describe('resolveLinkageRoute', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns pre-computed route if present', async () => {
    const contract = makeContract({ route: '/existing/route' })
    const result = await resolveLinkageRoute(contract, PROJECT_ID)
    expect(result).toBe('/existing/route')
    expect(mockGet).not.toHaveBeenCalled()
  })

  it('resolves workpaper UUID directly', async () => {
    const uuid = '12345678-1234-1234-1234-123456789abc'
    const contract = makeContract({ target_type: 'workpaper', target_id: uuid })
    const result = await resolveLinkageRoute(contract, PROJECT_ID)
    expect(result).toBe(`/projects/${PROJECT_ID}/workpapers/${uuid}`)
  })

  it('resolves workpaper wp_code via API', async () => {
    mockGet.mockResolvedValueOnce({ working_paper_id: 'resolved-wp-id' })
    const contract = makeContract({ target_type: 'workpaper', target_id: 'D1' })
    const result = await resolveLinkageRoute(contract, PROJECT_ID)
    expect(mockGet).toHaveBeenCalledWith(`/api/projects/${PROJECT_ID}/wp-index/by-code/D1`)
    expect(result).toBe(`/projects/${PROJECT_ID}/workpapers/resolved-wp-id`)
  })

  it('returns null when wp_code API fails', async () => {
    mockGet.mockRejectedValueOnce(new Error('404'))
    const contract = makeContract({ target_type: 'workpaper', target_id: 'UNKNOWN' })
    const result = await resolveLinkageRoute(contract, PROJECT_ID)
    expect(result).toBeNull()
  })

  it('resolves report target', async () => {
    const contract = makeContract({ target_type: 'report', target_id: 'row-code-01' })
    const result = await resolveLinkageRoute(contract, PROJECT_ID)
    expect(result).toBe(`/projects/${PROJECT_ID}/reports?highlight=row-code-01`)
  })

  it('resolves note target', async () => {
    const contract = makeContract({ target_type: 'note', target_id: 'section-3' })
    const result = await resolveLinkageRoute(contract, PROJECT_ID)
    expect(result).toBe(`/projects/${PROJECT_ID}/disclosure-notes?section=section-3`)
  })

  it('resolves trial_balance target', async () => {
    const contract = makeContract({ target_type: 'trial_balance', target_id: 'tb-row-5' })
    const result = await resolveLinkageRoute(contract, PROJECT_ID)
    expect(result).toBe(`/projects/${PROJECT_ID}/trial-balance?highlight=tb-row-5`)
  })

  it('returns null for unsupported target_type', async () => {
    const contract = makeContract({ target_type: 'attachment', target_id: 'att-1' })
    const result = await resolveLinkageRoute(contract, PROJECT_ID)
    expect(result).toBeNull()
  })
})
