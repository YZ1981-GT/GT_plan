/**
 * useH4DualMode — 单元测试
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { useH4DualMode } from '../useH4DualMode'

describe('useH4DualMode', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({ healthy: true }),
    })))
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('默认 html，OO 健康检查后可切换', async () => {
    const autoSave = vi.fn(async () => {})
    const reloadAll = vi.fn(async () => {})
    const api = useH4DualMode({
      wpId: ref('wp-h4'),
      autoSave,
      reloadAll,
    })
    expect(api.currentMode.value).toBe('html')
    await api.checkOoHealth()
    expect(api.isOoAvailable.value).toBe(true)
    await api.switchMode('onlyoffice')
    expect(autoSave).toHaveBeenCalled()
    expect(api.currentMode.value).toBe('onlyoffice')
    expect(localStorage.getItem('h4-dual-mode:wp-h4')).toBe('onlyoffice')
    await api.switchMode('html')
    expect(reloadAll).toHaveBeenCalled()
    expect(api.currentMode.value).toBe('html')
  })

  it('OO 不可用时拒绝切到 onlyoffice', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false })))
    const api = useH4DualMode({ wpId: ref('wp-h4') })
    await api.checkOoHealth()
    expect(api.isOoAvailable.value).toBe(false)
    await api.switchMode('onlyoffice')
    expect(api.currentMode.value).toBe('html')
  })
})
