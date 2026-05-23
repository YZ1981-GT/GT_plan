/**
 * AttachmentDropZoneOverlay.spec.ts — AT-1 拖拽上传附件 overlay vitest
 *
 * spec proposal-remaining-18 task 3.4
 *
 * 验证：
 * 1. dragenter 显示 overlay；dragleave 计数归零后隐藏
 * 2. drop 文件 → 调 uploadAttachment(projectId, formData) 验证 metadata 包含 wp_id + sheet_name + reference_type=workpaper
 * 3. 上传成功后调用 attachments.associate 并在 notes 中携带 sheet:{sheet_name}
 * 4. 文件类型/大小校验失败时 emit error 且不发起 HTTP 请求
 * 5. 多文件批量上传：成功+失败混合时 emit 多次 + 显示部分成功提示
 * 6. wpId 缺失时不发起上传
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import AttachmentDropZoneOverlay from '../AttachmentDropZoneOverlay.vue'

const mockUploadAttachment = vi.fn()
const mockHttpPost = vi.fn()

vi.mock('@/services/commonApi', () => ({
  uploadAttachment: (...args: unknown[]) => mockUploadAttachment(...args),
}))

vi.mock('@/services/apiProxy', () => ({
  api: {
    post: (...args: unknown[]) => mockHttpPost(...args),
    get: vi.fn(),
  },
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

function makeFile(name: string, size: number, type: string = 'image/png'): File {
  // 不要真正分配大字节，size 通过 Object.defineProperty 伪造
  const file = new File([new Uint8Array(Math.min(size, 16))], name, { type })
  Object.defineProperty(file, 'size', { value: size })
  return file
}

function makeDataTransfer(files: File[]): DataTransfer {
  // jsdom 不实现 DataTransfer，构造最简兼容对象
  return {
    files: Object.assign(files, { item: (i: number) => files[i] }) as any,
    types: ['Files'],
  } as unknown as DataTransfer
}

describe('AttachmentDropZoneOverlay', () => {
  beforeEach(() => {
    mockUploadAttachment.mockReset()
    mockHttpPost.mockReset()
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

    // 模拟 dragenter
    const enterEvent = new Event('dragenter') as DragEvent
    Object.defineProperty(enterEvent, 'dataTransfer', { value: { types: ['Files'] } })
    containerEl.dispatchEvent(enterEvent)
    await nextTick()
    expect((wrapper.vm as any).visible).toBe(true)

    // dragleave 计数归零隐藏
    const leaveEvent = new Event('dragleave') as DragEvent
    Object.defineProperty(leaveEvent, 'dataTransfer', { value: { types: ['Files'] } })
    containerEl.dispatchEvent(leaveEvent)
    await nextTick()
    expect((wrapper.vm as any).visible).toBe(false)

    document.body.removeChild(containerEl)
    wrapper.unmount()
  })

  it('drop 文件 → 调 uploadAttachment 携带 reference_type=workpaper 和 reference_id=wp_id', async () => {
    mockUploadAttachment.mockResolvedValue({ id: 'att-1' })
    mockHttpPost.mockResolvedValue({})

    const containerEl = document.createElement('div')
    const wrapper = mount(AttachmentDropZoneOverlay, {
      props: {
        containerEl,
        projectId: 'project-uuid',
        wpId: 'wp-uuid',
        sheetName: '审定表E1-1',
      },
      global: globalStubs,
    })
    await nextTick()

    const file = makeFile('evidence.pdf', 1024, 'application/pdf')
    await (wrapper.vm as any)._uploadFiles([file])
    await flushPromises()

    expect(mockUploadAttachment).toHaveBeenCalledTimes(1)
    const [calledProjectId, fd] = mockUploadAttachment.mock.calls[0] as [string, FormData]
    expect(calledProjectId).toBe('project-uuid')
    expect(fd.get('file')).toBe(file)
    expect(fd.get('reference_type')).toBe('workpaper')
    expect(fd.get('reference_id')).toBe('wp-uuid')
    expect(fd.get('attachment_type')).toBe('evidence')
    expect(String(fd.get('title'))).toContain('审定表E1-1')

    // 关联调用 — notes 携带 sheet 元数据
    expect(mockHttpPost).toHaveBeenCalledTimes(1)
    const [associateUrl, body] = mockHttpPost.mock.calls[0] as [string, any]
    expect(associateUrl).toBe('/api/attachments/att-1/associate')
    expect(body.wp_id).toBe('wp-uuid')
    expect(body.association_type).toBe('evidence')
    expect(body.notes).toBe('sheet:审定表E1-1')

    expect(wrapper.emitted('uploaded')).toBeTruthy()
    expect(wrapper.emitted('uploaded')![0][0]).toMatchObject({
      attachment_id: 'att-1',
      file_name: 'evidence.pdf',
      wp_id: 'wp-uuid',
      sheet_name: '审定表E1-1',
    })

    wrapper.unmount()
  })

  it('文件类型不允许时 emit error 且不发起 HTTP 请求', async () => {
    const containerEl = document.createElement('div')
    const wrapper = mount(AttachmentDropZoneOverlay, {
      props: {
        containerEl,
        projectId: 'p1',
        wpId: 'wp1',
        sheetName: 'Sheet1',
      },
      global: globalStubs,
    })
    await nextTick()

    const exe = makeFile('virus.exe', 1024, 'application/octet-stream')
    await (wrapper.vm as any)._uploadFiles([exe])
    await flushPromises()

    expect(mockUploadAttachment).not.toHaveBeenCalled()
    expect(wrapper.emitted('error')).toBeTruthy()
    expect(wrapper.emitted('error')![0][0]).toContain('不支持的文件类型')

    wrapper.unmount()
  })

  it('文件超过 20MB 时 emit error 且不发起 HTTP 请求', async () => {
    const containerEl = document.createElement('div')
    const wrapper = mount(AttachmentDropZoneOverlay, {
      props: {
        containerEl,
        projectId: 'p1',
        wpId: 'wp1',
      },
      global: globalStubs,
    })
    await nextTick()

    const big = makeFile('big.pdf', 25 * 1024 * 1024, 'application/pdf')
    await (wrapper.vm as any)._uploadFiles([big])
    await flushPromises()

    expect(mockUploadAttachment).not.toHaveBeenCalled()
    expect(wrapper.emitted('error')).toBeTruthy()
    expect(wrapper.emitted('error')![0][0]).toMatch(/超过 20MB/)

    wrapper.unmount()
  })

  it('wpId 为空时不发起上传 + emit error', async () => {
    const containerEl = document.createElement('div')
    const wrapper = mount(AttachmentDropZoneOverlay, {
      props: {
        containerEl,
        projectId: 'p1',
        wpId: '',
      },
      global: globalStubs,
    })
    await nextTick()

    const file = makeFile('a.png', 100, 'image/png')
    await (wrapper.vm as any)._uploadFiles([file])
    await flushPromises()

    expect(mockUploadAttachment).not.toHaveBeenCalled()
    expect(wrapper.emitted('error')).toBeTruthy()

    wrapper.unmount()
  })

  it('多文件批量：成功 + 失败混合时分别 emit', async () => {
    mockUploadAttachment
      .mockResolvedValueOnce({ id: 'att-good' })
    mockHttpPost.mockResolvedValue({})

    const containerEl = document.createElement('div')
    const wrapper = mount(AttachmentDropZoneOverlay, {
      props: {
        containerEl,
        projectId: 'p1',
        wpId: 'wp1',
        sheetName: 'S1',
      },
      global: globalStubs,
    })
    await nextTick()

    const ok = makeFile('a.pdf', 100, 'application/pdf')
    const bad = makeFile('virus.exe', 100, 'application/octet-stream')
    await (wrapper.vm as any)._uploadFiles([ok, bad])
    await flushPromises()

    expect(mockUploadAttachment).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('uploaded')).toBeTruthy()
    expect(wrapper.emitted('error')).toBeTruthy()
    expect(wrapper.emitted('uploaded')!.length).toBe(1)

    wrapper.unmount()
  })

  it('sheetName 为空时 notes 为 null', async () => {
    mockUploadAttachment.mockResolvedValue({ id: 'att-x' })
    mockHttpPost.mockResolvedValue({})

    const containerEl = document.createElement('div')
    const wrapper = mount(AttachmentDropZoneOverlay, {
      props: {
        containerEl,
        projectId: 'p1',
        wpId: 'wp1',
        sheetName: '',
      },
      global: globalStubs,
    })
    await nextTick()

    const file = makeFile('a.pdf', 100, 'application/pdf')
    await (wrapper.vm as any)._uploadFiles([file])
    await flushPromises()

    expect(mockHttpPost).toHaveBeenCalledTimes(1)
    const [, body] = mockHttpPost.mock.calls[0] as [string, any]
    expect(body.notes).toBeNull()

    wrapper.unmount()
  })

  it('上传失败（HTTP 错误）emit error 不抛异常', async () => {
    mockUploadAttachment.mockRejectedValue({
      response: { data: { detail: '后端错误' } },
    })

    const containerEl = document.createElement('div')
    const wrapper = mount(AttachmentDropZoneOverlay, {
      props: {
        containerEl,
        projectId: 'p1',
        wpId: 'wp1',
      },
      global: globalStubs,
    })
    await nextTick()

    const file = makeFile('a.pdf', 100, 'application/pdf')
    await expect((wrapper.vm as any)._uploadFiles([file])).resolves.toBeUndefined()
    await flushPromises()

    expect(wrapper.emitted('error')).toBeTruthy()
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

    // 切换容器
    await wrapper.setProps({ containerEl: c2 })
    await nextTick()

    // c2 上 dragenter 应触发 overlay 显示
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
