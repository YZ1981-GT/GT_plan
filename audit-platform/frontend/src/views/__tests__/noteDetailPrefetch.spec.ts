/**
 * 附注目录 hover 预取不得取消「点击取当前章」的请求（spec disclosure-note-template-word-realignment Task 27 浏览器实测）。
 *
 * 预取与点击发的是同一个 GET，`http` 的 GET 去重会取消先发的那一个。原实现点击后不掐预取：鼠标移入后 200ms 内点击、
 * 且点击的请求 200ms 内没回（后端慢）时，晚到的预取把点击的请求取消，`onNodeClick` 当失败置空 ⇒ 中间栏回到
 * 「请从左侧目录选择章节」，要再点一次（2026-10-17 和平 八、1 两次复现，请求记录 = 一条 ERR_ABORTED + 一条 200）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createNoteDetailPrefetch } from '@/views/composables/noteDetailPrefetch'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 't', refreshToken: null, logout: vi.fn(), setTokens: vi.fn() }),
}))
vi.mock('nprogress', () => ({ default: { start: vi.fn(), done: vi.fn(), inc: vi.fn() } }))
vi.mock('element-plus', () => ({ ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn() } }))
vi.mock('@/composables/useVersionCheck', () => ({ versionBridge: { check: vi.fn() } }))

const NOTE_URL = '/api/disclosure-notes/p1/2025/%E5%85%AB%E3%80%811'
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

describe('与真实 GET 去重一起跑：点击请求不被晚到的预取取消', () => {
  let http: typeof import('@/utils/http').default
  let originalAdapter: any

  beforeEach(async () => {
    vi.resetModules()
    http = (await import('@/utils/http')).default
    originalAdapter = http.defaults.adapter
    http.defaults.adapter = async (config: any) => {
      await sleep(40) // 慢后端：点击的请求 40ms 才回，预取 10ms 就到点
      if (config.signal?.aborted) throw Object.assign(new Error('canceled'), { code: 'ERR_CANCELED', name: 'CanceledError' })
      return { data: { note_section: '八、1' }, status: 200, statusText: 'OK', headers: {}, config }
    }
  })
  afterEach(() => { http.defaults.adapter = originalAdapter })

  function setup() {
    const cache = new Map<string, unknown>()
    const prefetch = createNoteDetailPrefetch(() => http.get(NOTE_URL), cache, (s) => s, 10)
    return { cache, prefetch }
  }

  it('根因特征：不掐预取 ⇒ 点击的请求被取消', async () => {
    const { prefetch } = setup()
    prefetch.schedule('八、1')
    const click = http.get(NOTE_URL)
    await expect(click).rejects.toMatchObject({ code: 'ERR_CANCELED' })
  })

  it('开始取当前章前 cancel() ⇒ 点击的请求照常返回、预取不再发', async () => {
    const { cache, prefetch } = setup()
    prefetch.schedule('八、1')
    prefetch.cancel()
    const click = await http.get(NOTE_URL)
    expect(click.status).toBe(200)
    await sleep(30)
    expect(cache.size).toBe(0)
  })
})

describe('createNoteDetailPrefetch', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('停留到点后加载进缓存', async () => {
    const cache = new Map<string, unknown>()
    const load = vi.fn(async (s: string) => ({ s }))
    createNoteDetailPrefetch(load, cache, (s) => `k:${s}`).schedule('八、1')
    await vi.advanceTimersByTimeAsync(199)
    expect(load).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    expect(load).toHaveBeenCalledWith('八、1')
    expect(cache.get('k:八、1')).toEqual({ s: '八、1' })
  })

  it('到点时已有缓存（点击已取回）就不再请求', async () => {
    const cache = new Map<string, unknown>()
    const load = vi.fn(async () => ({}))
    createNoteDetailPrefetch(load, cache, (s) => s).schedule('八、1')
    cache.set('八、1', { from: 'click' })
    await vi.advanceTimersByTimeAsync(300)
    expect(load).not.toHaveBeenCalled()
    expect(cache.get('八、1')).toEqual({ from: 'click' })
  })

  it('移到另一节只保留最后一次；预取失败静默', async () => {
    const cache = new Map<string, unknown>()
    const load = vi.fn(async () => { throw new Error('500') })
    const prefetch = createNoteDetailPrefetch(load, cache, (s) => s)
    prefetch.schedule('八、1')
    prefetch.schedule('八、2')
    await vi.advanceTimersByTimeAsync(300)
    expect(load.mock.calls).toEqual([['八、2']])
    expect(cache.size).toBe(0)
  })
})

describe('DisclosureEditor 接线', () => {
  const src = readFileSync(resolve(__dirname, '../DisclosureEditor.vue'), 'utf-8')

  it('fetchDetail 发请求前先掐预取', () => {
    expect(src).toMatch(/async function fetchDetail\([^)]*\) \{\r?\n\s*_prefetch\.cancel\(\)/)
  })

  it('目录节点移入 / 移出走同一个预取器，不再自带定时器', () => {
    expect(src).toMatch(/_prefetch\.schedule\(data\.note_section\)/)
    expect(src).toMatch(/function onTreeNodeMouseLeave\(\) \{ _prefetch\.cancel\(\) \}/)
    expect(src).not.toMatch(/_prefetchTimer/)
  })
})
