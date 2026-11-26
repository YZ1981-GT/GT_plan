/**
 * GtWpAiReviewToolbar 的两处真实缺陷守卫（spec llm-linkage-audit-practice-closure 任务 15）。
 *
 * 2026-11-15 浏览器实测在 B1-1 底稿页抓到：
 * 1. 弹窗标题渲染成 `B1-1 undefined AI 复核` —— `label` 是可选 prop，未传时把
 *    `undefined` 直接拼进了标题（模板里裸插值 `${label}`）。
 * 2. 按钮可见角色漏了 `eqcr`，而后端 `review.workpaper` 的 `allowed_roles` 明确含 eqcr
 *    （ADR-LLM-008：页面角色集合必须与后端任务声明逐值一致）⇒ EQCR 看不到复核按钮，
 *    后端却允许其独立复核。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

const currentRole = { value: 'admin' }

vi.mock('@/composables/usePermissionMatrix', () => ({
  usePermissionMatrix: () => ({ currentRole }),
}))

// defineAsyncComponent 的 ReviewPanel 在弹窗内，这里只关心标题与可见性，桩掉即可。
// 🔴 不能只给 { default }：defineAsyncComponent 在包装层会读组件上的 `__isTeleport` / `__isKeepAlive`
//    等内部标记，缺了它们就是 8 条 "No __isTeleport export is defined on the mock"（2026-11-26 CI 实测）。
vi.mock('../AiReviewPanel.vue', () => ({
  __esModule: true,
  default: {
    name: 'AiReviewPanel',
    __isTeleport: false,
    __isKeepAlive: false,
    __isSuspense: false,
    template: '<div class="review-panel-stub" />',
  },
}))

import GtWpAiReviewToolbar from '../GtWpAiReviewToolbar.vue'

// 后端 `review.workpaper` 的 allowed_roles（现读 backend/app/services/ai_task_registry.py）
const BACKEND_REVIEW_ROLES = ['admin', 'partner', 'manager', 'qc', 'eqcr']
const BACKEND_DENIED_ROLES = ['auditor', 'readonly']

function mountWithRole(role: string, extra: Record<string, unknown> = {}) {
  currentRole.value = role
  return mount(GtWpAiReviewToolbar, {
    props: {
      wpId: 'wp-1',
      projectId: 'p-1',
      wpCodePrefix: 'B1-1',
      sheetName: '风险评估表-承接',
      year: 2025,
      ...extra,
    },
    global: {
      stubs: {
        'el-button': { template: '<button><slot /></button>' },
        'el-tooltip': { template: '<span><slot /></span>' },
        'el-dialog': {
          props: ['modelValue', 'title'],
          template: '<div class="dialog-stub" :data-title="title"><slot /></div>',
        },
      },
    },
  })
}

beforeEach(() => {
  currentRole.value = 'admin'
})

describe('GtWpAiReviewToolbar 弹窗标题', () => {
  it('未传 label 时标题不含 undefined', () => {
    const wrapper = mountWithRole('admin')
    const title = wrapper.find('.dialog-stub').attributes('data-title') ?? ''
    expect(title).not.toContain('undefined')
    expect(title).toBe('B1-1 AI 复核')
  })

  it('传了 label 时标题为「编码 科目名 AI 复核」', () => {
    const wrapper = mountWithRole('admin', { label: '风险评估' })
    const title = wrapper.find('.dialog-stub').attributes('data-title') ?? ''
    expect(title).toBe('B1-1 风险评估 AI 复核')
  })

  it('label 是空白串时按未传处理（不出现多余空格）', () => {
    const wrapper = mountWithRole('admin', { label: '   ' })
    const title = wrapper.find('.dialog-stub').attributes('data-title') ?? ''
    expect(title).toBe('B1-1 AI 复核')
  })
})

describe('GtWpAiReviewToolbar 角色可见性', () => {
  it.each(BACKEND_REVIEW_ROLES)('后端允许的角色 %s 能看到复核按钮', (role) => {
    const wrapper = mountWithRole(role)
    expect(wrapper.find('.wp-ai-review-toolbar').exists()).toBe(true)
  })

  it.each(BACKEND_DENIED_ROLES)('后端未允许的角色 %s 看不到复核按钮', (role) => {
    const wrapper = mountWithRole(role)
    expect(wrapper.find('.wp-ai-review-toolbar').exists()).toBe(false)
  })
})
