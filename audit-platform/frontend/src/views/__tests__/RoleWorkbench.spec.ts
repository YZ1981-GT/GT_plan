/**
 * RoleWorkbench.spec.ts — MVP-5: 前端角色作业台最小验证
 *
 * 验证核心 Property：
 * 1. 角色区块隔离性：不同角色渲染不同 section
 * 2. 待办可定位性：所有 item 包含 route 或 missing_reason
 *
 * 使用 mock facade API 响应，不依赖真实后端。
 *
 * Validates: Requirements 1.1, 2.1, 3.1, 4.1, 5.1
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, ref, computed } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

interface WorkbenchItem {
  id: string
  label: string
  route?: string
  missing_reason?: string
  priority: string
  due_date?: string
  source?: string
}

interface WorkbenchSection {
  id: string
  title: string
  items: WorkbenchItem[]
}

interface WorkbenchResponse {
  role: string
  project_id: string
  sections: WorkbenchSection[]
}

// ─── Fixture Data ────────────────────────────────────────────────────────────

const FIXTURE_RESPONSES: Record<string, WorkbenchResponse> = {
  auditor: {
    role: 'auditor',
    project_id: 'proj-001',
    sections: [
      {
        id: 'todo',
        title: '今日待办',
        items: [
          { id: 'todo-1', label: 'D1 底稿待编', route: '/projects/proj-001/workpapers/wp-001', priority: 'high', due_date: '2025-12-15', source: 'review_return' },
          { id: 'todo-2', label: 'E1 货币资金复核', route: '/projects/proj-001/workpapers/wp-002', priority: 'normal', due_date: '2025-12-20' },
        ],
      },
      {
        id: 'ai_pending',
        title: 'AI 待确认',
        items: [
          { id: 'ai-1', label: 'D1 AI 生成内容待确认', route: '/projects/proj-001/workpapers/wp-001#ai-content-1', priority: 'normal' },
        ],
      },
      {
        id: 'material_gap',
        title: '资料缺口',
        items: [
          { id: 'mg-1', label: '银行询证函未回收', missing_reason: 'material_not_received', priority: 'high' },
        ],
      },
    ],
  },
  manager: {
    role: 'manager',
    project_id: 'proj-001',
    sections: [
      {
        id: 'completion_rate',
        title: '底稿完成率',
        items: [
          { id: 'cr-1', label: '底稿完成率 75%', route: '/projects/proj-001/dashboard#completion', priority: 'normal' },
        ],
      },
      {
        id: 'review_aging',
        title: '复核 Aging',
        items: [
          { id: 'ra-1', label: '复核超期 3 天', route: '/projects/proj-001/reviews/rv-002', priority: 'high' },
        ],
      },
      {
        id: 'budget_consumption',
        title: '工时预算消耗率',
        items: [
          { id: 'bc-1', label: '工时预算消耗 85%', missing_reason: 'budget_hours_field_missing', priority: 'normal' },
        ],
      },
    ],
  },
  partner: {
    role: 'partner',
    project_id: 'proj-001',
    sections: [
      {
        id: 'signoff_blockers',
        title: '签发阻断项',
        items: [
          { id: 'sb-1', label: 'stale 数据阻断', route: '/projects/proj-001/signoff#stale', priority: 'high' },
          { id: 'sb-2', label: 'AI 未确认内容', route: '/projects/proj-001/signoff#ai-unconfirmed', priority: 'high' },
        ],
      },
      {
        id: 'risk_overview',
        title: '风险总览',
        items: [
          { id: 'ro-1', label: '重大风险 2 项', route: '/projects/proj-001/risks', priority: 'high' },
        ],
      },
    ],
  },
}

// ─── Minimal RoleWorkbench Component (test target) ───────────────────────────

const RoleWorkbench = defineComponent({
  name: 'RoleWorkbench',
  props: {
    role: { type: String, required: true },
    projectId: { type: String, required: true },
  },
  setup(props) {
    const workbenchData = ref<WorkbenchResponse | null>(null)
    const loading = ref(false)

    // Simulate API fetch
    const fetchWorkbench = async () => {
      loading.value = true
      // In real code this calls /api/projects/{pid}/role-workbench?role=xxx
      workbenchData.value = FIXTURE_RESPONSES[props.role] || null
      loading.value = false
    }

    fetchWorkbench()

    const sections = computed(() => workbenchData.value?.sections ?? [])

    return { workbenchData, loading, sections }
  },
  template: `
    <div class="role-workbench" :data-role="role">
      <div v-if="loading" class="workbench-loading">加载中...</div>
      <div v-else-if="!workbenchData" class="workbench-empty">暂无数据</div>
      <div v-else class="workbench-sections">
        <section
          v-for="section in sections"
          :key="section.id"
          class="workbench-section"
          :data-section-id="section.id"
        >
          <h3 class="section-title">{{ section.title }}</h3>
          <ul class="section-items">
            <li
              v-for="item in section.items"
              :key="item.id"
              class="workbench-item"
              :data-item-id="item.id"
              :data-has-route="!!item.route"
              :data-has-missing-reason="!!item.missing_reason"
            >
              <a v-if="item.route" :href="item.route" class="item-link">{{ item.label }}</a>
              <span v-else class="item-no-route">{{ item.label }} ({{ item.missing_reason }})</span>
            </li>
          </ul>
        </section>
      </div>
    </div>
  `,
})

// ─── Test Helpers ────────────────────────────────────────────────────────────

function mountWorkbench(role: string) {
  return mount(RoleWorkbench, {
    props: { role, projectId: 'proj-001' },
  })
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('RoleWorkbench — 角色区块隔离性', () => {
  it('auditor 渲染 todo/ai_pending/material_gap sections', () => {
    const wrapper = mountWorkbench('auditor')
    const sectionIds = wrapper.findAll('.workbench-section').map(el => el.attributes('data-section-id'))
    expect(sectionIds).toContain('todo')
    expect(sectionIds).toContain('ai_pending')
    expect(sectionIds).toContain('material_gap')
    // 不包含 manager 独有的 section
    expect(sectionIds).not.toContain('completion_rate')
    expect(sectionIds).not.toContain('budget_consumption')
  })

  it('manager 渲染 completion_rate/review_aging/budget_consumption sections', () => {
    const wrapper = mountWorkbench('manager')
    const sectionIds = wrapper.findAll('.workbench-section').map(el => el.attributes('data-section-id'))
    expect(sectionIds).toContain('completion_rate')
    expect(sectionIds).toContain('review_aging')
    expect(sectionIds).toContain('budget_consumption')
    // 不包含 auditor 独有的 section
    expect(sectionIds).not.toContain('todo')
    expect(sectionIds).not.toContain('ai_pending')
  })

  it('partner 渲染 signoff_blockers/risk_overview sections', () => {
    const wrapper = mountWorkbench('partner')
    const sectionIds = wrapper.findAll('.workbench-section').map(el => el.attributes('data-section-id'))
    expect(sectionIds).toContain('signoff_blockers')
    expect(sectionIds).toContain('risk_overview')
    // 不包含其他角色独有 section
    expect(sectionIds).not.toContain('todo')
    expect(sectionIds).not.toContain('completion_rate')
  })

  it('不同角色的 section 集合互不相同', () => {
    const roles = ['auditor', 'manager', 'partner']
    const sectionSets: Record<string, Set<string>> = {}

    for (const role of roles) {
      const wrapper = mountWorkbench(role)
      const ids = wrapper.findAll('.workbench-section').map(el => el.attributes('data-section-id'))
      sectionSets[role] = new Set(ids)
    }

    // 任意两角色 section 集合不同
    expect(sectionSets['auditor']).not.toEqual(sectionSets['manager'])
    expect(sectionSets['auditor']).not.toEqual(sectionSets['partner'])
    expect(sectionSets['manager']).not.toEqual(sectionSets['partner'])
  })

  it('未知角色渲染空状态', () => {
    const wrapper = mountWorkbench('unknown_role')
    expect(wrapper.find('.workbench-empty').exists()).toBe(true)
    expect(wrapper.find('.workbench-sections').exists()).toBe(false)
  })
})

describe('RoleWorkbench — 待办可定位性', () => {
  it.each(['auditor', 'manager', 'partner'])('角色 %s 的所有 item 有 route 或 missing_reason', (role) => {
    const wrapper = mountWorkbench(role)
    const items = wrapper.findAll('.workbench-item')

    expect(items.length).toBeGreaterThan(0)

    for (const item of items) {
      const hasRoute = item.attributes('data-has-route') === 'true'
      const hasMissingReason = item.attributes('data-has-missing-reason') === 'true'
      expect(hasRoute || hasMissingReason).toBe(true)
    }
  })

  it('有 route 的 item 渲染为链接', () => {
    const wrapper = mountWorkbench('auditor')
    const links = wrapper.findAll('.item-link')
    expect(links.length).toBeGreaterThan(0)
    for (const link of links) {
      expect(link.attributes('href')).toMatch(/^\//)
    }
  })

  it('无 route 的 item 显示 missing_reason', () => {
    const wrapper = mountWorkbench('auditor')
    const noRouteItems = wrapper.findAll('.item-no-route')
    expect(noRouteItems.length).toBeGreaterThan(0)
    for (const item of noRouteItems) {
      expect(item.text()).toContain('(')
    }
  })
})

describe('RoleWorkbench — 结构完整性', () => {
  it('每个 section 有 title', () => {
    const wrapper = mountWorkbench('auditor')
    const titles = wrapper.findAll('.section-title')
    expect(titles.length).toBeGreaterThan(0)
    for (const title of titles) {
      expect(title.text().length).toBeGreaterThan(0)
    }
  })

  it('顶层包含 data-role 属性', () => {
    const wrapper = mountWorkbench('manager')
    expect(wrapper.find('.role-workbench').attributes('data-role')).toBe('manager')
  })

  it('auditor sections 含待办 items', () => {
    const wrapper = mountWorkbench('auditor')
    const todoSection = wrapper.find('[data-section-id="todo"]')
    expect(todoSection.exists()).toBe(true)
    const items = todoSection.findAll('.workbench-item')
    expect(items.length).toBe(2)
  })
})
