import { nextTick, ref } from 'vue'
import { describe, expect, it } from 'vitest'
import { useMountOnFirstOpen } from '../useMountOnFirstOpen'

describe('useMountOnFirstOpen', () => {
  it('初始关闭时不挂载，首次打开后永久保持挂载', async () => {
    const visible = ref(false)
    const mounted = useMountOnFirstOpen(visible)
    expect(mounted.value).toBe(false)
    visible.value = true
    await nextTick()
    expect(mounted.value).toBe(true)
    visible.value = false
    await nextTick()
    expect(mounted.value).toBe(true)
  })

  it('初始已打开时立即挂载', () => {
    expect(useMountOnFirstOpen(ref(true)).value).toBe(true)
  })
})
