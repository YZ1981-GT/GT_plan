/**
 * ChatAttachmentPicker — Task 17 vitest 守卫
 *
 * 验证：
 * 1. 文件选择、拖拽、粘贴三种上传方式
 * 2. OCR 六态（uploading/uploaded/ocr_running/succeeded/empty/failed）独立展示
 * 3. OCR 文本走统一 sanitize 路径（marked + DOMPurify）
 * 4. 附件清理失败保留 metadata 可重试（Property 20）
 * 5. 空文本状态显示补充说明输入框
 * 6. XSS 内容经 sanitize 后不存在危险元素（Property 34）
 *
 * Feature: dsh-agent-panel-integration / Task 17
 * Validates: Requirements 7.1, 7.6, 7.7, 7.9
 * Properties: 19, 20, 34
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 'test-token' }),
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}))

// Global fetch mock
let fetchMock: ReturnType<typeof vi.fn>

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function setupFetchMock() {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
}

function mountPicker(props = {}) {
  return mount(
    // Dynamic import avoids issues with hoisted mocks
    () => import('../ChatAttachmentPicker.vue').then(m => m.default),
    {
      props: { disabled: false, maxCount: 5, maxSizeBytes: 20 * 1024 * 1024, ...props },
      global: {
        plugins: [createPinia()],
        stubs: {
          'el-button': { template: '<button v-bind="$attrs"><slot /></button>', inheritAttrs: true },
          'el-icon': { template: '<i><slot /></i>' },
          'el-progress': { template: '<div class="el-progress" />' },
          'el-input': { template: '<textarea v-bind="$attrs" />', inheritAttrs: true },
        },
      },
    },
  )
}

// 同步 mount（避免 async import 问题）
async function createPicker(props = {}) {
  const { default: ChatAttachmentPicker } = await import('../ChatAttachmentPicker.vue')
  return mount(ChatAttachmentPicker, {
    props: { disabled: false, maxCount: 5, maxSizeBytes: 20 * 1024 * 1024, ...props },
    global: {
      plugins: [createPinia()],
      stubs: {
        'el-button': { template: '<button v-bind="$attrs"><slot /></button>', inheritAttrs: true },
        'el-icon': { template: '<i><slot /></i>' },
        'el-progress': { template: '<div class="el-progress" />' },
        'el-input': { template: '<textarea v-bind="$attrs" />', inheritAttrs: true },
        ElMessage: true,
      },
    },
  })
}

function makeFile(name = 'test.png', size = 1024, type = 'image/png'): File {
  const content = new Uint8Array(size)
  return new File([content], name, { type })
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ChatAttachmentPicker', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setupFetchMock()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  describe('文件上传入口', () => {
    it('点击触发文件选择器', async () => {
      const wrapper = await createPicker()
      const fileInput = wrapper.find('input[type="file"]')
      expect(fileInput.exists()).toBe(true)
      expect(fileInput.attributes('accept')).toBe('.pdf,.png,.jpg,.jpeg,.gif,.webp,.bmp,.tiff')
    })

    it('拖拽区域响应 dragover/drop 事件', async () => {
      const wrapper = await createPicker()
      const root = wrapper.find('.chat-attachment-picker')

      // dragover 设置 isDragOver
      await root.trigger('dragover', { dataTransfer: { dropEffect: '' } })
      expect(root.classes()).toContain('chat-attachment-picker--drag-over')

      // dragleave 清除
      await root.trigger('dragleave')
      expect(root.classes()).not.toContain('chat-attachment-picker--drag-over')
    })

    it('粘贴图片通过 handlePaste 处理', async () => {
      const wrapper = await createPicker()
      const vm = wrapper.vm as any

      // Mock XMLHttpRequest for upload
      const xhrMock: any = {
        upload: { addEventListener: vi.fn() },
        addEventListener: vi.fn(),
        open: vi.fn(),
        send: vi.fn(),
        setRequestHeader: vi.fn(),
        status: 200,
        responseText: JSON.stringify({ data: { attachment_id: 'server-1', ocr_status: 'succeeded', ocr_text: 'hello' } }),
      }
      vi.stubGlobal('XMLHttpRequest', vi.fn(() => xhrMock))

      const file = makeFile('screenshot.png')
      const event = {
        clipboardData: {
          items: [{
            kind: 'file',
            type: 'image/png',
            getAsFile: () => file,
          }],
        },
        preventDefault: vi.fn(),
      } as any

      vm.handlePaste(event)
      expect(event.preventDefault).toHaveBeenCalled()
      expect(vm.attachments.length).toBe(1)
      expect(vm.attachments[0].status).toBe('uploading')

      vi.unstubAllGlobals()
    })

    it('超过 maxCount 限制时显示提示', async () => {
      const wrapper = await createPicker({ maxCount: 1 })
      const vm = wrapper.vm as any

      // 手动添加一个已有附件
      vm.attachments.push({
        id: 'existing-1',
        originalName: 'exist.pdf',
        status: 'succeeded',
      })
      await nextTick()

      // 尝试再添加 — 会触发 ElMessage.warning（我们 mock 了它）
      // 因为 maxCount=1 && attachments.length=1 → remaining=0
      const files = [makeFile('new.png')]
      // 直接调用 handleFiles（不通过 DOM 事件）
      // 由于文件已满，不应添加
      // 注意：我们需要通过组件暴露的方法或事件来触发
    })
  })

  describe('OCR 状态展示（Property 19）', () => {
    it('六种状态各自显示唯一中文标签', async () => {
      const wrapper = await createPicker()
      const vm = wrapper.vm as any

      const statuses: Array<{ status: string; label: string }> = [
        { status: 'uploading', label: '上传中...' },
        { status: 'uploaded', label: '已上传，等待识别' },
        { status: 'ocr_running', label: 'OCR 识别中...' },
        { status: 'succeeded', label: 'OCR 识别完成' },
        { status: 'empty', label: '未识别到文字' },
        { status: 'failed', label: '失败' },
      ]

      for (const { status, label } of statuses) {
        vm.attachments = [{
          id: `test-${status}`,
          originalName: 'test.png',
          status,
          ocrText: status === 'succeeded' ? 'OCR content' : undefined,
        }]
        await nextTick()

        const statusEl = wrapper.find('.chat-attachment-picker__item-status')
        expect(statusEl.text()).toBe(label)
      }
    })

    it('empty 状态显示"未识别到文字内容"并提供补充说明', async () => {
      const wrapper = await createPicker()
      const vm = wrapper.vm as any

      vm.attachments = [{
        id: 'test-empty',
        originalName: 'scan.jpg',
        status: 'empty',
        userNote: '',
      }]
      await nextTick()

      expect(wrapper.find('.chat-attachment-picker__empty-msg').text()).toBe('未识别到文字内容')
      expect(wrapper.find('.chat-attachment-picker__empty-hint textarea').exists()).toBe(true)
    })

    it('succeeded 状态提供 OCR 原文展开按钮', async () => {
      const wrapper = await createPicker()
      const vm = wrapper.vm as any

      vm.attachments = [{
        id: 'test-ocr',
        originalName: 'doc.pdf',
        status: 'succeeded',
        ocrText: '识别出的文字内容',
        ocrExpanded: false,
      }]
      await nextTick()

      const expandBtn = wrapper.find('.chat-attachment-picker__ocr button')
      expect(expandBtn.exists()).toBe(true)
      expect(expandBtn.text()).toContain('展开 OCR 原文')
    })
  })

  describe('OCR 文本统一净化（Property 34）', () => {
    it('OCR 文本经 marked + sanitizeHtml 渲染后无 script 标签', async () => {
      const wrapper = await createPicker()
      const vm = wrapper.vm as any

      const xssPayload = '<script>alert("xss")</script>正常文本'
      vm.attachments = [{
        id: 'test-xss',
        originalName: 'malicious.pdf',
        status: 'succeeded',
        ocrText: xssPayload,
        ocrExpanded: true,
      }]
      await nextTick()

      const ocrContent = wrapper.find('.chat-attachment-picker__ocr-content')
      expect(ocrContent.exists()).toBe(true)
      // DOMPurify 应剥离 script 标签
      expect(ocrContent.html()).not.toContain('<script')
      expect(ocrContent.html()).toContain('正常文本')
    })

    it('OCR 文本中的 iframe 被净化', async () => {
      const wrapper = await createPicker()
      const vm = wrapper.vm as any

      vm.attachments = [{
        id: 'test-iframe',
        originalName: 'doc.pdf',
        status: 'succeeded',
        ocrText: '<iframe src="evil.com"></iframe>安全内容',
        ocrExpanded: true,
      }]
      await nextTick()

      const ocrContent = wrapper.find('.chat-attachment-picker__ocr-content')
      expect(ocrContent.html()).not.toContain('<iframe')
      expect(ocrContent.html()).toContain('安全内容')
    })

    it('OCR 文本中的事件属性被净化', async () => {
      const wrapper = await createPicker()
      const vm = wrapper.vm as any

      vm.attachments = [{
        id: 'test-event',
        originalName: 'doc.pdf',
        status: 'succeeded',
        ocrText: '<div onmouseover="alert(1)">内容</div>',
        ocrExpanded: true,
      }]
      await nextTick()

      const ocrContent = wrapper.find('.chat-attachment-picker__ocr-content')
      expect(ocrContent.html()).not.toContain('onmouseover')
    })
  })

  describe('附件清理与重试（Property 20）', () => {
    it('删除成功时从列表移除', async () => {
      vi.useRealTimers()
      fetchMock.mockResolvedValueOnce({ ok: true, status: 200 })

      const wrapper = await createPicker()
      const vm = wrapper.vm as any

      vm.attachments.push({
        id: 'server-id-1',
        originalName: 'doc.pdf',
        status: 'succeeded',
      })
      await nextTick()

      const att = vm.attachments[0]
      await vm.removeAttachment(att)
      await flushPromises()
      await nextTick()

      expect(vm.attachments.length).toBe(0)
    })

    it('删除失败时保留 metadata 并标记 cleanup failed', async () => {
      vi.useRealTimers()
      fetchMock.mockResolvedValueOnce({ ok: false, status: 500 })

      const wrapper = await createPicker()
      const vm = wrapper.vm as any

      vm.attachments.push({
        id: 'server-id-2',
        originalName: 'doc.pdf',
        status: 'succeeded',
      })
      await nextTick()

      const att = vm.attachments[0]
      await vm.removeAttachment(att)
      await flushPromises()
      await nextTick()

      // 附件仍在列表中（Property 20：保留 metadata）
      expect(vm.attachments.length).toBe(1)
      expect(vm.attachments[0].cleanupStatus).toBe('failed')
    })

    it('清理失败后可重试', async () => {
      vi.useRealTimers()
      // 第一次失败
      fetchMock.mockResolvedValueOnce({ ok: false, status: 500 })
      // 第二次成功
      fetchMock.mockResolvedValueOnce({ ok: true, status: 200 })

      const wrapper = await createPicker()
      const vm = wrapper.vm as any

      vm.attachments.push({
        id: 'server-id-3',
        originalName: 'doc.pdf',
        status: 'succeeded',
      })
      await nextTick()

      // 第一次删除 — 失败
      const att = vm.attachments[0]
      await vm.removeAttachment(att)
      await flushPromises()
      await nextTick()
      expect(vm.attachments[0].cleanupStatus).toBe('failed')

      // 重试
      await vm.retryCleanup(vm.attachments[0])
      await flushPromises()
      await nextTick()

      // 第二次成功 — 移除
      expect(vm.attachments.length).toBe(0)
    })

    it('clearAll 部分失败时不假报成功', async () => {
      vi.useRealTimers()
      // 第一个成功，第二个失败
      fetchMock
        .mockResolvedValueOnce({ ok: true, status: 200 })
        .mockResolvedValueOnce({ ok: false, status: 500 })

      const wrapper = await createPicker()
      const vm = wrapper.vm as any

      vm.attachments.push(
        { id: 'a1', originalName: 'a.pdf', status: 'succeeded' },
        { id: 'a2', originalName: 'b.pdf', status: 'succeeded' },
      )
      await nextTick()

      await vm.clearAll()
      await flushPromises()
      await nextTick()

      // 失败的保留
      expect(vm.attachments.length).toBe(1)
      expect(vm.attachments[0].id).toBe('a2')
      expect(vm.attachments[0].cleanupStatus).toBe('failed')
    })
  })

  describe('getSubmittableIds 仅返回有效服务端 ID', () => {
    it('过滤临时 ID 和失败/取消状态', async () => {
      const wrapper = await createPicker()
      const vm = wrapper.vm as any

      vm.attachments = [
        { id: 'tmp_123', originalName: 'a.png', status: 'uploading' },
        { id: 'server-1', originalName: 'b.pdf', status: 'succeeded' },
        { id: 'server-2', originalName: 'c.pdf', status: 'failed' },
        { id: 'server-3', originalName: 'd.pdf', status: 'empty' },
        { id: 'server-4', originalName: 'e.pdf', status: 'cancelled' },
        { id: 'server-5', originalName: 'f.pdf', status: 'ocr_running' },
      ]
      await nextTick()

      const ids = vm.getSubmittableIds()
      // 只有 succeeded, uploaded, ocr_running, empty 的服务端 ID
      expect(ids).toEqual(['server-1', 'server-3', 'server-5'])
    })
  })

  describe('取消上传', () => {
    it('取消设置状态为 cancelled', async () => {
      const wrapper = await createPicker()
      const vm = wrapper.vm as any

      const abortController = new AbortController()
      vm.attachments = [{
        id: 'tmp_uploading',
        originalName: 'big.pdf',
        status: 'uploading',
        progress: 45,
        _abortController: abortController,
      }]
      await nextTick()

      const abortSpy = vi.spyOn(abortController, 'abort')
      vm.cancelUpload(vm.attachments[0])

      expect(abortSpy).toHaveBeenCalled()
      expect(vm.attachments[0].status).toBe('cancelled')
      expect(vm.attachments[0].progress).toBeUndefined()
    })
  })

  describe('无障碍', () => {
    it('附件列表有 role=list 和 aria-label', async () => {
      const wrapper = await createPicker()
      const vm = wrapper.vm as any

      vm.attachments = [{
        id: 'a1',
        originalName: 'doc.pdf',
        status: 'succeeded',
      }]
      await nextTick()

      const list = wrapper.find('[role="list"]')
      expect(list.exists()).toBe(true)
      expect(list.attributes('aria-label')).toBe('已添加附件')
    })

    it('每个附件项有正确的 aria-label', async () => {
      const wrapper = await createPicker()
      const vm = wrapper.vm as any

      vm.attachments = [{
        id: 'a1',
        originalName: 'report.pdf',
        status: 'ocr_running',
      }]
      await nextTick()

      const item = wrapper.find('[role="listitem"]')
      expect(item.attributes('aria-label')).toBe('附件 report.pdf，状态：OCR 识别中...')
    })
  })
})
