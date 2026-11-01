import { effectScope } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  create: vi.fn(),
  wait: vi.fn(),
  cancel: vi.fn(),
  httpPost: vi.fn(),
  message: vi.fn(),
}))
vi.mock('@/services/aiTaskJobs', () => ({
  createOrResumeAiTaskJob: (...args: any[]) => mocks.create(...args),
  waitForAiTaskJob: (...args: any[]) => mocks.wait(...args),
  cancelAiTaskJob: (...args: any[]) => mocks.cancel(...args),
  isAiTaskTerminal: (status: string) => ['succeeded', 'partial_failed', 'failed', 'cancelled'].includes(status),
}))
vi.mock('@/utils/http', () => ({
  default: { post: (...args: any[]) => mocks.httpPost(...args), patch: vi.fn() },
  downloadFile: vi.fn(),
}))
vi.mock('element-plus', () => ({
  ElMessage: { success: mocks.message, warning: mocks.message, error: mocks.message },
}))

import { useReviewPanel } from './useReviewPanel'

const base = {
  job_id: 'j1', project_id: 'p1', year: 2025,
  task_kind: 'workpaper_batch_review' as const,
  version: 1, progress_total: 1, progress_done: 0,
  failed_count: 0, cancelled_count: 0, cancel_requested: false,
  created_at: null, started_at: null, finished_at: null, updated_at: null,
}
const queued = { ...base, status: 'queued' as const, items: [{
  item_id: 'i1', ordinal: 0, target_type: 'workpaper' as const,
  target_id: 'w1', target_key: '应收账款', status: 'queued' as const,
  generation_id: 'g1', message_id: null, attempt_count: 0, max_attempts: 3,
  next_attempt_at: null, baseline_version: '1', before_hash: 'h',
  started_at: null, finished_at: null, result: null, error_code: null, error_message: null,
}] }
const final = { ...base, version: 2, status: 'succeeded' as const, progress_done: 1, items: [{
  ...queued.items[0], status: 'succeeded' as const, result: {
    wp_id: 'w1', sheet_name: '应收账款', review_status: 'deterministic_failure',
    findings: [], risk_summary: { high: 0, medium: 0, low: 0 }, prompt_source: 'sheet',
    deterministic_checks: [{
      code: 'D2-RECON-TB', passed: false, severity: 'blocking',
      check_type: 'balance', message: '审定表与试算表不一致',
    }],
  },
}] }

describe('useReviewPanel durable job', () => {
  beforeEach(() => {
    for (const mock of Object.values(mocks)) mock.mockReset()
  })

  it('批量复核只创建耐久任务，并保留系统检查分栏', async () => {
    mocks.create.mockResolvedValue(queued)
    mocks.wait.mockImplementation(async (_p: string, _s: any, update: (v: any) => void) => {
      update(final)
      return final
    })
    const scope = effectScope()
    const panel = scope.run(() => useReviewPanel('p1', 'D2', 2025))!
    await panel.startBatchReview()
    expect(mocks.create).toHaveBeenCalledWith(
      'p1', '2025:D2:batch-review',
      { task_kind: 'workpaper_batch_review', year: 2025, wp_code_prefix: 'D2' },
    )
    expect(mocks.httpPost).not.toHaveBeenCalled()
    expect(panel.sheets.value[0].passStatus).toBe('deterministic_failure')
    expect(panel.sheets.value[0].systemChecks[0].code).toBe('D2-RECON-TB')
    expect(panel.progress.current).toBe(1)
    scope.stop()
  })
})
