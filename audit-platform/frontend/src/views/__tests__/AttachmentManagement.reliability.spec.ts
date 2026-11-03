import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

const state = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), message: { success: vi.fn(), warning: vi.fn(), info: vi.fn(), error: vi.fn() },
}))
vi.mock('@/services/apiProxy', () => ({ api: { get: state.get, post: state.post } }))
vi.mock('@/services/sse/projectEventStream', () => ({ subscribeProjectEvent: () => ({ close: vi.fn() }) }))
vi.mock('@/utils/http', () => ({ downloadFile: vi.fn() }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'p-1' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('element-plus', () => ({ ElMessage: state.message }))
vi.mock('@element-plus/icons-vue', () => {
  const icon = { render: () => null }
  return {
    Search: icon, Upload: icon, Document: icon, View: icon, Link: icon, Download: icon,
    RefreshRight: icon, Right: icon, Check: icon, FolderOpened: icon, FolderChecked: icon, Reading: icon,
  }
})

import AttachmentManagement from '../AttachmentManagement.vue'

const pass = (name: string) => defineComponent({ name, setup: (_p, { slots }) => () => h('div', { class: name }, slots.default?.()) })
const Button = defineComponent({
  props: { disabled: Boolean }, emits: ['click'], inheritAttrs: false,
  setup: (p, { emit, slots, attrs }) => () => h('button', {
    disabled: p.disabled, 'aria-label': attrs['aria-label'], title: attrs.title, onClick: () => emit('click'),
  }, slots.default?.()),
})
const stubs = {
  'el-button': Button,
  'el-input': pass('el-input'), 'el-select': pass('el-select'), 'el-option': true,
  'el-upload': pass('el-upload'), 'el-tooltip': pass('el-tooltip'), 'el-icon': pass('el-icon'),
  'el-tag': pass('el-tag'), 'el-form': pass('el-form'), 'el-form-item': pass('el-form-item'),
  'el-dialog': true, 'el-pagination': pass('el-pagination'), Transition: pass('transition'),
  TransitionGroup: pass('transition-group'), AttachmentPreview: true, OcrConfirmDialog: true,
  BatchUploadResultDialog: true, AttachmentHandbookDialog: true,
}

function envelope(over: Record<string, unknown> = {}) {
  return {
    items: [{
      id: 'a-1', file_name: '回函.pdf', file_type: 'pdf', file_size: 12,
      ocr_status: 'failed', linked_wp_count: 1, created_at: '2026-01-01',
    }],
    total: 51, page: 1, page_size: 50,
    summary: { total_size: 1024, ocr_completed: 25, linked_count: 7 },
    capabilities: { upload: true, associate: true, ocr_confirm: true, ocr_retry: true },
    ...over,
  }
}

async function mountPage() {
  const wrapper = mount(AttachmentManagement, {
    global: { stubs, directives: { loading: () => {} } },
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.clearAllMocks()
  state.get.mockResolvedValue(envelope())
})

describe('AttachmentManagement 列表可靠性', () => {
  it('使用服务端分页/汇总/能力，并只按能力展示写入口', async () => {
    const wrapper = await mountPage()
    expect(state.get).toHaveBeenCalledWith('/api/projects/p-1/attachments', expect.objectContaining({
      params: { page: 1, page_size: 50 }, _silent: true, _dedupe: false,
    }))
    expect(wrapper.text()).toContain('51')
    expect(wrapper.text()).toContain('1.0 KB')
    expect(wrapper.text()).toContain('上传文件')
    expect(wrapper.text()).toContain('上传文件夹')
    expect(wrapper.find('button[aria-label="重新识别 回函.pdf"]').exists()).toBe(true)
    expect(wrapper.find('.el-pagination').exists()).toBe(true)

    state.get.mockResolvedValueOnce(envelope({
      capabilities: { upload: false, associate: false, ocr_confirm: false, ocr_retry: false },
    }))
    await (wrapper.vm as any).loadAttachments()
    await flushPromises()
    expect(wrapper.text()).not.toContain('上传文件')
    expect(wrapper.text()).not.toContain('上传文件夹')
    expect(wrapper.find('button[aria-label="重新识别 回函.pdf"]').exists()).toBe(false)
  })

  it('网络失败显示可重试错误，不伪装成“暂无附件”', async () => {
    state.get.mockRejectedValueOnce(Object.assign(new Error('offline'), { response: { status: 500 } }))
    const wrapper = await mountPage()
    expect(wrapper.text()).toContain('附件加载失败')
    expect(wrapper.text()).toContain('重试')
    expect(wrapper.text()).not.toContain('暂无附件')
  })

  it('dragover 不累加进入计数，251 个文件在任何网络写入前被拒绝', async () => {
    const wrapper = await mountPage()
    const root = wrapper.find('.gt-attachment-page')
    await root.trigger('dragenter')
    expect(wrapper.find('.gt-att-dropzone').exists()).toBe(true)
    for (let index = 0; index < 5; index++) await root.trigger('dragover')
    await root.trigger('dragleave')
    expect(wrapper.find('.gt-att-dropzone').exists()).toBe(false)

    const files = Array.from({ length: 251 }, (_, index) => new File(['x'], `f${index}.pdf`, { type: 'application/pdf' }))
    await root.trigger('drop', { dataTransfer: { files } })
    await flushPromises()
    expect(state.post).not.toHaveBeenCalled()
    expect(state.message.warning).toHaveBeenCalledWith('单批最多上传 250 个文件')
  })

  it('无权限与合法空列表使用不同状态', async () => {
    state.get.mockRejectedValueOnce(Object.assign(new Error('denied'), { response: { status: 403 } }))
    const denied = await mountPage()
    expect(denied.text()).toContain('无权查看本项目附件')
    denied.unmount()

    state.get.mockResolvedValueOnce(envelope({ items: [], total: 0, summary: {} }))
    const empty = await mountPage()
    expect(empty.text()).toContain('暂无附件')
    expect(empty.text()).not.toContain('附件加载失败')
  })
})
