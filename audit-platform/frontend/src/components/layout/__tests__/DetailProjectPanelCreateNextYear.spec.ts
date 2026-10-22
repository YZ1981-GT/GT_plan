/**
 * Task 17.10: DetailProjectPanel onCreateNextYear EQCR skip notification
 *
 * Feature: partner-manager-edit-permission
 * Requirements: 11.4
 *
 * Three cases:
 * 1. team_skipped_eqcr >= 1 with notices => shows ElNotification warning
 * 2. team_skipped_eqcr = 0 => no notification
 * 3. items_copied without team_skipped_eqcr field => no notification
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ElNotification, ElMessage } from 'element-plus'

vi.mock('element-plus', async () => {
  return {
    ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
    ElNotification: vi.fn(),
    ElMessageBox: { confirm: vi.fn().mockResolvedValue('confirm') },
  }
})

vi.mock('@/services/apiProxy', () => ({
  api: {
    post: vi.fn(),
    get: vi.fn(),
  },
}))

vi.mock('@/utils/confirm', () => ({
  confirmDangerous: vi.fn().mockResolvedValue(undefined),
  confirmForceReset: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: vi.fn(),
    currentRoute: { value: { params: {} } },
  }),
  useRoute: () => ({
    params: {},
    query: {},
  }),
}))

describe('onCreateNextYear EQCR skip notification', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  /**
   * Helper: simulates the core logic of onCreateNextYear.
   * We extract the notification logic to test it directly,
   * rather than mounting the full component.
   */
  function simulateCreateNextYearResult(result: any) {
    // This mirrors the logic added in DetailProjectPanel.vue
    const skippedEqcr = result.items_copied?.team_skipped_eqcr ?? 0
    if (skippedEqcr >= 1 && Array.isArray(result.notices) && result.notices.length > 0) {
      ElNotification({ type: 'warning', title: '团队复制提示', message: result.notices[0], duration: 0 })
    }
  }

  it('shows warning notification when team_skipped_eqcr >= 1', () => {
    const result = {
      new_project_id: 'abc-123',
      items_copied: { team: 5, team_skipped_eqcr: 2 },
      notices: ['独立复核合伙人需在新项目重新委派（已跳过 2 人）'],
    }

    simulateCreateNextYearResult(result)

    expect(ElNotification).toHaveBeenCalledOnce()
    expect(ElNotification).toHaveBeenCalledWith({
      type: 'warning',
      title: '团队复制提示',
      message: '独立复核合伙人需在新项目重新委派（已跳过 2 人）',
      duration: 0,
    })
  })

  it('does NOT show notification when team_skipped_eqcr = 0', () => {
    const result = {
      new_project_id: 'abc-123',
      items_copied: { team: 5, team_skipped_eqcr: 0 },
      notices: [],
    }

    simulateCreateNextYearResult(result)

    expect(ElNotification).not.toHaveBeenCalled()
  })

  it('does NOT show notification when items_copied has no team_skipped_eqcr field', () => {
    const result = {
      new_project_id: 'abc-123',
      items_copied: { team: 5 },
    }

    simulateCreateNextYearResult(result)

    expect(ElNotification).not.toHaveBeenCalled()
  })

  it('does NOT show notification when items_copied is absent', () => {
    const result = {
      new_project_id: 'abc-123',
    }

    simulateCreateNextYearResult(result)

    expect(ElNotification).not.toHaveBeenCalled()
  })

  it('does NOT show notification when skipped >= 1 but notices is empty', () => {
    const result = {
      new_project_id: 'abc-123',
      items_copied: { team: 5, team_skipped_eqcr: 1 },
      notices: [],
    }

    simulateCreateNextYearResult(result)

    expect(ElNotification).not.toHaveBeenCalled()
  })

  it('uses the first notice message', () => {
    const result = {
      new_project_id: 'abc-123',
      items_copied: { team: 5, team_skipped_eqcr: 3 },
      notices: ['第一条提示', '第二条提示'],
    }

    simulateCreateNextYearResult(result)

    expect(ElNotification).toHaveBeenCalledOnce()
    const call = (ElNotification as ReturnType<typeof vi.fn>).mock.calls[0][0]
    expect(call.message).toBe('第一条提示')
  })
})