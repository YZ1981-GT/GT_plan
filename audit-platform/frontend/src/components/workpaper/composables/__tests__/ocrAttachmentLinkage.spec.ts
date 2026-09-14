/**
 * ocrAttachmentLinkage — 单元测试
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import {
  appendOcrLinkageFields,
  extractAttachmentId,
} from '../ocrAttachmentLinkage'

describe('ocrAttachmentLinkage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('extractAttachmentId 兼容多层信封', () => {
    expect(extractAttachmentId({ id: 'a1' })).toBe('a1')
    expect(extractAttachmentId({ data: { id: 'a2' } })).toBe('a2')
    expect(extractAttachmentId({ data: { attachment_id: 'a3' } })).toBe('a3')
    expect(extractAttachmentId(null)).toBe(null)
  })

  it('appendOcrLinkageFields 仅在有 id 时写入', () => {
    const fd = new FormData()
    fd.append('file', new Blob(['x']), 'x.pdf')
    appendOcrLinkageFields(fd, {})
    expect(fd.has('attachment_id')).toBe(false)

    appendOcrLinkageFields(fd, { attachmentId: 'att-9', forceReocr: true })
    expect(fd.get('attachment_id')).toBe('att-9')
    expect(fd.get('force_reocr')).toBe('true')
  })
})
