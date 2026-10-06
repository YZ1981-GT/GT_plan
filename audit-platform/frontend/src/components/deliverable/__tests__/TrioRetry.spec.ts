/**
 * TrioRetryButton + TrioAttemptHistory 单元测试
 * Spec: chain-closure-phase4-deliverable-center-trio Task 11
 *
 * 验证（需求 5.6, 6.3, 6.5）：
 * 1. 重试按钮：失败项 + 有权限时可见且可点击
 * 2. 重试按钮：无权限时置灰并说明原因
 * 3. 重试按钮：快照变更时置灰并说明原因
 * 4. 点击重试 → 调用真实 API → loading → 状态更新
 * 5. 尝试历史：按 attempt_no 升序展示全部尝试
 * 6. 旧失败记录在新尝试成功后保留展示
 * 7. 变异：按钮只改本地状态不发请求 → 测试必须红
 */
import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import type { TrioJob, TrioJobItem, TrioJobAttempt } from '@/services/deliverableApi'

// ── mock API 模块 ──────────────────────────────────────────

const { mockRetryTrioJob, mockGetTrioItemAttempts } = vi.hoisted(() => ({
  mockRetryTrioJob: vi.fn(),
  mockGetTrioItemAttempts: vi.fn(),
}))

vi.mock('@/services/deliverableApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/deliverableApi')>()
  return {
    ...actual,
    retryTrioJob: (...args: any[]) => mockRetryTrioJob(...args),
    getTrioItemAttempts: (...args: any[]) => mockGetTrioItemAttempts(...args),
  }
})

import TrioRetryButton from '../TrioRetryButton.vue'
import TrioAttemptHistory from '../TrioAttemptHistory.vue'

// ── Element Plus 轻量 stubs ──────────────────────────────────

const stubButton = {
  template: `<button
    class="el-button-stub"
    :disabled="disabled"
    :data-loading="loading"
    @click="!disabled && $emit('click', $event)"
  ><slot /></button>`,
  props: ['type', 'size', 'loading', 'disabled'],
  emits: ['click'],
}

const stubTooltip = {
  template: '<div class="el-tooltip-stub" :data-content="content" :data-disabled="disabled"><slot /></div>',
  props: ['content', 'disabled', 'placement'],
}

const stubIcon = { template: '<i class="el-icon-stub"><slot /></i>' }

const stubTag = {
  template: '<span class="el-tag-stub" :data-type="type"><slot /></span>',
  props: ['type', 'size'],
}

const stubTimeline = { template: '<div class="el-timeline-stub"><slot /></div>' }
const stubTimelineItem = {
  template: '<div class="el-timeline-item-stub" :data-type="type" :data-ts="timestamp"><slot /></div>',
  props: ['type', 'timestamp', 'placement'],
}

const stubCollapse = { template: '<div class="el-collapse-stub"><slot /></div>' }
const stubCollapseItem = {
  template: '<div class="el-collapse-item-stub"><slot /></div>',
  props: ['title'],
}

const stubSkeleton = { template: '<div class="el-skeleton-stub" />', props: ['rows', 'animated'] }

const retryGlobal = {
  stubs: {
    'el-button': stubButton,
    'el-tooltip': stubTooltip,
    'el-icon': stubIcon,
  },
}

const historyGlobal = {
  stubs: {
    'el-timeline': stubTimeline,
    'el-timeline-item': stubTimelineItem,
    'el-tag': stubTag,
    'el-collapse': stubCollapse,
    'el-collapse-item': stubCollapseItem,
    'el-skeleton': stubSkeleton,
    'el-icon': stubIcon,
  },
}

// ── 工厂函数 ──────────────────────────────────────────

function makeItem(overrides: Partial<TrioJobItem> = {}): TrioJobItem {
  return {
    id: 'item-1',
    job_id: 'job-1',
    step_key: 'financial_report',
    sequence: 1,
    status: 'succeeded',
    attempt_count: 1,
    last_attempt_id: 'att-1',
    error_message: null,
    snapshot_id: 'snap-1',
    finished_at: '2025-01-01T12:00:00Z',
    ...overrides,
  }
}

function makeJob(overrides: Partial<TrioJob> = {}, items?: TrioJobItem[]): TrioJob {
  return {
    id: 'job-1',
    project_id: 'p1',
    year: 2024,
    kind: 'deliverable_trio',
    status: 'partial',
    snapshot_id: 'snap-1',
    trio_total: 3,
    trio_succeeded: 2,
    created_by: 'admin',
    created_at: '2025-01-01T10:00:00Z',
    started_at: '2025-01-01T10:00:01Z',
    finished_at: '2025-01-01T10:05:00Z',
    items: items ?? [
      makeItem({ id: 'item-1', step_key: 'financial_report', sequence: 1, status: 'succeeded' }),
      makeItem({ id: 'item-2', step_key: 'disclosure_notes', sequence: 2, status: 'failed', error_message: '附注模板缺失' }),
      makeItem({ id: 'item-3', step_key: 'audit_report', sequence: 3, status: 'succeeded' }),
    ],
    ...overrides,
  }
}

function makeAttempt(overrides: Partial<TrioJobAttempt> = {}): TrioJobAttempt {
  return {
    id: 'att-1',
    job_id: 'job-1',
    item_id: 'item-2',
    attempt_no: 1,
    status: 'failed',
    started_at: '2025-01-01T10:01:00Z',
    finished_at: '2025-01-01T10:01:30Z',
    snapshot_id: 'snap-1',
    error_type: 'TemplateNotFoundError',
    error_message: '附注模板缺失',
    diagnostic_detail: '模板 disclosure_notes_v2 未找到',
    file_path: null,
    file_size: null,
    file_sha256: null,
    version_id: null,
    created_by: 'admin',
    ...overrides,
  }
}

function mountRetryButton(propsOverride: Record<string, any> = {}) {
  return mount(TrioRetryButton, {
    props: {
      job: makeJob(),
      projectId: 'p1',
      canRetry: true,
      snapshotValid: true,
      ...propsOverride,
    },
    global: retryGlobal,
  })
}

function mountHistory(propsOverride: Record<string, any> = {}) {
  return mount(TrioAttemptHistory, {
    props: {
      projectId: 'p1',
      itemId: 'item-2',
      ...propsOverride,
    },
    global: historyGlobal,
  })
}

// ── TrioRetryButton 测试 ──────────────────────────────────

describe('TrioRetryButton — 可见性与可交互', () => {
  beforeEach(() => {
    mockRetryTrioJob.mockReset()
  })

  it('失败项 + 有权限 + 快照有效 → 按钮可点击', () => {
    const wrapper = mountRetryButton()
    const btn = wrapper.find('.el-button-stub')
    expect(btn.exists()).toBe(true)
    expect(btn.attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).toContain('重试失败项')
  })

  it('无权限 → 按钮置灰', () => {
    const wrapper = mountRetryButton({ canRetry: false })
    const btn = wrapper.find('.el-button-stub')
    expect(btn.attributes('disabled')).toBeDefined()
    const tooltip = wrapper.find('.el-tooltip-stub')
    expect(tooltip.attributes('data-content')).toContain('无重试权限')
  })

  it('快照已变更 → 按钮置灰', () => {
    const wrapper = mountRetryButton({ snapshotValid: false })
    const btn = wrapper.find('.el-button-stub')
    expect(btn.attributes('disabled')).toBeDefined()
    const tooltip = wrapper.find('.el-tooltip-stub')
    expect(tooltip.attributes('data-content')).toContain('快照已变更')
  })

  it('没有失败项 → 按钮置灰', () => {
    const allSucceeded = makeJob({ status: 'succeeded' }, [
      makeItem({ status: 'succeeded' }),
      makeItem({ id: 'item-2', step_key: 'disclosure_notes', sequence: 2, status: 'succeeded' }),
      makeItem({ id: 'item-3', step_key: 'audit_report', sequence: 3, status: 'succeeded' }),
    ])
    const wrapper = mountRetryButton({ job: allSucceeded })
    const btn = wrapper.find('.el-button-stub')
    expect(btn.attributes('disabled')).toBeDefined()
  })

  it('有运行中项 → 按钮置灰', () => {
    const withRunning = makeJob({}, [
      makeItem({ status: 'succeeded' }),
      makeItem({ id: 'item-2', step_key: 'disclosure_notes', sequence: 2, status: 'running' }),
      makeItem({ id: 'item-3', step_key: 'audit_report', sequence: 3, status: 'queued' }),
    ])
    const wrapper = mountRetryButton({ job: withRunning })
    const btn = wrapper.find('.el-button-stub')
    expect(btn.attributes('disabled')).toBeDefined()
  })
})

describe('TrioRetryButton — 重试交互', () => {
  beforeEach(() => {
    mockRetryTrioJob.mockReset()
  })

  it('点击调用真实 retry API 并 emit retried', async () => {
    const succeededJob = makeJob({ status: 'succeeded', trio_succeeded: 3 }, [
      makeItem({ status: 'succeeded' }),
      makeItem({ id: 'item-2', step_key: 'disclosure_notes', sequence: 2, status: 'succeeded' }),
      makeItem({ id: 'item-3', step_key: 'audit_report', sequence: 3, status: 'succeeded' }),
    ])
    mockRetryTrioJob.mockResolvedValue(succeededJob)

    const wrapper = mountRetryButton()
    const btn = wrapper.find('.el-button-stub')
    await btn.trigger('click')
    await flushPromises()

    // 验证调用了真实 API（非仅改本地状态）
    expect(mockRetryTrioJob).toHaveBeenCalledWith('p1', 'job-1')
    expect(mockRetryTrioJob).toHaveBeenCalledTimes(1)

    // emit retried 事件
    const emitted = wrapper.emitted('retried')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual(succeededJob)
  })

  it('点击后展示 loading 状态', async () => {
    // 让 API 挂起不 resolve
    let resolveRetry!: (v: TrioJob) => void
    mockRetryTrioJob.mockReturnValue(
      new Promise<TrioJob>((r) => { resolveRetry = r }),
    )

    const wrapper = mountRetryButton()
    const btn = wrapper.find('.el-button-stub')
    await btn.trigger('click')

    // loading 中
    expect(btn.attributes('data-loading')).toBe('true')
    expect(wrapper.text()).toContain('重试中')

    // resolve 结束 loading
    resolveRetry(makeJob({ status: 'succeeded' }))
    await flushPromises()
    expect(wrapper.find('.el-button-stub').attributes('data-loading')).toBe('false')
  })

  it('API 失败时不 emit retried', async () => {
    mockRetryTrioJob.mockRejectedValue(new Error('409 快照已过期'))

    const wrapper = mountRetryButton()
    await wrapper.find('.el-button-stub').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('retried')).toBeFalsy()
  })

  it('变异：若按钮只改本地状态不发请求 → 测试必红', async () => {
    /**
     * 本用例验证：retryTrioJob 必须被真实调用。
     * 若实现中 handleRetry 被改为只更新 retrying.value 而不调 API，
     * 则 mockRetryTrioJob.toHaveBeenCalled() 断言会失败。
     */
    mockRetryTrioJob.mockResolvedValue(makeJob({ status: 'succeeded' }))

    const wrapper = mountRetryButton()
    await wrapper.find('.el-button-stub').trigger('click')
    await flushPromises()

    // 核心断言：API 必须被调用
    expect(mockRetryTrioJob).toHaveBeenCalledTimes(1)
    expect(mockRetryTrioJob).toHaveBeenCalledWith('p1', 'job-1')

    // 辅助断言：emit 必须携带 API 返回值（非本地拼凑）
    const emitted = wrapper.emitted('retried')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toHaveProperty('status', 'succeeded')
  })
})

// ── TrioAttemptHistory 测试 ──────────────────────────────────

describe('TrioAttemptHistory — 尝试历史展示', () => {
  beforeEach(() => {
    mockGetTrioItemAttempts.mockReset()
  })

  it('按 attempt_no 升序展示全部尝试', async () => {
    mockGetTrioItemAttempts.mockResolvedValue([
      makeAttempt({ id: 'att-2', attempt_no: 2, status: 'succeeded', error_message: null, error_type: null, diagnostic_detail: null }),
      makeAttempt({ id: 'att-1', attempt_no: 1, status: 'failed' }),
    ])

    const wrapper = mountHistory()
    await flushPromises()

    const items = wrapper.findAll('.el-timeline-item-stub')
    expect(items).toHaveLength(2)

    // 第一个是 attempt_no=1（升序）
    expect(items[0].text()).toContain('第 1 次尝试')
    expect(items[1].text()).toContain('第 2 次尝试')
  })

  it('展示失败 attempt 的错误信息和状态标签', async () => {
    mockGetTrioItemAttempts.mockResolvedValue([
      makeAttempt(),
    ])

    const wrapper = mountHistory()
    await flushPromises()

    expect(wrapper.text()).toContain('失败')
    expect(wrapper.text()).toContain('附注模板缺失')
  })

  it('旧失败记录在新尝试成功后保留展示', async () => {
    mockGetTrioItemAttempts.mockResolvedValue([
      makeAttempt({ id: 'att-1', attempt_no: 1, status: 'failed', error_message: '附注模板缺失' }),
      makeAttempt({
        id: 'att-2',
        attempt_no: 2,
        status: 'succeeded',
        error_message: null,
        error_type: null,
        diagnostic_detail: null,
      }),
    ])

    const wrapper = mountHistory()
    await flushPromises()

    const items = wrapper.findAll('.el-timeline-item-stub')
    expect(items).toHaveLength(2)

    // 旧失败仍展示
    expect(items[0].text()).toContain('第 1 次尝试')
    expect(items[0].text()).toContain('失败')
    expect(items[0].text()).toContain('附注模板缺失')

    // 新成功也展示
    expect(items[1].text()).toContain('第 2 次尝试')
    expect(items[1].text()).toContain('成功')
  })

  it('无尝试记录时展示空态', async () => {
    mockGetTrioItemAttempts.mockResolvedValue([])

    const wrapper = mountHistory()
    await flushPromises()

    expect(wrapper.text()).toContain('暂无尝试记录')
  })

  it('API 调用传入正确参数', async () => {
    mockGetTrioItemAttempts.mockResolvedValue([])

    mountHistory({ projectId: 'proj-abc', itemId: 'item-xyz' })
    await flushPromises()

    expect(mockGetTrioItemAttempts).toHaveBeenCalledWith('proj-abc', 'item-xyz')
  })

  it('展示诊断详情（错误类型和诊断信息）', async () => {
    mockGetTrioItemAttempts.mockResolvedValue([
      makeAttempt(),
    ])

    const wrapper = mountHistory()
    await flushPromises()

    // 诊断区域存在
    const collapseItem = wrapper.find('.el-collapse-item-stub')
    expect(collapseItem.exists()).toBe(true)
    expect(wrapper.text()).toContain('TemplateNotFoundError')
    expect(wrapper.text()).toContain('disclosure_notes_v2 未找到')
  })

  it('expose reload() 可供外部重新拉取', async () => {
    mockGetTrioItemAttempts.mockResolvedValueOnce([
      makeAttempt({ attempt_no: 1, status: 'failed' }),
    ])

    const wrapper = mountHistory()
    await flushPromises()
    expect(wrapper.findAll('.el-timeline-item-stub')).toHaveLength(1)

    mockGetTrioItemAttempts.mockResolvedValueOnce([
      makeAttempt({ attempt_no: 1, status: 'failed' }),
      makeAttempt({ id: 'att-2', attempt_no: 2, status: 'succeeded', error_message: null, error_type: null, diagnostic_detail: null }),
    ])

    await (wrapper.vm as any).reload()
    await flushPromises()
    expect(wrapper.findAll('.el-timeline-item-stub')).toHaveLength(2)
  })
})
