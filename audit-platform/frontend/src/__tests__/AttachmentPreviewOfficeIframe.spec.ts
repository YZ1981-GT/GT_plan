/**
 * AttachmentPreviewDrawer - AT-2 Office iframe paths
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { attachments as P_att, officePreview } from '@/services/apiPaths'
import AttachmentPreviewDrawer from '@/components/common/AttachmentPreviewDrawer.vue'

vi.mock('@/components/attachment/preview/ExtendedFormatPreview.vue', () => ({
  default: {
    name: 'ExtendedFormatPreview',
    template: '<div class="extended-format-preview" data-testid="extended-stub" />',
    props: ['attachmentId', 'downloadUrl', 'fileName', 'typeHint'],
  },
}))

const stubs = {
  'el-drawer': {
    template: '<div class="el-drawer" :data-visible="modelValue"><slot /></div>',
    props: ['modelValue', 'title', 'direction', 'size'],
  },
  'el-empty': {
    template: '<div class="el-empty"><slot /></div>',
  },
  'el-button': {
    template: '<button class="el-button"><slot /></button>',
  },
  OcrStatusBadge: { template: '<span class="ocr-badge" />' },
}

describe('AT-2 apiPaths', () => {
  it('previewPdf path', () => {
    expect(P_att.previewPdf('abc-123')).toBe('/api/attachments/abc-123/preview-pdf')
  })

  it('officePreview.health path', () => {
    expect(officePreview.health).toBe('/api/office-preview/health')
  })

  it('preview and previewPdf differ', () => {
    expect(P_att.preview('xyz')).toBe('/api/attachments/xyz/preview')
    expect(P_att.previewPdf('xyz')).toBe('/api/attachments/xyz/preview-pdf')
    expect(P_att.preview('xyz')).not.toBe(P_att.previewPdf('xyz'))
  })
})

describe('AT-2 AttachmentPreviewDrawer routing', () => {
  it('docx uses previewPdf', () => {
    const wrapper = mount(AttachmentPreviewDrawer, {
      global: { stubs },
      props: {
        modelValue: true,
        attachment: {
          id: 'att-1',
          name: 'report.docx',
          type_hint: '',
          preview_url: '/api/attachments/att-1/preview',
          download_url: '/api/attachments/att-1/download',
        },
      },
    })
    expect(wrapper.find('iframe').attributes('src')).toBe('/api/attachments/att-1/preview-pdf')
  })

  it('xlsx uses previewPdf', () => {
    const wrapper = mount(AttachmentPreviewDrawer, {
      global: { stubs },
      props: {
        modelValue: true,
        attachment: {
          id: 'att-2',
          name: 'data.xlsx',
          type_hint: '',
          preview_url: '/api/attachments/att-2/preview',
          download_url: '/api/attachments/att-2/download',
        },
      },
    })
    expect(wrapper.find('iframe').attributes('src')).toBe('/api/attachments/att-2/preview-pdf')
  })

  it('pdf keeps preview_url', () => {
    const wrapper = mount(AttachmentPreviewDrawer, {
      global: { stubs },
      props: {
        modelValue: true,
        attachment: {
          id: 'att-3',
          name: 'doc.pdf',
          type_hint: 'application/pdf',
          preview_url: '/api/attachments/att-3/preview',
          download_url: '/api/attachments/att-3/download',
        },
      },
    })
    expect(wrapper.find('iframe').attributes('src')).toBe('/api/attachments/att-3/preview')
  })

  it('image renders img', () => {
    const wrapper = mount(AttachmentPreviewDrawer, {
      global: { stubs },
      props: {
        modelValue: true,
        attachment: {
          id: 'att-4',
          name: 'photo.png',
          type_hint: 'image/png',
          preview_url: '/api/attachments/att-4/preview',
          download_url: '/api/attachments/att-4/download',
        },
      },
    })
    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.find('img').exists()).toBe(true)
  })

  it('zip mounts ExtendedFormatPreview', () => {
    const wrapper = mount(AttachmentPreviewDrawer, {
      global: { stubs },
      props: {
        modelValue: true,
        attachment: {
          id: 'att-5',
          name: 'archive.zip',
          type_hint: 'application/zip',
          preview_url: '',
          download_url: '/api/attachments/att-5/download',
        },
      },
    })
    expect(wrapper.find('[data-testid="extended-stub"]').exists()).toBe(true)
  })

  it('pptx uses previewPdf', () => {
    const wrapper = mount(AttachmentPreviewDrawer, {
      global: { stubs },
      props: {
        modelValue: true,
        attachment: {
          id: 'att-6',
          name: 'slides.pptx',
          preview_url: '/api/attachments/att-6/preview',
          download_url: '/api/attachments/att-6/download',
        },
      },
    })
    expect(wrapper.find('iframe').attributes('src')).toBe('/api/attachments/att-6/preview-pdf')
  })
})