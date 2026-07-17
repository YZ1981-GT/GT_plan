/**
 * useF2SpecialContractOcr — F2-56 合同履约成本检查行级 OCR
 */
import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import type { ContractCostCheckRow } from './useF2ContractCostCheck'

export interface F2SpeOcrFields {
  contractNo?: string
  contractDate?: string
  amount?: number | string
  supplier?: string
  invoiceNo?: string
  projectName?: string
}

export function useF2SpecialContractOcr(wpId: Ref<string>) {
  const ocrLoadingId = ref<string | null>(null)

  async function uploadAndMerge(
    rowId: string,
    file: File,
    updateRow: (id: string, patch: Partial<ContractCostCheckRow>) => void,
  ): Promise<void> {
    ocrLoadingId.value = rowId
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await http.post(
        `/api/workpapers/${wpId.value}/f2-spe/contract-ocr`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
      )
      const data = res.data?.data ?? res.data
      const fields = (data?.extracted_fields ?? {}) as F2SpeOcrFields
      const confidence = data?.confidence ?? 0

      const summary = Object.entries(fields)
        .filter(([, v]) => v != null && v !== '' && v !== 0)
        .map(([k, v]) => `${k}: ${v}`)
        .join('\n')

      await ElMessageBox.confirm(
        `OCR 置信度 ${(confidence * 100).toFixed(0)}%${confidence < 0.8 ? '（建议人工核对）' : ''}\n\n${summary || '未提取到有效字段'}`,
        'OCR 提取结果',
        { confirmButtonText: '填入当前行', cancelButtonText: '取消', type: confidence < 0.8 ? 'warning' : 'info' },
      )

      const patch: Partial<ContractCostCheckRow> = {}
      if (fields.projectName) patch.projectName = String(fields.projectName)
      const datePart = fields.contractDate ? String(fields.contractDate) : ''
      const noPart = fields.contractNo ? String(fields.contractNo) : ''
      if (datePart || noPart) {
        patch.contractDateNo = [datePart, noPart].filter(Boolean).join(' / ')
      }
      if (fields.invoiceNo) patch.voucherNo = String(fields.invoiceNo)
      const amt = typeof fields.amount === 'number' ? fields.amount : parseFloat(String(fields.amount || '0'))
      if (amt > 0) patch.voucherAmount = amt
      if (fields.supplier) patch.logisticsProvider = String(fields.supplier)

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
