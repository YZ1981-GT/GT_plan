/**
 * useF2SubcontractOcr — F2-35 委托加工表三行级 OCR
 * 复用 POST /f2/contract-ocr 字段 schema，按目标组映射到 SubcontractSupplier2Row。
 */
import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import type { SubcontractSupplier2Row } from './useF2InspectionCheckFormulas'
import type { F2PurchaseOcrFields } from './useF2PurchaseOcr'
import { buildLinkedOcrFormData } from './ocrAttachmentLinkage'

/** contract=合同/加工单位组；fee=加工费结算单据组 */
export type SubcontractOcrTarget = 'contract' | 'fee'

/** 纯函数：OCR 字段 → 表三行 patch（供单测） */
export function mapOcrFieldsToSubcontract(
  fields: F2PurchaseOcrFields,
  target: SubcontractOcrTarget,
): Partial<SubcontractSupplier2Row> {
  const patch: Partial<SubcontractSupplier2Row> = {}
  const amt =
    typeof fields.amount === 'number'
      ? fields.amount
      : parseFloat(String(fields.amount || '0')) || 0

  if (target === 'contract') {
    if (fields.supplier) patch.processor = String(fields.supplier)
    if (fields.purchaseOrderNo) patch.contractNo = String(fields.purchaseOrderNo)
    if (fields.orderDate) patch.issueDate = String(fields.orderDate)
    if (fields.itemName) {
      patch.remark = `品名 ${fields.itemName}`
    }
  } else {
    if (amt > 0) patch.fee = amt
    if (fields.supplier) patch.processor = patch.processor || String(fields.supplier)
    if (fields.invoiceNo) {
      patch.remark = `结算单据 ${fields.invoiceNo}`
    } else if (fields.purchaseOrderNo) {
      patch.remark = `结算单据 ${fields.purchaseOrderNo}`
    }
    if (fields.orderDate && !patch.issueDate) {
      // 结算日写入备注尾，避免覆盖发出时间
      patch.remark = [patch.remark, `结算日 ${fields.orderDate}`].filter(Boolean).join('；')
    }
  }
  return patch
}

export function useF2SubcontractOcr(wpId: Ref<string>, projectId?: Ref<string>) {
  const ocrLoadingId = ref<string | null>(null)

  async function uploadAndMerge(
    rowId: string,
    file: File,
    target: SubcontractOcrTarget,
    updateRow: (id: string, patch: Partial<SubcontractSupplier2Row>) => void,
  ): Promise<void> {
    if (!wpId.value) {
      ElMessage.warning('缺少底稿 ID，无法 OCR')
      return
    }
    ocrLoadingId.value = `${rowId}:${target}`
    try {
      const { form } = await buildLinkedOcrFormData(file, {
        projectId: projectId?.value,
        wpId: wpId.value,
      })
      const res = await http.post(
        `/api/workpapers/${wpId.value}/f2/contract-ocr`,
        form,
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
      const title = target === 'contract' ? 'OCR · 合同/加工单位' : 'OCR · 加工费结算'
      await ElMessageBox.confirm(
        `OCR 置信度 ${(confidence * 100).toFixed(0)}%${lowConf ? '（建议人工核对）' : ''}\n\n${summary || '未提取到有效字段'}`,
        title,
        { confirmButtonText: '填入当前行', cancelButtonText: '取消', type: lowConf ? 'warning' : 'info' },
      )

      const patch = mapOcrFieldsToSubcontract(fields, target)
      if (!Object.keys(patch).length) {
        ElMessage.info('无可填入字段')
        return
      }
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

export default useF2SubcontractOcr
