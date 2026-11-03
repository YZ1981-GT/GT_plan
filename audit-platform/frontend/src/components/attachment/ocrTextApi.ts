/**
 * 附件识别文本：取全文 / 核对后确认（spec attachment-security-baseline 需求 3.5）。
 *
 * 列表、详情、上传回执里的 `ocr_text` 只是 200 字预览。确认弹窗原先拿它当初值、确认时整体写回
 * `PUT ocr-status` ⇒ 确认一次全文就被截成 200 字。现在：打开核对时取全文与 sha256，确认时带上这个
 * sha256（`base_sha256`），后端与当前全文一致才写；不一致返回 409（文本在核对期间被改过）。
 */
import { api } from '@/services/apiProxy'
import { attachments as P_att } from '@/services/apiPaths'

export interface OcrTextSnapshot {
  text: string
  sha256: string
  length: number
  confirmed: boolean
}

export const OCR_TEXT_CHANGED_TIP = '识别文本已更新，请重新打开核对后再确认'

export async function loadOcrText(attachmentId: string): Promise<OcrTextSnapshot> {
  const data: any = await api.get(P_att.ocrText(attachmentId), { _silent: true } as any)
  return {
    text: data?.ocr_text ?? '',
    sha256: data?.sha256 ?? '',
    length: Number(data?.length ?? 0),
    confirmed: Boolean(data?.ocr_confirmed),
  }
}

/** 确认识别结果；`revisedText` 只在用户改过文本时传（不传 = 原文确认）。 */
export async function confirmOcrText(attachmentId: string, baseSha256: string, revisedText?: string): Promise<any> {
  const body: Record<string, string> = { base_sha256: baseSha256 }
  if (revisedText !== undefined) body.ocr_text = revisedText
  return api.post(P_att.ocrConfirm(attachmentId), body, { _silent: true } as any)
}

/** 后端判定「核对的不是当前全文」（409 OCR_TEXT_CHANGED）。 */
export function isOcrTextChanged(e: any): boolean {
  return e?.response?.status === 409
}
