/**
 * 函证替代程序行内单据：识别 / 仅上传（spec attachment-confirmation-evidence-loop 需求 3.1，ADR-ACE-03）
 *
 * 两条路都走 Spec B 入口、只挂到本行：表页 = 替代程序页编码（如 `D0-5`），单元格 = `row:{行 id}`。
 * 识别端点先建附件再识别，识别失败附件也已挂上 ⇒ 无论成败都让本底稿的共享链接仓重取（行内小眼睛立即可见）。
 */
import http from '@/utils/http'
import { appendRowEvidence, refreshRowEvidence, rowEvidenceCell } from '@/components/attachment/rowEvidence'
import { uploadWorkpaperEvidence } from '@/components/attachment/workpaperEvidence'
import { UPLOAD_ONLY_EVIDENCE_TYPE, type AltDocType } from './alternativeDocMapping'

export interface AltRowTarget {
  projectId: string
  wpId: string
  sheetKey: string
  rowId: string
}

export interface AltDocOcrResult {
  attachment_id: string
  document_type: string
  ocr_text: string
  extracted_fields: Record<string, unknown>
  confidence: number
}

/** 上传并按单据类型识别；失败抛出（调用方 `handleApiError` 提示） */
export async function recognizeAlternativeDoc(
  target: AltRowTarget,
  file: File,
  documentType: AltDocType,
): Promise<AltDocOcrResult> {
  const form = new FormData()
  form.append('file', file)
  form.append('document_type', documentType)
  appendRowEvidence(form, target.sheetKey, rowEvidenceCell(target.rowId))
  try {
    const res: any = await http.post(
      `/api/workpapers/${target.wpId}/confirmation-alternative/doc-ocr`,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    return (res?.data ?? res) as AltDocOcrResult
  } finally {
    refreshRowEvidence(target.projectId, target.wpId)
  }
}

/** 仅上传，不识别（附件类型「支持文件」） */
export async function uploadAlternativeEvidence(target: AltRowTarget, file: File): Promise<string> {
  const { attachment } = await uploadWorkpaperEvidence({
    projectId: target.projectId,
    wpId: target.wpId,
    file,
    evidenceType: UPLOAD_ONLY_EVIDENCE_TYPE,
    sheetName: target.sheetKey,
    cellRef: rowEvidenceCell(target.rowId),
  })
  return attachment.id
}
