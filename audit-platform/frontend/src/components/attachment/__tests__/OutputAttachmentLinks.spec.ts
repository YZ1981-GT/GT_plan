import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const get = vi.fn()
const post = vi.fn()
const del = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => get(...args),
    post: (...args: any[]) => post(...args),
    delete: (...args: any[]) => del(...args),
  },
}))
vi.mock('@/composables/usePermissionMatrix', () => ({
  usePermissionMatrix: () => ({ canDo: () => true }),
}))
vi.mock('@/stores/project', () => ({ useProjectStore: () => ({ projectStatus: 'execution' }) }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('element-plus', () => ({ ElMessage: { success: vi.fn() } }))
vi.mock('../AttachmentEyeButton.vue', () => ({
  default: { props: ['attachmentId'], template: '<button class="eye">{{ attachmentId }}</button>' },
}))

import OutputAttachmentLinks from '../OutputAttachmentLinks.vue'

const button = { template: '<button v-bind="$attrs" @click="$emit(\'click\')"><slot /></button>' }
const stubs = {
  'el-button': button,
  'el-alert': { props: ['title'], template: '<div class="alert">{{ title }}<slot /></div>' },
  'el-dialog': { template: '<div><slot /><slot name="footer" /></div>' },
  'el-select': { template: '<select><slot /></select>' },
  'el-option': true,
  'el-empty': true,
}

const mountLinks = (initialAttachments?: any[]) => mount(OutputAttachmentLinks, {
  props: {
    projectId: 'p1', objectType: 'report_row', targetType: 'report_row',
    targetRef: 'BS-001', resource: 'report', initialAttachments,
  },
  global: { stubs },
})

describe('OutputAttachmentLinks', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
    del.mockReset()
  })

  it('使用父级已有溯源结果，不重复请求，并可预览', async () => {
    const wrapper = mountLinks([{ id: 'l1', attachment_id: 'a1', target_type: 'report_row', target_ref: 'BS-001', file_name: '依据.pdf' }])
    await flushPromises()
    expect(get).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('依据.pdf')
    expect(wrapper.find('.eye').exists()).toBe(true)
  })

  it('没有初始值时查询统一 lineage，失败明确区别于空附件', async () => {
    get.mockRejectedValueOnce(new Error('offline'))
    const wrapper = mountLinks()
    await flushPromises()
    expect(get).toHaveBeenCalledWith('/api/projects/p1/lineage', expect.objectContaining({
      params: { object_type: 'report_row', object_id: 'BS-001', direction: 'both' },
      _dedupe: false,
    }))
    expect(wrapper.text()).toContain('不能据此判断为无附件')
  })

  it('关联和解除使用稳定 target_ref，随后重取统一结果', async () => {
    get
      .mockResolvedValueOnce([{ id: 'a1', file_name: '依据.pdf' }])
      .mockResolvedValueOnce({ attachments: [{ id: 'l1', attachment_id: 'a1', target_type: 'report_row', target_ref: 'BS-001', file_name: '依据.pdf' }] })
      .mockResolvedValueOnce({ attachments: [] })
    post.mockResolvedValue({ id: 'l1' })
    del.mockResolvedValue({})
    const wrapper = mountLinks([])
    await wrapper.get('[data-testid="output-attachment-add"]').trigger('click')
    await flushPromises()
    ;(wrapper.vm as any).selectedId = 'a1'
    await (wrapper.vm as any).linkSelected()
    expect(post).toHaveBeenCalledWith('/api/attachments/a1/link', {
      target_type: 'report_row', target_ref: 'BS-001',
    }, { _silent: true })
    await (wrapper.vm as any).unlink({ id: 'l1', attachment_id: 'a1' })
    expect(del).toHaveBeenCalledWith('/api/attachments/a1/link/l1', { _silent: true })
  })
})
