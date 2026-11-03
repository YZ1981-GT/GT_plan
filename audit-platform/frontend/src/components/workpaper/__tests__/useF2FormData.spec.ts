/**
 * useF2FormData — 单元测试
 *
 * 覆盖：debouncedSave 乐观更新 / strict-CAS saveBatch / 禁止直接 TB 回写 / flushPending
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'

// Mock api
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn().mockResolvedValue({ data: [] }),
    put: vi.fn().mockResolvedValue({ data: { ok: true } }),
  },
}))

import { api } from '@/services/apiProxy'
import { useF2FormData } from '../composables/useF2FormData'

describe('useF2FormData', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('debouncedSave 立即更新 allResponses（乐观更新）', () => {
    const formData = useF2FormData({ wpId: ref('wp-1'), projectId: ref('proj-1') })

    formData.debouncedSave('F2-3-rows', { remark: '{"test":true}' })

    const resp = formData.allResponses.value.get('F2-3-rows')
    expect(resp).toBeDefined()
    expect(resp!.remark).toBe('{"test":true}')
  })

  it('debouncedSave 2秒后触发 API 保存', async () => {
    const formData = useF2FormData({ wpId: ref('wp-1'), projectId: ref('proj-1') })

    formData.debouncedSave('F2-3-rows', { remark: 'data' })

    // API 未调用（还在 debounce 期间）
    expect(api.put).not.toHaveBeenCalled()

    // 快进 2 秒
    vi.advanceTimersByTime(2000)
    await vi.runAllTimersAsync()

    expect(api.put).toHaveBeenCalledWith(
      '/api/workpapers/wp-1/checklist-responses',
      expect.objectContaining({
        project_id: 'proj-1',
        require_if_match: true,
        items: expect.arrayContaining([
          expect.objectContaining({ item_id: 'F2-3-rows', remark: 'data' }),
        ]),
      }),
      { _dedupe: false },
    )
  })

  it('debouncedSave 重复调用同 itemId 只发一次请求', async () => {
    const formData = useF2FormData({ wpId: ref('wp-1'), projectId: ref('proj-1') })

    formData.debouncedSave('F2-3-rows', { remark: 'v1' })
    vi.advanceTimersByTime(500)
    formData.debouncedSave('F2-3-rows', { remark: 'v2' })
    vi.advanceTimersByTime(500)
    formData.debouncedSave('F2-3-rows', { remark: 'v3' })

    vi.advanceTimersByTime(2000)
    await vi.runAllTimersAsync()

    // 只调用一次（最后值）
    expect(api.put).toHaveBeenCalledTimes(1)
    const call = (api.put as any).mock.calls[0]
    expect(call[1].items[0].remark).toBe('v3')
  })

  it('saveBatch 立即发送批量请求', async () => {
    const formData = useF2FormData({ wpId: ref('wp-1'), projectId: ref('proj-1') })

    await formData.saveBatch([
      { itemId: 'F2-1-adj-note', data: { remark: 'note1' } },
      { itemId: 'F2-1-adj-conclusion', data: { remark: 'conclusion1' } },
    ])

    expect(api.put).toHaveBeenCalledTimes(1)
    const items = (api.put as any).mock.calls[0][1].items
    expect(items).toHaveLength(2)
    expect(Object.fromEntries(items.map((item: any) => [item.item_id, item.remark]))).toEqual({
      'F2-1-adj-note': 'note1',
      'F2-1-adj-conclusion': 'conclusion1',
    })
  })

  it('不暴露绕过显式发布门的直接 TB 回写方法', () => {
    const formData = useF2FormData({ wpId: ref('wp-1'), projectId: ref('proj-1') })

    expect((formData as any).writebackTrialBalance).toBeUndefined()
    expect(api.put).not.toHaveBeenCalledWith(
      '/api/projects/proj-1/trial-balance/writeback',
      expect.anything(),
    )
  })

  it('saveImmediate 取消该 itemId 的 pending debounce', async () => {
    const formData = useF2FormData({ wpId: ref('wp-1'), projectId: ref('proj-1') })

    formData.debouncedSave('F2-3-rows', { remark: 'debounced' })
    await formData.saveImmediate('F2-3-rows', { remark: 'immediate' })

    // immediate 触发一次
    expect(api.put).toHaveBeenCalledTimes(1)
    expect((api.put as any).mock.calls[0][1].items[0].remark).toBe('immediate')

    // 快进 debounce 时间 — 不应再触发
    vi.advanceTimersByTime(3000)
    await vi.runAllTimersAsync()
    expect(api.put).toHaveBeenCalledTimes(1)
  })
})
