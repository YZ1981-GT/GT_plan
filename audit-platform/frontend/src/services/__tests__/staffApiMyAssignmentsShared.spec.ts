/**
 * 「我的委派项目」并发取数不被 GET 去重取消（spec platform-performance-residual-findings-closure 验收期发现）。
 *
 * 工时页 onMounted 取完人员编号紧接着 `getMyAssignments()`，「我的填报」（WeeklyTimesheet，`v-if` 等人员编号）随之
 * 挂载又取一次。原实现走 `utils/http`：同一 GET 在飞时后发者 abort 先发者 ⇒ 工时页的那次被取消、catch 静默 ⇒
 * 「预算对比」下拉恒空、图表从不渲染（2026-10-31 浏览器实测：只发出一次 XHR，下拉停在「选择项目」）。
 * 改走 apiProxy：同参数并发共用一次请求、不进取消前一个的去重表。
 *
 * 用真实 `utils/http` + `apiProxy`，只替换 axios 适配器（网络层）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 't', refreshToken: null, logout: vi.fn(), setTokens: vi.fn() }),
}))
vi.mock('nprogress', () => ({ default: { start: vi.fn(), done: vi.fn(), inc: vi.fn() } }))
vi.mock('element-plus', () => ({ ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn() } }))
vi.mock('@/composables/useVersionCheck', () => ({ versionBridge: { check: vi.fn() } }))

const ASSIGNMENTS = [
  { project_id: 'p1', project_name: '甲公司_2025' },
  { project_id: 'p2', project_name: '乙公司_2025' },
]

function canceledError(): Error {
  return Object.assign(new Error('canceled'), { code: 'ERR_CANCELED', name: 'CanceledError' })
}

describe('getMyAssignments 并发调用', () => {
  let http: typeof import('@/utils/http').default
  let sent: string[]
  let originalAdapter: any

  beforeEach(async () => {
    vi.resetModules()
    http = (await import('@/utils/http')).default
    sent = []
    originalAdapter = http.defaults.adapter
    http.defaults.adapter = async (config: any) => {
      if (config.signal?.aborted) throw canceledError()
      sent.push(String(config.url))
      await new Promise((r) => setTimeout(r, 20))
      if (config.signal?.aborted) throw canceledError()
      return { data: { code: 200, message: 'success', data: ASSIGNMENTS }, status: 200, statusText: 'OK', headers: {}, config }
    }
  })

  afterEach(() => {
    if (http) http.defaults.adapter = originalAdapter
  })

  it('同一时刻两个调用方（工时页 + 我的填报）都拿到列表，只发一次请求', async () => {
    const { getMyAssignments } = await import('@/services/staffApi')
    const [page, timesheet] = await Promise.allSettled([getMyAssignments(), getMyAssignments()])
    expect(page).toMatchObject({ status: 'fulfilled' })
    expect(timesheet).toMatchObject({ status: 'fulfilled' })
    expect((page as PromiseFulfilledResult<unknown[]>).value.map((a: any) => a.project_id)).toEqual(['p1', 'p2'])
    expect((timesheet as PromiseFulfilledResult<unknown[]>).value).toHaveLength(2)
    expect(sent).toEqual(['/api/projects/my/assignments'])
  })

  it('每个调用方拿自己的数组（一方增删不影响另一方）', async () => {
    const { getMyAssignments } = await import('@/services/staffApi')
    const [a, b] = await Promise.all([getMyAssignments(), getMyAssignments()])
    expect(a).not.toBe(b)
    a.push({ project_id: 'x' } as any)
    expect(b).toHaveLength(2)
  })

  it('机制自检：直接 http.get 同时取两次也共用一次请求（R11 起；原先先发的被去重取消，正是这样丢掉工时页那次）', async () => {
    const [first, second] = await Promise.allSettled([
      http.get('/api/projects/my/assignments'),
      http.get('/api/projects/my/assignments'),
    ])
    expect(first).toMatchObject({ status: 'fulfilled' })
    expect(second).toMatchObject({ status: 'fulfilled' })
    expect(sent).toEqual(['/api/projects/my/assignments'])
    const [a, b] = [first, second].map((r) => (r as PromiseFulfilledResult<any>).value.data)
    expect(a).toEqual(ASSIGNMENTS)
    expect(b).toEqual(ASSIGNMENTS)
    expect(a).not.toBe(b)
  })
})
