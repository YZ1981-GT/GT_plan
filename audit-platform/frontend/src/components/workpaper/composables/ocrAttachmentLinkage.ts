/**
 * OCR ↔ 附件证据链联动 — FormData 字段与「上传+关联」前置
 *
 * spec 复盘收口：后端 contract-ocr 已支持 attachment_id / force_reocr 回流；
 * 前端需统一传入，否则回流不触发。
 */
import http from '@/utils/http'
import { attachments as P_att } from '@/services/apiPaths'

export type OcrLinkageOpts = {
  attachmentId?: string | null
  forceReocr?: boolean
}

/** 从上传/创建响应中提取附件 id（兼容多层信封）。 */
export function extractAttachmentId(payload: unknown): string | null {
  if (!payload || typeof payload !== 'object') return null
  const root = payload as Record<string, any>
  const data = root.data ?? root
  const id = data?.id ?? data?.attachment_id ?? root.id ?? root.attachment_id
  if (id == null || id === '') return null
  return String(id)
}

/** 向 OCR multipart FormData 追加联动字段（幂等；空 id 不写）。 */
export function appendOcrLinkageFields(form: FormData, opts: OcrLinkageOpts = {}): FormData {
  const id = opts.attachmentId ? String(opts.attachmentId).trim() : ''
  if (id) form.append('attachment_id', id)
  if (opts.forceReocr) form.append('force_reocr', 'true')
  return form
}

/**
 * 上传附件并 associate 到指定底稿（权威链表）。
 * 失败抛错；成功返回 attachment_id。
 */
export async function uploadAndAssociateToWorkpaper(
  projectId: string,
  wpId: string,
  file: File,
  extra: { attachmentType?: string; title?: string } = {},
): Promise<string> {
  const form = new FormData()
  form.append('file', file)
  form.append('attachment_type', extra.attachmentType || 'evidence')
  form.append('reference_type', 'working_paper')
  form.append('reference_id', wpId)
  if (extra.title) form.append('title', extra.title)

  const uploadRes = await http.post(P_att.upload(projectId), form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    _silent: true,
  } as any)
  const attId = extractAttachmentId(uploadRes?.data?.data ?? uploadRes?.data ?? uploadRes)
  if (!attId) throw new Error('上传成功但未返回附件 id')

  try {
    await http.post(
      P_att.associate(attId),
      { wp_id: wpId, association_type: 'evidence' },
      { _silent: true } as any,
    )
  } catch {
    // associate 失败 fail-open：reference 已写，反查仍可能可见；OCR 回流靠 is_attachment_linked_to_wp
  }
  return attId
}

/**
 * 构造带联动字段的 OCR FormData。
 * 若提供 projectId+wpId，则先 upload+associate 再把 id 写入表单。
 */
export async function buildLinkedOcrFormData(
  file: File,
  opts: {
    projectId?: string
    wpId?: string
    attachmentId?: string | null
    forceReocr?: boolean
    extraFields?: Record<string, string>
  } = {},
): Promise<{ form: FormData; attachmentId: string | null }> {
  let attachmentId = opts.attachmentId ? String(opts.attachmentId) : null
  if (!attachmentId && opts.projectId && opts.wpId) {
    attachmentId = await uploadAndAssociateToWorkpaper(opts.projectId, opts.wpId, file)
  }
  const form = new FormData()
  form.append('file', file)
  if (opts.extraFields) {
    for (const [k, v] of Object.entries(opts.extraFields)) {
      if (v != null && v !== '') form.append(k, v)
    }
  }
  appendOcrLinkageFields(form, { attachmentId, forceReocr: opts.forceReocr })
  return { form, attachmentId }
}
