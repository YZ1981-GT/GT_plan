import { describe, expect, it } from 'vitest'
import {
  ATTACHMENT_UPLOAD_BUSY_MESSAGE,
  acquireAttachmentUpload,
  isAttachmentUploadActive,
  withAttachmentUpload,
} from '@/composables/attachmentUploadGate'

describe('attachmentUploadGate', () => {
  it('同一目标只允许一个上传，释放函数可重复调用', () => {
    const release = acquireAttachmentUpload('workpaper:p1:w1')
    expect(release).toEqual(expect.any(Function))
    expect(isAttachmentUploadActive('workpaper:p1:w1')).toBe(true)
    expect(acquireAttachmentUpload('workpaper:p1:w1')).toBeNull()
    expect(acquireAttachmentUpload('workpaper:p1:w2')).toEqual(expect.any(Function))

    release?.()
    release?.()
    expect(isAttachmentUploadActive('workpaper:p1:w1')).toBe(false)
  })

  it('任务成功或失败后都会释放目标，失败不会永久阻塞后续上传', async () => {
    await expect(withAttachmentUpload('project:p1', async () => 'ok')).resolves.toBe('ok')
    expect(isAttachmentUploadActive('project:p1')).toBe(false)

    await expect(withAttachmentUpload('project:p1', async () => {
      throw new Error('upload failed')
    })).rejects.toThrow('upload failed')
    expect(isAttachmentUploadActive('project:p1')).toBe(false)
  })

  it('已占用目标以稳定中文错误拒绝第二个任务', async () => {
    const release = acquireAttachmentUpload('knowledge-folder:f1')
    await expect(withAttachmentUpload('knowledge-folder:f1', async () => 'never'))
      .rejects.toThrow(ATTACHMENT_UPLOAD_BUSY_MESSAGE)
    release?.()
  })
})
