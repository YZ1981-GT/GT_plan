/**
 * useWpEvidenceLinks — 按底稿共享的证据链接仓（spec attachment-evidence-intake ADR-AEI-08，变异 #12）
 *
 * 并发判据一律挂起响应后再数调用次数（mock 立即返回时「只调 1 次」靠时序成立，测不到单飞）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

const mockGet = vi.fn()
const mockDelete = vi.fn()
vi.mock('@/utils/http', () => ({
  default: {
    get: (...args: any[]) => mockGet(...args),
    delete: (...args: any[]) => mockDelete(...args),
  },
}))

import {
  invalidateWpEvidenceLinks,
  loadWpEvidenceLinks,
  removeWpEvidenceLink,
  resetWpEvidenceLinksForTest,
  useWpEvidenceLinks,
} from '../useWpEvidenceLinks'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

function row(id: string, cellRef: string | null, sheetName: string | null = 'S1') {
  return {
    id, wp_id: 'w1', sheet_name: sheetName, cell_ref: cellRef, attachment_id: `a-${id}`, page_ref: null,
    evidence_type: null, check_conclusion: null, created_by: 'u1', created_at: null,
    attachment: { id: `a-${id}`, file_name: `${id}.pdf`, file_size: 1, file_type: 'pdf', attachment_type: 'evidence', ocr_status: null, created_at: null },
  }
}

const flush = async () => {
  for (let i = 0; i < 5; i++) await Promise.resolve()
  await nextTick()
}

describe('useWpEvidenceLinks', () => {
  beforeEach(() => {
    resetWpEvidenceLinksForTest()
    mockGet.mockReset()
    mockDelete.mockReset()
  })

  it('同一底稿并发加载共用一次请求，且关闭 http 的 GET 去重', async () => {
    const pending = deferred<any>()
    mockGet.mockReturnValueOnce(pending.promise)
    const a = loadWpEvidenceLinks('p1', 'w1')
    const b = loadWpEvidenceLinks('p1', 'w1')
    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(mockGet).toHaveBeenCalledWith('/api/projects/p1/workpapers/w1/evidence', expect.objectContaining({ _dedupe: false }))
    pending.resolve({ data: { items: [row('l1', 'item:1')], total: 1 } })
    expect((await a).map((r) => r.id)).toEqual(['l1'])
    expect(await b).toBe(await a)
    // 已加载：再取直接用缓存
    await loadWpEvidenceLinks('p1', 'w1')
    expect(mockGet).toHaveBeenCalledTimes(1)
  })

  it('不同底稿各自请求', async () => {
    mockGet.mockResolvedValue({ data: { items: [] } })
    await Promise.all([loadWpEvidenceLinks('p1', 'w1'), loadWpEvidenceLinks('p1', 'w2')])
    expect(mockGet.mock.calls.map((c) => c[0])).toEqual([
      '/api/projects/p1/workpapers/w1/evidence',
      '/api/projects/p1/workpapers/w2/evidence',
    ])
  })

  it('失效后旧纪元的在途结果不回写，有使用方时立即重取', async () => {
    const stale = deferred<any>()
    const fresh = deferred<any>()
    mockGet.mockReturnValueOnce(stale.promise).mockReturnValueOnce(fresh.promise)
    const scope = effectScope()
    const store = scope.run(() => useWpEvidenceLinks('p1', 'w1'))!
    await flush()
    expect(mockGet).toHaveBeenCalledTimes(1)

    void invalidateWpEvidenceLinks('p1', 'w1')
    expect(mockGet).toHaveBeenCalledTimes(2)
    fresh.resolve({ data: { items: [row('new', 'item:1')] } })
    await flush()
    stale.resolve({ data: { items: [row('old', 'item:1')] } })
    await flush()
    expect(store.links.value.map((r) => r.id)).toEqual(['new'])
    scope.stop()
  })

  it('没有使用方时失效只做标记，下次使用再取', async () => {
    mockGet.mockResolvedValue({ data: { items: [] } })
    await loadWpEvidenceLinks('p1', 'w1')
    await invalidateWpEvidenceLinks('p1', 'w1')
    expect(mockGet).toHaveBeenCalledTimes(1)
    await loadWpEvidenceLinks('p1', 'w1')
    expect(mockGet).toHaveBeenCalledTimes(2)
  })

  it('linksAt 按表页与单元格精确匹配；底稿切换后改读新底稿', async () => {
    mockGet
      .mockResolvedValueOnce({ data: { items: [row('l1', 'item:1'), row('l2', 'item:2'), row('l3', null, null)] } })
      .mockResolvedValueOnce({ data: { items: [row('m1', 'item:1')] } })
    const wpId = ref('w1')
    const scope = effectScope()
    const store = scope.run(() => useWpEvidenceLinks('p1', wpId))!
    await flush()
    expect(store.linksAt('S1', 'item:1').map((r) => r.id)).toEqual(['l1'])
    expect(store.linksAt(null, null).map((r) => r.id)).toEqual(['l3'])
    expect(store.linksAt('S1', 'item:9')).toEqual([])

    wpId.value = 'w2'
    await flush()
    expect(mockGet.mock.calls[1][0]).toBe('/api/projects/p1/workpapers/w2/evidence')
    expect(store.linksAt('S1', 'item:1').map((r) => r.id)).toEqual(['m1'])
    scope.stop()
  })

  it('移除链接走 DELETE 并重取', async () => {
    mockGet
      .mockResolvedValueOnce({ data: { items: [row('l1', 'item:1')] } })
      .mockResolvedValueOnce({ data: { items: [] } })
    mockDelete.mockResolvedValueOnce({ data: { ok: true } })
    const scope = effectScope()
    const store = scope.run(() => useWpEvidenceLinks('p1', 'w1'))!
    await flush()
    await removeWpEvidenceLink('p1', 'w1', 'l1')
    await flush()
    expect(mockDelete).toHaveBeenCalledWith('/api/projects/p1/workpapers/w1/evidence/l1', expect.anything())
    expect(store.links.value).toEqual([])
    scope.stop()
  })

  it('请求失败标记 error，不抛到使用方', async () => {
    mockGet.mockRejectedValueOnce(new Error('500'))
    const scope = effectScope()
    const store = scope.run(() => useWpEvidenceLinks('p1', 'w1'))!
    await flush()
    expect(store.error.value).toBe(true)
    expect(store.links.value).toEqual([])
    scope.stop()
  })

  it('缺项目或底稿不发请求', async () => {
    const scope = effectScope()
    const store = scope.run(() => useWpEvidenceLinks('', 'w1'))!
    await flush()
    expect(mockGet).not.toHaveBeenCalled()
    expect(store.links.value).toEqual([])
    scope.stop()
  })
})
