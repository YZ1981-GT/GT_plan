/**
 * GtRowActions 组件测试
 * Property 16: GtRowActions 可见性逻辑
 * Validates: Requirements 9.2, 9.3, 9.5
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import GtRowActions from '@/components/common/GtRowActions.vue'

describe('GtRowActions', () => {
  it('renders nothing when actions is empty', () => {
    const wrapper = mount(GtRowActions, {
      props: { actions: [] },
      global: {
        stubs: { 'el-button': true, 'el-dropdown': true, 'el-dropdown-menu': true, 'el-dropdown-item': true, 'el-icon': true, ArrowDown: true },
      },
    })
    // With 0 non-hidden actions, the component should not render
    expect(wrapper.find('.gt-row-actions').exists()).toBe(false)
  })

  it('renders 1 button directly without dropdown', () => {
    const wrapper = mount(GtRowActions, {
      props: {
        actions: [{ key: 'edit', label: '编辑', priority: 1 }],
      },
      global: {
        stubs: { 'el-button': false, 'el-dropdown': true, 'el-dropdown-menu': true, 'el-dropdown-item': true, 'el-icon': true, ArrowDown: true },
      },
    })
    expect(wrapper.find('.gt-row-actions').exists()).toBe(true)
    // 1 visible button, no dropdown
    const vm = wrapper.vm as any
    expect(vm.visibleActions.length).toBe(1)
    expect(vm.dropdownActions.length).toBe(0)
  })

  it('renders 2 buttons directly without dropdown (maxVisible=2)', () => {
    const wrapper = mount(GtRowActions, {
      props: {
        actions: [
          { key: 'edit', label: '编辑', priority: 1 },
          { key: 'delete', label: '删除', priority: 2 },
        ],
      },
      global: {
        stubs: { 'el-button': false, 'el-dropdown': true, 'el-dropdown-menu': true, 'el-dropdown-item': true, 'el-icon': true, ArrowDown: true },
      },
    })
    const vm = wrapper.vm as any
    expect(vm.visibleActions.length).toBe(2)
    expect(vm.dropdownActions.length).toBe(0)
  })

  it('renders 2 visible + 3 in dropdown when 5 actions provided', () => {
    const wrapper = mount(GtRowActions, {
      props: {
        actions: [
          { key: 'edit', label: '编辑', priority: 1 },
          { key: 'view', label: '查看', priority: 2 },
          { key: 'copy', label: '复制', priority: 3 },
          { key: 'archive', label: '归档', priority: 4 },
          { key: 'delete', label: '删除', priority: 5, danger: true },
        ],
      },
      global: {
        stubs: { 'el-button': false, 'el-dropdown': false, 'el-dropdown-menu': true, 'el-dropdown-item': true, 'el-icon': true, ArrowDown: true },
      },
    })
    const vm = wrapper.vm as any
    expect(vm.visibleActions.length).toBe(2)
    expect(vm.dropdownActions.length).toBe(3)
    // Verify priority sort: lowest priority values first
    expect(vm.visibleActions[0].key).toBe('edit')
    expect(vm.visibleActions[1].key).toBe('view')
  })

  it('filters out hidden actions', () => {
    const wrapper = mount(GtRowActions, {
      props: {
        actions: [
          { key: 'edit', label: '编辑', priority: 1 },
          { key: 'hidden-action', label: '隐藏', priority: 0, hidden: true },
          { key: 'delete', label: '删除', priority: 2 },
        ],
      },
      global: {
        stubs: { 'el-button': false, 'el-dropdown': true, 'el-dropdown-menu': true, 'el-dropdown-item': true, 'el-icon': true, ArrowDown: true },
      },
    })
    const vm = wrapper.vm as any
    // hidden action is filtered out, only 2 remain
    expect(vm.sortedActions.length).toBe(2)
    expect(vm.visibleActions.length).toBe(2)
    expect(vm.dropdownActions.length).toBe(0)
    // hidden-action should not appear
    expect(vm.sortedActions.find((a: any) => a.key === 'hidden-action')).toBeUndefined()
  })

  it('sorts by priority ascending (lowest priority = most visible)', () => {
    const wrapper = mount(GtRowActions, {
      props: {
        actions: [
          { key: 'c', label: 'C', priority: 30 },
          { key: 'a', label: 'A', priority: 10 },
          { key: 'b', label: 'B', priority: 20 },
          { key: 'd', label: 'D', priority: 5 },
        ],
        maxVisible: 2,
      },
      global: {
        stubs: { 'el-button': false, 'el-dropdown': false, 'el-dropdown-menu': true, 'el-dropdown-item': true, 'el-icon': true, ArrowDown: true },
      },
    })
    const vm = wrapper.vm as any
    // Sorted: d(5), a(10), b(20), c(30)
    expect(vm.visibleActions[0].key).toBe('d')
    expect(vm.visibleActions[1].key).toBe('a')
    expect(vm.dropdownActions[0].key).toBe('b')
    expect(vm.dropdownActions[1].key).toBe('c')
  })
})
