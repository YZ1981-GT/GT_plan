import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import DrilldownBreadcrumb from '../DrilldownBreadcrumb.vue'
import type { NavigationEntry } from '@/composables/useNavigationStack'

describe('DrilldownBreadcrumb', () => {
  const makeEntry = (path: string, label?: string): NavigationEntry => ({
    source_view: path,
    label,
  })

  it('does not render when stack is empty', () => {
    const wrapper = mount(DrilldownBreadcrumb, {
      props: { stack: [] },
    })
    expect(wrapper.find('.gt-breadcrumb').exists()).toBe(false)
  })

  it('renders all items when stack <= 5', () => {
    const stack = [
      makeEntry('/projects/1/trial-balance', '试算表'),
      makeEntry('/projects/1/drilldown', '穿透查询'),
      makeEntry('/projects/1/ledger', '明细账'),
    ]
    const wrapper = mount(DrilldownBreadcrumb, {
      props: { stack },
    })
    expect(wrapper.findAll('.gt-breadcrumb-item')).toHaveLength(3)
    expect(wrapper.text()).toContain('试算表')
    expect(wrapper.text()).toContain('穿透查询')
    expect(wrapper.text()).toContain('明细账')
  })

  it('marks last item as current (not clickable)', () => {
    const stack = [
      makeEntry('/projects/1/trial-balance', '试算表'),
      makeEntry('/projects/1/ledger', '明细账'),
    ]
    const wrapper = mount(DrilldownBreadcrumb, {
      props: { stack },
    })
    const items = wrapper.findAll('.gt-breadcrumb-item')
    expect(items[items.length - 1].classes()).toContain('gt-breadcrumb-item--current')
  })

  it('emits jump(index) when clicking non-current item', async () => {
    const stack = [
      makeEntry('/projects/1/trial-balance', '试算表'),
      makeEntry('/projects/1/drilldown', '穿透查询'),
      makeEntry('/projects/1/ledger', '明细账'),
    ]
    const wrapper = mount(DrilldownBreadcrumb, {
      props: { stack },
    })
    await wrapper.findAll('.gt-breadcrumb-item')[0].trigger('click')
    expect(wrapper.emitted('jump')?.[0]).toEqual([0])
  })

  it('does not emit jump when clicking current (last) item', async () => {
    const stack = [
      makeEntry('/projects/1/trial-balance', '试算表'),
      makeEntry('/projects/1/ledger', '明细账'),
    ]
    const wrapper = mount(DrilldownBreadcrumb, {
      props: { stack },
    })
    const items = wrapper.findAll('.gt-breadcrumb-item')
    await items[items.length - 1].trigger('click')
    expect(wrapper.emitted('jump')).toBeUndefined()
  })

  it('shows ellipsis when stack > 5', () => {
    const stack = Array.from({ length: 7 }, (_, i) =>
      makeEntry(`/projects/1/page-${i}`, `页面${i}`)
    )
    const wrapper = mount(DrilldownBreadcrumb, {
      props: { stack },
      global: { stubs: { 'el-popover': { template: '<div><slot name="reference" /><slot /></div>' } } },
    })
    expect(wrapper.find('.gt-breadcrumb-ellipsis').exists()).toBe(true)
  })

  it('infers label from path when label not provided', () => {
    const stack = [
      makeEntry('/projects/1/trial-balance'),
      makeEntry('/projects/1/adjustments'),
    ]
    const wrapper = mount(DrilldownBreadcrumb, {
      props: { stack },
    })
    expect(wrapper.text()).toContain('试算表')
    expect(wrapper.text()).toContain('调整分录')
  })

  it('shows ↓ icon for direction=down items', () => {
    const stack: NavigationEntry[] = [
      { source_view: '/projects/1/reports', label: '报表', direction: 'down' },
      { source_view: '/projects/1/trial-balance', label: '试算表' },
    ]
    const wrapper = mount(DrilldownBreadcrumb, {
      props: { stack },
    })
    const directionIcons = wrapper.findAll('.gt-breadcrumb-direction')
    expect(directionIcons).toHaveLength(1)
    expect(directionIcons[0].text()).toBe('↓')
    expect(directionIcons[0].classes()).toContain('gt-breadcrumb-direction--down')
  })

  it('shows ↑ icon for direction=up items', () => {
    const stack: NavigationEntry[] = [
      { source_view: '/projects/1/disclosure-notes', label: '附注', direction: 'up' },
      { source_view: '/projects/1/trial-balance', label: '试算表' },
    ]
    const wrapper = mount(DrilldownBreadcrumb, {
      props: { stack },
    })
    const directionIcons = wrapper.findAll('.gt-breadcrumb-direction')
    expect(directionIcons).toHaveLength(1)
    expect(directionIcons[0].text()).toBe('↑')
    expect(directionIcons[0].classes()).toContain('gt-breadcrumb-direction--up')
  })

  it('shows no direction icon when direction is not specified (backward compatible)', () => {
    const stack: NavigationEntry[] = [
      { source_view: '/projects/1/trial-balance', label: '试算表' },
      { source_view: '/projects/1/ledger', label: '明细账' },
    ]
    const wrapper = mount(DrilldownBreadcrumb, {
      props: { stack },
    })
    expect(wrapper.findAll('.gt-breadcrumb-direction')).toHaveLength(0)
  })

  it('shows mixed direction icons in multi-item stack', () => {
    const stack: NavigationEntry[] = [
      { source_view: '/projects/1/disclosure-notes', label: '附注', direction: 'up' },
      { source_view: '/projects/1/reports', label: '报表', direction: 'down' },
      { source_view: '/projects/1/trial-balance', label: '试算表' },
    ]
    const wrapper = mount(DrilldownBreadcrumb, {
      props: { stack },
    })
    const directionIcons = wrapper.findAll('.gt-breadcrumb-direction')
    expect(directionIcons).toHaveLength(2)
    expect(directionIcons[0].text()).toBe('↑')
    expect(directionIcons[1].text()).toBe('↓')
  })
})
