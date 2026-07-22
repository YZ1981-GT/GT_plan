/**
 * useE1DualMode — 双模式扩展冒烟
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const getMock = vi.fn(async () => ({ data: { data: { healthy: true } } }))

vi.mock('@/utils/http', () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
  },
}))

describe('useE1DualMode', () => {
  beforeEach(() => {
    getMock.mockClear()
    getMock.mockResolvedValue({ data: { data: { healthy: true } } })
  })

  it('defaults to structured mode', async () => {
    const { useE1DualMode } = await import('../useE1DualMode')
    const dm = useE1DualMode({ wpId: ref('wp-1') })
    expect(dm.currentMode.value).toBe('structured')
    expect(dm.isStructured.value).toBe(true)
  })

  it('checkOoHealth reflects health endpoint', async () => {
    const { useE1DualMode } = await import('../useE1DualMode')
    const dm = useE1DualMode({ wpId: ref('wp-2') })
    await dm.checkOoHealth()
    expect(dm.isOoAvailable.value).toBe(true)
  })

  it('allows online-edit when OO healthy', async () => {
    const { useE1DualMode } = await import('../useE1DualMode')
    const dm = useE1DualMode({ wpId: ref('wp-3') })
    await dm.checkOoHealth()
    dm.switchMode('online-edit')
    expect(dm.currentMode.value).toBe('online-edit')
    expect(dm.isOnlineEdit.value).toBe(true)
  })

  it('blocks online-edit when OO unhealthy', async () => {
    getMock.mockResolvedValue({ data: { data: { healthy: false } } })
    const { useE1DualMode } = await import('../useE1DualMode')
    const dm = useE1DualMode({ wpId: ref('wp-4') })
    await dm.checkOoHealth()
    expect(dm.isOoAvailable.value).toBe(false)
    dm.switchMode('online-edit')
    expect(dm.currentMode.value).toBe('structured')
  })
})
