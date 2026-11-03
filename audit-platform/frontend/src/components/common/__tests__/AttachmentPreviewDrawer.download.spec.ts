/**
 * AttachmentPreviewDrawer 可选下载与宽度（spec attachment-inline-preview ADR-AIP-05）
 *
 * - 不传 downloadable / size：没有底部按钮、宽度 480px（旧调用方 DOM 不变）；
 * - downloadable：底部「下载」带文件名走已鉴权下载，失败交统一错误提示。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const downloadFile = vi.hoisted(() => vi.fn())
vi.mock('@/utils/http', () => ({ default: { get: vi.fn() }, downloadFile }))
const handleApiError = vi.hoisted(() => vi.fn())
vi.mock('@/utils/errorHandler', () => ({ handleApiError }))
vi.mock('@/components/attachment/preview/AttachmentPreviewCore.vue', () => ({
  default: { name: 'CoreStub', props: ['attachment', 'active', 'variant'], template: '<div class="core-stub" />' },
}))

import AttachmentPreviewDrawer from '../AttachmentPreviewDrawer.vue'

const stubs = {
  'el-drawer': {
    props: ['modelValue', 'size', 'title'],
    template: '<div class="drawer-stub" :data-size="size"><slot /><div v-if="$slots.footer" class="drawer-footer"><slot name="footer" /></div></div>',
  },
  'el-button': {
    template: '<button class="el-button" :aria-label="$attrs[\'aria-label\']" :data-testid="$attrs[\'data-testid\']" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'loading'],
    inheritAttrs: false,
  },
}

const ATT = {
  id: 'a1',
  name: '回函.pdf',
  type_hint: 'application/pdf',
  preview_url: '/api/attachments/a1/preview',
  download_url: '/api/attachments/a1/download',
}

describe('AttachmentPreviewDrawer 下载与宽度', () => {
  beforeEach(() => {
    downloadFile.mockReset()
    handleApiError.mockReset()
  })

  it('不传 downloadable / size：无底部按钮、宽度 480px', () => {
    const wrapper = mount(AttachmentPreviewDrawer, { props: { modelValue: true, attachment: ATT }, global: { stubs } })
    expect(wrapper.find('.drawer-footer').exists()).toBe(false)
    expect(wrapper.find('.drawer-stub').attributes('data-size')).toBe('480px')
  })

  it('downloadable：底部「下载」带文件名走已鉴权下载', async () => {
    downloadFile.mockResolvedValueOnce(undefined)
    const wrapper = mount(AttachmentPreviewDrawer, {
      props: { modelValue: true, attachment: ATT, downloadable: true, size: '60%' },
      global: { stubs },
    })
    expect(wrapper.find('.drawer-stub').attributes('data-size')).toBe('60%')
    await wrapper.find('[data-testid="attachment-preview-download"]').trigger('click')
    await flushPromises()
    expect(downloadFile).toHaveBeenCalledWith('/api/attachments/a1/download', { fileName: '回函.pdf', silent: true })
    expect(handleApiError).not.toHaveBeenCalled()
  })

  it('下载失败交统一错误提示', async () => {
    const err = new Error('403')
    downloadFile.mockRejectedValueOnce(err)
    const wrapper = mount(AttachmentPreviewDrawer, {
      props: { modelValue: true, attachment: ATT, downloadable: true },
      global: { stubs },
    })
    await wrapper.find('[data-testid="attachment-preview-download"]').trigger('click')
    await flushPromises()
    expect(handleApiError).toHaveBeenCalledWith(err, '下载附件')
  })
})
