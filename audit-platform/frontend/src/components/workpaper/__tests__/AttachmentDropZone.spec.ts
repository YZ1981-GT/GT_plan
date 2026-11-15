import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({ upload: vi.fn(), warning: vi.fn() }))
const upload = mocks.upload
const warning = mocks.warning
vi.mock('@/components/attachment/workpaperEvidence', () => ({
  uploadWorkpaperEvidence: (...args: any[]) => mocks.upload(...args),
}))
vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus')
  return { ...actual, ElMessage: { warning: mocks.warning, success: vi.fn(), error: vi.fn() } }
})
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))

import AttachmentDropZone from '../AttachmentDropZone.vue'

function deferred<T>() {
  let resolve!: (value: T) => void
  return { promise: new Promise<T>((done) => { resolve = done }), resolve }
}

const file = () => new File(['x'], '证据.pdf', { type: 'application/pdf' })
const dropEvent = (f: File) => ({ dataTransfer: { files: [f], types: ['Files'] } }) as unknown as DragEvent

beforeEach(() => {
  upload.mockReset()
  warning.mockReset()
})

describe('AttachmentDropZone 上传互斥', () => {
  it('同一底稿同时拖放时只保留一个上传请求', async () => {
    const pending = deferred<{ attachment: { id: string } }>()
    upload.mockReturnValueOnce(pending.promise)
    const wrapper = mount(AttachmentDropZone, {
      props: { projectId: 'p1', wpId: 'w1' },
      slots: { default: '<div>内容</div>' },
      global: { stubs: { 'el-icon': true, 'el-progress': true } },
    })

    const first = (wrapper.vm as any).onDrop(dropEvent(file()))
    await flushPromises()
    expect(upload).toHaveBeenCalledTimes(1)

    await (wrapper.vm as any).onDrop(dropEvent(file()))
    expect(upload).toHaveBeenCalledTimes(1)
    expect(warning).toHaveBeenCalledWith('已有附件正在上传，请等待完成')

    pending.resolve({ attachment: { id: 'a1' } })
    await first
  })
})
