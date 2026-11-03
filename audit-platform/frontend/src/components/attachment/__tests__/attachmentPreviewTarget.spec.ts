/**
 * 预览目标构造（spec attachment-inline-preview ADR-AIP-02，变异 #1）
 *
 * 回归背景：右侧附件页签把后端 file_type（分类词 image / word / excel）当类型提示传给预览，
 * 预览按 `image/` 前缀判图片 ⇒ 图片恒显示「该格式暂不支持在线预览」；识别状态 completed 不在徽标枚举里 ⇒ 显示英文。
 */
import { describe, expect, it } from 'vitest'
import {
  normalizeOcrStatus,
  previewTypeHint,
  toAttachmentPreview,
} from '../attachmentPreviewTarget'

describe('previewTypeHint', () => {
  it.each([
    ['回函.pdf', 'pdf', 'application/pdf'],
    ['凭证.PNG', 'image', 'image/png'],
    ['照片.jpg', 'image', 'image/jpeg'],
    ['扫描.jpeg', null, 'image/jpeg'],
    ['图.webp', 'webp', 'image/webp'],
  ])('%s（file_type=%s）→ %s', (name, fileType, expected) => {
    expect(previewTypeHint(name, fileType)).toBe(expected)
  })

  it('Office / 其他沿用 file_type（预览宿主按扩展名判 Office）', () => {
    expect(previewTypeHint('合同.docx', 'word')).toBe('word')
    expect(previewTypeHint('明细.xlsx', 'excel')).toBe('excel')
    expect(previewTypeHint('包.zip', 'zip')).toBe('zip')
  })

  it('无扩展名时用已是 MIME 的 file_type', () => {
    expect(previewTypeHint('noext', 'image/png')).toBe('image/png')
    expect(previewTypeHint('', '')).toBe('')
  })
})

describe('normalizeOcrStatus', () => {
  it.each([
    ['completed', 'ok'],
    ['ok', 'ok'],
    ['processing', 'processing'],
    ['failed', 'failed'],
    ['pending', 'pending'],
  ])('%s → %s', (raw, expected) => {
    expect(normalizeOcrStatus(raw)).toBe(expected)
  })

  it('空 / 未知值不给状态（不显示英文原文）', () => {
    expect(normalizeOcrStatus(null)).toBeUndefined()
    expect(normalizeOcrStatus('weird')).toBeUndefined()
  })
})

describe('toAttachmentPreview', () => {
  it('图片：MIME 类型提示 + 已鉴权的预览 / 下载端点 + 状态归一', () => {
    expect(toAttachmentPreview({ id: 'a1', file_name: '盘点照片.jpg', file_type: 'image', ocr_status: 'completed', ocr_text: '全文' }))
      .toEqual({
        id: 'a1',
        name: '盘点照片.jpg',
        type_hint: 'image/jpeg',
        preview_url: '/api/attachments/a1/preview',
        download_url: '/api/attachments/a1/download',
        ocr_status: 'ok',
        ocr_text: '全文',
      })
  })

  it('缺文件名给中文占位，空识别文本不带', () => {
    const t = toAttachmentPreview({ id: 'a2' })
    expect(t.name).toBe('附件')
    expect(t.ocr_text).toBeUndefined()
    expect(t.ocr_status).toBeUndefined()
  })
})
