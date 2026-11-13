/**
 * useVoucherConclusionIndex — 凭证键 → 各可见底稿凭证检查行的结论（spec voucher-workflow-linkage-lineage-closure R6.4，design §9）
 *
 * - 同一轮渲染里各行的键合成一次请求（静默、不参与去重），超过 500 个分段；查过的键 60 秒内不再查；
 * - 403 与其他失败分开、失败不进缓存、重试再查；后端扫描截断时标「可能不全」；
 * - 晚到的旧响应不覆盖之后为同一个键发起的查询结果；`project:reset` 清空。
 * 并发判据挂起响应后再数调用次数。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

const mockPost = vi.fn()
vi.mock('@/utils/http', () => ({ default: { post: (...a: any[]) => mockPost(...a) } }))

import { eventBus } from '@/utils/eventBus'
import {
  VOUCHER_CONCLUSION_CACHE_TTL_MS,
  refreshVoucherConclusions,
  resetVoucherConclusionIndexForTest,
  useVoucherConclusionIndex,
} from '../useVoucherConclusionIndex'

const PID = 'p1'
const vk = (no: string) => JSON.stringify(['2025', 'default', '2025-01-07', '记', no])
const entry = (wp: string, verdict = 'normal') => ({
  working_paper_id: `wp-${wp}`, wp_code: wp, wp_name: `${wp} 检查`, verdict, rows: 1, legacy: false,
})

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

const flush = async () => {
  for (let i = 0; i < 6; i++) await Promise.resolve()
  await nextTick()
}

function use(key: string, projectId = PID) {
  const scope = effectScope()
  const k = ref(key)
  const index = scope.run(() => useVoucherConclusionIndex(projectId, 2025, k))!
  return { index, key: k, stop: () => scope.stop() }
}

beforeEach(() => {
  resetVoucherConclusionIndexForTest()
  mockPost.mockReset()
  vi.useRealTimers()
})

describe('合批、分段与缓存', () => {
  it('同一轮的多个键只发一次请求（挂起响应再数），结果按键分发', async () => {
    const pending = deferred<unknown>()
    mockPost.mockReturnValueOnce(pending.promise)
    const a = use(vk('0001'))
    const b = use(vk('0002'))
    use(vk('0001'))
    await flush()
    expect(mockPost).toHaveBeenCalledTimes(1)
    const [url, body, opts] = mockPost.mock.calls[0]
    expect(url).toBe(`/api/projects/${PID}/ledger/voucher-conclusions/query`)
    expect(body).toEqual({ year: 2025, keys: [vk('0001'), vk('0002')] })
    expect(opts).toMatchObject({ _silent: true, _dedupe: false })
    expect(a.index.status.value).toBe('loading')
    pending.resolve({ data: { conclusions: { [vk('0001')]: [entry('D2', 'abnormal')] }, truncated: false } })
    await flush()
    expect(a.index.entries.value.map((e) => e.wp_code)).toEqual(['D2'])
    expect(a.index.status.value).toBe('ready')
    expect(b.index.entries.value).toEqual([])
    expect(b.index.status.value).toBe('ready')
  })

  it('超过 500 个键分段；查过的 60 秒内不再查，过期后再查', async () => {
    mockPost.mockResolvedValue({ data: { conclusions: {}, truncated: false } })
    const keys = Array.from({ length: 1100 }, (_, i) => vk(String(i).padStart(4, '0')))
    await refreshVoucherConclusions(PID, 2025, keys)
    expect(mockPost.mock.calls.map((c) => (c[1] as { keys: string[] }).keys.length)).toEqual([500, 500, 100])
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(Date.now())
    use(keys[0])
    await flush()
    expect(mockPost).toHaveBeenCalledTimes(3)
    vi.setSystemTime(Date.now() + VOUCHER_CONCLUSION_CACHE_TTL_MS + 1)
    use(keys[0])
    await flush()
    expect(mockPost).toHaveBeenCalledTimes(4)
  })
})

describe('失败、截断与竞态', () => {
  it('403 记为 forbidden、其他失败记为 error，都不进缓存；重试再查', async () => {
    mockPost.mockRejectedValueOnce({ response: { status: 403 } })
    const a = use(vk('0001'))
    await flush()
    expect(a.index.status.value).toBe('forbidden')
    mockPost.mockRejectedValueOnce({ response: { status: 500 } })
    await a.index.retry()
    await flush()
    expect(a.index.status.value).toBe('error')
    mockPost.mockResolvedValueOnce({ data: { conclusions: { [vk('0001')]: [entry('E1')] }, truncated: false } })
    await a.index.retry()
    await flush()
    expect(a.index.status.value).toBe('ready')
    expect(a.index.entries.value).toHaveLength(1)
  })

  it('后端扫描截断：标「可能不全」', async () => {
    mockPost.mockResolvedValueOnce({ data: { conclusions: {}, truncated: true } })
    const a = use(vk('0001'))
    await flush()
    expect(a.index.partial.value).toBe(true)
  })

  it('晚到的旧响应不覆盖之后的查询结果', async () => {
    const first = deferred<unknown>()
    const second = deferred<unknown>()
    mockPost.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const a = use(vk('0001'))
    await flush()
    const retry = a.index.retry()
    second.resolve({ data: { conclusions: { [vk('0001')]: [entry('NEW')] } } })
    await retry
    first.resolve({ data: { conclusions: { [vk('0001')]: [entry('OLD')] } } })
    await flush()
    expect(a.index.entries.value.map((e) => e.wp_code)).toEqual(['NEW'])
  })

  it('project:reset 清空该项目的结果', async () => {
    mockPost.mockResolvedValue({ data: { conclusions: { [vk('0001')]: [entry('D2')] } } })
    const a = use(vk('0001'))
    await flush()
    expect(a.index.entries.value).toHaveLength(1)
    eventBus.emit('project:reset', { projectId: PID } as any)
    await flush()
    expect(a.index.entries.value).toEqual([])
  })
})
