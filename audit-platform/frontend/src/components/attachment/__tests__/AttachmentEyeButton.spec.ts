/**
 * AttachmentEyeButton —「小眼睛」（spec attachment-inline-preview ADR-AIP-01，变异 #2 / #3）
 *
 * - 点开才取附件信息（文件名 / 类型 / 识别状态），识别文本被截断时再取全文；
 * - 预览抽屉第一次点开才挂载；
 * - 附件已删除或无权查看 ⇒ 中文提示，不打开空预览。
 * mock 用后端真实返回形状（GET /api/attachments/{id}、GET …/ocr-text；http 拦截器已解包信封）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const mockGet = vi.fn()
vi.mock('@/utils/http', () => ({
  default: { get: (...args: any[]) => mockGet(...args) },
  downloadFile: vi.fn(),
}))

const message = vi.hoisted(() => ({ warning: vi.fn(), error: vi.fn(), success: vi.fn() }))
vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus')
  return { ...actual, ElMessage: message }
})

vi.mock('@/components/common/AttachmentPreviewDrawer.vue', async () => {
  const vue = await import('vue')
  return {
    default: vue.defineComponent({
      name: 'AttachmentPreviewDrawerStub',
      // 布尔 prop 要声明类型：模板里 `downloadable` 简写传的是空串，只有 Boolean 类型才会转成 true
      props: { modelValue: Boolean, attachment: Object, downloadable: Boolean, size: String },
      setup(props: any) {
        return () =>
          vue.h('div', {
            class: 'drawer-stub',
            'data-open': String(!!props.modelValue),
            'data-name': props.attachment?.name ?? '',
            'data-type': props.attachment?.type_hint ?? '',
            'data-ocr': props.attachment?.ocr_text ?? '',
            'data-status': props.attachment?.ocr_status ?? '',
            'data-download': String(!!props.downloadable),
          })
      },
    }),
  }
})

import AttachmentEyeButton from '../AttachmentEyeButton.vue'

const stubs = {
  'el-tooltip': { template: '<span><slot /></span>' },
  'el-button': {
    template: '<button class="el-button" :aria-label="$attrs[\'aria-label\']" @click="$emit(\'click\', $event)"><slot /></button>',
    props: ['type', 'size', 'loading', 'link'],
    inheritAttrs: false,
  },
  'el-icon': { template: '<i><slot /></i>' },
}

function detail(over: Record<string, unknown> = {}) {
  return {
    id: 'a1',
    project_id: 'p1',
    file_name: '盘点照片.jpg',
    file_type: 'image',
    file_size: 2048,
    attachment_type: 'stocktake',
    ocr_status: 'completed',
    ocr_text: '前 200 字…',
    ocr_text_length: 1200,
    ocr_text_truncated: true,
    is_deleted: false,
    ...over,
  }
}

function mountEye(props: Record<string, unknown> = {}) {
  return mount(AttachmentEyeButton, { props: { attachmentId: 'a1', ...props }, global: { stubs } })
}

describe('AttachmentEyeButton', () => {
  beforeEach(() => {
    mockGet.mockReset()
    message.warning.mockReset()
    message.error.mockReset()
  })

  it('未点开不发请求、不挂预览抽屉', async () => {
    const wrapper = mountEye({ fileName: '回函.pdf' })
    await flushPromises()
    expect(mockGet).not.toHaveBeenCalled()
    expect(wrapper.find('.drawer-stub').exists()).toBe(false)
    expect(wrapper.find('button').attributes('aria-label')).toBe('预览 回函.pdf')
  })

  it('点开：取详情 → 截断时取全文 → 打开抽屉（图片给 MIME、状态归一、可下载）', async () => {
    mockGet
      .mockResolvedValueOnce({ data: detail() })
      .mockResolvedValueOnce({ data: { attachment_id: 'a1', ocr_status: 'completed', ocr_text: '识别全文', sha256: 'x', length: 4 } })
    const wrapper = mountEye()
    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(mockGet.mock.calls.map((c) => c[0])).toEqual(['/api/attachments/a1', '/api/attachments/a1/ocr-text'])
    const drawer = wrapper.find('.drawer-stub')
    expect(drawer.attributes('data-open')).toBe('true')
    expect(drawer.attributes('data-name')).toBe('盘点照片.jpg')
    expect(drawer.attributes('data-type')).toBe('image/jpeg')
    expect(drawer.attributes('data-ocr')).toBe('识别全文')
    expect(drawer.attributes('data-status')).toBe('ok')
    expect(drawer.attributes('data-download')).toBe('true')
  })

  it('未截断不取全文，直接用详情里的识别文本', async () => {
    mockGet.mockResolvedValueOnce({ data: detail({ file_name: '回函.pdf', file_type: 'pdf', ocr_text: '短文本', ocr_text_truncated: false }) })
    const wrapper = mountEye()
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.drawer-stub').attributes('data-type')).toBe('application/pdf')
    expect(wrapper.find('.drawer-stub').attributes('data-ocr')).toBe('短文本')
  })

  it.each([404, 403])('附件不存在 / 无权查看（%s）⇒ 中文提示，不打开预览', async (status) => {
    mockGet.mockRejectedValueOnce(Object.assign(new Error(String(status)), { response: { status } }))
    const wrapper = mountEye({ fileName: '已删除.pdf' })
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(message.warning).toHaveBeenCalledWith('附件不存在或无权查看')
    expect(wrapper.find('.drawer-stub').exists()).toBe(false)
  })

  it('其他错误 ⇒ 中文失败提示', async () => {
    mockGet.mockRejectedValueOnce(Object.assign(new Error('500'), { response: { status: 500 } }))
    const wrapper = mountEye()
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(message.error).toHaveBeenCalledWith('附件信息读取失败，请稍后重试')
    expect(wrapper.find('.drawer-stub').exists()).toBe(false)
  })

  it('全文取不到时保留预览片段，仍打开原件', async () => {
    mockGet
      .mockResolvedValueOnce({ data: detail({ ocr_text: '片段' }) })
      .mockRejectedValueOnce(new Error('network'))
    const wrapper = mountEye()
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(wrapper.find('.drawer-stub').attributes('data-open')).toBe('true')
    expect(wrapper.find('.drawer-stub').attributes('data-ocr')).toBe('片段')
  })
})
