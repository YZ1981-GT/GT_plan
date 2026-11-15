import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useTableDensityMetrics } from '../useTableDensityMetrics'

describe('useTableDensityMetrics', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('从显示偏好映射三档数字行高与表头高度', () => {
    const prefs = useDisplayPrefsStore()
    const metrics = useTableDensityMetrics()

    expect(metrics.density.value).toBe('default')
    expect(metrics.rowHeight.value).toBe(40)
    expect(metrics.estimatedRowHeight.value).toBe(40)
    expect(metrics.headerHeight.value).toBe(40)

    prefs.setDensity('compact')
    expect(metrics.rowHeight.value).toBe(32)
    expect(metrics.headerHeight.value).toBe(32)

    prefs.setDensity('comfortable')
    expect(metrics.rowHeight.value).toBe(48)
    expect(metrics.headerHeight.value).toBe(48)
  })

  it('字号或密度变化都会生成新的虚拟表重挂载键', () => {
    const prefs = useDisplayPrefsStore()
    const metrics = useTableDensityMetrics()
    const initial = metrics.remountKey.value

    prefs.setDensity('compact')
    const compact = metrics.remountKey.value
    expect(compact).not.toBe(initial)

    prefs.setFontSize('lg')
    expect(metrics.remountKey.value).not.toBe(compact)
  })
})
