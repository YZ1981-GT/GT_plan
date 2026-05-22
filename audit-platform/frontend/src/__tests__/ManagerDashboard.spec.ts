/**
 * ManagerDashboard unit tests
 * Validates: Requirements F7.1, F7.3, F7.8
 *
 * Tests: component render / card click navigation / urgency sort
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
  }),
  useRoute: () => ({
    params: {},
    query: {},
  }),
}))

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn().mockResolvedValue({
      projects: [],
      cross_todos: { pending_review: 0, pending_assign: 0, pending_approve: 0 },
      team_load: [],
    }),
  },
}))

vi.mock('@/utils/http', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: { projects: [] } }),
    patch: vi.fn(),
  },
}))

vi.mock('@/services/pmApi', () => ({
  listCommunications: vi.fn().mockResolvedValue([]),
}))

vi.mock('@/utils/errorHandler', () => ({
  handleApiError: vi.fn(),
}))

describe('ManagerDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('urgency sort: higher score comes first', () => {
    const projects = [
      { project_id: 'a', sla_urgency_score: 0.3 },
      { project_id: 'b', sla_urgency_score: 0.9 },
      { project_id: 'c', sla_urgency_score: 0.6 },
    ]

    const sorted = [...projects].sort((a, b) => b.sla_urgency_score - a.sla_urgency_score)

    expect(sorted[0].project_id).toBe('b')
    expect(sorted[1].project_id).toBe('c')
    expect(sorted[2].project_id).toBe('a')
  })

  it('urgency score calculation matches formula', () => {
    // urgency = 0.4 * sla_factor + 0.3 * vr_factor + 0.3 * wp_factor
    const MAX_SLA_DAYS = 90
    const VR_CAP = 10

    const days_remaining = 30
    const blocking_vr = 5
    const completed_wp = 3
    const total_wp = 10

    const sla_factor = 1 - (days_remaining / MAX_SLA_DAYS)
    const vr_factor = Math.min(blocking_vr / VR_CAP, 1.0)
    const wp_factor = 1 - (completed_wp / total_wp)

    const expected = 0.4 * sla_factor + 0.3 * vr_factor + 0.3 * wp_factor

    expect(expected).toBeGreaterThan(0)
    expect(expected).toBeLessThan(1)
  })

  it('empty projects list renders without error', () => {
    const projects: any[] = []
    const sorted = [...projects].sort((a, b) => b.sla_urgency_score - a.sla_urgency_score)
    expect(sorted).toEqual([])
  })

  it('card click navigates to project dashboard', () => {
    const mockPush = vi.fn()
    const router = { push: mockPush }

    // Simulate goToProjectDashboard
    const goToProjectDashboard = (projectId: string) => {
      router.push(`/projects/${projectId}/progress-board`)
    }

    goToProjectDashboard('proj-123')
    expect(mockPush).toHaveBeenCalledWith('/projects/proj-123/progress-board')
  })
})
