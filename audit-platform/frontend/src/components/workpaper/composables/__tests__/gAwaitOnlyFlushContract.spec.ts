/**
 * G 循环 await-only formData 的 flush 契约（运行时行为，不是源码形态）。
 *
 * 源码形态守卫（pendingWritesCoverageRatchet）只能证明「写法对了」，证明不了
 * 「flush 真的会等 PUT 落库、失败真的会传到调用方」。这里用挂起 / 拒绝的 PUT 做真实验证：
 *
 *   * PUT 未 resolve 时 flushPending() 不得完成 —— 否则 flushHtml 会在数据落库前读 projection；
 *   * PUT 拒绝时 flushPending() 必须 reject —— 否则过渡屏障放行、随后的 OO 保存覆盖这次编辑；
 *   * 两种失败传递形态各测一个代表：G9 = 耗尽重试后落本地草稿再抛；G1 = 立即落草稿并向上传递。
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
  ElMessageBox: { confirm: vi.fn() },
}))

const { useG9FormData } = await import('../useG9FormData')
const { useG8FormData } = await import('../useG8FormData')
const { useG10FormData } = await import('../useG10FormData')
const { useG11FormData } = await import('../useG11FormData')
const { useG12FormData } = await import('../useG12FormData')
const { useG13FormData } = await import('../useG13FormData')
const { useG14FormData } = await import('../useG14FormData')
const { useG1TraFinFormData } = await import('../useG1TraFinFormData')
const { useG3FormData } = await import('../useG3FormData')
const { useG5LonRecFormData } = await import('../useG5LonRecFormData')
const { useG6SppiFormData } = await import('../useG6SppiFormData')
const { useG4EclFormData } = await import('../useG4EclFormData')
const { useG6MainFormData } = await import('../useG6MainFormData')
const { useG4SppiFormData } = await import('@/composables/useG4SppiFormData')
const { api } = await import('@/services/apiProxy')
const { ElMessageBox } = await import('element-plus')
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
let consoleErrorSpy: { mockRestore(): void } | undefined

function inScope<T>(factory: () => T): T {
  const scope = effectScope()
  scopes.push(scope)
  return scope.run(factory) as T
}

beforeEach(() => {
  sessionStorage.setItem('user', JSON.stringify({ id: 'user-1' }))
  consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined)
  put.mockReset()
  vi.mocked(api.get).mockReset()
  vi.mocked(ElMessageBox.confirm).mockReset()
  vi.mocked(ElMessageBox.confirm).mockResolvedValue('confirm' as any)
  vi.mocked(api.get).mockResolvedValue([])
  localStorage.clear()
  vi.useFakeTimers()
})

afterEach(async () => {
  while (scopes.length) scopes.pop()?.stop()
  // onScopeDispose 会发起最后一次 queue.flush；先排空 fake timer/微任务，再清全局 pending
  // 注册表，避免上一例的已拒绝/已完成请求污染下一例的屏障时序。
  await vi.runAllTimersAsync()
  await Promise.resolve()
  await flushPendingWrites().catch(() => undefined)
  vi.useRealTimers()
  localStorage.clear()
  sessionStorage.clear()
  consoleErrorSpy?.mockRestore()
  consoleErrorSpy = undefined
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
    const flush = formData.flushPending()
    const rejected = expect(flush).rejects.toThrow('503')
    await vi.advanceTimersByTimeAsync(1500)
    await rejected
    expect(put).toHaveBeenCalledTimes(3)

    // 失败保留草稿：数据既没静默消失，也不会被当成已保存。
    expect(localStorage.getItem('g9-draft:user-1:wp-1:G9-1-remark')).toContain('网络断了')
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

  it('409 版本冲突保留草稿，后续屏障只阻断不重发陈旧版本', async () => {
    const conflict = Object.assign(new Error('版本冲突'), { response: { status: 409 } })
    put.mockRejectedValue(conflict)
    const formData = inScope(() => useG9FormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))

    formData.debouncedSave('G9-1-remark', { remark: '冲突后的本地编辑' })
    await expect(formData.flushPending()).rejects.toBe(conflict)
    expect(localStorage.getItem('g9-draft:user-1:wp-1:G9-1-remark')).toContain('冲突后的本地编辑')
    expect(put).toHaveBeenCalledOnce()

    await expect(flushPendingWrites()).rejects.toBeInstanceOf(PendingWritesFlushError)
    expect(put).toHaveBeenCalledOnce()
  })

  it('在途请求被冲突拒绝后保留更晚输入的草稿与原 CAS 基线', async () => {
    vi.mocked(api.get).mockImplementation(async (url: string) => (
      url.includes('checklist-responses')
        ? [{ item_id: 'G9-1-remark', conclusion: null, remark: '远端 A', updated_at: 'version-A' }]
        : {}
    ))
    const request = deferred()
    const conflict = Object.assign(new Error('版本冲突'), { response: { status: 409 } })
    put.mockReturnValueOnce(request.promise)
    const formData = inScope(() => useG9FormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))
    await formData.loadAll()

    const saving = formData.saveImmediate('G9-1-remark', { remark: '本地 A' })
    await Promise.resolve()
    await Promise.resolve()
    formData.debouncedSave('G9-1-remark', { remark: '本地 B' })
    const rejected = expect(saving).rejects.toBe(conflict)
    request.reject(conflict)
    await rejected

    expect(JSON.parse(localStorage.getItem('g9-draft:user-1:wp-1:G9-1-remark') || '{}')).toMatchObject({
      item: { item_id: 'G9-1-remark', remark: '本地 B' },
      baseVersion: 'version-A',
    })
  })

  it('恢复草稿只在带版本的服务端成功回执后删除', async () => {
    localStorage.setItem(
      'g9-draft:user-1:wp-1:G9-1-remark',
      JSON.stringify({
        item: { item_id: 'G9-1-remark', conclusion: null, remark: '待恢复内容' },
        baseVersion: 'server-v1',
      }),
    )
    vi.mocked(api.get).mockImplementation(async (url: string) => (
      url.includes('checklist-responses')
        ? [{ item_id: 'G9-1-remark', conclusion: null, remark: '服务端旧值', updated_at: 'server-v1' }]
        : {}
    ))
    put.mockResolvedValue([{ item_id: 'G9-1-remark', updated_at: 'server-v2' }])
    const formData = inScope(() => useG9FormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))

    await formData.loadAll()

    expect(put).toHaveBeenCalledOnce()
    const body = put.mock.calls[0][1] as any
    expect(body.items).toEqual(expect.arrayContaining([
      expect.objectContaining({ item_id: 'G9-1-remark', if_match: 'server-v1', remark: '待恢复内容' }),
    ]))
    expect(localStorage.getItem('g9-draft:user-1:wp-1:G9-1-remark')).toBeNull()
  })

  it('选择丢弃本地冲突草稿时保留服务器正文且不发送覆盖请求', async () => {
    localStorage.setItem(
      'g9-draft:user-1:wp-1:G9-1-remark',
      JSON.stringify({
        item: { item_id: 'G9-1-remark', conclusion: null, remark: '本地旧值' },
        baseVersion: 'version-A',
      }),
    )
    vi.mocked(api.get).mockImplementation(async (url: string) => (
      url.includes('checklist-responses')
        ? [{ item_id: 'G9-1-remark', conclusion: null, remark: '远端 C', updated_at: 'version-C' }]
        : {}
    ))
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    const formData = inScope(() => useG9FormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))

    await formData.loadAll()

    expect(put).not.toHaveBeenCalled()
    expect(localStorage.getItem('g9-draft:user-1:wp-1:G9-1-remark')).toBeNull()
    expect(formData.allResponses.value.get('G9-1-remark')).toMatchObject({ remark: '远端 C' })
  })

  it('恢复到更高服务器版本时先让用户决定；保留后仅由下一次明确编辑按新版本保存', async () => {
    localStorage.setItem(
      'g9-draft:user-1:wp-1:G9-1-remark',
      JSON.stringify({
        item: { item_id: 'G9-1-remark', conclusion: null, remark: '本地 B' },
        baseVersion: 'version-A',
      }),
    )
    vi.mocked(api.get).mockImplementation(async (url: string) => (
      url.includes('checklist-responses')
        ? [{ item_id: 'G9-1-remark', conclusion: null, remark: '远端 C', updated_at: 'version-C' }]
        : {}
    ))
    const formData = inScope(() => useG9FormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))

    await formData.loadAll()

    expect(ElMessageBox.confirm).toHaveBeenCalledOnce()
    expect(put).not.toHaveBeenCalled()
    expect(formData.allResponses.value.get('G9-1-remark')).toMatchObject({ remark: '本地 B' })
    expect(localStorage.getItem('g9-draft:user-1:wp-1:G9-1-remark')).toContain('version-A')

    put.mockResolvedValue([{ item_id: 'G9-1-remark', updated_at: 'version-D' }])
    await formData.saveImmediate('G9-1-remark', { conclusion: 'Y' })
    const body = put.mock.calls[0][1] as any
    expect(body.items).toEqual(expect.arrayContaining([
      expect.objectContaining({
        item_id: 'G9-1-remark', conclusion: 'Y', remark: '本地 B', if_match: 'version-C',
      }),
    ]))
  })
})

describe('G1（失败留草稿并向上传递）', () => {
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

  it('checklist GET 失败时，render 快照的 version 仍作为 strict CAS 基线', async () => {
    vi.mocked(api.get).mockImplementation(async (url: string) => {
      if (url.includes('checklist-responses')) throw new Error('GET failed')
      return {
        responses_snapshot: {
          'G1-1-remark': { conclusion: null, remark: '快照值', version: 'snapshot-v1' },
        },
      }
    })
    put.mockResolvedValue([])
    const formData = inScope(() => useG1TraFinFormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))

    await formData.loadAll()
    await formData.saveImmediate('G1-1-remark', { remark: '改后值' })

    const body = put.mock.calls[0][1] as any
    expect(body.require_if_match).toBe(true)
    expect(body.items).toEqual(expect.arrayContaining([
      expect.objectContaining({ item_id: 'G1-1-remark', if_match: 'snapshot-v1' }),
    ]))
  })

  it('即时保存取消同条目的旧防抖，不能由旧快照覆盖新编辑', async () => {
    put.mockResolvedValue([])
    const formData = inScope(() => useG1TraFinFormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))

    formData.debouncedSave('G1-1-remark', { remark: '旧文本' })
    await formData.saveImmediate('G1-1-remark', { conclusion: 'Y' })
    await vi.advanceTimersByTimeAsync(5000)

    expect(put).toHaveBeenCalledOnce()
    const body = put.mock.calls[0][1] as any
    expect(body.items).toEqual(expect.arrayContaining([
      expect.objectContaining({ item_id: 'G1-1-remark', conclusion: 'Y', remark: '旧文本' }),
    ]))
  })

  it('GET 与 render snapshot 同时有值时只采用 GET 的内容和版本，不交叉拼接', async () => {
    vi.mocked(api.get).mockImplementation(async (url: string) => (
      url.includes('checklist-responses')
        ? [{ item_id: 'G1-1-remark', conclusion: 'GET', remark: 'GET值', updated_at: 'get-v1' }]
        : { responses_snapshot: { 'G1-1-remark': { conclusion: 'SNAPSHOT', remark: '快照值', version: 'snapshot-v2' } } }
    ))
    put.mockResolvedValue([])
    const formData = inScope(() => useG1TraFinFormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))

    await formData.loadAll()
    await formData.saveImmediate('G1-1-remark', { remark: '本地改动' })

    const body = put.mock.calls[0][1] as any
    expect(body.items).toEqual(expect.arrayContaining([
      expect.objectContaining({
        item_id: 'G1-1-remark', conclusion: 'GET', remark: '本地改动', if_match: 'get-v1',
      }),
    ]))
  })

  it('多个待存 item 合成一个原子批次，全部落库前 flush 不完成', async () => {
    const batch = deferred()
    put.mockReturnValueOnce(batch.promise)
    const formData = inScope(() => useG1TraFinFormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))

    formData.debouncedSave('G1-1-remark', { remark: 'a' })
    formData.debouncedSave('G1-2-remark', { remark: 'b' })
    const flush = formData.flushPending()
    const probe = settled(flush)

    await Promise.resolve()
    await Promise.resolve()
    // generation-safe queue 将同批未落库项合并成一次 CAS 请求，后端要么全写要么全拒绝。
    expect(put).toHaveBeenCalledOnce()
    const body = put.mock.calls[0][1] as any
    expect(body.items.map((item: any) => item.item_id).sort()).toEqual(['G1-1-remark', 'G1-2-remark'])
    expect(probe.done).toBe(false)

    batch.resolve()
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
    expect(localStorage.getItem('g9-draft:user-1:wp-1:G9-1-remark')).toContain('会失败')
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

  it('无自动重试的 G1 防抖失败必须让用户看见，不能静默', async () => {
    const { ElMessage } = await import('element-plus')
    put.mockRejectedValue(new Error('offline'))
    const formData = inScope(() => useG1TraFinFormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))

    formData.debouncedSave('G1-1-remark', { remark: '会失败' })
    await vi.advanceTimersByTimeAsync(2100)
    await vi.advanceTimersByTimeAsync(0)

    expect(ElMessage.error).toHaveBeenCalledWith('保存失败，请检查网络后重试')
  })
})


describe('G6 SPPI 多键防抖调度', () => {
  it('批次任一成员即时保存时同步刷出兄弟项，不能取消共享 timer 后让兄弟项滞留', async () => {
    put.mockResolvedValue({ data: [] })
    const formData = inScope(() => useG6SppiFormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))

    formData.debouncedSaveBatch([
      { itemId: 'G6-6-interest-data', data: { remark: '利息明细' } },
      { itemId: 'G6-6-rows', data: { remark: '利息行' } },
    ])
    await formData.saveImmediate('G6-6-interest-data', { conclusion: '已核对' })

    expect(put).toHaveBeenCalledOnce()
    const body = put.mock.calls[0][1] as any
    expect(body.items).toEqual(expect.arrayContaining([
      expect.objectContaining({
        item_id: 'G6-6-interest-data', conclusion: '已核对', remark: '利息明细',
      }),
      expect.objectContaining({ item_id: 'G6-6-rows', remark: '利息行' }),
    ]))

    await vi.advanceTimersByTimeAsync(5000)
    expect(put).toHaveBeenCalledOnce()
  })
})


describe('原本无草稿的 G4/G6 表单', () => {
  it.each([
    ['G4 ECL', () => useG4EclFormData({ wpId: ref('wp-1'), projectId: ref('p-1') }), 'G4-9-conclusion'],
    ['G4 SPPI', () => useG4SppiFormData({ wpId: ref('wp-1'), projectId: ref('p-1') }), 'G4-sppi-conclusion'],
    ['G6 main', () => useG6MainFormData({ wpId: ref('wp-1'), projectId: ref('p-1') }), 'G6-main-conclusion'],
    ['G6 SPPI', () => useG6SppiFormData({ wpId: ref('wp-1'), projectId: ref('p-1') }), 'G6-sppi-conclusion'],
  ])('%s 保存失败后可恢复草稿不丢', async (_name, create, itemId) => {
    const conflict = Object.assign(new Error('版本冲突'), { response: { status: 409 } })
    put.mockRejectedValue(conflict)
    const formData = inScope(create)

    await expect(formData.saveImmediate(itemId, { remark: '未落库内容' })).rejects.toBe(conflict)

    expect(localStorage.getItem(`strict-cas-draft:user-1:wp-1:${itemId}`)).toContain('未落库内容')
  })
})


type DraftableGFormData = {
  debouncedSave: (itemId: string, data: { remark?: string | null }) => void
}

describe('14 个 G strict-CAS 表单的输入即草稿', () => {
  it.each([
    ['G1', () => useG1TraFinFormData({ wpId: ref('wp-1'), projectId: ref('p-1') }), 'G1-1-remark', 'strict-cas-draft'],
    ['G3', () => useG3FormData({ wpId: ref('wp-1'), projectId: ref('p-1') }), 'G3-1-remark', 'strict-cas-draft'],
    ['G4 ECL', () => useG4EclFormData({ wpId: ref('wp-1'), projectId: ref('p-1') }), 'G4-9-conclusion', 'strict-cas-draft'],
    ['G4 SPPI', () => useG4SppiFormData({ wpId: ref('wp-1'), projectId: ref('p-1') }), 'G4-sppi-conclusion', 'strict-cas-draft'],
    ['G5', () => useG5LonRecFormData({ wpId: ref('wp-1'), projectId: ref('p-1') }), 'G5-1-remark', 'strict-cas-draft'],
    ['G6 main', () => useG6MainFormData({ wpId: ref('wp-1'), projectId: ref('p-1') }), 'G6-main-conclusion', 'strict-cas-draft'],
    ['G6 SPPI', () => useG6SppiFormData({ wpId: ref('wp-1'), projectId: ref('p-1') }), 'G6-sppi-conclusion', 'strict-cas-draft'],
    ['G8', () => useG8FormData({ wpId: ref('wp-1'), projectId: ref('p-1') }), 'G8-1-remark', 'g8-draft'],
    ['G9', () => useG9FormData({ wpId: ref('wp-1'), projectId: ref('p-1') }), 'G9-1-remark', 'g9-draft'],
    ['G10', () => useG10FormData({ wpId: ref('wp-1'), projectId: ref('p-1') }), 'G10-1-remark', 'g10-draft'],
    ['G11', () => useG11FormData({ wpId: ref('wp-1'), projectId: ref('p-1') }), 'G11-1-remark', 'g11-draft'],
    ['G12', () => useG12FormData({ wpId: ref('wp-1'), projectId: ref('p-1') }), 'G12-1-remark', 'g12-draft'],
    ['G13', () => useG13FormData({ wpId: ref('wp-1'), projectId: ref('p-1') }), 'G13-1-remark', 'strict-cas-draft'],
    ['G14', () => useG14FormData({ wpId: ref('wp-1'), projectId: ref('p-1') }), 'G14-1-remark', 'strict-cas-draft'],
  ])('%s 在防抖尚未发请求时已耐久化最新编辑', (_name, create, itemId, namespace) => {
    const formData = inScope(create as () => DraftableGFormData)

    formData.debouncedSave(itemId, { remark: '输入即草稿' })

    expect(put).not.toHaveBeenCalled()
    expect(JSON.parse(localStorage.getItem(`${namespace}:user-1:wp-1:${itemId}`) || '{}')).toMatchObject({
      item: { item_id: itemId, remark: '输入即草稿' },
    })
  })
})


describe('strict-CAS 冲突后的重建生命周期', () => {
  it('409 后编辑 B、卸载并新建表单时仍能保留 B，且不自动覆盖服务器 C', async () => {
    let serverVersion = 'version-A'
    let serverRemark = '远端 A'
    vi.mocked(api.get).mockImplementation(async (url: string) => (
      url.includes('checklist-responses')
        ? [{ item_id: 'G9-1-remark', conclusion: null, remark: serverRemark, updated_at: serverVersion }]
        : {}
    ))
    const request = deferred()
    const conflict = Object.assign(new Error('版本冲突'), { response: { status: 409 } })
    put.mockReturnValueOnce(request.promise)

    const firstScope = effectScope()
    const first = firstScope.run(() => useG9FormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))!
    await first.loadAll()
    const saving = first.saveImmediate('G9-1-remark', { remark: '本地 A' })
    await Promise.resolve()
    await Promise.resolve()
    first.debouncedSave('G9-1-remark', { remark: '本地 B' })
    const rejected = expect(saving).rejects.toBe(conflict)
    request.reject(conflict)
    await rejected

    firstScope.stop()
    serverVersion = 'version-C'
    serverRemark = '远端 C'
    const restored = inScope(() => useG9FormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))
    await restored.loadAll()

    expect(ElMessageBox.confirm).toHaveBeenCalledOnce()
    expect(put).toHaveBeenCalledOnce()
    expect(restored.allResponses.value.get('G9-1-remark')).toMatchObject({ remark: '本地 B' })
    expect(localStorage.getItem('g9-draft:user-1:wp-1:G9-1-remark')).toContain('version-A')
  })
})

describe('G1 fallback snapshot 的冻结边界', () => {
  it('render-config 降级快照不能解除 409 队列冻结', async () => {
    let checklistCalls = 0
    let renderCalls = 0
    vi.mocked(api.get).mockImplementation(async (url: string) => {
      if (url.includes('checklist-responses')) {
        checklistCalls += 1
        if (checklistCalls === 1) {
          return [{ item_id: 'G1-1-remark', conclusion: null, remark: '远端 A', updated_at: 'version-A' }]
        }
        throw new Error('GET failed')
      }
      renderCalls += 1
      return renderCalls === 1
        ? {}
        : { responses_snapshot: { 'G1-2-remark': { conclusion: null, remark: '快照', version: 'snapshot-v1' } } }
    })
    const conflict = Object.assign(new Error('版本冲突'), { response: { status: 409 } })
    put.mockRejectedValue(conflict)
    const formData = inScope(() => useG1TraFinFormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))

    await formData.loadAll()
    await expect(formData.saveImmediate('G1-1-remark', { remark: '本地 A' })).rejects.toBe(conflict)
    await formData.loadAll()
    formData.debouncedSave('G1-1-remark', { remark: '本地 B' })
    await vi.advanceTimersByTimeAsync(2100)

    expect(put).toHaveBeenCalledOnce()
  })
})


describe('同一实例的冲突重载', () => {
  async function makeG9Conflict(status = 409) {
    let serverVersion = 'version-A'
    let serverRemark = '远端 A'
    vi.mocked(api.get).mockImplementation(async (url: string) => (
      url.includes('checklist-responses')
        ? [{ item_id: 'G9-1-remark', conclusion: null, remark: serverRemark, updated_at: serverVersion }]
        : {}
    ))
    const conflict = Object.assign(
      new Error(status === 428 ? '需要版本' : '版本冲突'),
      { response: { status } },
    )
    put.mockRejectedValueOnce(conflict).mockResolvedValue([])
    const formData = inScope(() => useG9FormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))
    await formData.loadAll()
    await expect(formData.saveImmediate('G9-1-remark', { remark: '本地 A' })).rejects.toBe(conflict)
    serverVersion = 'version-C'
    serverRemark = '远端 C'
    return { formData, conflict }
  }

  it('428 缺失版本的重载也必须由用户决定，不自动重发', async () => {
    const { formData } = await makeG9Conflict(428)

    await formData.loadAll()
    await formData.flushPending()

    expect(ElMessageBox.confirm).toHaveBeenCalledOnce()
    expect(put).toHaveBeenCalledOnce()
  })

  it('选择保留时清掉旧 pending，之后的 flush 不会自动覆盖服务器', async () => {
    const { formData } = await makeG9Conflict()

    await formData.loadAll()
    await formData.flushPending()

    expect(ElMessageBox.confirm).toHaveBeenCalledOnce()
    expect(formData.allResponses.value.get('G9-1-remark')).toMatchObject({ remark: '本地 A' })
    expect(put).toHaveBeenCalledOnce()
  })

  it('选择丢弃时清掉旧 pending，之后的 flush 不会制造冗余更新', async () => {
    const { formData } = await makeG9Conflict()
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')

    await formData.loadAll()
    await formData.flushPending()

    expect(formData.allResponses.value.get('G9-1-remark')).toMatchObject({ remark: '远端 C' })
    expect(localStorage.getItem('g9-draft:user-1:wp-1:G9-1-remark')).toBeNull()
    expect(put).toHaveBeenCalledOnce()
  })
})


describe('多条冲突草稿的恢复冻结', () => {
  it('两条冲突草稿在首个确认弹窗等待时都不能被全局屏障自动提交或清除', async () => {
    let firstServerVersion = 'version-A'
    const secondServerVersion = 'version-A'
    vi.mocked(api.get).mockImplementation(async (url: string) => (
      url.includes('checklist-responses')
        ? [
          { item_id: 'G9-1-remark', conclusion: null, remark: '远端 A1', updated_at: firstServerVersion },
          { item_id: 'G9-2-remark', conclusion: null, remark: '远端 A2', updated_at: secondServerVersion },
        ]
        : {}
    ))
    const conflict = Object.assign(new Error('版本冲突'), { response: { status: 409 } })
    put.mockRejectedValueOnce(conflict).mockResolvedValue([])
    const formData = inScope(() => useG9FormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))
    await formData.loadAll()
    formData.debouncedSave('G9-1-remark', { remark: '本地 B1' })
    formData.debouncedSave('G9-2-remark', { remark: '本地 B2' })
    await expect(formData.flushPending()).rejects.toBe(conflict)

    firstServerVersion = 'version-C'
    const dialog = deferred()
    vi.mocked(ElMessageBox.confirm).mockImplementationOnce(() => dialog.promise as any)
    const reloading = formData.loadAll()
    await Promise.resolve()
    await Promise.resolve()
    await flushPendingWrites()

    expect(put).toHaveBeenCalledOnce()
    expect(localStorage.getItem('g9-draft:user-1:wp-1:G9-1-remark')).toContain('本地 B1')
    expect(localStorage.getItem('g9-draft:user-1:wp-1:G9-2-remark')).toContain('本地 B2')

    dialog.resolve()
    await reloading
    await formData.flushPending()
    expect(put).toHaveBeenCalledOnce()
  })
})


describe('无权读取时的草稿边界', () => {
  it('403 不把本地 checklist 草稿恢复到当前表单', async () => {
    localStorage.setItem(
      'g9-draft:user-1:wp-1:G9-1-remark',
      JSON.stringify({
        item: { item_id: 'G9-1-remark', conclusion: null, remark: '前一会话草稿' },
        baseVersion: 'version-A',
      }),
    )
    const denied = Object.assign(new Error('forbidden'), { response: { status: 403 } })
    vi.mocked(api.get).mockImplementation(async (url: string) => {
      if (url.includes('checklist-responses')) throw denied
      return {}
    })
    const formData = inScope(() => useG9FormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))

    await formData.loadAll()

    expect(formData.allResponses.value.has('G9-1-remark')).toBe(false)
    expect(localStorage.getItem('g9-draft:user-1:wp-1:G9-1-remark')).toContain('前一会话草稿')
    expect(put).not.toHaveBeenCalled()
  })
})


describe('4xx 之后的新编辑仍需人工决定', () => {
  it('被拒批次中的 B 再次编辑后，重建实例也不能因版本相同自动提交', async () => {
    let firstServerVersion = 'version-A'
    const secondServerVersion = 'version-A'
    vi.mocked(api.get).mockImplementation(async (url: string) => (
      url.includes('checklist-responses')
        ? [
          { item_id: 'G9-1-remark', conclusion: null, remark: '远端 A1', updated_at: firstServerVersion },
          { item_id: 'G9-2-remark', conclusion: null, remark: '远端 A2', updated_at: secondServerVersion },
        ]
        : {}
    ))
    const conflict = Object.assign(new Error('版本冲突'), { response: { status: 409 } })
    put.mockRejectedValueOnce(conflict).mockResolvedValue([])
    const first = inScope(() => useG9FormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))
    await first.loadAll()
    first.debouncedSave('G9-1-remark', { remark: '本地 B1' })
    first.debouncedSave('G9-2-remark', { remark: '本地 B2' })
    await expect(first.flushPending()).rejects.toBe(conflict)

    first.debouncedSave('G9-2-remark', { remark: '4xx 后新编辑 B2' })
    expect(JSON.parse(localStorage.getItem('g9-draft:user-1:wp-1:G9-2-remark') || '{}'))
      .toMatchObject({ requiresConfirmation: true, item: { remark: '4xx 后新编辑 B2' } })

    firstServerVersion = 'version-C'
    const restored = inScope(() => useG9FormData({ wpId: ref('wp-1'), projectId: ref('p-1') }))
    await restored.loadAll()
    await restored.flushPending()

    expect(put).toHaveBeenCalledOnce()
    expect(restored.allResponses.value.get('G9-2-remark')).toMatchObject({ remark: '4xx 后新编辑 B2' })
  })
})