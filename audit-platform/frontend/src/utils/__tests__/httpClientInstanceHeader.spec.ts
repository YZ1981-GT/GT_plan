/**
 * 写请求带窗口编号 X-Client-Instance（spec workpaper-multi-window-lock-gaps R2.6 / R3.4 / R5.4）。
 *
 * 后端按它判断底稿保存 / 导入是不是持锁的那个窗口发的；原先只有编辑锁端点带，保存 / 导入不带，
 * 后端分不出同一个人的两个窗口。普通 GET 不带（只读请求与编辑锁无关）；编辑锁端点、取 OnlyOffice 配置
 * （锁在别的窗口时后端给只读配置）不论方法都带。编号没定下来时这几类请求先等认领（复制出来的标签页认领时可能换号）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { inst } = vi.hoisted(() => ({
  inst: {
    id: 'window-1',
    settled: true,
    claim: null as null | { promise: Promise<string>; resolve: (id: string) => void },
  },
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 't', refreshToken: null, logout: vi.fn(), setTokens: vi.fn() }),
}))
vi.mock('nprogress', () => ({ default: { start: vi.fn(), done: vi.fn(), inc: vi.fn() } }))
vi.mock('element-plus', () => ({ ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn() } }))
vi.mock('@/composables/useVersionCheck', () => ({ versionBridge: { check: vi.fn(), push: vi.fn() } }))
vi.mock('@/utils/clientInstance', () => ({
  getClientInstanceId: () => inst.id,
  isClientInstanceSettled: () => inst.settled,
  claimClientInstanceId: () => inst.claim?.promise ?? Promise.resolve(inst.id),
}))

describe('http 请求拦截器：窗口编号', () => {
  let http: typeof import('@/utils/http').default
  let originalAdapter: any
  let sent: Array<{ method: string; url: string; instance: unknown }>

  beforeEach(async () => {
    vi.resetModules()
    inst.id = 'window-1'
    inst.settled = true
    inst.claim = null
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

  it('PUT / POST / PATCH / DELETE 都带；普通 GET 不带；编辑锁端点与 OnlyOffice 配置的 GET 也带', async () => {
    await http.put('/api/workpapers/wp-1/checklist-responses', { items: [] }, { _silent: true } as any)
    await http.post('/api/workpapers/wp-1/d4/import-data', {}, { _silent: true } as any)
    await http.patch('/api/workpapers/wp-1/x', {}, { _silent: true } as any)
    await http.delete('/api/workpapers/wp-1/y', { _silent: true } as any)
    await http.get('/api/projects', { _silent: true } as any)
    await http.get('/api/editing-locks/active', { _silent: true } as any)
    await http.get('/api/workpapers/wp-1/sheets/D4-1/onlyoffice-config', { _silent: true } as any)

    expect(sent.map((s) => [s.method, s.instance])).toEqual([
      ['PUT', 'window-1'],
      ['POST', 'window-1'],
      ['PATCH', 'window-1'],
      ['DELETE', 'window-1'],
      ['GET', undefined],
      ['GET', 'window-1'],
      ['GET', 'window-1'],
    ])
  })

  it('编号没定下来：写请求与 OnlyOffice 配置等认领，按认领后的编号发；普通 GET 不等', async () => {
    inst.settled = false
    inst.id = 'copied-from-tab-a'
    let resolveClaim!: (id: string) => void
    const promise = new Promise<string>((r) => { resolveClaim = r })
    inst.claim = { promise, resolve: resolveClaim }

    const write = http.post('/api/workpapers/wp-1/e1/statement-ocr', {}, { _silent: true } as any)
    const config = http.get('/api/workpapers/wp-1/sheets/D4-1/onlyoffice-config', { _silent: true } as any)
    await http.get('/api/projects', { _silent: true } as any)
    expect(sent.map((s) => s.url)).toEqual(['/api/projects'])

    inst.id = 'fresh-b' // 认领时发现编号被原标签页占着，换了新号
    inst.settled = true
    resolveClaim('fresh-b')
    await Promise.all([write, config])
    expect(sent.slice(1).map((s) => [s.method, s.instance])).toEqual([
      ['POST', 'fresh-b'],
      ['GET', 'fresh-b'],
    ])
  })
})
