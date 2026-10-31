import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const mockGetWpIndex = vi.fn()
const mockApiGet = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'test-project' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/services/workpaperApi', () => ({
  getWpIndex: (...args: unknown[]) => mockGetWpIndex(...args),
}))
vi.mock('@/services/apiProxy', () => ({
  api: { get: (...args: unknown[]) => mockApiGet(...args) },
}))

import GtS32Bundle from '../../s32-fraud-bundle/GtS32Bundle.vue'
import GtS33Bundle from '../../s33-ann14-bundle/GtS33Bundle.vue'
import GtS35Bundle from '../../s35-refinance-bundle/GtS35Bundle.vue'

/**
 * 不能只测 shared mapper：S32/S33/S35 各自有独立的 state composable、
 * visibleTabs 和 template 绑定。2026-10-31 曾出现四个已提交 bundle caller
 * 都 import 未提交组件的情况，本测试逐个挂载三个非 S34 宿主，确认
 * `assignedToMap[tab.wpCode]` 真正进了 BundleAssigneeDisplay。
 */
const CASES = [
  ['S32', GtS32Bundle, 'S32-1'],
  ['S33', GtS33Bundle, 'S33-1'],
  ['S35', GtS35Bundle, 'S35-1'],
] as const

const stubs = {
  ElTabs: { template: '<div class="tabs"><slot /></div>', props: ['modelValue'] },
  ElTabPane: { template: '<div class="pane"><slot /></div>', props: ['name', 'label', 'lazy'] },
  ElResult: { template: '<div><slot /><slot name="sub-title" /></div>' },
  ElAlert: { template: '<div><slot /></div>' },
  ElIcon: { template: '<i><slot /></i>' },
  ElRadioGroup: { template: '<div><slot /></div>' },
  ElRadioButton: { template: '<button><slot /></button>', props: ['value'] },
  GtAProgramConsole: { template: '<div />' },
  GtGridSheet: { template: '<div />' },
  GtS35DetailTable: { template: '<div />' },
  CircleCheckFilled: { template: '<i />' },
  Loading: { template: '<i />' },
  RemoveFilled: { template: '<i />' },
}

function item(wpCode: string, assignedTo: string | null) {
  return {
    id: `idx-${wpCode}`,
    wp_id: `wp-${wpCode}`,
    wp_code: wpCode,
    assigned_to: assignedTo,
    assigned_to_name: assignedTo ? '测试编制人' : null,
    assigned_to_username: assignedTo ? 'tester' : null,
    status: 'not_started',
  }
}

describe('S32/S33/S35 bundle 负责人标签接线', () => {
  beforeEach(() => {
    mockGetWpIndex.mockReset()
    mockApiGet.mockReset()
    mockApiGet.mockResolvedValue(null)
  })

  it.each(CASES)('%s：有 assigned_to 时显示真实标签和姓名', async (_family, component, wpCode) => {
    mockGetWpIndex.mockResolvedValue([item(wpCode, `user-${wpCode}`)])
    const wrapper = mount(component, { props: { wpId: 'bundle-parent' }, global: { stubs } })
    await flushPromises()

    const label = wrapper.find('.gt-bundle-assignee')
    expect(label.exists()).toBe(true)
    expect(label.text()).toContain('编制人')
    expect(label.text()).toContain('测试编制人')
    expect(label.attributes('aria-label')).toBe(`${wpCode} 编制人：测试编制人`)
  })

  it.each(CASES)('%s：assigned_to 为空时不渲染空负责人标签', async (_family, component, wpCode) => {
    mockGetWpIndex.mockResolvedValue([item(wpCode, null)])
    const wrapper = mount(component, { props: { wpId: 'bundle-parent' }, global: { stubs } })
    await flushPromises()

    expect(wrapper.find('.gt-bundle-assignee').exists()).toBe(false)
  })
})