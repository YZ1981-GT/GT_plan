/**
 * useAuthedObjectUrl — 原件预览走已鉴权请求（spec attachment-security-baseline 任务 12）
 *
 * 缺陷：iframe / img 直接用 /api 路径当 src，浏览器原生加载带不上 Bearer 头 ⇒ 恒 401，
 * 预览区显示 {"code":401,"message":"Not authenticated"}。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'
import { flushPromises } from '@vue/test-utils'

const apiMock = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api: apiMock, default: apiMock }))

import {
  AUTHED_OBJECT_URL_CACHE_MAX_ENTRIES,
  AUTHED_OBJECT_URL_CACHE_TTL_MS,
  authedObjectUrlFailureText,
  clearAuthedObjectUrlCache,
  useAuthedObjectUrl,
} from '@/composables/useAuthedObjectUrl'

let created: Blob[] = []
let revoked: string[] = []

beforeEach(() => {
  clearAuthedObjectUrlCache()
  apiMock.get.mockReset()
  created = []
  revoked = []
  ;(URL as any).createObjectURL = vi.fn((b: Blob) => {
    created.push(b)
    return `blob:test-${created.length}`
  })
  ;(URL as any).revokeObjectURL = vi.fn((u: string) => { revoked.push(u) })
})

afterEach(() => {
  vi.restoreAllMocks()
})

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

function run(source: () => string, options?: Parameters<typeof useAuthedObjectUrl>[1]) {
  const scope = effectScope()
  const result = scope.run(() => useAuthedObjectUrl(source, options))!
  return { scope, ...result }
}

describe('useAuthedObjectUrl', () => {
  it('经 api.get 取 blob（静默、不去重、可中止），换成 blob: 地址', async () => {
    apiMock.get.mockResolvedValue(new Blob(['%PDF'], { type: 'application/pdf' }))
    const { url, state, scope } = run(() => '/api/attachments/a1/preview')
    expect(state.value).toBe('loading')
    await flushPromises()

    expect(apiMock.get).toHaveBeenCalledTimes(1)
    const [path, cfg] = apiMock.get.mock.calls[0]
    expect(path).toBe('/api/attachments/a1/preview')
    expect(cfg).toMatchObject({ responseType: 'blob', _silent: true, _dedupe: false })
    expect(cfg.signal).toBeInstanceOf(AbortSignal)
    expect(state.value).toBe('ready')
    expect(url.value).toBe('blob:test-1')
    scope.stop()
  })

  it('源地址为空：不发请求，状态 idle', async () => {
    const { url, state, scope } = run(() => '')
    await flushPromises()
    expect(apiMock.get).not.toHaveBeenCalled()
    expect(state.value).toBe('idle')
    expect(url.value).toBe('')
    scope.stop()
  })

  it('源地址变化：中止在途请求、晚到的旧响应不覆盖新地址、旧地址被释放', async () => {
    const first = deferred<Blob>()
    const second = deferred<Blob>()
    apiMock.get.mockImplementationOnce(() => first.promise).mockImplementationOnce(() => second.promise)
    const src = ref('/api/attachments/a1/preview')
    const { url, state, scope } = run(() => src.value)
    const firstSignal: AbortSignal = apiMock.get.mock.calls[0][1].signal

    src.value = '/api/attachments/a2/preview'
    await nextTick()
    expect(firstSignal.aborted).toBe(true)

    second.resolve(new Blob(['b'], { type: 'image/png' }))
    await flushPromises()
    expect(url.value).toBe('blob:test-1')
    first.resolve(new Blob(['a'], { type: 'image/png' }))
    await flushPromises()
    expect(url.value).toBe('blob:test-1') // 旧响应被丢弃
    expect(created).toHaveLength(1)
    expect(state.value).toBe('ready')

    src.value = ''
    await flushPromises()
    expect(revoked).toEqual(['blob:test-1'])
    expect(state.value).toBe('idle')
    scope.stop()
  })

  it.each([
    [403, 'forbidden', '无权查看该文件'],
    [404, 'not_found', '文件不存在或已删除'],
    [500, 'failed', '文件加载失败，请稍后重试'],
  ])('HTTP %i → %s', async (status, expected, text) => {
    apiMock.get.mockRejectedValue({ response: { status } })
    const { url, state, scope } = run(() => '/api/attachments/a1/preview')
    await flushPromises()
    expect(state.value).toBe(expected)
    expect(authedObjectUrlFailureText(state.value)).toBe(text)
    expect(url.value).toBe('')
    scope.stop()
  })

  it('端点回 JSON（previewable:false）不当文件显示', async () => {
    apiMock.get.mockResolvedValue(new Blob(['{"previewable":false}'], { type: 'application/json' }))
    const { url, state, scope } = run(() => '/api/attachments/a1/preview')
    await flushPromises()
    expect(state.value).toBe('failed')
    expect(url.value).toBe('')
    expect(created).toHaveLength(0)
    scope.stop()
  })

  it('失败请求结算后会移出在途表，下一次进入可重新请求', async () => {
    apiMock.get
      .mockRejectedValueOnce({ response: { status: 500 } })
      .mockResolvedValueOnce(new Blob(['retry'], { type: 'image/png' }))

    const first = run(() => '/api/attachments/retry/preview')
    await flushPromises()
    expect(first.state.value).toBe('failed')
    first.scope.stop()

    const second = run(() => '/api/attachments/retry/preview')
    await flushPromises()
    expect(apiMock.get).toHaveBeenCalledTimes(2)
    expect(second.state.value).toBe('ready')
    second.scope.stop()
  })

  it('options.type 强制 blob 类型（iframe 显示 PDF）', async () => {
    apiMock.get.mockResolvedValue(new Blob(['%PDF'], { type: 'application/octet-stream' }))
    const { scope } = run(() => '/api/attachments/a1/preview', { type: () => 'application/pdf' })
    await flushPromises()
    expect(created).toHaveLength(1)
    expect(created[0].type).toBe('application/pdf')
    scope.stop()
  })

  it('作用域销毁：释放地址并中止在途请求', async () => {
    apiMock.get.mockResolvedValueOnce(new Blob(['x'], { type: 'image/png' }))
    const done = run(() => '/api/attachments/a1/preview')
    await flushPromises()
    done.scope.stop()
    expect(revoked).toEqual(['blob:test-1'])

    const pending = deferred<Blob>()
    apiMock.get.mockImplementationOnce(() => pending.promise)
    const inflightScope = run(() => '/api/attachments/a2/preview')
    const signal: AbortSignal = apiMock.get.mock.calls[1][1].signal
    inflightScope.scope.stop()
    expect(signal.aborted).toBe(true)
    pending.resolve(new Blob(['y'], { type: 'image/png' }))
    await flushPromises()
    expect(inflightScope.url.value).toBe('')
    expect(created).toHaveLength(1)
  })

  it('相同地址共享在途请求，但每个作用域独立生成并释放 object URL', async () => {
    const pending = deferred<Blob>()
    apiMock.get.mockReturnValueOnce(pending.promise)
    const first = run(() => '/api/attachments/shared/preview')
    const second = run(() => '/api/attachments/shared/preview')
    expect(apiMock.get).toHaveBeenCalledTimes(1)
    const signal: AbortSignal = apiMock.get.mock.calls[0][1].signal

    first.scope.stop()
    expect(signal.aborted).toBe(false)
    pending.resolve(new Blob(['shared'], { type: 'image/png' }))
    await flushPromises()
    expect(second.url.value).toBe('blob:test-1')
    expect(created).toHaveLength(1)
    second.scope.stop()
    expect(revoked).toEqual(['blob:test-1'])
  })

  it('TTL 内复用 Blob，显式退出清理后下一次重新请求', async () => {
    apiMock.get.mockResolvedValue(new Blob(['cached'], { type: 'image/png' }))
    const first = run(() => '/api/attachments/cached/preview')
    await flushPromises()
    first.scope.stop()

    const withinTtl = run(() => '/api/attachments/cached/preview')
    await flushPromises()
    expect(apiMock.get).toHaveBeenCalledTimes(1)
    withinTtl.scope.stop()

    clearAuthedObjectUrlCache()
    const afterExit = run(() => '/api/attachments/cached/preview')
    await flushPromises()
    expect(apiMock.get).toHaveBeenCalledTimes(2)
    afterExit.scope.stop()
  })

  it('TTL 到期后不复用旧 Blob', async () => {
    vi.useFakeTimers()
    try {
      apiMock.get.mockResolvedValue(new Blob(['expiring'], { type: 'image/png' }))
      const first = run(() => '/api/attachments/expiring/preview')
      await flushPromises()
      first.scope.stop()

      vi.advanceTimersByTime(AUTHED_OBJECT_URL_CACHE_TTL_MS + 1)
      const second = run(() => '/api/attachments/expiring/preview')
      await flushPromises()
      expect(apiMock.get).toHaveBeenCalledTimes(2)
      second.scope.stop()
    } finally {
      vi.useRealTimers()
    }
  })

  it('达到容量上限时淘汰最早访问项', async () => {
    apiMock.get.mockImplementation(async (path: string) => new Blob([path], { type: 'image/png' }))
    for (let index = 0; index <= AUTHED_OBJECT_URL_CACHE_MAX_ENTRIES; index += 1) {
      const item = run(() => `/api/attachments/cache-${index}/preview`)
      await flushPromises()
      item.scope.stop()
    }
    const firstAgain = run(() => '/api/attachments/cache-0/preview')
    await flushPromises()
    expect(apiMock.get).toHaveBeenCalledTimes(AUTHED_OBJECT_URL_CACHE_MAX_ENTRIES + 2)
    firstAgain.scope.stop()
  })

  it('最后一个作用域离开后才中止共享在途请求，晚到响应不进入缓存', async () => {
    const pending = deferred<Blob>()
    apiMock.get.mockReturnValueOnce(pending.promise)
    const first = run(() => '/api/attachments/abort-shared/preview')
    const second = run(() => '/api/attachments/abort-shared/preview')
    const signal: AbortSignal = apiMock.get.mock.calls[0][1].signal

    first.scope.stop()
    expect(signal.aborted).toBe(false)
    second.scope.stop()
    expect(signal.aborted).toBe(true)
    pending.resolve(new Blob(['late'], { type: 'image/png' }))
    await flushPromises()

    const retry = run(() => '/api/attachments/abort-shared/preview')
    await flushPromises()
    expect(apiMock.get).toHaveBeenCalledTimes(2)
    retry.scope.stop()
  })
})
