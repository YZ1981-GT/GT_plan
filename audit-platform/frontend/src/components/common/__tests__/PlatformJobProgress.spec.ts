import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const api = vi.hoisted(() => ({
  get: vi.fn(),
  cancel: vi.fn(),
  retry: vi.fn(),
  subscribe: vi.fn(),
  close: vi.fn(),
}))

vi.mock('@/services/platformJobs', () => ({
  getPlatformJob: (...args: unknown[]) => api.get(...args),
  cancelPlatformJob: (...args: unknown[]) => api.cancel(...args),
  retryPlatformJob: (...args: unknown[]) => api.retry(...args),
  subscribePlatformJob: (...args: unknown[]) => api.subscribe(...args),
  isPlatformJobTerminal: (status: string) => ['succeeded', 'failed', 'cancelled'].includes(status),
  isPlatformJobFailed: (status: string) => ['failed', 'cancelled'].includes(status),
  platformJobPercent: (job: any) => Math.floor((job.progress_current * 100) / Math.max(1, job.progress_total)),
}))

import PlatformJobProgress from '../PlatformJobProgress.vue'

const queued = {
  job_id: 'j1', operation: 'formula_push', project_id: 'p1', actor_id: 'u1',
  status: 'queued', stage: 'authorizing', progress_current: 0, progress_total: 2,
  progress_message: '校验中', reserved_bytes: 0, result_ref: null,
  error_code: null, error_message: null, attempt_count: 1, max_attempts: 3,
  cancel_requested: false, version: 1, queued_at: null, started_at: null, finished_at: null,
}

describe('PlatformJobProgress', () => {
  beforeEach(() => {
    api.get.mockReset().mockResolvedValue(queued)
    api.cancel.mockReset()
    api.retry.mockReset()
    api.subscribe.mockReset().mockReturnValue({ close: api.close })
    api.close.mockReset()
  })

  function mountProgress() {
    return mount(PlatformJobProgress, {
      props: { projectId: 'p1', jobId: 'j1', title: '公式推送' },
      global: {
        stubs: {
          'el-alert': true,
          AsyncJobProgress: {
            props: ['title', 'percentage', 'status', 'message'],
            template: '<div data-testid="progress" :data-status="status">{{ title }} {{ percentage }} {{ message }}</div>',
          },
        },
      },
    })
  }

  it('初始 GET 后订阅 SSE 唤醒，状态端点仍是权威', async () => {
    const wrapper = mountProgress()
    await flushPromises()
    expect(api.get).toHaveBeenCalledWith('p1', 'j1')
    expect(api.subscribe).toHaveBeenCalled()
    expect(wrapper.find('[data-testid="progress"]').text()).toContain('公式推送')
  })

  it('完成状态只发一次 completed 并关闭订阅', async () => {
    let callback!: (job: any) => void
    api.subscribe.mockImplementation((_p: string, initial: any, cb: (job: any) => void) => {
      callback = cb
      return { close: api.close }
    })
    const wrapper = mountProgress()
    await flushPromises()
    callback({ ...queued, status: 'succeeded', version: 2, progress_current: 2, result_ref: { summary: {} } })
    await flushPromises()
    expect(wrapper.emitted('completed')).toHaveLength(1)
    expect(api.close).toHaveBeenCalled()
  })

  it('取消和重试经统一 API，retry 会更新 job id', async () => {
    api.cancel.mockResolvedValue({ ...queued, status: 'cancelled', version: 2 })
    api.retry.mockResolvedValue({ ...queued, job_id: 'j2', status: 'queued', version: 1 })
    const wrapper = mountProgress()
    await flushPromises()
    await wrapper.vm.cancel()
    await flushPromises()
    expect(api.cancel).toHaveBeenCalledWith('p1', 'j1')
    await wrapper.vm.retry()
    await flushPromises()
    expect(api.retry).toHaveBeenCalledWith('p1', 'j1')
    expect(api.get).toHaveBeenCalledWith('p1', 'j2')
    expect(wrapper.emitted('update:jobId')?.[0]).toEqual(['j2'])
  })
})
