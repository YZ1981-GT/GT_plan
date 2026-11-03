/**
 * 项目 store 的审计年度（spec post-push-residual-defect-closure 6.5.1）。
 *
 * 原先 `year` 初值是去年、换到没填审计年度的项目也不清：页面就静默按去年 / 上一个项目的年度取数
 * （浏览器实测交付中心请求 `year=2025` 回 500、附注编辑页取 `/2025` 回 404）。
 * 现在：初值 null；换项目先清空、取到项目信息再定（没填就是 null）；取失败单独记 failed；晚到的旧项目响应丢弃。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const getProject = vi.fn()
vi.mock('@/services/auditPlatformApi', () => ({ getProject: (...a: unknown[]) => getProject(...a) }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn().mockResolvedValue({ years: [] }) } }))
vi.mock('@/utils/eventBus', () => ({ eventBus: { emit: vi.fn() } }))

import { useProjectStore } from '@/stores/project'

const route = (pid: string | undefined, query: Record<string, string> = {}) =>
  ({ params: pid ? { projectId: pid } : {}, query }) as any

/** 手动放行的项目详情请求 */
function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

beforeEach(() => {
  setActivePinia(createPinia())
  getProject.mockReset()
})

describe('初值与非项目页', () => {
  it('初值：年度 null、状态 idle（不再是去年）', () => {
    const store = useProjectStore()
    expect(store.year).toBeNull()
    expect(store.yearStatus).toBe('idle')
    expect(store.currentProjectContext.year).toBeNull()
  })

  it('离开项目到非项目页：年度清空、回到 idle', async () => {
    getProject.mockResolvedValue({ client_name: '【测试】甲', audit_year: 2025 })
    const store = useProjectStore()
    await store.syncFromRoute(route('p1'))
    expect(store.year).toBe(2025)
    await store.syncFromRoute(route(undefined))
    expect(store.year).toBeNull()
    expect(store.yearStatus).toBe('idle')
    expect(store.projectId).toBe('')
  })
})

describe('换项目', () => {
  it('路由没带年度：取到项目信息前是 null + loading，取到后 = 项目审计年度 + ready', async () => {
    const d = deferred<any>()
    getProject.mockReturnValue(d.promise)
    const store = useProjectStore()
    const p = store.syncFromRoute(route('p1'))
    expect(store.year).toBeNull()
    expect(store.yearStatus).toBe('loading')
    d.resolve({ client_name: '【测试】甲', audit_year: 2025 })
    await p
    expect(store.year).toBe(2025)
    expect(store.auditYear).toBe(2025)
    expect(store.yearStatus).toBe('ready')
  })

  it('从有年度的项目换到没填年度的项目：年度为 null，不沿用上一个项目的 2025', async () => {
    getProject.mockResolvedValueOnce({ client_name: '【测试】甲', audit_year: 2025 })
    getProject.mockResolvedValueOnce({ client_name: '【测试】无年度' })
    const store = useProjectStore()
    await store.syncFromRoute(route('p1'))
    expect(store.year).toBe(2025)
    const p = store.syncFromRoute(route('p2'))
    expect(store.year).toBeNull() // 取项目信息期间也不是 2025
    await p
    expect(store.year).toBeNull()
    expect(store.auditYear).toBeNull()
    expect(store.yearStatus).toBe('ready')
    expect(store.clientName).toBe('【测试】无年度')
  })

  it('路由带年度：立即 ready 用路由年度，项目信息晚到也不覆盖', async () => {
    const d = deferred<any>()
    getProject.mockReturnValue(d.promise)
    const store = useProjectStore()
    const p = store.syncFromRoute(route('p1', { year: '2024' }))
    expect(store.year).toBe(2024)
    expect(store.yearStatus).toBe('ready')
    d.resolve({ client_name: '【测试】甲', audit_year: 2025 })
    await p
    expect(store.year).toBe(2024)
    expect(store.auditYear).toBe(2025)
  })

  it('路由年度不合法（null / 0 / 文字）按没带处理', async () => {
    getProject.mockResolvedValue({ client_name: '【测试】甲', audit_year: 2025 })
    const store = useProjectStore()
    await store.syncFromRoute(route('p1', { year: 'null' }))
    expect(store.year).toBe(2025)
  })

  it('乱序：先切 A 再切 B，A 的响应晚到 ⇒ 丢弃，年度与项目信息都是 B 的', async () => {
    const a = deferred<any>()
    const b = deferred<any>()
    getProject.mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise)
    const store = useProjectStore()
    const pa = store.syncFromRoute(route('pA'))
    const pb = store.syncFromRoute(route('pB'))
    b.resolve({ client_name: '【测试】乙', audit_year: 2024 })
    await pb
    a.resolve({ client_name: '【测试】甲', audit_year: 2025 })
    await pa
    expect(store.projectId).toBe('pB')
    expect(store.year).toBe(2024)
    expect(store.clientName).toBe('【测试】乙')
  })

  it('取项目信息不参与 GET 去重（被同址 GET 取消会误判成取失败）', async () => {
    getProject.mockResolvedValue({ audit_year: 2025 })
    const store = useProjectStore()
    await store.syncFromRoute(route('p1'))
    expect(getProject).toHaveBeenCalledWith('p1', { dedupe: false })
  })

  it('页内显式选了年度：晚到的项目信息不覆盖', async () => {
    const d = deferred<any>()
    getProject.mockReturnValue(d.promise)
    const store = useProjectStore()
    const p = store.syncFromRoute(route('p1'))
    store.changeYear(2023)
    d.resolve({ audit_year: 2025 })
    await p
    expect(store.year).toBe(2023)
    expect(store.yearStatus).toBe('ready')
  })
})

describe('取失败与重试', () => {
  it('两次都失败 ⇒ failed（不是「没填」），重试成功 ⇒ ready', async () => {
    getProject.mockRejectedValueOnce(new Error('HTTP 500')).mockRejectedValueOnce(new Error('HTTP 500'))
    const store = useProjectStore()
    await store.syncFromRoute(route('p1'))
    expect(getProject).toHaveBeenCalledTimes(2)
    expect(store.yearStatus).toBe('failed')
    expect(store.year).toBeNull()

    getProject.mockResolvedValueOnce({ client_name: '【测试】甲', audit_year: 2025 })
    await store.retryProjectContext()
    expect(store.yearStatus).toBe('ready')
    expect(store.year).toBe(2025)
  })

  it('失败后同一项目再导航：重取', async () => {
    getProject.mockRejectedValueOnce(new Error('x')).mockRejectedValueOnce(new Error('x'))
    const store = useProjectStore()
    await store.syncFromRoute(route('p1'))
    expect(store.yearStatus).toBe('failed')
    getProject.mockResolvedValueOnce({ audit_year: 2024 })
    await store.syncFromRoute(route('p1'))
    expect(store.yearStatus).toBe('ready')
    expect(store.year).toBe(2024)
  })

  it('路由带年度时取失败：年度照用路由的，仍是 ready', async () => {
    getProject.mockRejectedValue(new Error('x'))
    const store = useProjectStore()
    await store.syncFromRoute(route('p1', { year: '2024' }))
    expect(store.year).toBe(2024)
    expect(store.yearStatus).toBe('ready')
  })
})

describe('loadProjectContext（项目设置页）', () => {
  it('换到没填年度的项目：年度 null，不沿用上一个项目的', async () => {
    getProject.mockResolvedValueOnce({ audit_year: 2025 }).mockResolvedValueOnce({ client_name: '【测试】无年度' })
    const store = useProjectStore()
    await store.loadProjectContext('p1')
    expect(store.year).toBe(2025)
    await store.loadProjectContext('p2')
    expect(store.year).toBeNull()
    expect(store.yearStatus).toBe('ready')
  })

  it('同一项目重载：回到项目审计年度（原行为）', async () => {
    getProject.mockResolvedValue({ audit_year: 2025 })
    const store = useProjectStore()
    await store.loadProjectContext('p1')
    store.changeYear(2023)
    await store.loadProjectContext('p1')
    expect(store.year).toBe(2025)
  })
})
