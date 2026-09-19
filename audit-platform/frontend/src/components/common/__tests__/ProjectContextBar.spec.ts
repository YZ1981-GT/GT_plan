/**
 * ProjectContextBar — 单元测试 [P1-1]
 *
 * 验证：
 * 1. 展示项目名称、年度、准则、范围、状态、职责
 * 2. 只读状态提示（archived/signed）
 * 3. 无 projectId 时不渲染
 * 4. 角色映射
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { ref, computed } from 'vue'
import ProjectContextBar from '../ProjectContextBar.vue'

// ─── Reactive data that can be mutated between tests ──────────────────────

const projectId = ref('test-project-123')
const projectName = ref('测试项目')
const year = ref(2025)
const applicableStandard = ref('soe')
const auditScope = ref<'standalone' | 'consolidated'>('standalone')
const projectStatus = ref('execution')
const roleInProject = ref<string | null>('manager')

const mockSetCurrentYear = vi.fn()

vi.mock('@/stores/project', () => ({
  useProjectStore: () => ({
    get currentProjectContext() {
      return {
        projectId: projectId.value,
        projectName: projectName.value,
        year: year.value,
        applicableStandard: applicableStandard.value,
        auditScope: auditScope.value,
        projectStatus: projectStatus.value,
        roleInProject: roleInProject.value,
      }
    },
    get yearOptions() {
      return [2023, 2024, 2025, 2026]
    },
    setCurrentYear: mockSetCurrentYear,
  }),
}))

vi.mock('@/stores/dict', () => ({
  useDictStore: () => ({
    label: (_key: string, value: string) => value,
    type: (_key: string, _value: string) => 'info' as const,
    options: () => [],
  }),
}))

function mountBar() {
  return mount(ProjectContextBar, {
    global: {
      plugins: [createPinia()],
      stubs: {
        ElSelect: { template: '<span class="stub-select"><slot /></span>', props: ['modelValue'] },
        ElOption: { template: '<span />', props: ['label', 'value'] },
        ElTag: { template: '<span class="stub-tag"><slot /></span>', props: ['type', 'size', 'effect'] },
        ElIcon: { template: '<span class="stub-icon"><slot /></span>' },
        Lock: { template: '<span>🔒</span>' },
      },
    },
  })
}

describe('ProjectContextBar', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockSetCurrentYear.mockClear()
    projectId.value = 'test-project-123'
    projectName.value = '测试项目'
    year.value = 2025
    applicableStandard.value = 'soe'
    auditScope.value = 'standalone'
    projectStatus.value = 'execution'
    roleInProject.value = 'manager'
  })

  it('展示项目核心上下文信息', () => {
    const wrapper = mountBar()
    const html = wrapper.html()
    expect(html).toContain('测试项目')
    expect(html).toContain('项目')
    expect(html).toContain('年度')
    expect(html).toContain('准则')
    expect(html).toContain('范围')
    expect(html).toContain('状态')
    expect(html).toContain('职责')
  })

  it('准则映射正确：soe → 国企准则', () => {
    const wrapper = mountBar()
    expect(wrapper.html()).toContain('国企准则')
  })

  it('审计范围映射正确：standalone → 单体', () => {
    const wrapper = mountBar()
    expect(wrapper.html()).toContain('单体')
  })

  it('合并范围映射：consolidated → 合并', () => {
    auditScope.value = 'consolidated'
    const wrapper = mountBar()
    expect(wrapper.html()).toContain('合并')
  })

  it('archived 状态显示只读提示', () => {
    projectStatus.value = 'archived'
    const wrapper = mountBar()
    expect(wrapper.html()).toContain('已归档，数据只读')
  })

  it('signed 状态显示只读提示', () => {
    projectStatus.value = 'signed'
    const wrapper = mountBar()
    expect(wrapper.html()).toContain('已签发，数据只读')
  })

  it('无 projectId 时不渲染', () => {
    projectId.value = ''
    const wrapper = mountBar()
    expect(wrapper.find('.gt-context-bar').exists()).toBe(false)
  })

  it('角色映射：manager → 项目经理', () => {
    const wrapper = mountBar()
    expect(wrapper.html()).toContain('项目经理')
  })
})
