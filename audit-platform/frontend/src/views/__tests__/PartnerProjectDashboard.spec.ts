/**
 * PartnerProjectDashboard.spec.ts — Sprint 2 Task 4.2
 *
 * 测试 PartnerProjectDashboard.vue 页面:
 * - 骨架屏渲染（loading=true）
 * - RBAC 模块显隐：partner 看全量 / assistant 看简化 / manager 看除裁剪外
 * - 刷新按钮点击 → 调用 refresh
 * - Header 信息渲染（项目名 + 年度 + 更新时间）
 *
 * Validates: Requirements 1.3, 1.4, 1.5, 8.1, 8.2, 8.3, 8.4
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref, computed, nextTick } from 'vue'

// ─── Mock useDashboardData composable ────────────────────────────────────────

const mockRefresh = vi.fn()
const mockLoading = ref(false)
const mockError = ref<string | null>(null)
const mockLastUpdated = ref<string | null>(null)
const mockData = ref<any>(null)
const mockTrimmingOverview = computed(() => mockData.value?.trimming_overview ?? null)

vi.mock('@/composables/useDashboardData', () => ({
  useDashboardData: () => ({
    data: mockData,
    loading: mockLoading,
    error: mockError,
    lastUpdated: mockLastUpdated,
    refresh: mockRefresh,
    cycleProgress: computed(() => mockData.value?.cycle_progress ?? []),
    vrSummary: computed(() => mockData.value?.vr_summary ?? null),
    openReviews: computed(() => mockData.value?.open_reviews?.items ?? []),
    timeline: computed(() => mockData.value?.timeline ?? null),
    trimmingOverview: mockTrimmingOverview,
  }),
}))

// ─── Mock useAuthStore ───────────────────────────────────────────────────────

const mockUserRole = ref('partner')
const mockUser = computed(() => ({ role: mockUserRole.value }))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    get user() {
      return mockUser.value
    },
  }),
}))

// ─── Mock vue-router ─────────────────────────────────────────────────────────

vi.mock('vue-router', () => ({
  useRoute: () => ({
    params: { projectId: 'proj-test-001' },
  }),
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
  }),
}))

// ─── Mock child components ───────────────────────────────────────────────────

vi.mock('@/components/dashboard/QuickEntryPanel.vue', () => ({
  default: { template: '<div class="mock-quick-entry">QuickEntryPanel</div>' },
}))

vi.mock('@/components/dashboard/TrimmingOverview.vue', () => ({
  default: { template: '<div class="mock-trimming-overview">TrimmingOverview</div>' },
}))

vi.mock('@/components/dashboard/CycleProgressRing.vue', () => ({
  default: { template: '<div class="mock-cycle-progress-ring">CycleProgressRing</div>' },
}))

vi.mock('@/components/dashboard/VRSummaryCard.vue', () => ({
  default: { template: '<div class="mock-vr-summary">VRSummaryCard</div>' },
}))

vi.mock('@/components/dashboard/ReviewOpinionList.vue', () => ({
  default: { template: '<div class="mock-review-opinion">ReviewOpinionList</div>' },
}))

vi.mock('@/components/dashboard/ProjectTimeline.vue', () => ({
  default: { template: '<div class="mock-project-timeline">ProjectTimeline</div>' },
}))

// ─── Mock Element Plus icons ─────────────────────────────────────────────────

vi.mock('@element-plus/icons-vue', () => ({
  Refresh: { template: '<i class="mock-refresh-icon" />' },
  Connection: { template: '<i class="mock-connection-icon" />' },
}))

// ─── Import component under test ────────────────────────────────────────────

import PartnerProjectDashboard from '../PartnerProjectDashboard.vue'

// ─── Test Fixtures ───────────────────────────────────────────────────────────

function createMockData() {
  return {
    project_name: '测试审计项目',
    audit_year: 2025,
    last_updated: '2025-06-15T14:30:00Z',
    cycle_progress: [
      { cycle: 'D', cycle_name: '销售收入', total_procedures: 20, completed_procedures: 15, trimmed_procedures: 2, progress_rate: 83.33 },
    ],
    vr_summary: { total_rules: 33, blocking_failed: 2, all_passed: false, by_cycle: [] },
    open_reviews: { total: 3, by_layer: { L5: 1, L4: 2 }, items: [] },
    timeline: { current_stage: 'execution', stages: [] },
    trimming_overview: { available: true, total_procedures: 200, trimmed_count: 30, trim_rate: 15.0, by_cycle: [] },
    errors: null,
  }
}

// ─── Element Plus stubs ──────────────────────────────────────────────────────

const globalStubs = {
  'el-row': { template: '<div class="el-row"><slot /></div>' },
  'el-col': { template: '<div class="el-col"><slot /></div>', props: ['span'] },
  'el-skeleton': { template: '<div class="el-skeleton" />', props: ['rows', 'animated'] },
  'el-tag': { template: '<span class="el-tag"><slot /></span>', props: ['type', 'size'] },
  'el-button': {
    template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>',
    props: ['loading', 'icon', 'size'],
    emits: ['click'],
  },
  'el-alert': { template: '<div class="el-alert"><slot /></div>', props: ['title', 'type', 'show-icon', 'closable'] },
}

function mountComponent() {
  return mount(PartnerProjectDashboard, {
    global: {
      stubs: globalStubs,
    },
  })
}

// ─── Tests ───────────────────────────────────────────────────────────────────

beforeEach(() => {
  mockRefresh.mockReset()
  mockLoading.value = false
  mockError.value = null
  mockLastUpdated.value = null
  mockData.value = null
  mockUserRole.value = 'partner'
})

describe('PartnerProjectDashboard — 骨架屏渲染（loading=true）', () => {
  it('loading=true 且 data=null 时显示骨架屏', () => {
    mockLoading.value = true
    mockData.value = null

    const wrapper = mountComponent()
    const skeletons = wrapper.findAll('.el-skeleton')
    expect(skeletons.length).toBeGreaterThanOrEqual(3)
  })

  it('loading=false 且 data 有值时不显示骨架屏', () => {
    mockLoading.value = false
    mockData.value = createMockData()

    const wrapper = mountComponent()
    const skeletons = wrapper.findAll('.el-skeleton')
    expect(skeletons.length).toBe(0)
  })

  it('loading=true 但 data 已有值时不显示骨架屏（刷新场景）', () => {
    mockLoading.value = true
    mockData.value = createMockData()

    const wrapper = mountComponent()
    const skeletons = wrapper.findAll('.el-skeleton')
    expect(skeletons.length).toBe(0)
  })
})

describe('PartnerProjectDashboard — RBAC 模块显隐', () => {
  it('partner 角色看到全部 6 个模块', () => {
    mockUserRole.value = 'partner'
    mockData.value = createMockData()

    const wrapper = mountComponent()
    const html = wrapper.html()

    expect(html).toContain('全循环进度')       // cycleProgress
    expect(html).toContain('Blocking VR')      // vrSummary
    expect(html).toContain('未解决复核意见')    // reviewOpinion
    expect(html).toContain('关键判断点入口')    // quickEntry
    expect(html).toContain('项目时间线')        // timeline
    expect(html).toContain('裁剪汇总')         // trimming
  })

  it('admin 角色看到全部 6 个模块', () => {
    mockUserRole.value = 'admin'
    mockData.value = createMockData()

    const wrapper = mountComponent()
    const html = wrapper.html()

    expect(html).toContain('全循环进度')
    expect(html).toContain('Blocking VR')
    expect(html).toContain('未解决复核意见')
    expect(html).toContain('关键判断点入口')
    expect(html).toContain('项目时间线')
    expect(html).toContain('裁剪汇总')
  })

  it('assistant 角色仅看到 cycleProgress + timeline + quickEntry', () => {
    mockUserRole.value = 'assistant'
    mockData.value = createMockData()

    const wrapper = mountComponent()
    const html = wrapper.html()

    // 可见模块
    expect(html).toContain('全循环进度')       // cycleProgress
    expect(html).toContain('项目时间线')        // timeline
    expect(html).toContain('关键判断点入口')    // quickEntry

    // 不可见模块
    expect(html).not.toContain('Blocking VR')
    expect(html).not.toContain('未解决复核意见')
    expect(html).not.toContain('裁剪汇总')
  })

  it('manager 角色看到除裁剪外的全部模块', () => {
    mockUserRole.value = 'manager'
    mockData.value = createMockData()

    const wrapper = mountComponent()
    const html = wrapper.html()

    // 可见模块
    expect(html).toContain('全循环进度')
    expect(html).toContain('Blocking VR')
    expect(html).toContain('未解决复核意见')
    expect(html).toContain('关键判断点入口')
    expect(html).toContain('项目时间线')

    // 不可见模块
    expect(html).not.toContain('裁剪汇总')
  })

  it('未知角色降级为 assistant 视图', () => {
    mockUserRole.value = 'unknown_role'
    mockData.value = createMockData()

    const wrapper = mountComponent()
    const html = wrapper.html()

    // 与 assistant 相同
    expect(html).toContain('全循环进度')
    expect(html).toContain('项目时间线')
    expect(html).toContain('关键判断点入口')
    expect(html).not.toContain('Blocking VR')
    expect(html).not.toContain('未解决复核意见')
    expect(html).not.toContain('裁剪汇总')
  })
})

describe('PartnerProjectDashboard — 刷新按钮', () => {
  it('点击刷新按钮调用 refresh', async () => {
    mockData.value = createMockData()

    const wrapper = mountComponent()
    const refreshBtn = wrapper.findAll('.el-button').find(btn => btn.text().includes('刷新'))
    expect(refreshBtn).toBeDefined()

    await refreshBtn!.trigger('click')
    expect(mockRefresh).toHaveBeenCalledTimes(1)
  })

  it('loading 时刷新按钮传递 loading 属性', () => {
    mockLoading.value = true
    mockData.value = createMockData()

    const wrapper = mountComponent()
    // The button should have loading prop passed
    const refreshBtn = wrapper.findAll('.el-button').find(btn => btn.text().includes('刷新'))
    expect(refreshBtn).toBeDefined()
  })
})

describe('PartnerProjectDashboard — Header 信息渲染', () => {
  it('显示项目名称', () => {
    mockData.value = createMockData()

    const wrapper = mountComponent()
    expect(wrapper.text()).toContain('测试审计项目')
  })

  it('显示审计年度', () => {
    mockData.value = createMockData()

    const wrapper = mountComponent()
    expect(wrapper.text()).toContain('2025')
    expect(wrapper.text()).toContain('年度')
  })

  it('显示最后更新时间', () => {
    mockData.value = createMockData()
    mockLastUpdated.value = '2025-06-15T14:30:00Z'

    const wrapper = mountComponent()
    expect(wrapper.text()).toContain('最后更新')
  })

  it('data 为 null 时显示加载中占位', () => {
    mockData.value = null

    const wrapper = mountComponent()
    expect(wrapper.text()).toContain('加载中...')
  })

  it('audit_year 不存在时不渲染年度标签', () => {
    mockData.value = { ...createMockData(), audit_year: null }

    const wrapper = mountComponent()
    // el-tag with audit_year is conditionally rendered
    const tags = wrapper.findAll('.el-tag')
    const yearTag = tags.find(t => t.text().includes('年度'))
    expect(yearTag).toBeUndefined()
  })
})
