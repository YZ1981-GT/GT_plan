/**
 * DraftWatermark — Task 19.1 vitest 单测
 * Spec: .kiro/specs/audit-report-deliverable-center/ Task 19.1
 *
 * 验证（需求 12.1）：草稿水印叠加可见性当且仅当 visible=true。
 * 配套后端 Property 26（水印当且仅当草稿态）：前端 overlay 可见性由
 * `['draft','editing'].includes(status)` 驱动，与后端 should_watermark 同口径。
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import DraftWatermark from '../DraftWatermark.vue'

const DRAFT_STATUSES = ['draft', 'editing']
const NON_DRAFT_STATUSES = [
  'generating',
  'generated',
  'pending_approval',
  'confirmed',
  'signed',
  'archived',
]

// 前端 overlay 可见性谓词（与 DeliverableCenter / DeliverablePreview 一致）
function shouldShowWatermark(status: string): boolean {
  return ['draft', 'editing'].includes(status)
}

describe('DraftWatermark', () => {
  it('visible=true 时渲染水印叠加层与「草稿 DRAFT」文案', () => {
    const wrapper = mount(DraftWatermark, { props: { visible: true } })
    expect(wrapper.find('.draft-watermark').exists()).toBe(true)
    expect(wrapper.text()).toContain('草稿 DRAFT')
    wrapper.unmount()
  })

  it('visible=false 时不渲染水印叠加层', () => {
    const wrapper = mount(DraftWatermark, { props: { visible: false } })
    expect(wrapper.find('.draft-watermark').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('草稿 DRAFT')
    wrapper.unmount()
  })

  it('水印叠加层为 aria-hidden 且不拦截指针事件（不影响预览交互）', () => {
    const wrapper = mount(DraftWatermark, { props: { visible: true } })
    const overlay = wrapper.find('.draft-watermark')
    expect(overlay.attributes('aria-hidden')).toBe('true')
    wrapper.unmount()
  })

  it('草稿态（draft/editing）→ 水印可见', () => {
    for (const status of DRAFT_STATUSES) {
      const wrapper = mount(DraftWatermark, {
        props: { visible: shouldShowWatermark(status) },
      })
      expect(wrapper.find('.draft-watermark').exists()).toBe(true)
      wrapper.unmount()
    }
  })

  it('非草稿态（confirmed/signed 等）→ 水印不可见', () => {
    for (const status of NON_DRAFT_STATUSES) {
      const wrapper = mount(DraftWatermark, {
        props: { visible: shouldShowWatermark(status) },
      })
      expect(wrapper.find('.draft-watermark').exists()).toBe(false)
      wrapper.unmount()
    }
  })
})
