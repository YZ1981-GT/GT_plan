/**
 * OCR ↔ 附件证据链联动 — 识别请求的 FormData 字段
 *
 * 后端识别端点统一经底稿证据入口（spec attachment-evidence-intake ADR-AEI-01/05）：
 * - 带 `attachment_id`：附件须在同项目且已在本底稿（整稿关联 / 行级证据链接 / 函证挂载），否则 404；
 *   识别读已存的原件，结果写回该附件；
 * - 不带：端点先建附件并关联本底稿（带 `evidence_sheet` / `evidence_cell` 时只写该位置的证据链接），再识别。
 *
 * 因此前端**不再前置上传**：原先先走旧上传端点再 associate（编制人调 associate 恒 404，失败时还会拿着空 id 继续识别），
 * 现在一次识别请求就把附件建好、挂好。需要先有附件再识别（如行内「上传 → 再识别」）用
 * `components/attachment/workpaperEvidence.uploadWorkpaperEvidence`，再把回执里的 id 填进 `attachmentId`。
 */

export type OcrLinkageOpts = {
  attachmentId?: string | null
  forceReocr?: boolean
  /** 证据类型（不传由后端按底稿编码与端点取缺省） */
  evidenceType?: string | null
  /** 只在未带附件编号时生效：新建附件挂到这个表页 / 单元格（行级证据链接） */
  evidenceSheet?: string | null
  evidenceCell?: string | null
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

/** 向 OCR multipart FormData 追加联动字段（空值不写）。 */
export function appendOcrLinkageFields(form: FormData, opts: OcrLinkageOpts = {}): FormData {
  const id = opts.attachmentId ? String(opts.attachmentId).trim() : ''
  if (id) form.append('attachment_id', id)
  if (opts.forceReocr) form.append('force_reocr', 'true')
  if (opts.evidenceType) form.append('evidence_type', opts.evidenceType)
  if (!id && opts.evidenceSheet) form.append('evidence_sheet', opts.evidenceSheet)
  if (!id && opts.evidenceCell) form.append('evidence_cell', opts.evidenceCell)
  return form
}

/**
 * 构造带联动字段的 OCR FormData（不发请求）。
 *
 * `projectId` / `wpId` 仅为兼容既有调用保留：识别端点路径已含底稿，附件由端点自己建。
 */
export async function buildLinkedOcrFormData(
  file: File,
  opts: {
    projectId?: string
    wpId?: string
    attachmentId?: string | null
    forceReocr?: boolean
    evidenceType?: string | null
    evidenceSheet?: string | null
    evidenceCell?: string | null
    extraFields?: Record<string, string>
  } = {},
): Promise<{ form: FormData; attachmentId: string | null }> {
  const attachmentId = opts.attachmentId ? String(opts.attachmentId) : null
  const form = new FormData()
  form.append('file', file)
  if (opts.extraFields) {
    for (const [k, v] of Object.entries(opts.extraFields)) {
      if (v != null && v !== '') form.append(k, v)
    }
  }
  appendOcrLinkageFields(form, {
    attachmentId,
    forceReocr: opts.forceReocr,
    evidenceType: opts.evidenceType,
    evidenceSheet: opts.evidenceSheet,
    evidenceCell: opts.evidenceCell,
  })
  return { form, attachmentId }
}
