import { beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { ref } from 'vue'

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn(), put: vi.fn() },
}))
vi.mock('@/utils/eventBus', () => ({
  eventBus: { emit: vi.fn(), on: vi.fn(), off: vi.fn() },
}))

import { api } from '@/services/apiProxy'
import { useK5FormData } from '../composables/useK5FormData'
import {
  collectK5Responses,
  normalizeK5Remark,
  toK5PersistencePatch,
} from '../k5/k5Persistence'

describe('K5 persistence migration', () => {
  beforeEach(() => vi.clearAllMocks())

  it('normalizes historical double JSON from responses_snapshot without changing business data', () => {
    const rows = [{ projectName: '质保项目', estimatedLoss: 120000 }]
    const legacy = JSON.stringify({ remark: JSON.stringify(rows) })
    const responses = collectK5Responses({
      'K5-2-rows': { remark: legacy, conclusion: '' },
    })

    expect(responses).toHaveLength(1)
    expect(responses[0].conclusion).toBeNull()
    expect(responses[0]).toMatchObject({
      item_id: 'K5-2-rows',
      remark: JSON.stringify(rows),
    })
    expect(normalizeK5Remark('普通审计说明')).toBe('普通审计说明')
    expect(toK5PersistencePatch({ remark: rows }).remark).toBe(JSON.stringify(rows))
    expect(toK5PersistencePatch({ remark: rows, conclusion: '' }).conclusion).toBeNull()
  })

  it('hydrates snapshot, loads through Adapter, and sends year to TB', async () => {
    const rows = [{ projectName: '弃置义务', estimatedLoss: 80000 }]
    vi.mocked(api.get).mockImplementation(async (url: string) => {
      if (url.endsWith('/render-config')) return { data: { sheets: [{ html_data: {
        responses_snapshot: {
          'K5-2-rows': { remark: JSON.stringify({ remark: JSON.stringify(rows) }) },
        },
      } }] } }
      if (url.endsWith('/checklist-responses')) return []
      return []
    })

    const form = useK5FormData({
      wpId: ref('wp-k5'), projectId: ref('project-real'), year: ref(2025), sheetPrefix: '2',
    })
    await form.selfLoad()

    expect(form.getResponse('rows')).toEqual(rows)
    expect(api.get).toHaveBeenCalledWith('/api/workpapers/wp-k5/checklist-responses')
    expect(api.get).toHaveBeenCalledWith(
      '/api/projects/project-real/trial-balance',
      expect.objectContaining({ params: { account_prefix: '2701', year: 2025 } }),
    )
  })

  it('writes a single-layer standard payload with /api and the real project_id', async () => {
    vi.mocked(api.put).mockImplementation(async (_url, body: any) => body.items)
    const form = useK5FormData({
      wpId: ref('wp-k5'), projectId: ref('project-real'), year: ref(2025), sheetPrefix: '4',
    })
    const rows = [{ productName: '产品A', bookProvision: 100 }]

    await form.saveResponse('rows', { remark: rows })

    expect(api.put).toHaveBeenCalledWith(
      '/api/workpapers/wp-k5/checklist-responses',
      {
        project_id: 'project-real',
        items: [{
          item_id: 'K5-4-rows',
          remark: JSON.stringify(rows),
          conclusion: null,
          wp_ref: null,
        }],
      },
      expect.objectContaining({ _silent: true, signal: expect.any(AbortSignal) }),
    )
    const body = vi.mocked(api.put).mock.calls[0][1] as any
    expect(JSON.parse(body.items[0].remark)).toEqual(rows)
    expect(JSON.parse(body.items[0].remark)).not.toHaveProperty('remark')
  })

  it('keeps the K5 entry on Runtime Boundary and removes duplicate providers/I/O', () => {
    const source = readFileSync(resolve(__dirname, '../GtK5Provisions.vue'), 'utf8')
    expect(source).toContain('useChecklistPersistence')
    expect(source).toContain('WorkpaperRuntimeContextKey')
    expect(source).not.toContain('useWorkpaperVersionToolbar')
    expect(source).not.toContain("provide('openReviewDialog'")
    expect(source).not.toMatch(/http\.put\([^\n]*checklist-responses/)
    expect(source).not.toContain('<GtWpVersionTrail')
  })
})
