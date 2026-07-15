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
    localStorage.clear()
    getMock.mockClear()
    getMock.mockResolvedValue({ data: { data: { healthy: true } } })
  })

  it('persists mode per wpId+sheet', async () => {
    const { useE1DualMode } = await import('../useE1DualMode')
    const wpId = ref('wp-1')
    const sheetName = ref('E1-31')
    const dm = useE1DualMode({ wpId, sheetName })
    await dm.checkOoHealth()
    expect(dm.isOoAvailable.value).toBe(true)
    expect(dm.currentMode.value).toBe('html')

    await dm.switchMode('onlyoffice')
    expect(dm.currentMode.value).toBe('onlyoffice')
    expect(localStorage.getItem('e1-dual-mode:wp-1:E1-31')).toBe('onlyoffice')

    const dm2 = useE1DualMode({ wpId, sheetName })
    expect(dm2.currentMode.value).toBe('onlyoffice')
  })

  it('maps legacy structured storage to html', async () => {
    localStorage.setItem('e1-dual-mode:wp-2:E1-26', 'structured')
    const { useE1DualMode } = await import('../useE1DualMode')
    const dm = useE1DualMode({
      wpId: ref('wp-2'),
      sheetName: ref('E1-26'),
    })
    expect(dm.currentMode.value).toBe('html')
    expect(dm.isStructured.value).toBe(true)
  })

  it('blocks onlyoffice when OO unhealthy', async () => {
    getMock.mockResolvedValue({ data: { data: { healthy: false } } })
    const { useE1DualMode } = await import('../useE1DualMode')
    const dm = useE1DualMode({
      wpId: ref('wp-3'),
      sheetName: ref('E1-29'),
    })
    await dm.checkOoHealth()
    expect(dm.isOoAvailable.value).toBe(false)
    await dm.switchMode('onlyoffice')
    expect(dm.currentMode.value).toBe('html')
  })
})
