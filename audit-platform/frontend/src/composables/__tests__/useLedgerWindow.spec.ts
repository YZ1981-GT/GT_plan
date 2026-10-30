import { effectScope, nextTick } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { useLedgerWindow, type LedgerWindowFetcher } from '@/composables/useLedgerWindow'
import type { LedgerWindowQuery, LedgerWindowResponse } from '@/services/ledgerWindowApi'

const BASE: LedgerWindowQuery = {
  kind: 'ledger', projectId: 'p1', year: 2025, accountCode: '1002', limit: 2,
}

function response(page: number, total = 20): LedgerWindowResponse {
  const start = page * 2 + 1
  return {
    kind: 'ledger', dataset_id: 'd1', query_fingerprint: 'q1',
    entries: [{ id: `r${start}` }, { id: `r${start + 1}` }],
    summary: {
      total, annual_opening: '1.00', annual_opening_signed: '1.00', annual_opening_direction: 'debit',
      range_opening: '1.00', range_opening_signed: '1.00', range_opening_direction: 'debit',
      debit_total: '10.00', credit_total: '2.00', undated_count: 0, months: [], warnings: [],
    },
    page: { limit: 2, page_index: page, start, end: start + 1,
      has_more: page < 8, next_cursor: page < 8 ? `c${page + 1}` : null },
    extra_columns: page === 0 ? ['批次'] : [], subtotals: [],
  }
}

function state(fetcher: LedgerWindowFetcher) {
  const scope = effectScope()
  const value = scope.run(() => useLedgerWindow(fetcher))!
  return { value, stop: () => scope.stop() }
}

describe('useLedgerWindow', () => {
  it('首窗、下一窗、上一窗走 cursor 栈；后一窗空 extra_columns 不抹掉首窗列', async () => {
    const fetcher = vi.fn(async (query: LedgerWindowQuery) => {
      const page = query.cursor ? Number(query.cursor.slice(1)) : 0
      return response(page)
    })
    const { value, stop } = state(fetcher)
    await value.loadFirst(BASE)
    await value.next()
    expect(value.response.value?.page.page_index).toBe(1)
    expect(value.extraColumns.value).toEqual(['批次'])
    expect(value.rangeText.value).toBe('第 3–4 条，共 20 条')
    await value.previous()
    expect(value.response.value?.page.page_index).toBe(0)
    expect(fetcher).toHaveBeenCalledTimes(2) // 第 1 页由 LRU 命中
    stop()
  })

  it('新查询中止旧请求，晚到的旧响应不能覆盖新状态', async () => {
    const pending: Array<{ query: LedgerWindowQuery; signal?: AbortSignal; resolve: (r: LedgerWindowResponse) => void }> = []
    const fetcher: LedgerWindowFetcher = (query, signal) => new Promise((resolve) => pending.push({ query, signal, resolve }))
    const { value, stop } = state(fetcher)
    const old = value.loadFirst(BASE)
    await nextTick()
    const fresh = value.loadFirst({ ...BASE, accountCode: '1003' })
    await nextTick()
    expect(pending[0].signal?.aborted).toBe(true)
    pending[1].resolve({ ...response(0), query_fingerprint: 'new', entries: [{ id: 'fresh' }] })
    await fresh
    pending[0].resolve({ ...response(0), entries: [{ id: 'stale' }] })
    await old
    expect(value.response.value?.entries[0].id).toBe('fresh')
    stop()
  })

  it('缓存严格限制为五个窗口，第六窗淘汰最旧窗', async () => {
    const fetcher = vi.fn(async (query: LedgerWindowQuery) => {
      const page = query.cursor ? Number(query.cursor.slice(1)) : 0
      return response(page)
    })
    const { value, stop } = state(fetcher)
    await value.loadFirst(BASE)
    for (let i = 0; i < 5; i++) await value.next()
    expect(value.cacheSize.value).toBe(5)
    for (let i = 0; i < 5; i++) await value.previous()
    expect(value.response.value?.page.page_index).toBe(0)
    expect(fetcher).toHaveBeenCalledTimes(7) // 6 个新窗口 + 被淘汰的首页重取
    stop()
  })

  it('服务端报告数据集切换时清空窗口，不把旧行留在界面', async () => {
    const changed = Object.assign(new Error('changed'), {
      response: { data: { detail: { error_code: 'LEDGER_SNAPSHOT_CHANGED' } } },
    })
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response(0))
      .mockRejectedValueOnce(changed)
    const { value, stop } = state(fetcher)
    await value.loadFirst(BASE)
    await expect(value.next()).rejects.toBe(changed)
    expect(value.response.value).toBeNull()
    expect(value.position.value).toBe(-1)
    expect(value.cacheSize.value).toBe(0)
    stop()
  })

  it('刷新绕过当前 LRU，同一 cursor 重新请求', async () => {
    const fetcher = vi.fn(async (query: LedgerWindowQuery) => response(query.cursor ? 1 : 0))
    const { value, stop } = state(fetcher)
    await value.loadFirst(BASE)
    await value.reload()
    expect(fetcher).toHaveBeenCalledTimes(2)
    stop()
  })
})


  it('即使服务端意外返回不同数据集，也清空旧窗口而不混用', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response(0))
      .mockResolvedValueOnce({ ...response(1), dataset_id: 'd2' })
    const { value, stop } = state(fetcher)
    await value.loadFirst(BASE)
    await expect(value.next()).rejects.toMatchObject({ code: 'LEDGER_SNAPSHOT_CHANGED' })
    expect(value.response.value).toBeNull()
    expect(value.cacheSize.value).toBe(0)
    stop()
  })
