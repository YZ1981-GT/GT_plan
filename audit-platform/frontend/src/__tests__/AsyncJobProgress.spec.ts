/**
 * AsyncJobProgress.vue 组件测试
 *
 * 验证 props→render + emit 行为：
 * - 进度条百分比渲染
 * - 状态切换（completed/failed）对应 UI 变化
 * - cancel/retry/close 事件触发
 * - title/message 渲染
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AsyncJobProgress from '@/components/common/AsyncJobProgress.vue'

const stubs = {
  'el-progress': {
    template: '<div class="el-progress" :data-percentage="percentage" :data-status="status"><slot /></div>',
    props: ['percentage', 'status', 'strokeWidth', 'textInside', 'showText'],
  },
  'el-tag': {
    template: '<span class="el-tag" :data-type="type"><slot /></span>',
    props: ['type', 'size', 'effect'],
  },
  'el-button': {
    template: '<button class="el-button" :data-type="type" @click="$emit(\'click\')"><slot /></button>',
    emits: ['click'],
    props: ['type', 'size', 'plain', 'link'],
  },
}

function factory(props: Record<string, any> = {}) {
  return mount(AsyncJobProgress, {
    props: {
      visible: true,
      ...props,
    },
    global: { stubs },
  })
}

describe('AsyncJobProgress', () => {
  it('renders progress bar at 50% when status=running, percentage=50', () => {
    const wrapper = factory({ status: 'running', percentage: 50 })
    const progress = wrapper.find('.el-progress')
    expect(progress.exists()).toBe(true)
    expect(progress.attributes('data-percentage')).toBe('50')
  })

  it('renders success state when status=completed', () => {
    const wrapper = factory({ status: 'completed', percentage: 100 })
    const progress = wrapper.find('.el-progress')
    expect(progress.attributes('data-status')).toBe('success')
    // completed state should have the completed class
    expect(wrapper.find('.gt-async-job-progress--completed').exists()).toBe(true)
  })

  it('shows close button when status=completed', () => {
    const wrapper = factory({ status: 'completed', percentage: 100, closable: true })
    const buttons = wrapper.findAll('.el-button')
    const closeBtn = buttons.find((b) => b.text().includes('关闭'))
    expect(closeBtn).toBeDefined()
  })

  it('renders exception state when status=failed', () => {
    const wrapper = factory({ status: 'failed', percentage: 30 })
    const progress = wrapper.find('.el-progress')
    expect(progress.attributes('data-status')).toBe('exception')
    expect(wrapper.find('.gt-async-job-progress--failed').exists()).toBe(true)
  })

  it('shows retry button when status=failed', () => {
    const wrapper = factory({ status: 'failed', retryable: true })
    const buttons = wrapper.findAll('.el-button')
    const retryBtn = buttons.find((b) => b.text().includes('重试'))
    expect(retryBtn).toBeDefined()
  })

  it('emits cancel when cancel button clicked', async () => {
    const wrapper = factory({ status: 'running', cancelable: true })
    const buttons = wrapper.findAll('.el-button')
    const cancelBtn = buttons.find((b) => b.text().includes('取消'))
    expect(cancelBtn).toBeDefined()
    await cancelBtn!.trigger('click')
    expect(wrapper.emitted('cancel')).toBeTruthy()
    expect(wrapper.emitted('cancel')!.length).toBe(1)
  })

  it('emits retry when retry button clicked', async () => {
    const wrapper = factory({ status: 'failed', retryable: true })
    const buttons = wrapper.findAll('.el-button')
    const retryBtn = buttons.find((b) => b.text().includes('重试'))
    expect(retryBtn).toBeDefined()
    await retryBtn!.trigger('click')
    expect(wrapper.emitted('retry')).toBeTruthy()
    expect(wrapper.emitted('retry')!.length).toBe(1)
  })

  it('emits close when close button clicked', async () => {
    const wrapper = factory({ status: 'completed', closable: true })
    const buttons = wrapper.findAll('.el-button')
    const closeBtn = buttons.find((b) => b.text().includes('关闭'))
    expect(closeBtn).toBeDefined()
    await closeBtn!.trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()
    expect(wrapper.emitted('close')!.length).toBe(1)
  })

  it('renders title prop correctly', () => {
    const wrapper = factory({ title: '导入进度' })
    expect(wrapper.find('.gt-async-job-progress__title').text()).toBe('导入进度')
  })

  it('renders message prop correctly', () => {
    const wrapper = factory({ message: '正在处理第 3/10 个文件' })
    expect(wrapper.find('.gt-async-job-progress__message').text()).toBe('正在处理第 3/10 个文件')
  })

  it('clamps percentage to 0-100 range', () => {
    const wrapper = factory({ percentage: 150, status: 'running' })
    const progress = wrapper.find('.el-progress')
    expect(progress.attributes('data-percentage')).toBe('100')
  })

  it('does not render when visible=false', () => {
    const wrapper = factory({ visible: false })
    expect(wrapper.find('.gt-async-job-progress').exists()).toBe(false)
  })

  it('does not show cancel button when cancelable=false', () => {
    const wrapper = factory({ status: 'running', cancelable: false })
    const buttons = wrapper.findAll('.el-button')
    const cancelBtn = buttons.find((b) => b.text().includes('取消'))
    expect(cancelBtn).toBeUndefined()
  })
})
