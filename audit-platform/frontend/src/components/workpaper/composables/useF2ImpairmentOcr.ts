/**
 * useF2ImpairmentOcr — F2-47 跌价测试行级 OCR
 */
import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import type { ImpairmentTestRow } from './useF2ImpairmentTest'

export interface F2ImpairmentOcrFields {
  itemName?: string
  qty?: number | string
  unitCost?: number | string
  sellingPrice?: number | string
  completionCost?: number | string
  sellingExpense?: number | string
  tax?: number | string
}

function parseNum(v: number | string | undefined): number {
  if (typeof v === 'number') return v
  const n = parseFloat(String(v ?? '0'))
  return Number.isFinite(n) ? n : 0
}

export function useF2ImpairmentOcr(wpId: Ref<string>) {
  const ocrLoadingId = ref<string | null>(null)

  async function uploadAndMerge(
    rowId: string,
    file: File,
    updateRow: (id: string, patch: Partial<ImpairmentTestRow>) => void,
  ): Promise<void> {
    ocrLoadingId.value = rowId
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await http.post(
        `/api/workpapers/${wpId.value}/f2-val/contract-ocr`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
      )
      const data = res.data?.data ?? res.data
      const fields = (data?.extracted_fields ?? {}) as F2ImpairmentOcrFields
      const confidence = data?.confidence ?? 0

      const summary = Object.entries(fields)
        .filter(([, v]) => v != null && v !== '' && v !== 0)
        .map(([k, v]) => `${k}: ${v}`)
        .join('\n')

      const lowConf = confidence < 0.8
      await ElMessageBox.confirm(
        `OCR 置信度 ${(confidence * 100).toFixed(0)}%${lowConf ? '（建议人工核对）' : ''}\n\n${summary || '未提取到有效字段'}`,
        'OCR 提取结果 · 跌价测试',
        { confirmButtonText: '填入当前行', cancelButtonText: '取消', type: lowConf ? 'warning' : 'info' },
      )

      const patch: Partial<ImpairmentTestRow> = {}
      if (fields.itemName) patch.itemName = String(fields.itemName)
      const qty = parseNum(fields.qty)
      const unitCost = parseNum(fields.unitCost)
      if (qty > 0) patch.qty = qty
      if (unitCost > 0) patch.unitCost = unitCost
      if (fields.sellingPrice != null) patch.sellingPrice = parseNum(fields.sellingPrice)
      if (fields.completionCost != null) patch.completionCost = parseNum(fields.completionCost)
      if (fields.sellingExpense != null) patch.sellingExpense = parseNum(fields.sellingExpense)
      if (fields.tax != null) patch.tax = parseNum(fields.tax)

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
