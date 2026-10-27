/**
 * AttachmentDropZoneOverlay.spec.ts — AT-1 拖拽上传附件 overlay vitest
 *
 * spec proposal-remaining-18 task 3.4；上传改走底稿证据入口（spec attachment-evidence-intake 需求 5.4）
 *
 * 验证：
 * 1. dragenter 显示 overlay；dragleave 计数归零后隐藏
 * 2. drop 文件 → 经 uploadWorkpaperEvidence 上传：有当前表页 ⇒ 挂到该表页；无表页 ⇒ 整稿关联；不再另调 associate
 * 3. 文件类型/大小校验失败时 emit error 且不发起上传
 * 4. 多文件批量上传：成功+失败混合时 emit 多次 + 显示部分成功提示
 * 5. wpId 缺失时不发起上传
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import AttachmentDropZoneOverlay from '../AttachmentDropZoneOverlay.vue'

const mockUpload = vi.fn()

vi.mock('@/components/attachment/workpaperEvidence', () => ({
  uploadWorkpaperEvidence: (...args: unknown[]) => mockUpload(...args),
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}))

vi.mock('@element-plus/icons-vue', () => ({
  Loading: { template: '<i class="loading-icon" />' },
}))

const globalStubs = {
  stubs: {
    'el-icon': { template: '<i><slot /></i>' },
    Teleport: { template: '<div><slot /></div>' },
    Transition: { template: '<div><slot /></div>' },
  },
}

const uploaded = (id: string) => ({ attachment: { id }, evidenceLink: null })

function makeFile(name: string, size: number, type: string = 'image/png'): File {
  // 不要真正分配大字节，size 通过 Object.defineProperty 伪造
  const file = new File([new Uint8Array(Math.min(size, 16))], name, { type })
  Object.defineProperty(file, 'size', { value: size })
  return file
}

function mountOverlay(props: Record<string, unknown>) {
  const containerEl = document.createElement('div')
  return mount(AttachmentDropZoneOverlay, {
    props: { containerEl, projectId: 'p1', wpId: 'wp1', ...props },
    global: globalStubs,
  })
}

describe('AttachmentDropZoneOverlay', () => {
  beforeEach(() => {
    mockUpload.mockReset()
  })

  it('dragenter 显示 overlay，dragleave 计数归零后隐藏', async () => {
    const containerEl = document.createElement('div')
    document.body.appendChild(containerEl)

    const wrapper = mount(AttachmentDropZoneOverlay, {
      props: {
        containerEl,
        projectId: 'p1',
        wpId: 'wp1',
        sheetName: '审定表E1-1',
      },
      global: globalStubs,
    })
    await nextTick()

    const enterEvent = new Event('dragenter') as DragEvent
    Object.defineProperty(enterEvent, 'dataTransfer', { value: { types: ['Files'] } })
    containerEl.dispatchEvent(enterEvent)
    await nextTick()
    expect((wrapper.vm as any).visible).toBe(true)

    const leaveEvent = new Event('dragleave') as DragEvent
    Object.defineProperty(leaveEvent, 'dataTransfer', { value: { types: ['Files'] } })
    containerEl.dispatchEvent(leaveEvent)
    await nextTick()
    expect((wrapper.vm as any).visible).toBe(false)

    document.body.removeChild(containerEl)
    wrapper.unmount()
  })

  it('drop 文件 → 经证据入口上传并挂到当前表页', async () => {
    mockUpload.mockResolvedValue(uploaded('att-1'))
    const wrapper = mountOverlay({ projectId: 'project-uuid', wpId: 'wp-uuid', sheetName: '审定表E1-1' })
    await nextTick()

    const file = makeFile('evidence.pdf', 1024, 'application/pdf')
    await (wrapper.vm as any)._uploadFiles([file])
    await flushPromises()

    expect(mockUpload).toHaveBeenCalledTimes(1)
    expect(mockUpload.mock.calls[0][0]).toEqual({
      projectId: 'project-uuid', wpId: 'wp-uuid', file, sheetName: '审定表E1-1',
    })
    expect(wrapper.emitted('uploaded')![0][0]).toMatchObject({
      attachment_id: 'att-1',
      file_name: 'evidence.pdf',
      wp_id: 'wp-uuid',
      sheet_name: '审定表E1-1',
    })
    expect(wrapper.emitted('error')).toBeFalsy()

    wrapper.unmount()
  })

  it('没有当前表页时整稿关联（不带位置）', async () => {
    mockUpload.mockResolvedValue(uploaded('att-x'))
    const wrapper = mountOverlay({ sheetName: '' })
    await nextTick()

    await (wrapper.vm as any)._uploadFiles([makeFile('a.pdf', 100, 'application/pdf')])
    await flushPromises()

    expect(mockUpload.mock.calls[0][0].sheetName).toBeNull()
    expect(wrapper.emitted('uploaded')![0][0]).toMatchObject({ attachment_id: 'att-x', sheet_name: null })

    wrapper.unmount()
  })

  it('文件类型不允许时 emit error 且不发起上传', async () => {
    const wrapper = mountOverlay({ sheetName: 'Sheet1' })
    await nextTick()

    await (wrapper.vm as any)._uploadFiles([makeFile('virus.exe', 1024, 'application/octet-stream')])
    await flushPromises()

    expect(mockUpload).not.toHaveBeenCalled()
    expect(wrapper.emitted('error')![0][0]).toContain('不支持的文件类型')

    wrapper.unmount()
  })

  it('文件超过 20MB 时 emit error 且不发起上传', async () => {
    const wrapper = mountOverlay({})
    await nextTick()

    await (wrapper.vm as any)._uploadFiles([makeFile('big.pdf', 25 * 1024 * 1024, 'application/pdf')])
    await flushPromises()

    expect(mockUpload).not.toHaveBeenCalled()
    expect(wrapper.emitted('error')![0][0]).toMatch(/超过 20MB/)

    wrapper.unmount()
  })

  it('wpId 为空时不发起上传 + emit error', async () => {
    const wrapper = mountOverlay({ wpId: '' })
    await nextTick()

    await (wrapper.vm as any)._uploadFiles([makeFile('a.png', 100, 'image/png')])
    await flushPromises()

    expect(mockUpload).not.toHaveBeenCalled()
    expect(wrapper.emitted('error')).toBeTruthy()

    wrapper.unmount()
  })

  it('多文件批量：成功 + 失败混合时分别 emit', async () => {
    mockUpload.mockResolvedValueOnce(uploaded('att-good'))
    const wrapper = mountOverlay({ sheetName: 'S1' })
    await nextTick()

    const ok = makeFile('a.pdf', 100, 'application/pdf')
    const bad = makeFile('virus.exe', 100, 'application/octet-stream')
    await (wrapper.vm as any)._uploadFiles([ok, bad])
    await flushPromises()

    expect(mockUpload).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('uploaded')!.length).toBe(1)
    expect(wrapper.emitted('error')).toBeTruthy()

    wrapper.unmount()
  })

  it('上传失败（HTTP 错误）emit error 不抛异常', async () => {
    mockUpload.mockRejectedValue({ response: { data: { detail: '后端错误' } } })
    const wrapper = mountOverlay({})
    await nextTick()

    await expect((wrapper.vm as any)._uploadFiles([makeFile('a.pdf', 100, 'application/pdf')])).resolves.toBeUndefined()
    await flushPromises()

    expect(wrapper.emitted('error')![0][0]).toContain('后端错误')

    wrapper.unmount()
  })

  it('容器 containerEl 变更时重新挂载事件监听', async () => {
    const c1 = document.createElement('div')
    const c2 = document.createElement('div')
    document.body.appendChild(c1)
    document.body.appendChild(c2)

    const wrapper = mount(AttachmentDropZoneOverlay, {
      props: {
        containerEl: c1,
        projectId: 'p1',
        wpId: 'wp1',
      },
      global: globalStubs,
    })
    await nextTick()

    await wrapper.setProps({ containerEl: c2 })
    await nextTick()

    const enter = new Event('dragenter') as DragEvent
    Object.defineProperty(enter, 'dataTransfer', { value: { types: ['Files'] } })
    c2.dispatchEvent(enter)
    await nextTick()
    expect((wrapper.vm as any).visible).toBe(true)

    document.body.removeChild(c1)
    document.body.removeChild(c2)
    wrapper.unmount()
  })
})
