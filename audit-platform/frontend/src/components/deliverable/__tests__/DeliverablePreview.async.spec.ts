import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const { docxLoads } = vi.hoisted(() => ({ docxLoads: { value: 0 } }))
vi.mock('@vue-office/docx', () => {
  docxLoads.value += 1
  throw new Error('chunk unavailable')
})
vi.mock('@vue-office/pdf', () => ({
  __esModule: true,
  default: { name: 'VueOfficePdf', template: '<div class="pdf-preview" />' },
}))
vi.mock('@vue-office/excel', () => ({
  __esModule: true,
  default: { name: 'VueOfficeExcel', template: '<div class="excel-preview" />' },
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ token: 'token' }) }))
vi.mock('@/utils/http', () => ({ downloadFile: vi.fn() }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))

import DeliverablePreview from '../DeliverablePreview.vue'

const global = {
  directives: {
    loading: {
      mounted: (el: HTMLElement, binding: { value: boolean }) => { el.dataset.loading = String(binding.value) },
      updated: (el: HTMLElement, binding: { value: boolean }) => { el.dataset.loading = String(binding.value) },
    },
  },
  stubs: {
    DraftWatermark: true,
    ElDialog: { template: '<section><slot /><slot name="footer" /></section>' },
    ElAlert: { props: ['title', 'description'], template: '<div class="alert" :data-title="title" :data-description="description" />' },
    ElButton: { template: '<button><slot /></button>' },
  },
}

describe('DeliverablePreview 异步 Office 边界', () => {
  it('chunk 连续两次加载失败后结束 loading 并显示中文下载降级', async () => {
    const wrapper = mount(DeliverablePreview, {
      props: { title: '预览', previewType: 'docx', url: '/api/file.docx' },
      global,
    })
    await flushPromises()
    await flushPromises()

    expect(docxLoads.value).toBeGreaterThanOrEqual(1)
    expect(wrapper.find('.deliverable-preview').attributes('data-loading')).toBe('false')
    expect(wrapper.find('.alert').attributes('data-title')).toBe('预览组件加载失败')
    expect(wrapper.text()).toContain('下载')
  })

  it('Office 缺少 URL 时不保持假 loading，切换同类型 URL 会重新进入 loading', async () => {
    const wrapper = mount(DeliverablePreview, {
      props: { title: '预览', previewType: 'pdf' },
      global,
    })
    await flushPromises()
    expect(wrapper.find('.deliverable-preview').attributes('data-loading')).toBe('false')

    await wrapper.setProps({ url: '/api/file.pdf' })
    expect(wrapper.find('.deliverable-preview').attributes('data-loading')).toBe('true')
  })
})
