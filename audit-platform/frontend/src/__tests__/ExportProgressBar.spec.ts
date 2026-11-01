/**
 * ExportProgressBar — 批量导出 SSE 进度组件测试
 * Validates: requirements.md §三 C-3
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const { getStatus } = vi.hoisted(() => ({ getStatus: vi.fn() }))
vi.mock('@/services/workpaperApi', () => ({ getWorkpaperPackExportStatus: getStatus }))
import { eventBus } from '@/utils/eventBus'
import ExportProgressBar from '@/components/workpaper/ExportProgressBar.vue'

describe('ExportProgressBar', () => {
  beforeEach(() => {
    eventBus.all.clear()
    getStatus.mockReset().mockImplementation(() => new Promise(() => {}))
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


describe('ExportProgressBar 状态恢复', () => {
  it('SSE 事件缺失时从权威状态端点恢复完成结果', async () => {
    getStatus.mockResolvedValueOnce({
      task_id: 'task-poll', status: 'complete', done: 6, total: 6, percent: 100,
      download_url: '/api/exports/task-poll', error: null,
    })
    const wrapper = mount(ExportProgressBar, {
      props: { taskId: 'task-poll', total: 6 },
    })
    await flushPromises()

    expect(getStatus).toHaveBeenCalledWith('task-poll')
    expect(wrapper.text()).toContain('6 / 6')
    expect(wrapper.text()).toContain('下载 ZIP')
    expect(wrapper.emitted('complete')?.[0]?.[0]).toBe('/api/exports/task-poll')
    wrapper.unmount()
  })
})
