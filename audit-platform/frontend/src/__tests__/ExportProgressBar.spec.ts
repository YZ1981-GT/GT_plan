/**
 * ExportProgressBar — 批量导出 SSE 进度组件测试
 * Validates: requirements.md §三 C-3
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { eventBus } from '@/utils/eventBus'
import ExportProgressBar from '@/components/workpaper/ExportProgressBar.vue'

describe('ExportProgressBar', () => {
  beforeEach(() => {
    eventBus.all.clear()
  })

  it('renders initial pending state with total', () => {
    const wrapper = mount(ExportProgressBar, {
      props: { taskId: 'task-1', total: 5 },
    })
    expect(wrapper.text()).toContain('0 / 5')
  })

  it('updates progress on export.progress events for matching task_id', async () => {
    const wrapper = mount(ExportProgressBar, {
      props: { taskId: 'task-2', total: 4 },
    })

    eventBus.emit('sse:sync-event', {
      event_type: 'export.progress',
      project_id: 'p-1',
      extra: { task_id: 'task-2', done: 2, total: 4, percent: 50 },
    } as any)
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('2 / 4')
  })

  it('ignores events for different task_id', async () => {
    const wrapper = mount(ExportProgressBar, {
      props: { taskId: 'task-3', total: 4 },
    })

    eventBus.emit('sse:sync-event', {
      event_type: 'export.progress',
      project_id: 'p-1',
      extra: { task_id: 'OTHER', done: 9, total: 9, percent: 100 },
    } as any)
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('0 / 4')
  })

  it('emits complete event with download_url on export.complete', async () => {
    const wrapper = mount(ExportProgressBar, {
      props: { taskId: 'task-4', total: 3 },
    })

    eventBus.emit('sse:sync-event', {
      event_type: 'export.complete',
      project_id: 'p-1',
      extra: {
        task_id: 'task-4',
        done: 3,
        total: 3,
        download_url: '/api/exports/task-4',
      },
    } as any)
    await wrapper.vm.$nextTick()

    const emitted = wrapper.emitted('complete')
    expect(emitted).toBeTruthy()
    expect(emitted?.[0]?.[0]).toBe('/api/exports/task-4')
  })

  it('emits failed event on export.failed', async () => {
    const wrapper = mount(ExportProgressBar, {
      props: { taskId: 'task-5', total: 2 },
    })

    eventBus.emit('sse:sync-event', {
      event_type: 'export.failed',
      project_id: 'p-1',
      extra: { task_id: 'task-5', error: 'db unavailable' },
    } as any)
    await wrapper.vm.$nextTick()

    const emitted = wrapper.emitted('failed')
    expect(emitted).toBeTruthy()
    expect(emitted?.[0]?.[0]).toBe('db unavailable')
    expect(wrapper.text()).toContain('db unavailable')
  })
})
