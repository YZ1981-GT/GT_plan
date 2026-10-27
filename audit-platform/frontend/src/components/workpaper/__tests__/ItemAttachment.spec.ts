/**
 * ItemAttachment — 行级证据（spec attachment-evidence-intake 需求 5.1，ADR-AEI-08，变异 #11 / #12）
 *
 * 回归背景：上传时把位置写进 title、列表拉全项目附件再按 title 过滤；后端从不保存 title ⇒
 * 上传后永远看不见，删除只是本页隐藏。改造后上传走底稿证据入口（只写行级证据链接），
 * 列表读本底稿共享链接仓，移除 = 删除链接。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockDelete = vi.fn()
vi.mock('@/utils/http', () => ({
  default: {
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
    delete: (...args: any[]) => mockDelete(...args),
  },
  downloadFile: vi.fn(),
}))

const confirmDelete = vi.fn()
vi.mock('@/utils/confirm', () => ({ confirmDelete: (...args: any[]) => confirmDelete(...args) }))

const handleApiError = vi.fn()
vi.mock('@/utils/errorHandler', () => ({ handleApiError: (...args: any[]) => handleApiError(...args) }))

vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus')
  return { ...actual, ElMessage: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }
})

import ItemAttachment from '../ItemAttachment.vue'
import { resetWpEvidenceLinksForTest } from '@/composables/useWpEvidenceLinks'

const UploadStub = defineComponent({
  name: 'ElUploadStub',
  props: ['httpRequest', 'beforeUpload', 'accept', 'autoUpload', 'showFileList'],
  setup(_props, { slots }) {
    return () => h('div', { class: 'el-upload-stub' }, slots.default?.())
  },
})

const stubs = {
  'el-upload': UploadStub,
  'el-button': {
    template: '<button class="el-button" :aria-label="$attrs[\'aria-label\']" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'loading', 'text', 'plain'],
    inheritAttrs: false,
  },
  'el-icon': { template: '<i><slot /></i>' },
}

/** 后端 GET …/evidence 的真实形状（http 拦截器已解包信封 ⇒ res.data = 业务体）。 */
function linkRow(id: string, cellRef: string, fileName: string, sheetName = 'D2A') {
  return {
    id,
    wp_id: 'w1',
    sheet_name: sheetName,
    cell_ref: cellRef,
    attachment_id: `att-${id}`,
    page_ref: null,
    evidence_type: 'voucher',
    check_conclusion: null,
    created_by: 'u1',
    created_at: '2026-10-27T08:00:00',
    attachment: {
      id: `att-${id}`,
      file_name: fileName,
      file_size: 2048,
      file_type: 'pdf',
      attachment_type: 'voucher',
      ocr_status: null,
      created_at: '2026-10-27T08:00:00',
    },
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => { resolve = r })
  return { promise, resolve }
}

function mountItem(props: Record<string, unknown> = {}) {
  return mount(ItemAttachment, {
    props: { projectId: 'p1', wpId: 'w1', sheetKey: 'D2A', itemIndex: 3, ...props },
    global: { stubs },
  })
}

describe('ItemAttachment', () => {
  beforeEach(() => {
    resetWpEvidenceLinksForTest()
    mockGet.mockReset()
    mockPost.mockReset()
    mockDelete.mockReset()
    confirmDelete.mockReset()
    handleApiError.mockReset()
  })

  it('上传走证据入口并只带行级位置，回执后本行立即可见', async () => {
    mockGet
      .mockResolvedValueOnce({ data: { items: [], total: 0 } })
      .mockResolvedValueOnce({ data: { items: [linkRow('l1', 'item:3', '合同.pdf')], total: 1 } })
    mockPost.mockResolvedValueOnce({
      data: { attachment: { id: 'att-l1', file_name: '合同.pdf' }, evidence_link: { id: 'l1' } },
    })
    const wrapper = mountItem({ evidenceType: 'contract' })
    await flushPromises()
    expect(wrapper.text()).not.toContain('合同.pdf')

    const file = new File(['%PDF-1.4'], '合同.pdf', { type: 'application/pdf' })
    await wrapper.findComponent(UploadStub).props('httpRequest')({ file })
    await flushPromises()

    expect(mockPost).toHaveBeenCalledTimes(1)
    const [url, form] = mockPost.mock.calls[0]
    expect(url).toBe('/api/projects/p1/workpapers/w1/evidence/upload')
    expect((form as FormData).get('sheet_name')).toBe('D2A')
    expect((form as FormData).get('cell_ref')).toBe('item:3')
    expect((form as FormData).get('evidence_type')).toBe('contract')
    for (const legacy of ['title', 'document_type', 'reference_type', 'attachment_type']) {
      expect((form as FormData).has(legacy), legacy).toBe(false)
    }
    expect(mockGet).toHaveBeenCalledTimes(2)
    expect(mockGet.mock.calls[1][0]).toBe('/api/projects/p1/workpapers/w1/evidence')
    expect(wrapper.text()).toContain('合同.pdf')
  })

  it('只显示本行位置的链接（同表页其他行、其他表页不显示）', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        items: [
          linkRow('l1', 'item:3', '本行.pdf'),
          linkRow('l2', 'item:4', '下一行.pdf'),
          linkRow('l3', 'item:3', '别的表页.pdf', 'D2B'),
        ],
      },
    })
    const wrapper = mountItem()
    await flushPromises()
    expect(wrapper.text()).toContain('本行.pdf')
    expect(wrapper.text()).not.toContain('下一行.pdf')
    expect(wrapper.text()).not.toContain('别的表页.pdf')
  })

  it('移除 = 删除本行证据链接，随后重取', async () => {
    mockGet
      .mockResolvedValueOnce({ data: { items: [linkRow('l1', 'item:3', '凭证.pdf')] } })
      .mockResolvedValueOnce({ data: { items: [] } })
    mockDelete.mockResolvedValueOnce({ data: { ok: true } })
    confirmDelete.mockResolvedValueOnce(undefined)
    const wrapper = mountItem()
    await flushPromises()

    await wrapper.find('button[aria-label="移除本行证据 凭证.pdf"]').trigger('click')
    await flushPromises()

    expect(mockDelete).toHaveBeenCalledWith('/api/projects/p1/workpapers/w1/evidence/l1', expect.anything())
    expect(wrapper.text()).not.toContain('凭证.pdf')
    expect(handleApiError).not.toHaveBeenCalled()
  })

  it('取消确认不删除', async () => {
    mockGet.mockResolvedValueOnce({ data: { items: [linkRow('l1', 'item:3', '凭证.pdf')] } })
    confirmDelete.mockRejectedValueOnce('cancel')
    const wrapper = mountItem()
    await flushPromises()
    await wrapper.find('button[aria-label="移除本行证据 凭证.pdf"]').trigger('click')
    await flushPromises()
    expect(mockDelete).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('凭证.pdf')
  })

  it('同一底稿多个实例只发一次列表请求（挂起响应后再数）', async () => {
    const pending = deferred<any>()
    mockGet.mockReturnValueOnce(pending.promise)
    const wrappers = [3, 4, 5].map((idx) => mountItem({ itemIndex: idx }))
    await flushPromises()
    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(mockGet.mock.calls[0][1]).toMatchObject({ _dedupe: false })

    pending.resolve({ data: { items: [linkRow('l1', 'item:3', '三.pdf'), linkRow('l2', 'item:5', '五.pdf')] } })
    await flushPromises()
    expect(wrappers[0].text()).toContain('三.pdf')
    expect(wrappers[1].text()).not.toContain('.pdf')
    expect(wrappers[2].text()).toContain('五.pdf')
    expect(mockGet).toHaveBeenCalledTimes(1)
  })

  it('只读：不显示上传与移除', async () => {
    mockGet.mockResolvedValueOnce({ data: { items: [linkRow('l1', 'item:3', '凭证.pdf')] } })
    const wrapper = mountItem({ readonly: true })
    await flushPromises()
    expect(wrapper.text()).toContain('凭证.pdf')
    expect(wrapper.findComponent(UploadStub).exists()).toBe(false)
    expect(wrapper.find('button[aria-label="移除本行证据 凭证.pdf"]').exists()).toBe(false)
  })

  it('上传失败交给统一错误提示，列表不变', async () => {
    mockGet.mockResolvedValueOnce({ data: { items: [] } })
    const err = Object.assign(new Error('413'), { response: { status: 413 } })
    mockPost.mockRejectedValueOnce(err)
    const wrapper = mountItem()
    await flushPromises()
    const file = new File(['x'], '大文件.pdf', { type: 'application/pdf' })
    await wrapper.findComponent(UploadStub).props('httpRequest')({ file })
    await flushPromises()
    expect(handleApiError).toHaveBeenCalledWith(err, '上传附件')
    expect(mockGet).toHaveBeenCalledTimes(1)
  })
})
