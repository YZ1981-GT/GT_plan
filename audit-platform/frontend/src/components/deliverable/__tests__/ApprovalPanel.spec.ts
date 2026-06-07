/**
 * ApprovalPanel 单元测试
 * Feature: audit-report-deliverable-center, Task 16.2 前端审批面板
 * Requirements: 7.4, 7.5（状态栏显示审批进度与审批人 / 审批动作触发）
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ApprovalPanel from '../ApprovalPanel.vue'

const globalConfig = {
  stubs: {
    'el-card': { template: '<div class="el-card"><slot name="header" /><slot /></div>' },
    'el-tag': { template: '<span class="el-tag"><slot /></span>' },
    'el-button': {
      props: ['type', 'size', 'loading'],
      emits: ['click'],
      template: '<button @click="$emit(\'click\')"><slot /></button>',
    },
  },
}

function mountPanel(propsOverride = {}) {
  return mount(ApprovalPanel, {
    props: { taskId: 'task-1', status: 'editing', ...propsOverride },
    global: globalConfig,
  })
}

describe('ApprovalPanel — 状态显示（需求 7.5）', () => {
  it('taskId 为空时不渲染', () => {
    const wrapper = mount(ApprovalPanel, {
      props: { taskId: null, status: 'editing' },
      global: globalConfig,
    })
    expect(wrapper.find('.approval-panel').exists()).toBe(false)
  })

  it('展示中文状态标签', () => {
    const wrapper = mountPanel({ status: 'pending_approval' })
    expect(wrapper.text()).toContain('待审批')
  })

  it('已确认状态展示中文标签', () => {
    const wrapper = mountPanel({ status: 'confirmed' })
    expect(wrapper.text()).toContain('已确认')
  })

  it('展示审批人', () => {
    const wrapper = mountPanel({ status: 'confirmed', approvalBy: '张三' })
    expect(wrapper.text()).toContain('审批人：张三')
  })

  it('展示驳回原因', () => {
    const wrapper = mountPanel({ status: 'editing', rejectReason: '格式不合规' })
    expect(wrapper.text()).toContain('驳回原因：格式不合规')
  })

  it('未知状态回退展示原始值', () => {
    const wrapper = mountPanel({ status: 'weird_status' })
    expect(wrapper.text()).toContain('weird_status')
  })
})

describe('ApprovalPanel — 动作触发（需求 7.1/7.2/7.3）', () => {
  it('canSubmit 时展示提交审批按钮并 emit submit', async () => {
    const wrapper = mountPanel({ status: 'editing', canSubmit: true })
    const btn = wrapper.findAll('button').find((b) => b.text().includes('提交审批'))
    expect(btn).toBeTruthy()
    await btn!.trigger('click')
    expect(wrapper.emitted('submit')).toBeTruthy()
  })

  it('canApprove 时展示批准/驳回按钮并 emit approve/reject', async () => {
    const wrapper = mountPanel({ status: 'pending_approval', canApprove: true })
    const buttons = wrapper.findAll('button')
    const approveBtn = buttons.find((b) => b.text().includes('批准'))
    const rejectBtn = buttons.find((b) => b.text().includes('驳回'))
    expect(approveBtn).toBeTruthy()
    expect(rejectBtn).toBeTruthy()
    await approveBtn!.trigger('click')
    await rejectBtn!.trigger('click')
    expect(wrapper.emitted('approve')).toBeTruthy()
    expect(wrapper.emitted('reject')).toBeTruthy()
  })

  it('非 canSubmit 时不展示提交审批按钮', () => {
    const wrapper = mountPanel({ status: 'editing', canSubmit: false })
    const btn = wrapper.findAll('button').find((b) => b.text().includes('提交审批'))
    expect(btn).toBeFalsy()
  })

  it('非 canApprove 时不展示批准按钮', () => {
    const wrapper = mountPanel({ status: 'pending_approval', canApprove: false })
    const btn = wrapper.findAll('button').find((b) => b.text().includes('批准'))
    expect(btn).toBeFalsy()
  })
})
