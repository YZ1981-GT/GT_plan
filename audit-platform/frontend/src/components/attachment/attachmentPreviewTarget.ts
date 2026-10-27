/**
 * 预览目标的唯一构造（spec attachment-inline-preview ADR-AIP-02）
 *
 * 预览宿主（AttachmentPreviewCore 的 server 变体）按 MIME 判 PDF / 图片：`type_hint` 以 `image/` 开头才当图片，
 * 等于 `application/pdf` 或文件名以 `.pdf` 结尾才当 PDF。后端附件的 `file_type` 存的是分类词
 * （`image` / `word` / `excel` / 扩展名，见 `AttachmentService._guess_file_type`），原样当类型提示传进去，
 * 图片恒判成「不支持在线预览」（右侧附件页签即此）。这里按扩展名给 MIME，取不到再沿用 `file_type`。
 *
 * 识别状态：后端写 `completed`，状态徽标的枚举是 `ok`，原样传进去顶部显示英文 `completed`。
 */
import { attachments as P_att } from '@/services/apiPaths'
import type { AttachmentForPreview } from '@/components/attachment/preview/AttachmentPreviewCore.vue'

const IMAGE_MIME: Record<string, string> = {
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  gif: 'image/gif',
  webp: 'image/webp',
  bmp: 'image/bmp',
  svg: 'image/svg+xml',
}

function extOf(fileName: string): string {
  const dot = fileName.lastIndexOf('.')
  return dot >= 0 ? fileName.slice(dot + 1).trim().toLowerCase() : ''
}

/** 类型提示：PDF / 图片给 MIME；其余沿用后端的 `file_type`（Office 由预览宿主按扩展名判）。 */
export function previewTypeHint(fileName: string | null | undefined, fileType?: string | null): string {
  const ext = extOf(fileName || '')
  if (ext === 'pdf') return 'application/pdf'
  if (IMAGE_MIME[ext]) return IMAGE_MIME[ext]
  const hint = (fileType || '').trim()
  if (hint.includes('/')) return hint
  return hint
}

/** 后端识别状态 → 状态徽标枚举；未知值不显示徽标。 */
export function normalizeOcrStatus(status: string | null | undefined): AttachmentForPreview['ocr_status'] {
  switch ((status || '').trim().toLowerCase()) {
    case 'completed':
    case 'ok':
    case 'done':
      return 'ok'
    case 'processing':
    case 'running':
      return 'processing'
    case 'failed':
    case 'error':
      return 'failed'
    case 'pending':
      return 'pending'
    default:
      return undefined
  }
}

export interface PreviewSource {
  id: string
  file_name?: string | null
  file_type?: string | null
  ocr_status?: string | null
  ocr_text?: string | null
}

/** 构造预览目标：预览 / 下载都走已鉴权的附件端点。 */
export function toAttachmentPreview(src: PreviewSource): AttachmentForPreview {
  const name = src.file_name || '附件'
  return {
    id: src.id,
    name,
    type_hint: previewTypeHint(name, src.file_type),
    preview_url: P_att.preview(src.id),
    download_url: P_att.download(src.id),
    ocr_status: normalizeOcrStatus(src.ocr_status),
    ocr_text: src.ocr_text || undefined,
  }
}
