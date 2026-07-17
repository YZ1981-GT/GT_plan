/**
 * useF2PurchaseOcr — F2-33 采购入库行级 OCR
 */
import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import type { InspectionCheckRow } from './useF2InspectionCheckFormulas'

export interface F2PurchaseOcrFields {
  purchaseOrderNo?: string
  orderDate?: string
  amount?: number | string
  supplier?: string
  invoiceNo?: string
  itemName?: string
}

export function useF2PurchaseOcr(wpId: Ref<string>) {
  const ocrLoadingId = ref<string | null>(null)

  async function uploadAndMerge(
    rowId: string,
    file: File,
    updateRow: (id: string, patch: Partial<InspectionCheckRow>) => void,
  ): Promise<void> {
    ocrLoadingId.value = rowId
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await http.post(
        `/api/workpapers/${wpId.value}/f2/contract-ocr`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
      )
      const data = res.data?.data ?? res.data
      const fields = (data?.extracted_fields ?? {}) as F2PurchaseOcrFields
      const confidence = data?.confidence ?? 0

      const summary = Object.entries(fields)
        .filter(([, v]) => v != null && v !== '' && v !== 0)
        .map(([k, v]) => `${k}: ${v}`)
        .join('\n')

      const lowConf = confidence < 0.8
      await ElMessageBox.confirm(
        `OCR 置信度 ${(confidence * 100).toFixed(0)}%${lowConf ? '（建议人工核对）' : ''}\n\n${summary || '未提取到有效字段'}`,
        'OCR 提取结果',
        { confirmButtonText: '填入当前行', cancelButtonText: '取消', type: lowConf ? 'warning' : 'info' },
      )

      const patch: Partial<InspectionCheckRow> = { sampleSource: 'OCR识别' }
      if (fields.supplier) {
        patch.party = String(fields.supplier)
        if ('invoiceParty' in ({} as InspectionCheckRow) || true) {
          ;(patch as Record<string, unknown>).invoiceParty = String(fields.supplier)
        }
      }
      if (fields.purchaseOrderNo) {
        ;(patch as Record<string, unknown>).recvDateNo = String(fields.purchaseOrderNo)
        patch.docNo = String(fields.purchaseOrderNo)
      }
      if (fields.itemName) patch.itemName = String(fields.itemName)
      if (fields.invoiceNo) {
        ;(patch as Record<string, unknown>).invoiceDateNo = String(fields.invoiceNo)
      }
      const amt = typeof fields.amount === 'number' ? fields.amount : parseFloat(String(fields.amount || '0'))
      if (amt > 0) {
        patch.amount = amt
        ;(patch as Record<string, unknown>).invoiceAmount = amt
      }
      if (fields.orderDate) patch.remark = `单据日期 ${fields.orderDate}`

      updateRow(rowId, patch)
      ElMessage.success('OCR 结果已填入')
    } catch (err: any) {
      if (err !== 'cancel' && err?.message !== 'cancel') {
        ElMessage.warning('OCR 识别失败')
      }
    } finally {
      ocrLoadingId.value = null
    }
  }

  return { ocrLoadingId, uploadAndMerge }
}
