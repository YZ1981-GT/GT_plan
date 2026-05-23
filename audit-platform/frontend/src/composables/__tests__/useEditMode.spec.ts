/**
 * useEditMode — 单测
 * 覆盖 D-2（proposal-remaining-18 task 1.1）：编辑模式过渡动画
 *
 * 测试点：
 * 1. transitioning 默认 false
 * 2. isEditing 切换时 transitioning 立即变 true
 * 3. 300ms 后 transitioning 自动回到 false
 * 4. 连续切换不会丢失最后一次过渡（timer 重置）
 * 5. useEditTransition 独立 helper 同样工作
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, ref, nextTick } from 'vue'
import { useEditMode, useEditTransition, EDIT_TRANSITION_MS } from '../useEditMode'

// vue-router mock：onBeforeRouteLeave 在测试环境下需 stub
vi.mock('vue-router', () => ({
  onBeforeRouteLeave: vi.fn(),
}))

// ElMessageBox mock：避免实际弹窗
vi.mock('element-plus', () => ({
  ElMessageBox: {
    confirm: vi.fn().mockResolvedValue('confirm'),
  },
}))

/** Helper：在 setup 中调用 composable 并返回结果 */
function withSetup<T>(composable: () => T): { result: T; wrapper: ReturnType<typeof mount> } {
  let result!: T
  const Comp = defineComponent({
    setup() {
      result = composable()
      return {}
    },
    template: '<div />',
  })
  const wrapper = mount(Comp)
  return { result, wrapper }
}

describe('useEditMode — D-2 编辑模式过渡（proposal-remaining-18 task 1.1）', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('EDIT_TRANSITION_MS 常量等于 300（与 CSS 动画时长一致）', () => {
    expect(EDIT_TRANSITION_MS).toBe(300)
  })

  it('初始状态 transitioning 为 false', () => {
    const { result } = withSetup(() => useEditMode())
    expect(result.transitioning.value).toBe(false)
  })

  it('enterEdit() 切换后 transitioning 立即为 true，300ms 后自动恢复 false', async () => {
    const { result } = withSetup(() => useEditMode())
    expect(result.isEditing.value).toBe(false)
    expect(result.transitioning.value).toBe(false)

    result.enterEdit()
    await nextTick() // watch 触发
    expect(result.isEditing.value).toBe(true)
    expect(result.transitioning.value).toBe(true)

    // 推进 299ms — 仍在过渡中
    vi.advanceTimersByTime(299)
    expect(result.transitioning.value).toBe(true)

    // 再推进 1ms（累计 300ms）— 过渡结束
    vi.advanceTimersByTime(1)
    expect(result.transitioning.value).toBe(false)
  })

  it('exitEdit(true) 强制退出 → transitioning 触发 → 300ms 后恢复', async () => {
    const { result } = withSetup(() => useEditMode({ initialEditing: true }))
    expect(result.isEditing.value).toBe(true)

    await result.exitEdit(true)
    await nextTick()
    expect(result.isEditing.value).toBe(false)
    expect(result.transitioning.value).toBe(true)

    vi.advanceTimersByTime(EDIT_TRANSITION_MS)
    expect(result.transitioning.value).toBe(false)
  })

  it('连续切换：timer 被重置，最终 300ms 后回 false', async () => {
    const { result } = withSetup(() => useEditMode())

    result.enterEdit()
    await nextTick()
    vi.advanceTimersByTime(150)
    expect(result.transitioning.value).toBe(true)

    // 在过渡中再次切换 → timer 重置
    await result.exitEdit(true)
    await nextTick()
    expect(result.transitioning.value).toBe(true)

    // 仅推进 200ms（距离最后切换 < 300ms）
    vi.advanceTimersByTime(200)
    expect(result.transitioning.value).toBe(true)

    // 再推进 100ms（累计 300ms 自最后一次切换）
    vi.advanceTimersByTime(100)
    expect(result.transitioning.value).toBe(false)
  })

  it('保留原有 API：isEditing/isDirty/enterEdit/exitEdit/markDirty/clearDirty 不变', () => {
    const { result } = withSetup(() => useEditMode())
    expect(result.isEditing).toBeDefined()
    expect(result.isDirty).toBeDefined()
    expect(result.transitioning).toBeDefined()
    expect(typeof result.enterEdit).toBe('function')
    expect(typeof result.exitEdit).toBe('function')
    expect(typeof result.markDirty).toBe('function')
    expect(typeof result.clearDirty).toBe('function')

    expect(result.isEditing.value).toBe(false)
    expect(result.isDirty.value).toBe(false)

    result.markDirty()
    expect(result.isDirty.value).toBe(true)
    result.clearDirty()
    expect(result.isDirty.value).toBe(false)
  })
})

describe('useEditTransition — 独立过渡 helper（用于 WorkpaperEditor editLock.isMine）', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('source ref 切换时 transitioning 进入 true → 300ms 后回 false', async () => {
    const source = ref(false)
    const { result } = withSetup(() => useEditTransition(source))

    expect(result.transitioning.value).toBe(false)

    source.value = true
    await nextTick()
    expect(result.transitioning.value).toBe(true)

    vi.advanceTimersByTime(EDIT_TRANSITION_MS)
    expect(result.transitioning.value).toBe(false)
  })

  it('反向切换（true → false）也触发过渡', async () => {
    const source = ref(true)
    const { result } = withSetup(() => useEditTransition(source))

    expect(result.transitioning.value).toBe(false)

    source.value = false
    await nextTick()
    expect(result.transitioning.value).toBe(true)

    vi.advanceTimersByTime(EDIT_TRANSITION_MS)
    expect(result.transitioning.value).toBe(false)
  })
})
