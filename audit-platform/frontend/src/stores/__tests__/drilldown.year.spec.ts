/**
 * 穿透 store 的年度（spec post-push-residual-defect-closure 6.5.3）：
 * 原先初值是今年 ⇒ 页面没解析出年度时，翻页 / 筛选照样按今年取数；现在初值 null，缺项目 / 缺年度不取数。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const get = vi.fn()
vi.mock('@/utils/http', () => ({ default: { get: (...a: unknown[]) => get(...a) } }))

import { useDrilldownStore } from '@/stores/drilldown'

beforeEach(() => {
  setActivePinia(createPinia())
  get.mockReset().mockResolvedValue({ data: { items: [], total: 0 } })
})

describe('drilldown store 年度', () => {
  it('初值 null（不是今年）', () => {
    expect(useDrilldownStore().year).toBeNull()
  })

  it('没设项目与年度：四个取数都不发', async () => {
    const s = useDrilldownStore()
    await s.fetchBalance()
    await s.fetchLedger()
    await s.fetchAuxBalance()
    await s.fetchAuxLedger()
    expect(get).not.toHaveBeenCalled()
  })

  it('页面解析不出年度时 setProject(pid, null)：之前的年度被清掉，翻页不再按旧年度取', async () => {
    const s = useDrilldownStore()
    s.setProject('p1', 2024)
    s.setProject('p1', null)
    await s.fetchBalance()
    expect(get).not.toHaveBeenCalled()
  })

  it('项目与年度齐了：按该年度取余额', async () => {
    const s = useDrilldownStore()
    s.setProject('p1', 2025)
    await s.fetchBalance()
    expect(get).toHaveBeenCalledWith('/api/projects/p1/drilldown/balance', { params: expect.objectContaining({ year: 2025 }) })
  })
})
