/**
 * useH1StocktakeOcr — H1-10 盘点行级 OCR（复用 F2-st contract-ocr · sheet=H1-10）
 */
import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import type { StocktakeCheckRow } from './h1StocktakeCheckModel'

function parseNum(v: unknown): number {
  if (typeof v === 'number') return v
  const n = parseFloat(String(v ?? '0'))
  return Number.isFinite(n) ? n : 0
}

function str(v: unknown): string {
  return v == null ? '' : String(v)
}

export function useH1StocktakeOcr(wpId: Ref<string>) {
  const ocrLoadingId = ref<string | null>(null)

  async function uploadAndMerge(
    rowId: string,
    file: File,
    updateRow: (id: string, patch: Partial<StocktakeCheckRow>) => void,
  ): Promise<void> {
    ocrLoadingId.value = rowId
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await http.post(
        `/api/workpapers/${wpId.value}/f2-st/contract-ocr?sheet=${encodeURIComponent('H1-10')}`,
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
        'OCR 提取结果 · H1-10',
        { confirmButtonText: '填入当前行', cancelButtonText: '取消', type: lowConf ? 'warning' : 'info' },
      )

      const patch: Partial<StocktakeCheckRow> = {}
      if (fields.itemName) patch.name = str(fields.itemName)
      if (fields.itemCode) patch.assetNo = str(fields.itemCode)
      if (fields.spec) patch.spec = str(fields.spec)
      if (fields.unit) patch.unit = str(fields.unit)
      if (fields.unitPrice != null) patch.unitPrice = parseNum(fields.unitPrice)
      if (fields.bookQty != null) patch.bookQty = parseNum(fields.bookQty)
      if (fields.bookAmount != null) patch.bookAmount = parseNum(fields.bookAmount)
      if (fields.clientCountQty != null) patch.clientCountQty = parseNum(fields.clientCountQty)
      if (fields.sampleQty != null) patch.sampleQty = parseNum(fields.sampleQty)
      if (fields.qualityStatus) {
        patch.qualityStatus = str(fields.qualityStatus)
        patch.actualStatus = str(fields.qualityStatus)
      }
      if (fields.varianceReason) patch.diffReason = str(fields.varianceReason)

      if (Object.keys(patch).length) {
        updateRow(rowId, patch)
        ElMessage.success('已填入 OCR 结果（仅覆盖有值字段）')
      } else {
        ElMessage.warning('未识别到可填字段')
      }
    } catch (e: any) {
      if (e !== 'cancel' && e?.toString?.() !== 'cancel') {
        ElMessage.error(e?.response?.data?.detail || e?.message || 'OCR 失败')
      }
    } finally {
      ocrLoadingId.value = null
    }
  }

  return { ocrLoadingId, uploadAndMerge }
}

export default useH1StocktakeOcr
