/**
 * 写请求带窗口编号 X-Client-Instance（spec workpaper-multi-window-lock-gaps R2.6）。
 *
 * 后端按它判断底稿保存 / 导入是不是持锁的那个窗口发的；原先只有编辑锁端点带，保存 / 导入不带，
 * 后端分不出同一个人的两个窗口。GET 不带（只读请求与编辑锁无关），编辑锁端点不论方法都带。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 't', refreshToken: null, logout: vi.fn(), setTokens: vi.fn() }),
}))
vi.mock('nprogress', () => ({ default: { start: vi.fn(), done: vi.fn(), inc: vi.fn() } }))
vi.mock('element-plus', () => ({ ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn() } }))
vi.mock('@/composables/useVersionCheck', () => ({ versionBridge: { check: vi.fn(), push: vi.fn() } }))
vi.mock('@/utils/clientInstance', () => ({ getClientInstanceId: () => 'window-1' }))

describe('http 请求拦截器：窗口编号', () => {
  let http: typeof import('@/utils/http').default
  let originalAdapter: any
  let sent: Array<{ method: string; url: string; instance: unknown }>

  beforeEach(async () => {
    vi.resetModules()
    http = (await import('@/utils/http')).default
    sent = []
    originalAdapter = http.defaults.adapter
    http.defaults.adapter = async (config: any) => {
      sent.push({ method: String(config.method).toUpperCase(), url: String(config.url), instance: config.headers?.['X-Client-Instance'] })
      return { data: { code: 200, message: 'success', data: {} }, status: 200, statusText: 'OK', headers: {}, config }
    }
  })

  afterEach(() => {
    if (http) http.defaults.adapter = originalAdapter
  })

  it('PUT / POST / PATCH / DELETE 都带；普通 GET 不带；编辑锁端点 GET 也带', async () => {
    await http.put('/api/workpapers/wp-1/checklist-responses', { items: [] }, { _silent: true } as any)
    await http.post('/api/workpapers/wp-1/d4/import-data', {}, { _silent: true } as any)
    await http.patch('/api/workpapers/wp-1/x', {}, { _silent: true } as any)
    await http.delete('/api/workpapers/wp-1/y', { _silent: true } as any)
    await http.get('/api/projects', { _silent: true } as any)
    await http.get('/api/editing-locks/active', { _silent: true } as any)

    expect(sent.map((s) => [s.method, s.instance])).toEqual([
      ['PUT', 'window-1'],
      ['POST', 'window-1'],
      ['PATCH', 'window-1'],
      ['DELETE', 'window-1'],
      ['GET', undefined],
      ['GET', 'window-1'],
    ])
  })
})
