/**
 * useK1VoucherOcr — K1 凭证检查行级 OCR（/api/workpapers/{wpId}/d4/contract-ocr）
 *
 * 对齐 K12/K13：上传 → 确认 → 回填 supportingDoc / remark。
 * 识别附件挂到调用方给的位置（表页 + 行槽位，spec attachment-inline-preview），📎 旁的小眼睛按同一位置读取。
 * 🔴 原写 `/api/d4/contract-ocr`（缺底稿 id，后端无此路由 ⇒ 恒 404），正文又读 text / content（回执字段是 ocr_text）。
 */
import { ref, toValue, type MaybeRefOrGetter } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { appendRowEvidence, refreshRowEvidence, rowEvidenceCell } from '@/components/attachment/rowEvidence'

/** K1-12 两张凭证表（本期发生 / 期后收款）的行槽位：`row:{表}-{行 id}`；表格与逐笔核对弹窗共用 */
export function voucherEvidenceCell(target: 'occurrence' | 'post', rowId: string): string {
  return rowEvidenceCell(`${target}-${rowId}`)
}

export interface K1OcrPosition {
  /** 表页键（如 K1-12） */
  sheet: string
  /** 行槽位（如 `row:occurrence-{id}`）；空 = 表页级 */
  cell?: string | null
  /** 凭证检查行：带了就按凭证身份挂（spec attachment-voucher-evidence-binding） */
  row?: unknown
}

export function useK1VoucherOcr(
  wpId: MaybeRefOrGetter<string | null | undefined>,
  projectId?: MaybeRefOrGetter<string | null | undefined>,
) {
  const ocrLoading = ref(false)

  async function runOcr(
    file: File,
    onConfirm: (text: string, fileName: string) => void,
    position?: K1OcrPosition,
  ): Promise<void> {
    if (ocrLoading.value) return
    const wid = toValue(wpId)
    if (!wid) {
      ElMessage.warning('缺少底稿信息，无法识别')
      return
    }
    ocrLoading.value = true
    try {
      const formData = new FormData()
      formData.append('file', file)
      if (position) appendRowEvidence(formData, position.sheet, position.cell, position.row)
      ElMessage.info('正在 OCR 识别…')
      const res = await http.post(`/api/workpapers/${wid}/d4/contract-ocr`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        _silent: true,
      } as any)
      refreshRowEvidence(toValue(projectId), wid)
      const ocrData = res?.data?.data ?? res?.data ?? {}
      const ocrText = String(ocrData.ocr_text || '').trim()
      if (!ocrText) {
        ElMessage.warning('附件已上传，但 OCR 未识别到文字内容')
        return
      }
      await ElMessageBox.confirm(
        `OCR 识别结果：\n\n${ocrText.slice(0, 500)}${ocrText.length > 500 ? '…' : ''}\n\n是否填入支持性文件/备注？`,
        'OCR 识别确认',
        { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' },
      )
      onConfirm(ocrText, file.name)
      ElMessage.success('OCR 内容已填入')
    } catch (err: any) {
      if (err === 'cancel' || err?.action === 'cancel') return
      ElMessage.error('OCR 识别失败：' + (err?.response?.data?.detail || err?.message || '未知错误'))
    } finally {
      ocrLoading.value = false
    }
  }

  return { ocrLoading, runOcr }
}

export default useK1VoucherOcr
