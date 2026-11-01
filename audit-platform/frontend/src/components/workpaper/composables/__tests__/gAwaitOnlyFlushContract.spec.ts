/**
 * G 循环 await-only formData 的 flush 契约（运行时行为，不是源码形态）。
 *
 * 源码形态守卫（pendingWritesCoverageRatchet）只能证明「写法对了」，证明不了
 * 「flush 真的会等 PUT 落库、失败真的会传到调用方」。这里用挂起 / 拒绝的 PUT 做真实验证：
 *
 *   * PUT 未 resolve 时 flushPending() 不得完成 —— 否则 flushHtml 会在数据落库前读 projection；
 *   * PUT 拒绝时 flushPending() 必须 reject —— 否则过渡屏障放行、随后的 OO 保存覆盖这次编辑；
 *   * 两种失败传递形态各测一个代表：G9 = 耗尽重试后落本地草稿再抛；G1 = 无 try，rejection 自然冒泡。
 *
 * Spec: workpaper-writeback-data-loss-and-mirror-consistency-closure R1.4
 */
import { effectScope, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const put = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(async () => []),
    put: (...args: unknown[]) => put(...args),
    post: vi.fn(async () => ({})),
  },
}))
vi.mock('@/services/trialBalanceRows', () => ({ fetchTrialBalanceRows: vi.fn(async () => ({ rows: [] })) }))
vi.mock('../workpaperAuditYear', () => ({ useWorkpaperAuditYear: () => ref(2025) }))
vi.mock('@/utils/eventBus', () => ({ eventBus: { emit: vi.fn(), on: vi.fn(), off: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn(), info: vi.fn() },
}))

const { useG9FormData } = await import('../useG9FormData')
const { useG1TraFinFormData } = await import('../useG1TraFinFormData')
const { flushPendingWrites, PendingWritesFlushError } = await import('../../sync/pendingWrites')

function deferred<T = void>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail })
  return { promise, resolve, reject }
}

/** 让 flush 的 promise 有机会推进，同时不吞掉它的最终状态。 */
function settled(promise: Promise<unknown>): { done: boolean; error: unknown } {
  const probe = { done: false, error: undefined as unknown }
  promise.then(
    () => { probe.done = true },
    (err) => { probe.done = true; probe.error = err },
  )
  return probe
}

const scopes: Array<ReturnType<typeof effectScope>> = []

function inScope<T>(factory: () => T): T {
  const scope = effectScope()
  scopes.push(scope)
  return scope.run(factory) as T
}

beforeEach(() => {
  put.mockReset()
  localStorage.clear()
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  while (scopes.length) scopes.pop()?.stop()
})

describe('G9（耗尽重试 → 本地草稿 → 抛错）', () => {
  it('PUT 未 resolve 时 flushPending 不完成', async () => {
    const pending = deferred()
    put.mockReturnValue(pending.promise)
    const formData = inScope(() => useG9FormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))

    formData.debouncedSave('G9-1-remark', { remark: '现场补录' })
    const flush = formData.flushPending()
    const probe = settled(flush)

    await Promise.resolve()
    await Promise.resolve()
    expect(put).toHaveBeenCalledOnce()
    expect(probe.done).toBe(false)

    pending.resolve()
    await flush
    expect(probe.done).toBe(true)
    expect(probe.error).toBeUndefined()
  })

  it('PUT 拒绝时 flushPending reject，且编辑落到本地草稿不丢', async () => {
    put.mockRejectedValue(new Error('503'))
    const formData = inScope(() => useG9FormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))

    formData.debouncedSave('G9-1-remark', { remark: '网络断了' })
    await expect(formData.flushPending()).rejects.toThrow(/保存未落库/)

    // flushPending 传 retries=1，耗尽后写草稿：数据既没静默消失，也没被当成已保存
    expect(localStorage.getItem('g9-draft:wp-1:G9-1-remark')).toContain('网络断了')
  })

  it('flushPending 清掉 debounce 计时器，不会在之后重复 PUT', async () => {
    put.mockResolvedValue({})
    const formData = inScope(() => useG9FormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))

    formData.debouncedSave('G9-1-remark', { remark: 'x' })
    await formData.flushPending()
    expect(put).toHaveBeenCalledOnce()

    await vi.advanceTimersByTimeAsync(5000)
    expect(put).toHaveBeenCalledOnce()
  })
})

describe('G1（无 try，PUT rejection 自然冒泡）', () => {
  it('PUT 未 resolve 时 flushPending 不完成', async () => {
    const pending = deferred()
    put.mockReturnValue(pending.promise)
    const formData = inScope(() => useG1TraFinFormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))

    formData.debouncedSave('G1-1-remark', { remark: '待落库' })
    const flush = formData.flushPending()
    const probe = settled(flush)

    await Promise.resolve()
    await Promise.resolve()
    expect(put).toHaveBeenCalledOnce()
    expect(probe.done).toBe(false)

    pending.resolve()
    await flush
    expect(probe.error).toBeUndefined()
  })

  it('PUT 拒绝时 flushPending 以原始错误 reject', async () => {
    put.mockRejectedValue(new Error('500 internal'))
    const formData = inScope(() => useG1TraFinFormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))

    formData.debouncedSave('G1-1-remark', { remark: '会失败' })
    await expect(formData.flushPending()).rejects.toThrow('500 internal')
  })

  it('多个待存 item 全部等齐才算 flush 完成', async () => {
    const first = deferred()
    const second = deferred()
    put.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const formData = inScope(() => useG1TraFinFormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))

    formData.debouncedSave('G1-1-remark', { remark: 'a' })
    formData.debouncedSave('G1-2-remark', { remark: 'b' })
    const flush = formData.flushPending()
    const probe = settled(flush)

    await Promise.resolve()
    await Promise.resolve()
    expect(put).toHaveBeenCalledTimes(2)

    first.resolve()
    await Promise.resolve()
    await Promise.resolve()
    expect(probe.done).toBe(false)

    second.resolve()
    await flush
    expect(probe.done).toBe(true)
  })
})

// ─── 在途 PUT 必须被过渡屏障等到 ─────────────────────────────────────────────
//
// 这是第三轮语义审查抓到的 P1。防抖回调原来是「先删 timer 记账、再 fire-and-forget」：
// 计时器一触发，那发 PUT 就从屏障视野消失 —— flushPending 遍历空表立刻 resolve，
// _inFlight 里也没有它，屏障放行，readStoreProjection 与在途 PUT 竞态（design §2.3「在途型」）。
//
// 只看 flushPending 证明不了这条：它那时已经无事可做。必须从屏障入口 flushPendingWrites() 验。
describe('在途 PUT 与过渡屏障', () => {
  it('计时器已触发、PUT 在途时，屏障不得放行', async () => {
    const pending = deferred()
    put.mockReturnValue(pending.promise)
    const formData = inScope(() => useG9FormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))

    formData.debouncedSave('G9-1-remark', { remark: '防抖中' })
    // 推进到防抖触发：此刻 _debounceTimers 已被回调清空，PUT 已发出且未返回
    await vi.advanceTimersByTimeAsync(2100)
    expect(put).toHaveBeenCalledOnce()

    const barrier = flushPendingWrites()
    const probe = settled(barrier)
    await Promise.resolve()
    await Promise.resolve()
    // flushPending 此时无事可做；若在途 PUT 没被 track，屏障会在这里就放行
    expect(probe.done).toBe(false)

    pending.resolve()
    await barrier
    expect(probe.done).toBe(true)
    expect(probe.error).toBeUndefined()
  })

  it('在途 PUT 失败时屏障抛 PendingWritesFlushError（调用方必须保持 HTML）', async () => {
    put.mockRejectedValue(new Error('502 bad gateway'))
    const formData = inScope(() => useG9FormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))

    formData.debouncedSave('G9-1-remark', { remark: '会失败' })
    // 防抖路径用默认 retries=3，重试之间有 500 / 1000ms 退避；假时钟下必须显式推进，
    // 否则重试链永远停在 setTimeout 上（这正是这两条用例第一版超时的原因）。
    await vi.advanceTimersByTimeAsync(2100)
    expect(put).toHaveBeenCalled()

    const barrier = flushPendingWrites()
    const probe = settled(barrier)
    await vi.advanceTimersByTimeAsync(2000)
    expect(probe.done).toBe(true)
    expect(probe.error).toBeInstanceOf(PendingWritesFlushError)
    // 草稿兜底仍在：数据没有静默消失
    expect(localStorage.getItem('g9-draft:wp-1:G9-1-remark')).toContain('会失败')
  })

  it('在途失败会被屏障看见并排空：恢复后下一次屏障可以通过', async () => {
    // G1 的 saveImmediate 没有重试，rejection 是立即的；必须让它在屏障运行期间才结算，
    // 否则 trackPendingWrite 的 settled 已从 _inFlight 移除，这条就测不到「屏障看见失败」。
    const pending = deferred()
    put.mockReturnValue(pending.promise)
    const formData = inScope(() => useG1TraFinFormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))

    formData.debouncedSave('G1-1-remark', { remark: '先失败' })
    await vi.advanceTimersByTimeAsync(2100)

    const first = settled(flushPendingWrites())
    await Promise.resolve()
    await Promise.resolve()
    expect(first.done).toBe(false)

    pending.reject(new Error('offline'))
    await vi.advanceTimersByTimeAsync(0)
    expect(first.error).toBeInstanceOf(PendingWritesFlushError)

    // 失败的 in-flight 不得滞留在屏障里，否则「恢复后可重试」永远过不去
    put.mockResolvedValue({})
    const second = settled(flushPendingWrites())
    await vi.advanceTimersByTimeAsync(0)
    expect(second.done).toBe(true)
    expect(second.error).toBeUndefined()
  })

  it('这四家（无重试无草稿）的防抖失败必须让用户看见，不能静默', async () => {
    const { ElMessage } = await import('element-plus')
    put.mockRejectedValue(new Error('offline'))
    const formData = inScope(() => useG1TraFinFormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))

    formData.debouncedSave('G1-1-remark', { remark: '会失败' })
    await vi.advanceTimersByTimeAsync(2100)
    await vi.advanceTimersByTimeAsync(0)

    expect(ElMessage.error).toHaveBeenCalledWith('保存失败，请检查网络后重试')
  })
})
