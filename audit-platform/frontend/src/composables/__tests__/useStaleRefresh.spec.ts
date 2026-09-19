/**
 * useStaleRefresh.spec.ts — stale 刷新 composable 测试（任务 14.2 + 15.3）
 *
 * Spec:   .kiro/specs/global-refinement-v5-closure/ Tasks 14.2, 15.3
 *
 * Property 2: 项目级事件分发不变量（fast-check）
 * 单测: mode='prompt' 匹配→isStale / 不匹配→忽略 / refresh()→isStale 回 false
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import * as fc from 'fast-check'
import { ref, nextTick } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent } from 'vue'

import { useStaleRefresh } from '../useStaleRefresh'
import { eventBus } from '@/utils/eventBus'

/** Helper: mount composable in component context for lifecycle hooks */
function withSetup<T>(fn: () => T): { result: T; wrapper: ReturnType<typeof mount> } {
  let result!: T
  const Comp = defineComponent({
    setup() { result = fn(); return {} },
    template: '<div/>',
  })
  const wrapper = mount(Comp)
  return { result, wrapper }
}

// Feature: global-refinement-v5-closure, Property 2
describe('Property 2: 项目级事件分发不变量', () => {
  afterEach(() => { eventBus.all.clear() })

  it('匹配 projectId 则触发 onRefresh 或 isStale=true，不匹配则忽略', () => {
    const eventNames = fc.constantFrom(
      'trial-balance:updated',
      'adjustment:saved',
      'dataset:activated',
      'year:changed',
      'project:updated',
    ) as fc.Arbitrary<any>
    const projectIds = fc.string({ minLength: 4, maxLength: 12 })

    fc.assert(
      fc.property(eventNames, projectIds, projectIds, (eventName, currentPid, eventPid) => {
        const projectId = ref(currentPid)
        const onRefresh = vi.fn()

        const { result, wrapper } = withSetup(() =>
          useStaleRefresh(projectId, { mode: 'prompt', onRefresh }),
        )

        // Emit event with eventPid
        eventBus.emit(eventName, { projectId: eventPid })

        if (currentPid === eventPid) {
          // 匹配：mode='prompt' → isStale=true
          expect(result.isStale.value).toBe(true)
        } else {
          // 不匹配：忽略
          expect(result.isStale.value).toBe(false)
          expect(onRefresh).not.toHaveBeenCalled()
        }

        wrapper.unmount()
        eventBus.all.clear()
      }),
      { numRuns: 5 },
    )
  })
})

// Task 15.3: 接入页 stale 提示单测
describe('useStaleRefresh — Task 15.3 接入页 stale 提示', () => {
  afterEach(() => { eventBus.all.clear() })

  it('派发匹配 projectId 的事件 → mode="prompt" 时 isStale=true', () => {
    const projectId = ref('proj-001')
    const onRefresh = vi.fn()

    const { result, wrapper } = withSetup(() =>
      useStaleRefresh(projectId, { mode: 'prompt', onRefresh }),
    )

    eventBus.emit('trial-balance:updated', { projectId: 'proj-001' })

    expect(result.isStale.value).toBe(true)
    expect(onRefresh).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('派发不匹配 projectId → isStale 保持 false', () => {
    const projectId = ref('proj-001')
    const onRefresh = vi.fn()

    const { result, wrapper } = withSetup(() =>
      useStaleRefresh(projectId, { mode: 'prompt', onRefresh }),
    )

    eventBus.emit('adjustment:saved', { projectId: 'proj-OTHER' })

    expect(result.isStale.value).toBe(false)
    expect(onRefresh).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('调 refresh() → isStale 回 false', async () => {
    const projectId = ref('proj-001')
    const onRefresh = vi.fn().mockResolvedValue(undefined)

    const { result, wrapper } = withSetup(() =>
      useStaleRefresh(projectId, { mode: 'prompt', onRefresh }),
    )

    // 先标 stale
    eventBus.emit('trial-balance:updated', { projectId: 'proj-001' })
    expect(result.isStale.value).toBe(true)

    // 调 refresh
    await result.refresh()
    expect(result.isStale.value).toBe(false)
    expect(onRefresh).toHaveBeenCalled()
    wrapper.unmount()
  })

  it('mode="auto" + 匹配 → 直接调 onRefresh', () => {
    const projectId = ref('proj-002')
    const onRefresh = vi.fn()

    const { result, wrapper } = withSetup(() =>
      useStaleRefresh(projectId, { mode: 'auto', onRefresh }),
    )

    eventBus.emit('project:updated', { projectId: 'proj-002' })

    expect(onRefresh).toHaveBeenCalled()
    wrapper.unmount()
  })
})
