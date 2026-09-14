/**
 * WpPopupDocxEditor — 「完整编辑」按钮导航测试
 *
 * 验证 A16-x 弹窗中的「完整编辑」按钮调用 navigateToWorkpaper
 * 正确传递 wpCode 和 projectId，触发 A16-x → A16?version=A16-x 重定向。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

// ─── Mock 依赖 ──────────────────────────────────────────────────────────────

const mockNavigateToWorkpaper = vi.fn()

vi.mock('@/composables/useWorkpaperNavigation', () => ({
  useWorkpaperNavigation: () => ({
    navigateToWorkpaper: mockNavigateToWorkpaper,
    parseIndexRefs: vi.fn().mockReturnValue([]),
  }),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({
    params: { projectId: 'proj-test-001' },
  }),
  useRouter: () => ({
    push: vi.fn(),
  }),
}))

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn().mockResolvedValue({ available: false }),
    put: vi.fn().mockResolvedValue({}),
  },
}))

vi.mock('@/utils/http', () => ({
  downloadFile: vi.fn(),
}))

// Mock OnlyOfficeEditor as stub
vi.mock('@/components/deliverable/OnlyOfficeEditor.vue', () => ({
  default: defineComponent({
    name: 'OnlyOfficeEditorStub',
    render: () => h('div', 'stub'),
  }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), success: vi.fn(), error: vi.fn() },
}))

import WpPopupDocxEditor from '@/components/workpaper/WpPopupDocxEditor.vue'

const globalStubs = {
  'el-alert': { template: '<div class="el-alert"><slot /><slot name="title" /></div>' },
  'el-button': { template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>', emits: ['click'] },
  'el-divider': { template: '<span class="el-divider" />' },
  'el-tag': { template: '<span class="el-tag"><slot /></span>' },
  'el-radio-group': { template: '<div class="el-radio-group"><slot /></div>' },
  'el-radio-button': { template: '<label class="el-radio-button"><slot /></label>' },
}

describe('WpPopupDocxEditor — 完整编辑按钮', () => {
  beforeEach(() => {
    mockNavigateToWorkpaper.mockReset()
  })

  it('A16-3 弹窗显示「完整编辑」按钮', () => {
    const wrapper = mount(WpPopupDocxEditor, {
      props: { wpCode: 'A16-3', projectId: 'proj-test-001' },
      global: { stubs: globalStubs },
    })
    const buttons = wrapper.findAll('button')
    const fullEditBtn = buttons.find((b) => b.text().includes('完整编辑'))
    expect(fullEditBtn).toBeTruthy()
  })

  it('A16-7 弹窗显示「完整编辑」按钮', () => {
    const wrapper = mount(WpPopupDocxEditor, {
      props: { wpCode: 'A16-7', projectId: 'proj-002' },
      global: { stubs: globalStubs },
    })
    const buttons = wrapper.findAll('button')
    const fullEditBtn = buttons.find((b) => b.text().includes('完整编辑'))
    expect(fullEditBtn).toBeTruthy()
  })

  it('A8-1 弹窗不显示「完整编辑」按钮', () => {
    const wrapper = mount(WpPopupDocxEditor, {
      props: { wpCode: 'A8-1', projectId: 'proj-test-001' },
      global: { stubs: globalStubs },
    })
    const buttons = wrapper.findAll('button')
    const fullEditBtn = buttons.find((b) => b.text().includes('完整编辑'))
    expect(fullEditBtn).toBeFalsy()
  })

  it('点击「完整编辑」调用 navigateToWorkpaper(wpCode, projectId)', async () => {
    const wrapper = mount(WpPopupDocxEditor, {
      props: { wpCode: 'A16-3', projectId: 'proj-test-001' },
      global: { stubs: globalStubs },
    })
    const buttons = wrapper.findAll('button')
    const fullEditBtn = buttons.find((b) => b.text().includes('完整编辑'))
    expect(fullEditBtn).toBeTruthy()

    await fullEditBtn!.trigger('click')

    expect(mockNavigateToWorkpaper).toHaveBeenCalledWith('A16-3', 'proj-test-001')
  })

  it('未传 projectId 时从 route.params 读取', async () => {
    const wrapper = mount(WpPopupDocxEditor, {
      props: { wpCode: 'A16-1' },
      global: { stubs: globalStubs },
    })
    const buttons = wrapper.findAll('button')
    const fullEditBtn = buttons.find((b) => b.text().includes('完整编辑'))
    expect(fullEditBtn).toBeTruthy()

    await fullEditBtn!.trigger('click')

    // 从 route.params.projectId = 'proj-test-001' 读取
    expect(mockNavigateToWorkpaper).toHaveBeenCalledWith('A16-1', 'proj-test-001')
  })
})
