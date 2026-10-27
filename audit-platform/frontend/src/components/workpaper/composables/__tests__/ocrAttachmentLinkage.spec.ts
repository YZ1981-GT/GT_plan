/**
 * ocrAttachmentLinkage — 单元测试
 *
 * spec attachment-evidence-intake：识别端点自己建附件并关联本底稿 ⇒ 前端不再前置上传（原先先走旧上传端点再 associate）。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'

const mockPost = vi.fn()
vi.mock('@/utils/http', () => ({ default: { post: (...a: unknown[]) => mockPost(...a) } }))

import {
  appendOcrLinkageFields,
  buildLinkedOcrFormData,
  extractAttachmentId,
} from '../ocrAttachmentLinkage'

describe('ocrAttachmentLinkage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    mockPost.mockReset()
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

  it('证据位置只在未带附件编号时写入（已有附件不改挂位置）', () => {
    const fresh = appendOcrLinkageFields(new FormData(), {
      evidenceType: 'voucher', evidenceSheet: 'F3-5', evidenceCell: 'item:2',
    })
    expect([fresh.get('evidence_type'), fresh.get('evidence_sheet'), fresh.get('evidence_cell')])
      .toEqual(['voucher', 'F3-5', 'item:2'])

    const existing = appendOcrLinkageFields(new FormData(), {
      attachmentId: 'att-1', evidenceSheet: 'F3-5', evidenceCell: 'item:2',
    })
    expect(existing.get('attachment_id')).toBe('att-1')
    expect(existing.has('evidence_sheet')).toBe(false)
    expect(existing.has('evidence_cell')).toBe(false)
  })

  it('buildLinkedOcrFormData 不前置上传，不带附件编号时交给识别端点建附件', async () => {
    const file = new File(['%PDF'], '合同.pdf', { type: 'application/pdf' })
    const { form, attachmentId } = await buildLinkedOcrFormData(file, {
      projectId: 'p1', wpId: 'w1', extraFields: { document_type: 'contract', empty: '' },
    })
    expect(mockPost).not.toHaveBeenCalled()
    expect(attachmentId).toBeNull()
    expect(form.get('file')).toBe(file)
    expect(form.get('document_type')).toBe('contract')
    expect(form.has('empty')).toBe(false)
    expect(form.has('attachment_id')).toBe(false)
  })

  it('buildLinkedOcrFormData 带附件编号与重识别', async () => {
    const file = new File(['x'], 'a.png', { type: 'image/png' })
    const { form, attachmentId } = await buildLinkedOcrFormData(file, { attachmentId: 'att-7', forceReocr: true })
    expect(attachmentId).toBe('att-7')
    expect(form.get('attachment_id')).toBe('att-7')
    expect(form.get('force_reocr')).toBe('true')
    expect(mockPost).not.toHaveBeenCalled()
  })
})
