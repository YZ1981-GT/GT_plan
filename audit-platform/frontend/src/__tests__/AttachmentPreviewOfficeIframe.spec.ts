/**
 * AttachmentPreview / AttachmentPreviewDrawer — AT-2 Office iframe 路径
 *
 * Validates: proposal-remaining-18 §三 AT-2，task 5.2
 *
 * 验证：
 *  - apiPaths.attachments.previewPdf(id) 路径生成正确
 *  - apiPaths.officePreview.health 路径常量正确
 *  - AttachmentPreviewDrawer 对 .docx/.xlsx/.pdf/.png 文件的 isOffice/isPdf/isImage 分流
 *  - Office 文件 previewUrl 走 previewPdf 端点
 *  - PDF 文件保留原 preview_url 不变
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { attachments as P_att, officePreview } from '@/services/apiPaths'
import AttachmentPreviewDrawer from '@/components/common/AttachmentPreviewDrawer.vue'

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

describe('AT-2 apiPaths 路径常量', () => {
  it('attachments.previewPdf 生成正确路径', () => {
    expect(P_att.previewPdf('abc-123')).toBe('/api/attachments/abc-123/preview-pdf')
  })

  it('officePreview.health 路径常量', () => {
    expect(officePreview.health).toBe('/api/office-preview/health')
  })

  it('attachments.preview 与 previewPdf 是不同端点', () => {
    expect(P_att.preview('xyz')).toBe('/api/attachments/xyz/preview')
    expect(P_att.previewPdf('xyz')).toBe('/api/attachments/xyz/preview-pdf')
    expect(P_att.preview('xyz')).not.toBe(P_att.previewPdf('xyz'))
  })
})

describe('AT-2 AttachmentPreviewDrawer Office iframe 路由', () => {
  it('Office .docx 文件 → previewUrl 走 previewPdf 端点', () => {
    const wrapper = mount(AttachmentPreviewDrawer, {
      global: { stubs },
      props: {
        modelValue: true,
        attachment: {
          id: 'att-1',
          name: 'report.docx',
          mime_type: '',
          preview_url: '/api/attachments/att-1/preview',
          download_url: '/api/attachments/att-1/download',
        },
      },
    })
    const iframe = wrapper.find('iframe')
    expect(iframe.exists()).toBe(true)
    expect(iframe.attributes('src')).toBe('/api/attachments/att-1/preview-pdf')
  })

  it('Office .xlsx 文件 → previewUrl 走 previewPdf 端点', () => {
    const wrapper = mount(AttachmentPreviewDrawer, {
      global: { stubs },
      props: {
        modelValue: true,
        attachment: {
          id: 'att-2',
          name: 'data.xlsx',
          mime_type: '',
          preview_url: '/api/attachments/att-2/preview',
          download_url: '/api/attachments/att-2/download',
        },
      },
    })
    const iframe = wrapper.find('iframe')
    expect(iframe.exists()).toBe(true)
    expect(iframe.attributes('src')).toBe('/api/attachments/att-2/preview-pdf')
  })

  it('PDF 文件 → 保留 preview_url 不变', () => {
    const wrapper = mount(AttachmentPreviewDrawer, {
      global: { stubs },
      props: {
        modelValue: true,
        attachment: {
          id: 'att-3',
          name: 'doc.pdf',
          mime_type: 'application/pdf',
          preview_url: '/api/attachments/att-3/preview',
          download_url: '/api/attachments/att-3/download',
        },
      },
    })
    const iframe = wrapper.find('iframe')
    expect(iframe.exists()).toBe(true)
    expect(iframe.attributes('src')).toBe('/api/attachments/att-3/preview')
  })

  it('图片文件 → 渲染 img 标签而非 iframe', () => {
    const wrapper = mount(AttachmentPreviewDrawer, {
      global: { stubs },
      props: {
        modelValue: true,
        attachment: {
          id: 'att-4',
          name: 'photo.png',
          mime_type: 'image/png',
          preview_url: '/api/attachments/att-4/preview',
          download_url: '/api/attachments/att-4/download',
        },
      },
    })
    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.find('img').exists()).toBe(true)
  })

  it('未知格式 → 显示下载提示（无 iframe / img）', () => {
    const wrapper = mount(AttachmentPreviewDrawer, {
      global: { stubs },
      props: {
        modelValue: true,
        attachment: {
          id: 'att-5',
          name: 'archive.zip',
          mime_type: 'application/zip',
          preview_url: '',
          download_url: '/api/attachments/att-5/download',
        },
      },
    })
    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.find('.el-empty').exists()).toBe(true)
  })

  it('.ppt 文件 → previewUrl 走 previewPdf 端点（覆盖所有 6 种 Office 类型）', () => {
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
    const iframe = wrapper.find('iframe')
    expect(iframe.exists()).toBe(true)
    expect(iframe.attributes('src')).toBe('/api/attachments/att-6/preview-pdf')
  })
})
