/**
 * useNoteStale — 单测（Sprint 3 Task 3.6）
 *
 * Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 3 Task 3.6
 * Reqs:   R2.1 验收：章节列表红点 + tooltip + dismiss
 *
 * 验证：
 * 1. SSE 事件 ledger.dataset_activated 触发后 staleSections 更新（兼容大写枚举）
 * 2. payload.extra.affected_note_sections 给定时仅标对应章节
 * 3. dismissStale 仅本地清理；console.info 提示后端端点未实现
 * 4. projectId 切换 → 自动清空（避免跨项目串台）
 *
 * **Validates: Requirements R2.1**
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, ref, nextTick, type Ref } from 'vue'

import { useNoteStale, NOTE_STALE_ALL } from '../useNoteStale'
import { eventBus, type SyncEventPayload } from '@/utils/eventBus'

/** Helper: 在 setup 中调用 composable 并返回结果 */
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

describe('useNoteStale — Sprint 3 Task 3.6', () => {
  let projectId: Ref<string>

  beforeEach(() => {
    projectId = ref('proj-A')
  })

  afterEach(() => {
    // 清理 eventBus 订阅，避免测试间互相污染
    eventBus.all.clear()
  })

  it('SSE ledger.dataset_activated 事件 → 全部章节标 stale (NOTE_STALE_ALL)', async () => {
    const { result, wrapper } = withSetup(() => useNoteStale(projectId))

    expect(result.staleSections.value.size).toBe(0)
    expect(result.hasAny.value).toBe(false)

    eventBus.emit('sse:sync-event', {
      event_type: 'ledger.dataset_activated',
      project_id: 'proj-A',
    } as SyncEventPayload)
    await nextTick()

    expect(result.staleSections.value.has(NOTE_STALE_ALL)).toBe(true)
    expect(result.hasAny.value).toBe(true)
    // 任何章节查询都应返回 true
    expect(result.isStale('五、6')).toBe(true)
    expect(result.isStale('八、固定资产')).toBe(true)

    wrapper.unmount()
  })

  it('payload.extra.affected_note_sections 给定 → 仅标对应章节，不影响其他', async () => {
    const { result, wrapper } = withSetup(() => useNoteStale(projectId))

    eventBus.emit('sse:sync-event', {
      event_type: 'workpaper.review_passed',
      project_id: 'proj-A',
      extra: { affected_note_sections: ['五、6', '五、7'] },
    } as SyncEventPayload)
    await nextTick()

    expect(result.isStale('五、6')).toBe(true)
    expect(result.isStale('五、7')).toBe(true)
    expect(result.isStale('五、8')).toBe(false)
    expect(result.staleSections.value.has(NOTE_STALE_ALL)).toBe(false)

    wrapper.unmount()
  })

  it('dismissStale 仅本地清理 + console.info 提示端点未实现', async () => {
    const { result, wrapper } = withSetup(() => useNoteStale(projectId))
    const infoSpy = vi.spyOn(console, 'info').mockImplementation(() => {})

    result.markStale('五、6')
    expect(result.isStale('五、6')).toBe(true)

    result.dismissStale('五、6')
    expect(result.isStale('五、6')).toBe(false)
    expect(infoSpy).toHaveBeenCalled()
    // 提示信息中应包含 dismissStale 标识 + 章节号
    const firstCallArgs = infoSpy.mock.calls[0]
    expect(firstCallArgs.some(arg => String(arg).includes('dismissStale'))).toBe(true)
    expect(firstCallArgs.some(arg => String(arg).includes('五、6'))).toBe(true)

    infoSpy.mockRestore()
    wrapper.unmount()
  })

  it('projectId 切换 → 自动清空（避免跨项目串台）', async () => {
    const { result, wrapper } = withSetup(() => useNoteStale(projectId))

    result.markStale('五、6')
    result.markStale('五、7')
    expect(result.staleSections.value.size).toBe(2)

    projectId.value = 'proj-B'
    await nextTick()

    expect(result.staleSections.value.size).toBe(0)
    expect(result.hasAny.value).toBe(false)

    wrapper.unmount()
  })

  it('dismissAll 清空全部本地标记', async () => {
    const { result, wrapper } = withSetup(() => useNoteStale(projectId))
    const infoSpy = vi.spyOn(console, 'info').mockImplementation(() => {})

    result.markStale('五、6')
    result.markStale('五、7')
    result.markStale('五、8')
    expect(result.staleSections.value.size).toBe(3)

    result.dismissAll()
    expect(result.staleSections.value.size).toBe(0)
    expect(result.hasAny.value).toBe(false)
    expect(infoSpy).toHaveBeenCalled()

    infoSpy.mockRestore()
    wrapper.unmount()
  })

  it('其他项目的 SSE 事件被过滤（project_id 不匹配）', async () => {
    const { result, wrapper } = withSetup(() => useNoteStale(projectId))

    eventBus.emit('sse:sync-event', {
      event_type: 'ledger.dataset_activated',
      project_id: 'proj-OTHER',
    } as SyncEventPayload)
    await nextTick()

    expect(result.staleSections.value.size).toBe(0)
    wrapper.unmount()
  })
})
