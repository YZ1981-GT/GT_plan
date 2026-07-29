/**
 * useF2SpecialContractOcr — F2-56 合同履约成本检查行级 OCR
 */
import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import type { ContractCostCheckRow } from './useF2ContractCostCheck'
import { buildLinkedOcrFormData } from './ocrAttachmentLinkage'

export interface F2SpeOcrFields {
  voucherNo?: string
  businessContent?: string
  offsetAccount?: string
  offsetProject?: string
  accountDetail?: string
  contractNo?: string
  contractDate?: string
  contractTerms?: string
  amount?: number | string
  projectName?: string
  receiptProductName?: string
  receiptAmount?: number | string
  receiptQty?: number | string
  receiptDateNo?: string
  logisticsQty?: number | string
  logisticsDateNo?: string
  logisticsProductName?: string
  logisticsProvider?: string
  allocQty?: number | string
  allocMonth?: string
  allocAmount?: number | string
  allocBasis?: string
}

export type F2SpeDocumentType = 'voucher' | 'contract' | 'receipt' | 'logistics' | 'allocation'

function numeric(value: number | string | undefined): number {
  const result = typeof value === 'number' ? value : Number.parseFloat(String(value || '0'))
  return Number.isFinite(result) ? result : 0
}

export function useF2SpecialContractOcr(wpId: Ref<string>, projectId?: Ref<string>) {
  const ocrLoadingId = ref<string | null>(null)

  async function uploadAndMerge(
    rowId: string,
    file: File,
    updateRow: (id: string, patch: Partial<ContractCostCheckRow>) => void,
    documentType: F2SpeDocumentType = 'contract',
  ): Promise<void> {
    ocrLoadingId.value = `${rowId}:${documentType}`
    try {
      const { form } = await buildLinkedOcrFormData(file, {
        projectId: projectId?.value,
        wpId: wpId.value,
        extraFields: { document_type: documentType },
      })
      const res = await http.post(
        `/api/workpapers/${wpId.value}/f2-spe/contract-ocr`,
        form,
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
      if (fields.accountDetail) patch.accountDetail = String(fields.accountDetail)
      if (documentType === 'voucher') {
        if (fields.voucherNo) patch.voucherNo = String(fields.voucherNo)
        if (fields.businessContent) patch.businessContent = String(fields.businessContent)
        if (fields.offsetAccount) patch.offsetAccount = String(fields.offsetAccount)
        if (fields.offsetProject) patch.offsetProject = String(fields.offsetProject)
        if (numeric(fields.amount)) patch.voucherAmount = numeric(fields.amount)
      } else if (documentType === 'contract') {
        const datePart = fields.contractDate ? String(fields.contractDate) : ''
        const noPart = fields.contractNo ? String(fields.contractNo) : ''
        if (datePart || noPart) patch.contractDateNo = [datePart, noPart].filter(Boolean).join(' / ')
        if (fields.contractTerms) patch.contractTerms = String(fields.contractTerms)
      } else if (documentType === 'receipt') {
        if (fields.receiptProductName) patch.receiptProductName = String(fields.receiptProductName)
        if (numeric(fields.receiptAmount)) patch.receiptAmount = numeric(fields.receiptAmount)
      } else if (documentType === 'logistics') {
        if (numeric(fields.logisticsQty)) patch.logisticsQty = numeric(fields.logisticsQty)
        if (fields.logisticsDateNo) patch.logisticsDateNo = String(fields.logisticsDateNo)
        if (fields.logisticsProductName) patch.logisticsProductName = String(fields.logisticsProductName)
        if (fields.logisticsProvider) patch.logisticsProvider = String(fields.logisticsProvider)
      } else if (documentType === 'allocation') {
        if (numeric(fields.allocQty)) patch.allocQty = numeric(fields.allocQty)
        if (fields.allocMonth) patch.allocMonth = String(fields.allocMonth)
        if (numeric(fields.allocAmount)) patch.allocAmount = numeric(fields.allocAmount)
        if (fields.allocBasis) patch.allocBasis = String(fields.allocBasis)
      }

      updateRow(rowId, patch)
      ElMessage.success('OCR 结果已填入对应单据区域')
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
