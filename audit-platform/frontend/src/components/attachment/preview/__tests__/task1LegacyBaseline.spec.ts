/**
 * Task 1 / Task 14 — Preview_Host / Drawer_Host / TabPanel 行为矩阵
 * Task 13 后：type_hint 重命名；OCR DTO 已投影；新增三类走 ExtendedFormatPreview
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import AttachmentPreview from '@/components/extension/AttachmentPreview.vue'
import AttachmentPreviewDrawer from '@/components/common/AttachmentPreviewDrawer.vue'

const EVIDENCE_ROOT = resolve(
  __dirname,
  '../../../../../../../.kiro/specs/_archive/05-business-features/audit-evidence-attachment-preview-format-expansion/evidence/attachment-preview-format-expansion',
)

function loadJson<T>(name: string): T {
  return JSON.parse(readFileSync(resolve(EVIDENCE_ROOT, name), 'utf8')) as T
}

const previewMatrix = loadJson<{
  unsupported_copy: string
  image_exts_frozen: string[]
  image_exts_explicitly_excluded: string[]
  cases: Array<{
    fileName: string
    fileType: string | null
    branch: string
    fetchesPreview: boolean
  }>
}>('preview_host_matrix.json')

const drawerMatrix = loadJson<{
  unsupported_copy: string
  office_exts_frozen: string[]
  cases: Array<{
    name: string
    type_hint: string
    branch: string
    previewSrcKind: string | null
  }>
}>('drawer_host_matrix.json')

const tabMatrix = loadJson<{
  office_exts_frozen: string[]
  type_hint_wiring_fact: {
    api_field: string
    drawer_prop_today?: string
    maps_file_type_to?: string
    mapping?: string
    ocr_fields_on_preview_payload?: boolean
  }
}>('tabpanel_office_icon_matrix.json')

const dto = loadJson<{
  sql_projection_today: string[]
  ocr_fields_projected?: boolean
}>('process_record_dto_red_baseline.json')

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(async (url: string) => {
      if (String(url).includes('/office-preview/health')) return { available: true }
      return new Blob(['x'], { type: 'application/octet-stream' })
    }),
  },
}))

vi.mock('@/utils/http', () => ({
  downloadFile: vi.fn(async () => undefined),
  default: { get: vi.fn() },
}))

vi.mock('@vue-office/docx', () => ({
  default: { name: 'VueOfficeDocx', template: '<div class="vue-office-docx" />', props: ['src'] },
}))
vi.mock('@vue-office/excel', () => ({
  default: { name: 'VueOfficeExcel', template: '<div class="vue-office-excel" />', props: ['src'] },
}))
vi.mock('@vue-office/pdf', () => ({
  default: { name: 'VueOfficePdf', template: '<div class="vue-office-pdf" />', props: ['src'] },
}))

vi.mock('@/components/attachment/preview/ExtendedFormatPreview.vue', () => ({
  default: {
    name: 'ExtendedFormatPreview',
    template: '<div class="extended-format-preview" data-testid="extended-stub" />',
    props: ['attachmentId', 'downloadUrl', 'fileName', 'typeHint'],
  },
}))

import { api } from '@/services/apiProxy'

if (typeof URL.createObjectURL !== 'function') {
  URL.createObjectURL = vi.fn(() => 'blob:task1-baseline') as unknown as typeof URL.createObjectURL
}
if (typeof URL.revokeObjectURL !== 'function') {
  URL.revokeObjectURL = vi.fn() as unknown as typeof URL.revokeObjectURL
}

const previewStubs = {
  'el-dialog': {
    template: '<div class="el-dialog"><slot /><slot name="footer" /></div>',
    props: ['modelValue', 'title'],
  },
  'el-empty': {
    template: '<div class="el-empty" :data-desc="description"><slot /></div>',
    props: ['description', 'imageSize'],
  },
  'el-button': { template: '<button><slot /></button>' },
  'el-image': {
    template: '<img class="el-image" :src="src" />',
    props: ['src', 'fit'],
  },
}

const drawerStubs = {
  'el-drawer': {
    template: '<div class="el-drawer" :data-visible="modelValue"><slot /></div>',
    props: ['modelValue', 'title', 'direction', 'size'],
  },
  'el-empty': {
    template: '<div class="el-empty" :data-desc="description"><slot /></div>',
    props: ['description'],
  },
  'el-button': { template: '<button><slot /></button>' },
  OcrStatusBadge: { template: '<span class="ocr-badge" />', props: ['status'] },
}

function detectPreviewBranch(wrapper: ReturnType<typeof mount>): string {
  if (wrapper.find('[data-testid="extended-stub"]').exists()) return 'extended'
  if (wrapper.find('.vue-office-docx').exists()) return 'docx'
  if (wrapper.find('.vue-office-excel').exists()) return 'excel'
  if (wrapper.find('.vue-office-pdf').exists()) return 'pdf'
  if (wrapper.find('.el-image').exists()) return 'image'
  if (wrapper.find('.el-empty').exists()) return 'unsupported'
  return 'unknown'
}

describe('Task13 OCR DTO projection', () => {
  it('process-record 投影含 ocr_status/ocr_text', () => {
    expect(dto.sql_projection_today).toEqual([
      'id', 'file_name', 'file_size', 'file_type', 'created_at', 'ocr_status', 'ocr_text',
    ])
    expect(dto.ocr_fields_projected).toBe(true)
  })
})

describe('Task1/14 Preview_Host legacy matrix', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
    vi.mocked(api.get).mockImplementation(async (url: string) => {
      if (String(url).includes('/office-preview/health')) return { available: true }
      return new Blob(['x'], { type: 'application/octet-stream' })
    })
  })

  it('图片集合冻结不含 svg', () => {
    expect(previewMatrix.image_exts_frozen).toEqual(['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'])
    expect(previewMatrix.image_exts_explicitly_excluded).toEqual(['svg'])
  })

  it.each(
    previewMatrix.cases.filter((c) =>
      !['e.zip', 'e.eml', 'e.msg', 'e.dxf'].includes(c.fileName),
    ),
  )(
    'fileName=$fileName fileType=$fileType → $branch',
    async ({ fileName, fileType, branch, fetchesPreview }) => {
      const wrapper = mount(AttachmentPreview, {
        global: { stubs: previewStubs },
        props: {
          modelValue: true,
          fileUrl: '/api/attachments/att-baseline/preview',
          fileName,
          attachmentId: 'att-baseline',
          downloadUrl: '/api/attachments/att-baseline/download',
          ...(fileType === null ? {} : { fileType: fileType || undefined }),
        },
      })
      await flushPromises()
      expect(detectPreviewBranch(wrapper)).toBe(branch)
      if (fetchesPreview) {
        expect(api.get).toHaveBeenCalledWith(
          '/api/attachments/att-baseline/preview',
          expect.objectContaining({ responseType: 'blob' }),
        )
      }
      wrapper.unmount()
    },
  )

  it('zip/eml/msg/dxf 挂 ExtendedFormatPreview', async () => {
    for (const fileName of ['a.zip', 'a.eml', 'a.msg', 'a.dxf']) {
      const wrapper = mount(AttachmentPreview, {
        global: { stubs: previewStubs },
        props: {
          modelValue: true,
          fileUrl: '/api/attachments/att-x/preview',
          fileName,
          attachmentId: 'att-x',
          downloadUrl: '/api/attachments/att-x/download',
        },
      })
      await flushPromises()
      expect(detectPreviewBranch(wrapper)).toBe('extended')
      wrapper.unmount()
    }
  })
})

describe('Task1/14 Drawer_Host matrix', () => {
  it('Office 10 项冻结', () => {
    expect(drawerMatrix.office_exts_frozen).toHaveLength(10)
  })

  it.each(drawerMatrix.cases)(
    'name=$name type_hint=$type_hint → $branch',
    async ({ name, type_hint, branch, previewSrcKind }) => {
      const wrapper = mount(AttachmentPreviewDrawer, {
        global: { stubs: drawerStubs },
        props: {
          modelValue: true,
          attachment: {
            id: 'att-drawer-1',
            name,
            type_hint,
            preview_url: '/api/attachments/att-drawer-1/preview',
            download_url: '/api/attachments/att-drawer-1/download',
          },
        },
      })
      await flushPromises()

      if (branch === 'extended') {
        expect(wrapper.find('[data-testid="extended-stub"]').exists()).toBe(true)
      } else if (branch === 'office' || branch === 'pdf') {
        const iframe = wrapper.find('iframe')
        expect(iframe.exists()).toBe(true)
        if (previewSrcKind === 'preview-pdf') {
          expect(iframe.attributes('src')).toBe('/api/attachments/att-drawer-1/preview-pdf')
        } else {
          expect(iframe.attributes('src')).toBe('/api/attachments/att-drawer-1/preview')
        }
      } else if (branch === 'image') {
        expect(wrapper.find('img').exists()).toBe(true)
      } else {
        expect(wrapper.find('.el-empty').exists()).toBe(true)
      }
      wrapper.unmount()
    },
  )
})

describe('Task13/14 AttachmentTabPanel 接线', () => {
  it('源码把 file_type 写入 type_hint，并传递 OCR', () => {
    const src = readFileSync(
      resolve(__dirname, '../../../workpaper/AttachmentTabPanel.vue'),
      'utf8',
    )
    expect(src).toMatch(/type_hint:\s*att\.file_type/)
    expect(src).toMatch(/ocr_status:\s*att\.ocr_status/)
    expect(src).toMatch(/ocr_text:\s*att\.ocr_text/)
    expect(src).not.toMatch(/mime_type:\s*att\.file_type/)
  })

  it('Office 读 LEGACY_CAPABILITIES.attachmentTab', () => {
    const src = readFileSync(
      resolve(__dirname, '../../../workpaper/AttachmentTabPanel.vue'),
      'utf8',
    )
    expect(src).toContain('LEGACY_CAPABILITIES.attachmentTab')
    expect(tabMatrix.office_exts_frozen).toHaveLength(6)
  })
})

describe('Task15 OCR + Office health copy regression', () => {
  it('Drawer OCR badge/text 仍可见，不改变旧字段', async () => {
    const wrapper = mount(AttachmentPreviewDrawer, {
      global: { stubs: drawerStubs },
      props: {
        modelValue: true,
        attachment: {
          id: 'att-ocr',
          name: 'scan.png',
          type_hint: 'image/png',
          preview_url: '/api/attachments/att-ocr/preview',
          download_url: '/api/attachments/att-ocr/download',
          ocr_status: 'ok',
          ocr_text: 'invoice-body',
        },
      },
    })
    await flushPromises()
    expect(wrapper.find('.ocr-badge').exists()).toBe(true)
    expect(wrapper.find('.gt-attach-preview__ocr-text').text()).toBe('invoice-body')
    expect(wrapper.find('img').exists()).toBe(true)
    wrapper.unmount()
  })

  it('LibreOffice 降级文案与 DWG 文案冻结（收敛后单一真源 = AttachmentPreviewCore）', () => {
    // 收敛：抽屉/弹窗薄壳的 legacy 文案全部下沉 AttachmentPreviewCore，文案单一真源在此
    const src = readFileSync(
      resolve(__dirname, '../AttachmentPreviewCore.vue'),
      'utf8',
    )
    expect(src).toContain(drawerMatrix.office_lo_down_copy)
    expect(src).toContain('DWG 图纸请下载后用 CAD 软件打开')
    expect(src).toContain(drawerMatrix.unsupported_copy)
  })

  it('Preview_Host unsupported 原文不变（收敛后单一真源 = AttachmentPreviewCore）', () => {
    const src = readFileSync(
      resolve(__dirname, '../AttachmentPreviewCore.vue'),
      'utf8',
    )
    expect(src).toContain(previewMatrix.unsupported_copy)
  })
})
