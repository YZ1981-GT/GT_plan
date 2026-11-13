/**
 * 显示偏好 API 客户端合同测试
 *
 * spec: platform-global-display-settings-closure 任务 4（design §3）
 * 约束：请求必须带 /api 前缀与后台/静默/不去重标记（偏好同步不得触发全局错误提示，
 * 也不得被平台 GET 去重取消）；409 必须转成携带服务端 current 的可恢复错误。
 *
 * Validates: Requirements AC-01（线格式往返）、AC-04、AC-09（409 冲突载荷）
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'

const mocked = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn() }))
vi.mock('@/utils/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/utils/http')>()),
  default: mocked,
}))

type ApiModule = typeof import('@/services/displayPreferencesApi')

// 全局 setup（src/test/setup.ts）会先 import displayPrefs store，连带把本模块和真实 http
// 装进模块缓存；不先 resetModules 就拿不到上面的 http mock（会真打 XHR）。
let api: ApiModule
let DISPLAY_PREFERENCES_URL: ApiModule['DISPLAY_PREFERENCES_URL']
let DisplayPreferencesRevisionConflict: ApiModule['DisplayPreferencesRevisionConflict']
let getDisplayPreferences: ApiModule['getDisplayPreferences']
let patchDisplayPreferences: ApiModule['patchDisplayPreferences']

function conflictError(data: unknown): Error & { response: { status: number; data: unknown } } {
  const error = new Error('conflict') as Error & { response: { status: number; data: unknown } }
  error.response = { status: 409, data }
  return error
}

describe('displayPreferencesApi', () => {
  beforeEach(async () => {
    mocked.get.mockReset()
    mocked.patch.mockReset()
    vi.resetModules()
    api = await import('@/services/displayPreferencesApi')
    ;({
      DISPLAY_PREFERENCES_URL,
      DisplayPreferencesRevisionConflict,
      getDisplayPreferences,
      patchDisplayPreferences,
    } = api)
  })

  it('http mock 已装上（否则下面的断言会变成真实网络调用）', async () => {
    mocked.get.mockResolvedValue({ data: {} })
    await getDisplayPreferences()
    expect(mocked.get).toHaveBeenCalledTimes(1)
  })

  it('端点带 /api 前缀', () => {
    expect(DISPLAY_PREFERENCES_URL).toBe('/api/users/me/display-preferences')
  })

  it('GET 归一 snake_case 响应并透传 signal 与后台标记', async () => {
    mocked.get.mockResolvedValue({
      data: { font_size: 'lg', decimals: 999, amount_unit_override: 'wan', revision: 5 },
    })
    const controller = new AbortController()
    const result = await getDisplayPreferences(controller.signal)

    expect(result.fontSize).toBe('lg')
    expect(result.amountUnitOverride).toBe('wan')
    expect(result.decimals).toBe(2)
    expect(result.revision).toBe(5)

    const [url, config] = mocked.get.mock.calls[0]
    expect(url).toBe(DISPLAY_PREFERENCES_URL)
    expect(config.signal).toBe(controller.signal)
    expect(config._background).toBe(true)
    expect(config._dedupe).toBe(false)
    expect(config._silent).toBe(true)
  })

  it('PATCH 发送 snake_case 线格式并归一响应', async () => {
    mocked.patch.mockResolvedValue({ data: { font_size: 'md', revision: 2 } })
    const result = await patchDisplayPreferences({ baseRevision: 1, fontSize: 'md' })

    expect(result.fontSize).toBe('md')
    expect(result.revision).toBe(2)
    const [url, body, config] = mocked.patch.mock.calls[0]
    expect(url).toBe(DISPLAY_PREFERENCES_URL)
    expect(body).toEqual({ base_revision: 1, font_size: 'md' })
    expect(config._dedupe).toBe(false)
    expect(config._silent).toBe(true)
  })

  it('PATCH 跟随项目单位时线格式含显式 null', async () => {
    mocked.patch.mockResolvedValue({ data: { revision: 3 } })
    await patchDisplayPreferences({ baseRevision: 2, amountUnitOverride: null })

    const body = mocked.patch.mock.calls[0][1] as Record<string, unknown>
    expect('amount_unit_override' in body).toBe(true)
    expect(body.amount_unit_override).toBeNull()
  })

  it('409 带 current 时抛出携带归一 current 的冲突错误', async () => {
    mocked.patch.mockRejectedValue(conflictError({
      code: 'DISPLAY_PREFERENCES_REVISION_CONFLICT',
      current: { font_size: 'xs', revision: 11, decimals: 999 },
    }))

    await expect(patchDisplayPreferences({ baseRevision: 1, fontSize: 'md' }))
      .rejects.toBeInstanceOf(DisplayPreferencesRevisionConflict)

    try {
      await patchDisplayPreferences({ baseRevision: 1, fontSize: 'md' })
      expect.unreachable('应抛出冲突错误')
    } catch (error) {
      expect(error).toBeInstanceOf(DisplayPreferencesRevisionConflict)
      const conflict = error as InstanceType<ApiModule['DisplayPreferencesRevisionConflict']>
      expect(conflict.current.revision).toBe(11)
      expect(conflict.current.fontSize).toBe('xs')
      // 冲突载荷同样经过范围保护
      expect(conflict.current.decimals).toBe(2)
    }
  })

  it('409 不带 current 时原样抛出，不伪造冲突载荷', async () => {
    const raw = conflictError({ code: 'SOMETHING_ELSE' })
    mocked.patch.mockRejectedValue(raw)

    await expect(patchDisplayPreferences({ baseRevision: 1, fontSize: 'md' })).rejects.toBe(raw)
  })

  it('其他错误原样抛出', async () => {
    const raw = new Error('network down')
    mocked.patch.mockRejectedValue(raw)
    await expect(patchDisplayPreferences({ baseRevision: 1, fontSize: 'md' })).rejects.toBe(raw)

    mocked.get.mockRejectedValue(raw)
    await expect(getDisplayPreferences()).rejects.toBe(raw)
  })
})
