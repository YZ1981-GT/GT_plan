import { describe, it, expect } from 'vitest'
import { ref, computed } from 'vue'
import { useWorkpaperBrowseMode } from '../useWorkpaperBrowseMode'
import { virtualTextCol } from '../virtualColumnHelpers'

describe('useWorkpaperBrowseMode', () => {
  it('≤30 行不启用虚拟速览', () => {
    const rows = ref(Array.from({ length: 20 }, (_, i) => ({ id: i })))
    const virtualColumns = computed(() => [virtualTextCol('id', 'ID', 60)])
    const { useVirtualScroll } = useWorkpaperBrowseMode({ rows, virtualColumns })
    expect(useVirtualScroll.value).toBe(false)
  })

  it('>30 行启用虚拟速览', () => {
    const rows = ref(Array.from({ length: 35 }, (_, i) => ({ id: i })))
    const virtualColumns = computed(() => [virtualTextCol('id', 'ID', 60)])
    const { useVirtualScroll, browseMode } = useWorkpaperBrowseMode({ rows, virtualColumns })
    expect(useVirtualScroll.value).toBe(true)
    expect(browseMode.value).toBe(true)
  })
})
