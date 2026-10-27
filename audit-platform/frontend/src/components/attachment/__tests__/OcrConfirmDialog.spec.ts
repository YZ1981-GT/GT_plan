/**
 * 识别结果确认：弹窗显示接口返回的全文、确认带 base sha256（spec attachment-security-baseline 需求 3.5）。
 *
 * 回归背景：弹窗原先拿列表里的 200 字预览当初值，确认时 `PUT ocr-status` 整体写回 ⇒ 全文被截断。
 * 挂起的 GET 在断言之前返回，测的是真实时序下的取值（不是 mock 立即返回碰巧对）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { reactive } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import OcrConfirmDialog from '@/components/attachment/OcrConfirmDialog.vue'
import BatchUploadResultDialog from '@/components/attachment/BatchUploadResultDialog.vue'

const apiMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
const msg = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }))

vi.mock('@/services/apiProxy', () => ({ api: apiMock, default: apiMock }))
vi.mock('element-plus', async () => {
  const real = await vi.importActual<any>('element-plus')
  return { ...real, ElMessage: msg }
})

const PREVIEW = '银行询证函回函（预览前 200 字）'
const FULL = '银行询证函回函\n' + '第001行：账号 62220001 余额 1000.00 元；'.repeat(40)

const stubs = {
  'el-dialog': { template: '<div class="el-dialog" v-if="modelValue"><slot /><slot name="footer" /></div>', props: ['modelValue'] },
  'el-input': {
    template: '<textarea class="ocr-text" :value="modelValue" :disabled="disabled" @input="$emit(\'update:modelValue\', $event.target.value)" />',
    props: ['modelValue', 'disabled'],
    emits: ['update:modelValue'],
  },
  'el-button': {
    template: '<button class="el-button" :data-type="type" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'disabled', 'loading'],
    emits: ['click'],
  },
  'el-tag': { template: '<span><slot /></span>' },
  'el-alert': { template: '<div class="el-alert">{{ title }}</div>', props: ['title'] },
  'el-checkbox': { template: '<span />' },
  'el-progress': { template: '<span />' },
  'el-icon': { template: '<i><slot /></i>' },
}
const directives = { loading: {} }

function snapshot(text: string, sha: string) {
  return { attachment_id: 'att-1', ocr_text: text, sha256: sha, length: text.length, ocr_confirmed: false }
}

function mountDialog() {
  return mount(OcrConfirmDialog, {
    props: {
      modelValue: true,
      payload: { attachmentId: 'att-1', fileName: '回函.pdf', fileType: 'pdf', previewUrl: '', ocrText: PREVIEW },
    },
    global: { stubs, directives },
  })
}

function confirmButton(wrapper: any) {
  return wrapper.findAll('button.el-button').find((b: any) => b.attributes('data-type') === 'primary')!
}

describe('OcrConfirmDialog', () => {
  beforeEach(() => {
    apiMock.get.mockReset()
    apiMock.post.mockReset()
    apiMock.put.mockReset()
    msg.success.mockReset()
    msg.warning.mockReset()
    msg.error.mockReset()
  })

  it('打开时显示接口返回的全文，而不是列表预览；全文返回前不能确认', async () => {
    let resolve!: (v: unknown) => void
    apiMock.get.mockReturnValueOnce(new Promise((r) => { resolve = r }))
    const wrapper = mountDialog()
    await flushPromises()
    expect(apiMock.get).toHaveBeenCalledWith('/api/attachments/att-1/ocr-text', { _silent: true })
    expect((wrapper.find('textarea.ocr-text').element as HTMLTextAreaElement).value).not.toBe(PREVIEW)
    expect(confirmButton(wrapper).attributes('disabled')).toBeDefined()

    resolve(snapshot(FULL, 'sha-full'))
    await flushPromises()
    expect((wrapper.find('textarea.ocr-text').element as HTMLTextAreaElement).value).toBe(FULL)
    expect(confirmButton(wrapper).attributes('disabled')).toBeUndefined()
  })

  it('原文确认：只带 base，不带文本、不走 ocr-status', async () => {
    apiMock.get.mockResolvedValueOnce(snapshot(FULL, 'sha-full'))
    apiMock.post.mockResolvedValueOnce({ ocr_confirmed: true })
    const wrapper = mountDialog()
    await flushPromises()
    await confirmButton(wrapper).trigger('click')
    await flushPromises()
    expect(apiMock.post).toHaveBeenCalledWith('/api/attachments/att-1/ocr-confirm', { base_sha256: 'sha-full' }, { _silent: true })
    expect(apiMock.put).not.toHaveBeenCalled()
    expect(wrapper.emitted('confirmed')?.[0]?.[0]).toEqual({ attachmentId: 'att-1', text: FULL })
  })

  it('修订后确认：带修订后的全文', async () => {
    apiMock.get.mockResolvedValueOnce(snapshot(FULL, 'sha-full'))
    apiMock.post.mockResolvedValueOnce({ ocr_confirmed: true })
    const wrapper = mountDialog()
    await flushPromises()
    await wrapper.find('textarea.ocr-text').setValue(FULL + '（已核对）')
    await confirmButton(wrapper).trigger('click')
    await flushPromises()
    expect(apiMock.post).toHaveBeenCalledWith(
      '/api/attachments/att-1/ocr-confirm', { base_sha256: 'sha-full', ocr_text: FULL + '（已核对）' }, { _silent: true },
    )
  })

  it('409：提示文本已更新并重新取全文，不关闭弹窗', async () => {
    apiMock.get.mockResolvedValueOnce(snapshot(FULL, 'sha-old')).mockResolvedValueOnce(snapshot(FULL + '补充页', 'sha-new'))
    apiMock.post.mockRejectedValueOnce({ response: { status: 409, data: { detail: { error_code: 'OCR_TEXT_CHANGED' } } } })
    const wrapper = mountDialog()
    await flushPromises()
    await confirmButton(wrapper).trigger('click')
    await flushPromises()
    expect(msg.warning).toHaveBeenCalledWith('识别文本已更新，请重新打开核对后再确认')
    expect(apiMock.get).toHaveBeenCalledTimes(2)
    expect((wrapper.find('textarea.ocr-text').element as HTMLTextAreaElement).value).toBe(FULL + '补充页')
    expect(wrapper.emitted('confirmed')).toBeUndefined()
  })
})

describe('BatchUploadResultDialog', () => {
  beforeEach(() => {
    apiMock.get.mockReset()
    apiMock.post.mockReset()
    apiMock.put.mockReset()
  })

  it('选中待确认文件时换成全文；全部确认对未打开过的文件按原文确认', async () => {
    apiMock.get.mockImplementation(async (url: string) =>
      url.includes('att-1') ? snapshot(FULL, 'sha-1') : { ...snapshot('第二份全文', 'sha-2'), attachment_id: 'att-2' })
    apiMock.post.mockResolvedValue({ ocr_confirmed: true })
    // 与附件管理页一致：items 是响应式数组（页面里是 ref([])）
    const items = reactive<any[]>([
      { fileName: '回函1.pdf', fileSize: 1, fileType: 'pdf', attachmentId: 'att-1', ocrText: PREVIEW, status: 'ocr_pending' },
      { fileName: '回函2.pdf', fileSize: 1, fileType: 'pdf', attachmentId: 'att-2', ocrText: '预览2', status: 'ocr_pending' },
    ])
    const wrapper = mount(BatchUploadResultDialog, {
      props: { modelValue: true, items },
      global: { stubs: { ...stubs, 'el-tag': { template: '<span><slot /></span>' } }, directives },
    })
    await flushPromises()
    expect((wrapper.find('textarea.ocr-text').element as HTMLTextAreaElement).value).toBe(FULL)

    const all = wrapper.findAll('button.el-button').find((b) => b.text().includes('全部确认入库'))!
    await all.trigger('click')
    await flushPromises()
    expect(apiMock.post.mock.calls).toEqual([
      ['/api/attachments/att-1/ocr-confirm', { base_sha256: 'sha-1' }, { _silent: true }],
      ['/api/attachments/att-2/ocr-confirm', { base_sha256: 'sha-2' }, { _silent: true }],
    ])
    expect(apiMock.put).not.toHaveBeenCalled()
    expect(items.map((i) => i.status)).toEqual(['ocr_confirmed', 'ocr_confirmed'])
  })
})

/**
 * 任务 12（2026-10-27 浏览器走查发现）：
 * ① 原件预览区 iframe / img 直接用 /api 路径当 src，浏览器原生加载带不上 Bearer 头 ⇒ 恒 401，
 *    左栏显示 {"code":401,"message":"Not authenticated"}，核对时看不到原件；
 * ② 全文 3607 字时文本框 autosize 到 688px，溢出布局盖住「确认入库」，按钮点不到。
 */
describe('原件预览走已鉴权请求 + 文本框不盖住按钮', () => {
  const PREVIEW_URL = '/api/attachments/att-1/preview'

  beforeEach(() => {
    apiMock.get.mockReset()
    apiMock.post.mockReset()
    ;(URL as any).createObjectURL = vi.fn(() => 'blob:ocr-preview')
    ;(URL as any).revokeObjectURL = vi.fn()
  })

  function routeGet(preview: () => Promise<unknown>) {
    apiMock.get.mockImplementation(async (url: string) =>
      url.endsWith('/ocr-text') ? snapshot(FULL, 'sha-full') : preview())
  }

  function mountWithPreview(fileType = 'pdf') {
    return mount(OcrConfirmDialog, {
      props: {
        modelValue: true,
        payload: { attachmentId: 'att-1', fileName: '回函.pdf', fileType, previewUrl: PREVIEW_URL, ocrText: PREVIEW },
      },
      global: { stubs, directives },
    })
  }

  it('PDF 原件经 api.get(blob) 取数，iframe 用 blob: 地址而不是 /api 路径', async () => {
    routeGet(async () => new Blob(['%PDF'], { type: 'application/pdf' }))
    const wrapper = mountWithPreview('pdf')
    await flushPromises()
    expect(apiMock.get).toHaveBeenCalledWith(PREVIEW_URL, expect.objectContaining({ responseType: 'blob', _silent: true }))
    const src = wrapper.find('iframe').attributes('src')
    expect(src).toBe('blob:ocr-preview')
    expect(src).not.toContain('/api/')
  })

  it('图片原件同样走 blob: 地址', async () => {
    routeGet(async () => new Blob(['img'], { type: 'image/png' }))
    const wrapper = mountWithPreview('png')
    await flushPromises()
    expect(wrapper.find('img').attributes('src')).toBe('blob:ocr-preview')
  })

  it('无权查看原件：不渲染 iframe，提示原因；识别全文照常可确认', async () => {
    routeGet(async () => { throw { response: { status: 403 } } })
    const wrapper = mountWithPreview('pdf')
    await flushPromises()
    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.text()).toContain('无权查看该文件')
    expect(confirmButton(wrapper).attributes('disabled')).toBeUndefined()
  })

  it('批量上传结果：选中待确认 PDF 时原件同样走 blob: 地址', async () => {
    apiMock.get.mockImplementation(async (url: string) =>
      url.endsWith('/ocr-text') ? snapshot(FULL, 'sha-1') : new Blob(['%PDF'], { type: 'application/pdf' }))
    const items = reactive<any[]>([
      { fileName: '回函1.pdf', fileSize: 1, fileType: 'pdf', attachmentId: 'att-1', previewUrl: PREVIEW_URL, ocrText: PREVIEW, status: 'ocr_pending' },
    ])
    const wrapper = mount(BatchUploadResultDialog, {
      props: { modelValue: true, items },
      global: { stubs, directives },
    })
    await flushPromises()
    expect(apiMock.get).toHaveBeenCalledWith(PREVIEW_URL, expect.objectContaining({ responseType: 'blob' }))
    expect(wrapper.find('iframe').attributes('src')).toBe('blob:ocr-preview')
  })

  it('两个弹窗的识别文本框都封顶高度并内部滚动（jsdom 不算布局，以样式为证；浏览器走查另验）', async () => {
    const { readFileSync } = await import('node:fs')
    const { resolve } = await import('node:path')
    for (const [file, cls] of [['OcrConfirmDialog.vue', 'gt-ocr-textarea'], ['BatchUploadResultDialog.vue', 'gt-batch-ocr-textarea']]) {
      const src = readFileSync(resolve(__dirname, '..', file), 'utf8')
      const rule = src.match(new RegExp(`\\.${cls} :deep\\(\\.el-textarea__inner\\) \\{([^}]*)\\}`))?.[1] ?? ''
      expect(rule, file).toMatch(/max-height:\s*calc\(/)
      expect(rule, file).toMatch(/overflow-y:\s*auto/)
    }
  })
})
