/**
 * TrioRetryPanel — chain-closure-phase4 Task 11 vitest 真挂载单测
 * Spec: .kiro/specs/chain-closure-phase4-deliverable-center-trio/ Task 11（需求 5.6/6.3/6.5）
 *
 * 覆盖：
 * 1. 失败项且有权限、快照有效 → 展示可点重试入口；点击调用**真实** retry API
 *    并继续轮询到成功；旧 attempt 失败原因保留（append-only）。
 * 2. 无编辑权限 → 重试按钮置灰 + 中文原因；点击不发请求。
 * 3. 快照失效 → 重试按钮置灰 + 中文原因 + 全局 stale 提示；点击不发请求。
 * 4. append-only：轮询刷新返回的 attempts 不含旧 id 时，旧失败原因仍保留并上抛。
 *
 * 变异哨兵（必须红）：若重试按钮只改本地状态而**不发**真实 API 请求，
 * 第 1 个用例对 `retryTrioJob` 的 toHaveBeenCalled 断言会失败。
 */
import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const { mockRetry, mockFetchJob, mockFetchAttempts } = vi.hoisted(() => ({
  mockRetry: vi.fn(),
  mockFetchJob: vi.fn(),
  mockFetchAttempts: vi.fn(),
}))

// 部分 mock：保留真实 TRIO_STEP_LABELS，仅替换三个网络方法。
vi.mock('@/services/deliverableApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/deliverableApi')>()
  return {
    ...actual,
    retryTrioJob: (...a: any[]) => mockRetry(...a),
    fetchTrioJob: (...a: any[]) => mockFetchJob(...a),
    fetchTrioJobAttempts: (...a: any[]) => mockFetchAttempts(...a),
  }
})

const { mockMsgSuccess, mockMsgWarning, mockMsgError } = vi.hoisted(() => ({
  mockMsgSuccess: vi.fn(),
  mockMsgWarning: vi.fn(),
  mockMsgError: vi.fn(),
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: (...a: any[]) => mockMsgSuccess(...a),
    warning: (...a: any[]) => mockMsgWarning(...a),
    error: (...a: any[]) => mockMsgError(...a),
  },
}))

import TrioRetryPanel from '../TrioRetryPanel.vue'
import type {
  ExportJobTrioResult,
  ExportJobTrioItem,
  ExportJobAttempt,
} from '@/services/deliverableApi'

// ─── 测试数据工厂 ───────────────────────────────────────────────────────────

function item(partial: Partial<ExportJobTrioItem> & { id: string }): ExportJobTrioItem {
  return {
    job_id: 'job-1',
    word_export_task_id: null,
    status: 'succeeded',
    error_message: null,
    finished_at: null,
    ...partial,
  }
}

/** 固定顺序三项：fin(succeeded) / notes(FAILED) / audit(blocked)。 */
function jobWithFailedNotes(): ExportJobTrioResult {
  return {
    id: 'job-1',
    project_id: 'p1',
    job_type: 'deliverable_trio',
    status: 'partial',
    payload: null,
    progress_total: 3,
    progress_done: 1,
    failed_count: 1,
    initiated_by: 'u1',
    created_at: null,
    updated_at: null,
    items: [
      item({ id: 'it-fin', status: 'succeeded' }),
      item({ id: 'it-notes', status: 'failed', error_message: '附注章节缺失（第1次）' }),
      item({ id: 'it-audit', status: 'blocked', error_message: '前置项失败' }),
    ],
  }
}

function attempt(partial: Partial<ExportJobAttempt> & { id: string; item_id: string; attempt_no: number }): ExportJobAttempt {
  return {
    job_id: 'job-1',
    status: 'failed',
    trigger: 'initial',
    snapshot_id: 'snap-1',
    error_type: 'ValueError',
    error_message: null,
    diagnostic_detail: null,
    file_path: null,
    file_size: null,
    file_sha256: null,
    version_id: null,
    started_at: null,
    finished_at: null,
    ...partial,
  }
}

function makePanel(props: Record<string, any> = {}) {
  return mount(TrioRetryPanel, {
    props: {
      projectId: 'p1',
      year: 2024,
      job: jobWithFailedNotes(),
      attempts: [
        attempt({ id: 'att-1', item_id: 'it-notes', attempt_no: 1, error_message: '附注章节缺失（第1次）' }),
      ],
      canEdit: true,
      snapshotValid: true,
      ...props,
    },
  })
}

describe('TrioRetryPanel', () => {
  beforeEach(() => {
    mockRetry.mockReset()
    mockFetchJob.mockReset()
    mockFetchAttempts.mockReset()
    mockMsgSuccess.mockReset()
    mockMsgWarning.mockReset()
    mockMsgError.mockReset()
  })

  it('失败项且有权限、快照有效时展示可点重试入口', () => {
    const wrapper = makePanel()
    const btn = wrapper.find('[data-testid="trio-retry-disclosure_notes"]')
    expect(btn.exists()).toBe(true)
    expect((btn.element as HTMLButtonElement).disabled).toBe(false)
    // 成功项不展示重试入口（需求 6.3：仅失败项）
    expect(wrapper.find('[data-testid="trio-retry-financial_report"]').exists()).toBe(false)
    // 展示当前失败原因
    expect(wrapper.find('[data-testid="trio-error-disclosure_notes"]').text()).toContain('附注章节缺失')
    // 展示历史 attempt
    expect(wrapper.find('[data-testid="trio-attempts-disclosure_notes"]').text()).toContain('第 1 次尝试')
  })

  it('点击重试调用真实 retry API 并继续轮询到成功，旧 attempt 保留', async () => {
    mockRetry.mockResolvedValue({ job_id: 'job-1', retried_count: 1 })
    // 轮询第一次即终态 succeeded
    const succeededJob: ExportJobTrioResult = {
      ...jobWithFailedNotes(),
      status: 'succeeded',
      items: [
        item({ id: 'it-fin', status: 'succeeded' }),
        item({ id: 'it-notes', status: 'succeeded', error_message: null }),
        item({ id: 'it-audit', status: 'succeeded' }),
      ],
    }
    mockFetchJob.mockResolvedValue(succeededJob)
    // 轮询刷新历史：新增第 2 次尝试（成功），旧 att-1 仍在
    mockFetchAttempts.mockResolvedValue([
      attempt({ id: 'att-1', item_id: 'it-notes', attempt_no: 1, status: 'failed', error_message: '附注章节缺失（第1次）' }),
      attempt({ id: 'att-2', item_id: 'it-notes', attempt_no: 2, status: 'succeeded', error_message: null }),
    ])

    const wrapper = makePanel()
    await wrapper.find('[data-testid="trio-retry-disclosure_notes"]').trigger('click')
    await flushPromises()

    // 变异哨兵：按钮必须发真实请求，而非只改本地状态
    expect(mockRetry).toHaveBeenCalledTimes(1)
    expect(mockRetry).toHaveBeenCalledWith('p1', 'job-1')
    // 继续轮询
    expect(mockFetchJob).toHaveBeenCalled()
    expect(mockFetchAttempts).toHaveBeenCalled()

    // 上抛 job-updated / attempts-updated
    const jobEvents = wrapper.emitted('job-updated')
    expect(jobEvents).toBeTruthy()
    expect((jobEvents!.at(-1)![0] as ExportJobTrioResult).status).toBe('succeeded')

    const attEvents = wrapper.emitted('attempts-updated')
    expect(attEvents).toBeTruthy()
    const merged = attEvents!.at(-1)![0] as ExportJobAttempt[]
    // append-only：旧 att-1 的失败原因保留，新 att-2 加入
    expect(merged.map((a) => a.id).sort()).toEqual(['att-1', 'att-2'])
    expect(merged.find((a) => a.id === 'att-1')?.error_message).toBe('附注章节缺失（第1次）')

    expect(mockMsgSuccess).toHaveBeenCalled()
  })

  it('无编辑权限时重试按钮置灰且点击不发请求', async () => {
    const wrapper = makePanel({ canEdit: false })
    const btn = wrapper.find('[data-testid="trio-retry-disclosure_notes"]')
    expect((btn.element as HTMLButtonElement).disabled).toBe(true)
    expect(wrapper.find('[data-testid="trio-retry-reason-disclosure_notes"]').text()).toContain('无编辑权限')

    await btn.trigger('click')
    await flushPromises()
    expect(mockRetry).not.toHaveBeenCalled()
  })

  it('快照失效时重试按钮置灰、显示 stale 提示且点击不发请求', async () => {
    const wrapper = makePanel({ snapshotValid: false })
    const btn = wrapper.find('[data-testid="trio-retry-disclosure_notes"]')
    expect((btn.element as HTMLButtonElement).disabled).toBe(true)
    expect(wrapper.find('[data-testid="trio-retry-reason-disclosure_notes"]').text()).toContain('快照已变化')
    expect(wrapper.find('[data-testid="trio-snapshot-stale"]').exists()).toBe(true)

    await btn.trigger('click')
    await flushPromises()
    expect(mockRetry).not.toHaveBeenCalled()
  })

  it('后端 409 时置为快照失效并上抛 snapshot-stale（旧原因不丢）', async () => {
    const err: any = new Error('conflict')
    err.response = { status: 409, data: { detail: '源数据在生成过程中发生变化' } }
    mockRetry.mockRejectedValue(err)

    const wrapper = makePanel()
    await wrapper.find('[data-testid="trio-retry-disclosure_notes"]').trigger('click')
    await flushPromises()

    expect(mockRetry).toHaveBeenCalledTimes(1)
    // 409 不应继续轮询
    expect(mockFetchJob).not.toHaveBeenCalled()
    expect(wrapper.emitted('snapshot-stale')).toBeTruthy()
    expect(mockMsgWarning).toHaveBeenCalled()
    // 旧历史仍在
    expect(wrapper.find('[data-testid="trio-attempts-disclosure_notes"]').text()).toContain('第 1 次尝试')
  })

  it('轮询刷新返回不含旧 attempt id 时，旧失败原因仍保留（append-only）', async () => {
    mockRetry.mockResolvedValue({ job_id: 'job-1', retried_count: 1 })
    mockFetchJob.mockResolvedValue({ ...jobWithFailedNotes(), status: 'failed' })
    // 刷新只回新 att-2（故意不含旧 att-1）
    mockFetchAttempts.mockResolvedValue([
      attempt({ id: 'att-2', item_id: 'it-notes', attempt_no: 2, status: 'failed', error_message: '仍然失败（第2次）' }),
    ])

    const wrapper = makePanel()
    await wrapper.find('[data-testid="trio-retry-disclosure_notes"]').trigger('click')
    await flushPromises()

    const attEvents = wrapper.emitted('attempts-updated')
    const merged = attEvents!.at(-1)![0] as ExportJobAttempt[]
    expect(merged.map((a) => a.id).sort()).toEqual(['att-1', 'att-2'])
    expect(merged.find((a) => a.id === 'att-1')?.error_message).toBe('附注章节缺失（第1次）')
  })
})
