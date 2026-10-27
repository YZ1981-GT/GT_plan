/**
 * AttachmentPreviewDrawer - AT-2 Office iframe paths
 *
 * 2026-10-27（spec attachment-security-baseline 任务 12）：原先断言 iframe 的 src 就是
 * `/api/attachments/{id}/preview(-pdf)` —— 钉住的正是缺陷：浏览器原生加载带不上 Bearer 头，
 * 抽屉里显示 {"code":401,...}。现改为断言「按同一路由取数」+「iframe 用 blob: 地址」。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { attachments as P_att, officePreview } from '@/services/apiPaths'
import AttachmentPreviewDrawer from '@/components/common/AttachmentPreviewDrawer.vue'

const apiMock = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api: apiMock, default: apiMock }))

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
    template: '<div class="el-empty"><span class="el-empty__desc">{{ description }}</span><slot /></div>',
    props: ['description'],
  },
  'el-button': {
    template: '<button class="el-button"><slot /></button>',
  },
  OcrStatusBadge: { template: '<span class="ocr-badge" />' },
}

/** 预览取数请求（responseType=blob）的路径 */
function previewRequests(): string[] {
  return apiMock.get.mock.calls
    .filter(([, cfg]) => cfg?.responseType === 'blob')
    .map(([url]) => String(url))
}

function mountDrawer(attachment: Record<string, unknown>) {
  return mount(AttachmentPreviewDrawer, {
    global: { stubs },
    props: { modelValue: true, attachment: attachment as any },
  })
}

beforeEach(() => {
  apiMock.get.mockReset()
  apiMock.get.mockImplementation(async (url: string) => {
    if (String(url).includes('/office-preview/health')) return { available: true }
    return new Blob(['%PDF'], { type: 'application/pdf' })
  })
  ;(URL as any).createObjectURL = vi.fn(() => 'blob:preview')
  ;(URL as any).revokeObjectURL = vi.fn()
})

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
  it.each([
    ['att-1', 'report.docx', '', '/api/attachments/att-1/preview-pdf'],
    ['att-2', 'data.xlsx', '', '/api/attachments/att-2/preview-pdf'],
    ['att-6', 'slides.pptx', undefined, '/api/attachments/att-6/preview-pdf'],
    ['att-3', 'doc.pdf', 'application/pdf', '/api/attachments/att-3/preview'],
  ])('%s %s（type_hint=%s）→ 经已鉴权请求取 %s，iframe 用 blob: 地址', async (id, name, typeHint, expected) => {
    const wrapper = mountDrawer({
      id,
      name,
      type_hint: typeHint,
      preview_url: `/api/attachments/${id}/preview`,
      download_url: `/api/attachments/${id}/download`,
    })
    await flushPromises()
    expect(previewRequests()).toEqual([expected])
    const src = wrapper.find('iframe').attributes('src')
    expect(src).toBe('blob:preview')
    expect(src).not.toContain('/api/')
    wrapper.unmount()
  })

  it('image renders img（同样走 blob: 地址）', async () => {
    const wrapper = mountDrawer({
      id: 'att-4',
      name: 'photo.png',
      type_hint: 'image/png',
      preview_url: '/api/attachments/att-4/preview',
      download_url: '/api/attachments/att-4/download',
    })
    await flushPromises()
    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.find('img').attributes('src')).toBe('blob:preview')
    expect(previewRequests()).toEqual(['/api/attachments/att-4/preview'])
  })

  it('zip mounts ExtendedFormatPreview（不走预览取数）', async () => {
    const wrapper = mountDrawer({
      id: 'att-5',
      name: 'archive.zip',
      type_hint: 'application/zip',
      preview_url: '',
      download_url: '/api/attachments/att-5/download',
    })
    await flushPromises()
    expect(wrapper.find('[data-testid="extended-stub"]').exists()).toBe(true)
    expect(previewRequests()).toEqual([])
  })

  it('无权查看：不显示 iframe，提示「无权查看该文件」', async () => {
    apiMock.get.mockImplementation(async (url: string) => {
      if (String(url).includes('/office-preview/health')) return { available: true }
      throw { response: { status: 403 } }
    })
    const wrapper = mountDrawer({
      id: 'att-7',
      name: 'doc.pdf',
      type_hint: 'application/pdf',
      preview_url: '/api/attachments/att-7/preview',
      download_url: '/api/attachments/att-7/download',
    })
    await flushPromises()
    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.text()).toContain('无权查看该文件')
  })
})
