/**
 * useF2DualMode unit tests — OO restore must wait for health check
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'

const httpGet = vi.fn()
vi.mock('@/utils/http', () => ({
  default: { get: (...args: unknown[]) => httpGet(...args) },
}))

describe('useF2DualMode', () => {
  beforeEach(() => {
    localStorage.clear()
    httpGet.mockReset()
  })
  afterEach(() => {
    localStorage.clear()
  })

  it('stays on html until OO health confirmed even if localStorage says onlyoffice', async () => {
    localStorage.setItem('f2-dual-mode:wp-1', 'onlyoffice')
    httpGet.mockImplementation(async (url: string) => {
      if (String(url).includes('health')) {
        return { data: { data: { healthy: false } } }
      }
      return { data: { data: {} } }
    })

    const { useF2DualMode } = await import('../useF2DualMode')
    const { mount } = await import('@vue/test-utils')
    const { defineComponent, h } = await import('vue')

    let api: ReturnType<typeof useF2DualMode> | null = null
    const Comp = defineComponent({
      setup() {
        api = useF2DualMode({ wpId: ref('wp-1'), sheetName: ref('八、开发产品F2-10') })
        return () => h('div')
      },
    })
    mount(Comp)
    // Immediately after mount, still html (async restore not done)
    expect(api!.currentMode.value).toBe('html')
    await nextTick()
    await new Promise((r) => setTimeout(r, 30))
    // Health failed → stay html
    expect(api!.currentMode.value).toBe('html')
    expect(api!.isOoAvailable.value).toBe(false)
    expect(localStorage.getItem('f2-dual-mode:wp-1')).toBe('html')
  })

  it('restores onlyoffice only after healthy + config success', async () => {
    localStorage.setItem('f2-dual-mode:wp-1', 'onlyoffice')
    httpGet.mockImplementation(async (url: string) => {
      if (String(url).includes('health')) {
        return { data: { data: { healthy: true } } }
      }
      if (String(url).includes('onlyoffice-config')) {
        return { data: { data: { document: {} } } }
      }
      return { data: {} }
    })

    const { useF2DualMode } = await import('../useF2DualMode')
    const { mount } = await import('@vue/test-utils')
    const { defineComponent, h } = await import('vue')

    let api: ReturnType<typeof useF2DualMode> | null = null
    const Comp = defineComponent({
      setup() {
        api = useF2DualMode({ wpId: ref('wp-1'), sheetName: ref('F2-10') })
        return () => h('div')
      },
    })
    mount(Comp)
    await nextTick()
    await new Promise((r) => setTimeout(r, 30))
    expect(api!.isOoAvailable.value).toBe(true)
    expect(api!.currentMode.value).toBe('onlyoffice')
  })
})
