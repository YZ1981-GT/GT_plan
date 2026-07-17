/**
 * useF2StocktakeOcr — F2 监盘行级 OCR（盘点表/核对单/抽盘记录）
 */
import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

export type F2StOcrSheet = 'F2-24' | 'F2-25' | 'F2-26'

function parseNum(v: unknown): number {
  if (typeof v === 'number') return v
  const n = parseFloat(String(v ?? '0'))
  return Number.isFinite(n) ? n : 0
}

function str(v: unknown): string {
  return v == null ? '' : String(v)
}

export function useF2StocktakeOcr(wpId: Ref<string>) {
  const ocrLoadingId = ref<string | null>(null)

  async function uploadAndMerge<T extends { id: string }>(
    sheet: F2StOcrSheet,
    rowId: string,
    file: File,
    updateRow: (id: string, patch: Partial<T>) => void,
  ): Promise<void> {
    ocrLoadingId.value = rowId
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await http.post(
        `/api/workpapers/${wpId.value}/f2-st/contract-ocr?sheet=${encodeURIComponent(sheet)}`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
      )
      const data = res.data?.data ?? res.data
      const fields = (data?.extracted_fields ?? {}) as Record<string, unknown>
      const confidence = data?.confidence ?? 0

      const summary = Object.entries(fields)
        .filter(([, v]) => v != null && v !== '' && v !== 0)
        .map(([k, v]) => `${k}: ${v}`)
        .join('\n')

      const lowConf = confidence < 0.8
      await ElMessageBox.confirm(
        `OCR 置信度 ${(confidence * 100).toFixed(0)}%${lowConf ? '（建议人工核对）' : ''}\n\n${summary || '未提取到有效字段'}`,
        `OCR 提取结果 · ${sheet}`,
        { confirmButtonText: '填入当前行', cancelButtonText: '取消', type: lowConf ? 'warning' : 'info' },
      )

      const patch: Record<string, unknown> = {}
      if (sheet === 'F2-24') {
        if (fields.itemName) patch.itemName = str(fields.itemName)
        if (fields.spec) patch.spec = str(fields.spec)
        if (fields.bookQty != null) patch.bookQty = parseNum(fields.bookQty)
        if (fields.bookAmount != null) patch.bookAmount = parseNum(fields.bookAmount)
        if (fields.erpQty != null) patch.erpQty = parseNum(fields.erpQty)
        if (fields.erpAmount != null) patch.erpAmount = parseNum(fields.erpAmount)
      } else if (sheet === 'F2-25') {
        if (fields.itemName) patch.itemName = str(fields.itemName)
        if (fields.itemCode) patch.itemCode = str(fields.itemCode)
        if (fields.spec) patch.spec = str(fields.spec)
        if (fields.unit) patch.unit = str(fields.unit)
        if (fields.unitPrice != null) patch.unitPrice = parseNum(fields.unitPrice)
        if (fields.bookQty != null) patch.bookQty = parseNum(fields.bookQty)
        if (fields.bookAmount != null) patch.bookAmount = parseNum(fields.bookAmount)
        if (fields.clientCountQty != null) patch.clientCountQty = parseNum(fields.clientCountQty)
        if (fields.sampleQty != null) patch.sampleQty = parseNum(fields.sampleQty)
        if (fields.qualityStatus) patch.qualityStatus = str(fields.qualityStatus)
        if (fields.varianceReason) patch.varianceReason = str(fields.varianceReason)
      } else if (sheet === 'F2-26') {
        if (fields.category) patch.category = str(fields.category)
        if (fields.itemCode) patch.itemCode = str(fields.itemCode)
        if (fields.itemName) patch.itemName = str(fields.itemName)
        if (fields.spec) patch.spec = str(fields.spec)
        if (fields.unit) patch.unit = str(fields.unit)
        if (fields.unitPrice != null) patch.unitPrice = parseNum(fields.unitPrice)
        if (fields.warehouse) patch.warehouse = str(fields.warehouse)
        if (fields.countDayQty != null) patch.countDayQty = parseNum(fields.countDayQty)
        if (fields.inboundQty != null) patch.inboundQty = parseNum(fields.inboundQty)
        if (fields.outboundQty != null) patch.outboundQty = parseNum(fields.outboundQty)
        if (fields.bookQty != null) patch.bookQty = parseNum(fields.bookQty)
        if (fields.varianceReason) patch.varianceReason = str(fields.varianceReason)
        if (fields.needAdjust) patch.needAdjust = str(fields.needAdjust)
      }

      updateRow(rowId, patch as Partial<T>)
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

export default useF2StocktakeOcr
