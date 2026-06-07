/**
 * resolveLinkageRoute 路由解析测试（P0 增强版）
 * 覆盖: workpaper (UUID/wp_code), report, note (section+cell), trial_balance, adjustment, ledger
 *
 * P0-3.5: wp_code 可直接解析到 WorkpaperEditor
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { resolveLinkageRoute } from '@/composables/useResolveLinkageRoute'
import type { LinkageContract } from '@/types/linkageContract'
import {
  SOURCE_TYPE_VALUES,
  LINKAGE_STATUS_VALUES,
  LINKAGE_CONFIDENCE_VALUES,
  CONFIDENCE_LEVEL_MAP,
} from '@/types/linkageContract'

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

  it('resolves note target without cell', async () => {
    const contract = makeContract({ target_type: 'note', target_id: 'section-3' })
    const result = await resolveLinkageRoute(contract, PROJECT_ID)
    expect(result).toBe(`/projects/${PROJECT_ID}/disclosure-notes?section=section-3`)
  })

  it('resolves note target with cell locator', async () => {
    const contract = makeContract({
      target_type: 'note',
      target_id: 'section-3',
      target_cell: 'table-1.row-2.col-1',
    })
    const result = await resolveLinkageRoute(contract, PROJECT_ID)
    expect(result).toBe(
      `/projects/${PROJECT_ID}/disclosure-notes?section=section-3&cell=table-1.row-2.col-1`,
    )
  })

  it('resolves trial_balance target', async () => {
    const contract = makeContract({ target_type: 'trial_balance', target_id: 'tb-row-5' })
    const result = await resolveLinkageRoute(contract, PROJECT_ID)
    expect(result).toBe(`/projects/${PROJECT_ID}/trial-balance?highlight=tb-row-5`)
  })

  it('resolves adjustment target', async () => {
    const contract = makeContract({ target_type: 'adjustment', target_id: 'adj-001' })
    const result = await resolveLinkageRoute(contract, PROJECT_ID)
    expect(result).toBe(`/projects/${PROJECT_ID}/adjustments?highlight=adj-001`)
  })

  it('resolves ledger target', async () => {
    const contract = makeContract({ target_type: 'ledger', target_id: '1001' })
    const result = await resolveLinkageRoute(contract, PROJECT_ID)
    expect(result).toBe(`/projects/${PROJECT_ID}/ledger?account=1001`)
  })

  it('returns null for unsupported target_type (attachment)', async () => {
    const contract = makeContract({ target_type: 'attachment', target_id: 'att-1' })
    const result = await resolveLinkageRoute(contract, PROJECT_ID)
    expect(result).toBeNull()
  })

  it('returns null for unsupported target_type (ai)', async () => {
    const contract = makeContract({ target_type: 'ai', target_id: 'ai-1' })
    const result = await resolveLinkageRoute(contract, PROJECT_ID)
    expect(result).toBeNull()
  })
})

describe('LinkageContract 枚举一致性', () => {
  it('SOURCE_TYPE_VALUES 包含 9 个值', () => {
    expect(SOURCE_TYPE_VALUES).toHaveLength(9)
  })

  it('LINKAGE_STATUS_VALUES 包含 4 个值', () => {
    expect(LINKAGE_STATUS_VALUES).toHaveLength(4)
    expect(LINKAGE_STATUS_VALUES).toContain('current')
    expect(LINKAGE_STATUS_VALUES).toContain('stale')
    expect(LINKAGE_STATUS_VALUES).toContain('conflict')
    expect(LINKAGE_STATUS_VALUES).toContain('manual_override')
  })

  it('LINKAGE_CONFIDENCE_VALUES 包含 4 个值', () => {
    expect(LINKAGE_CONFIDENCE_VALUES).toHaveLength(4)
    expect(LINKAGE_CONFIDENCE_VALUES).toContain('system')
    expect(LINKAGE_CONFIDENCE_VALUES).toContain('manual')
    expect(LINKAGE_CONFIDENCE_VALUES).toContain('ai_suggested')
    expect(LINKAGE_CONFIDENCE_VALUES).toContain('ai_confirmed')
  })

  it('CONFIDENCE_LEVEL_MAP 覆盖所有置信度', () => {
    for (const conf of LINKAGE_CONFIDENCE_VALUES) {
      expect(CONFIDENCE_LEVEL_MAP[conf]).toBeDefined()
      expect(['high', 'medium', 'low']).toContain(CONFIDENCE_LEVEL_MAP[conf])
    }
  })

  it('source_type 和 target_type 值域一致（前后端同构）', () => {
    // 前端定义的 SourceType 值必须与后端 Python 枚举一致
    const expectedValues = [
      'trial_balance', 'ledger', 'audit_sheet', 'workpaper',
      'adjustment', 'report', 'note', 'attachment', 'ai',
    ]
    expect(SOURCE_TYPE_VALUES.sort()).toEqual(expectedValues.sort())
  })
})
