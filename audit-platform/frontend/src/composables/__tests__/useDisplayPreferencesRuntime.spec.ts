/**
 * 账号偏好运行时安装测试
 *
 * spec: platform-global-display-settings-closure 任务 4（design §3、§4.1）
 * 这里只验「运行时能装上、按账号加载、把四档字号与密度写到 documentElement」；
 * DefaultLayout 接线、真实 Element Plus computedStyle 分别属于任务 5 与 A-V①。
 *
 * Validates: Requirements AC-04（按 userId 加载）、AC-08 的根变量部分
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn() }))
vi.mock('@/services/displayPreferencesApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/displayPreferencesApi')>()),
  getDisplayPreferences: (...args: unknown[]) => apiMock.get(...args),
  patchDisplayPreferences: (...args: unknown[]) => apiMock.patch(...args),
}))

type RuntimeModule = typeof import('@/composables/useDisplayPreferencesRuntime')
type StoreModule = typeof import('@/stores/displayPrefs')
type AuthModule = typeof import('@/stores/auth')

let runtimeModule: RuntimeModule
let prefs: ReturnType<StoreModule['useDisplayPrefsStore']>
let auth: ReturnType<AuthModule['useAuthStore']>
let piniaModule: typeof import('pinia')

function rootVar(name: string): string {
  return document.documentElement.style.getPropertyValue(name)
}

beforeEach(async () => {
  apiMock.get.mockReset()
  apiMock.patch.mockReset()
  apiMock.get.mockResolvedValue({ font_size: 'sm', density: 'default', revision: 1 })
  apiMock.patch.mockImplementation(async () => ({ revision: 2 }))
  localStorage.clear()
  document.documentElement.removeAttribute('style')
  delete document.documentElement.dataset.gtFontSize
  delete document.documentElement.dataset.gtDensity

  vi.resetModules()
  piniaModule = await import('pinia')
  piniaModule.setActivePinia(piniaModule.createPinia())
  runtimeModule = await import('@/composables/useDisplayPreferencesRuntime')
  const storeModule = await import('@/stores/displayPrefs')
  const authModule = await import('@/stores/auth')
  prefs = storeModule.useDisplayPrefsStore()
  auth = authModule.useAuthStore()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useDisplayPreferencesRuntime', () => {
  it('没有激活的 Pinia 时给出明确错误', () => {
    piniaModule.setActivePinia(undefined)
    expect(() => runtimeModule.useDisplayPreferencesRuntime()).toThrow(/Pinia/)
  })

  it('安装后把默认字号与密度写到 documentElement（sm=12px、标准密度）', async () => {
    const handle = runtimeModule.useDisplayPreferencesRuntime()
    await Promise.resolve()

    expect(rootVar('--gt-display-font-size')).toBe('12px')
    expect(rootVar('--wp-font-size')).toBe('12px')
    expect(rootVar('--gt-table-row-height')).toBe('40px')
    expect(rootVar('--gt-table-cell-padding-x')).toBe('12px')
    expect(rootVar('--gt-table-cell-padding-y')).toBe('8px')
    expect(document.documentElement.dataset.gtFontSize).toBe('12px')
    expect(document.documentElement.dataset.gtDensity).toBe('default')
    expect(handle.fontStyle.value).toEqual({ '--wp-font-size': '12px' })
  })

  it('四档字号与三档密度逐一写进根变量', async () => {
    const handle = runtimeModule.useDisplayPreferencesRuntime()
    await Promise.resolve()

    for (const [size, px] of [['xs', '11px'], ['sm', '12px'], ['md', '13px'], ['lg', '14px']] as const) {
      prefs.setFontSize(size)
      await Promise.resolve()
      expect(rootVar('--gt-display-font-size')).toBe(px)
      expect(handle.fontStyle.value['--wp-font-size']).toBe(px)
    }

    for (const [density, rowHeight] of [['compact', '32px'], ['default', '40px'], ['comfortable', '48px']] as const) {
      prefs.setDensity(density)
      await Promise.resolve()
      expect(rootVar('--gt-table-row-height')).toBe(rowHeight)
      expect(document.documentElement.dataset.gtDensity).toBe(density)
    }
  })

  it('同一个 Pinia 上重复调用只安装一次', () => {
    const first = runtimeModule.useDisplayPreferencesRuntime()
    const second = runtimeModule.useDisplayPreferencesRuntime()
    expect(second).toBe(first)
  })

  it('按 authStore.userId 加载偏好，账号变化即重新加载', async () => {
    auth.user = { id: 'user-a', username: 'a', role: 'auditor' } as never
    runtimeModule.useDisplayPreferencesRuntime()
    await Promise.resolve()
    await Promise.resolve()

    expect(apiMock.get).toHaveBeenCalledTimes(1)
    expect(prefs.ownerUserId).toBe('user-a')

    auth.user = { id: 'user-b', username: 'b', role: 'auditor' } as never
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()

    expect(prefs.ownerUserId).toBe('user-b')
    expect(apiMock.get).toHaveBeenCalledTimes(2)
  })

  it('未登录（userId 为空）不请求偏好', async () => {
    auth.user = null as never
    runtimeModule.useDisplayPreferencesRuntime()
    await Promise.resolve()
    await Promise.resolve()

    expect(apiMock.get).not.toHaveBeenCalled()
    expect(prefs.ownerUserId).toBeNull()
  })
})
