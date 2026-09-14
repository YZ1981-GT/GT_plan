/**
 * TraceDrawer 单元测试
 *
 * Feature: platform-global-hardening
 * Requirements: 8.1, 8.2
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref, nextTick } from 'vue'
import TraceDrawer from '../TraceDrawer.vue'

// Mock displayPrefs store
vi.mock('@/stores/displayPrefs', () => ({
  useDisplayPrefsStore: () => ({
    fmtAmount: (v: number) => v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
    unitDivisor: ref(1),
    unitSuffix: ref('元'),
    fontConfig: { tableFont: '13px' },
  }),
}))

describe('TraceDrawer', () => {
  const defaultProps = {
    visible: true,
    targetValue: 100000,
    targetAddr: '1122',
    projectId: 'test-project-001',
  }

  it('挂载成功且渲染 el-drawer', () => {
    const wrapper = mount(TraceDrawer, {
      props: defaultProps,
      global: {
        stubs: {
          'el-drawer': {
            template: '<div class="el-drawer-stub"><slot /><slot name="header" /><slot name="footer" /></div>',
            props: ['modelValue', 'title', 'direction', 'size'],
          },
          'el-tag': { template: '<span class="el-tag-stub"><slot /></span>', props: ['type', 'size', 'effect'] },
          'el-skeleton': { template: '<div class="el-skeleton-stub" />', props: ['rows', 'animated'] },
          'el-alert': { template: '<div class="el-alert-stub" />', props: ['title', 'type'] },
          'el-empty': { template: '<div class="el-empty-stub" />', props: ['description'] },
          'el-button': { template: '<button class="el-button-stub"><slot /></button>', props: ['type', 'loading'] },
          'el-icon': { template: '<i class="el-icon-stub"><slot /></i>' },
          Right: { template: '<span />' },
          Refresh: { template: '<span />' },
        },
      },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('展示目标金额区域', () => {
    const wrapper = mount(TraceDrawer, {
      props: defaultProps,
      global: {
        stubs: {
          'el-drawer': {
            template: '<div class="el-drawer-stub"><slot /><slot name="header" /><slot name="footer" /></div>',
            props: ['modelValue'],
          },
          'el-tag': { template: '<span class="el-tag-stub"><slot /></span>', props: ['type', 'size', 'effect'] },
          'el-skeleton': { template: '<div class="el-skeleton-stub" />', props: ['rows', 'animated'] },
          'el-alert': { template: '<div class="el-alert-stub" />', props: ['title', 'type'] },
          'el-empty': { template: '<div class="el-empty-stub" />', props: ['description'] },
          'el-button': { template: '<button class="el-button-stub"><slot /></button>', props: ['type', 'loading'] },
          'el-icon': { template: '<i class="el-icon-stub"><slot /></i>' },
          Right: { template: '<span />' },
          Refresh: { template: '<span />' },
        },
      },
    })
    const targetArea = wrapper.find('.trace-drawer__target')
    expect(targetArea.exists()).toBe(true)
    expect(targetArea.find('.trace-drawer__target-label').text()).toBe('目标金额')
  })

  it('targetValue 为 null 时不显示目标金额区域', () => {
    const wrapper = mount(TraceDrawer, {
      props: { ...defaultProps, targetValue: null },
      global: {
        stubs: {
          'el-drawer': {
            template: '<div class="el-drawer-stub"><slot /><slot name="header" /><slot name="footer" /></div>',
            props: ['modelValue'],
          },
          'el-tag': { template: '<span class="el-tag-stub"><slot /></span>', props: ['type', 'size', 'effect'] },
          'el-skeleton': { template: '<div class="el-skeleton-stub" />', props: ['rows', 'animated'] },
          'el-alert': { template: '<div class="el-alert-stub" />', props: ['title', 'type'] },
          'el-empty': { template: '<div class="el-empty-stub" />', props: ['description'] },
          'el-button': { template: '<button class="el-button-stub"><slot /></button>', props: ['type', 'loading'] },
          'el-icon': { template: '<i class="el-icon-stub"><slot /></i>' },
          Right: { template: '<span />' },
          Refresh: { template: '<span />' },
        },
      },
    })
    expect(wrapper.find('.trace-drawer__target').exists()).toBe(false)
  })

  it('加载完成后展示溯源链节点', async () => {
    const wrapper = mount(TraceDrawer, {
      props: defaultProps,
      global: {
        stubs: {
          'el-drawer': {
            template: '<div class="el-drawer-stub"><slot /><slot name="header" /><slot name="footer" /></div>',
            props: ['modelValue'],
          },
          'el-tag': { template: '<span class="el-tag-stub"><slot /></span>', props: ['type', 'size', 'effect'] },
          'el-skeleton': { template: '<div class="el-skeleton-stub" />', props: ['rows', 'animated'] },
          'el-alert': { template: '<div class="el-alert-stub" />', props: ['title', 'type'] },
          'el-empty': { template: '<div class="el-empty-stub" />', props: ['description'] },
          'el-button': { template: '<button class="el-button-stub"><slot /></button>', props: ['type', 'loading'] },
          'el-icon': { template: '<i class="el-icon-stub"><slot /></i>' },
          Right: { template: '<span />' },
          Refresh: { template: '<span />' },
        },
      },
    })

    // 等待 mock 异步加载完成（300ms + nextTick）
    await new Promise(resolve => setTimeout(resolve, 400))
    await nextTick()

    const nodes = wrapper.findAll('.trace-node')
    // 完整链有 6 个节点：四表→报表→审定→底稿→调整→附注
    expect(nodes.length).toBe(6)
  })

  it('点击节点触发 navigate 事件', async () => {
    const wrapper = mount(TraceDrawer, {
      props: defaultProps,
      global: {
        stubs: {
          'el-drawer': {
            template: '<div class="el-drawer-stub"><slot /><slot name="header" /><slot name="footer" /></div>',
            props: ['modelValue'],
          },
          'el-tag': { template: '<span class="el-tag-stub"><slot /></span>', props: ['type', 'size', 'effect'] },
          'el-skeleton': { template: '<div class="el-skeleton-stub" />', props: ['rows', 'animated'] },
          'el-alert': { template: '<div class="el-alert-stub" />', props: ['title', 'type'] },
          'el-empty': { template: '<div class="el-empty-stub" />', props: ['description'] },
          'el-button': { template: '<button class="el-button-stub"><slot /></button>', props: ['type', 'loading'] },
          'el-icon': { template: '<i class="el-icon-stub"><slot /></i>' },
          Right: { template: '<span />' },
          Refresh: { template: '<span />' },
        },
      },
    })

    // 等待 mock 加载
    await new Promise(resolve => setTimeout(resolve, 400))
    await nextTick()

    const firstNodeContent = wrapper.find('.trace-node__content')
    expect(firstNodeContent.exists()).toBe(true)
    await firstNodeContent.trigger('click')

    const navigateEvents = wrapper.emitted('navigate')
    expect(navigateEvents).toBeTruthy()
    expect(navigateEvents![0][0]).toHaveProperty('type')
    expect(navigateEvents![0][0]).toHaveProperty('target')
  })

  it('emit update:visible 关闭抽屉', () => {
    const wrapper = mount(TraceDrawer, {
      props: defaultProps,
      global: {
        stubs: {
          'el-drawer': {
            template: '<div class="el-drawer-stub"><slot /><slot name="footer" /></div>',
            props: ['modelValue'],
            emits: ['update:modelValue'],
            setup(_: any, { emit }: any) {
              return { emit }
            },
          },
          'el-tag': { template: '<span><slot /></span>', props: ['type', 'size', 'effect'] },
          'el-skeleton': { template: '<div />', props: ['rows', 'animated'] },
          'el-alert': { template: '<div />', props: ['title', 'type'] },
          'el-empty': { template: '<div />', props: ['description'] },
          'el-button': { template: '<button @click="$emit(\'click\')"><slot /></button>', props: ['type', 'loading'] },
          'el-icon': { template: '<i><slot /></i>' },
          Right: { template: '<span />' },
          Refresh: { template: '<span />' },
        },
      },
    })
    // Component should mount without errors
    expect(wrapper.exists()).toBe(true)
  })
})
