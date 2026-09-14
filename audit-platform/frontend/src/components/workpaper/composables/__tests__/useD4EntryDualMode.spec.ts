/**
 * useD4EntryDualMode — 单元测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useD4EntryDualMode } from '../useD4EntryDualMode'

describe('useD4EntryDualMode', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: { healthy: true } }),
    }))
  })

  it('resolveOoSheetName 解析 D4-1', () => {
    const { resolveOoSheetName } = useD4EntryDualMode({
      wpId: ref('wp1'),
      currentSheet: ref('D4-1'),
      availableSheets: ref([]),
      reloadAllResponses: async () => {},
    })
    expect(resolveOoSheetName()).toBe('营业收入审定表D4-1')
  })
})
