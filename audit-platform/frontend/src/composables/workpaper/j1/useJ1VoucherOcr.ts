/**
 * useJ1VoucherOcr — J1-8 凭证检查行级 OCR（薪酬单据识别）
 *
 * 复用 /d4/contract-ocr 端点（通用 OCR 能力）。
 * 识别字段映射：
 *   - date → 日期
 *   - amount → 金额
 *   - voucherNo / invoiceNo / docNo → 凭证编号
 *   - payee / supplier / debtorName → 薪酬项目/收款方
 *   - description / summary → 摘要
 */
import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

export interface J1OcrFields {
  date?: string
  amount?: number | string
  voucherNo?: string
  invoiceNo?: string
  docNo?: string
  payee?: string
  supplier?: string
  debtorName?: string
  description?: string
  summary?: string
  staffCount?: number | string
  approver?: string
}

/** OCR 字段 → 凭证行字段映射表 */
const FIELD_MAP: Record<string, string> = {
  date: 'date',
  amount: '_amount',
  voucherNo: 'voucherNo',
  invoiceNo: 'voucherNo',
  docNo: 'voucherNo',
  payee: 'debtorName',
  supplier: 'debtorName',
  debtorName: 'debtorName',
  description: 'businessContent',
  summary: 'businessContent',
  staffCount: '_staffCount',
  approver: '_approver',
}

export function useJ1VoucherOcr(wpId: Ref<string>) {
  const ocrLoadingId = ref<string | null>(null)

  /**
   * 上传附件并识别，弹窗确认后回填到行
   */
  async function uploadAndMerge(
    rowId: string,
    file: File,
    direction: 'credit' | 'debit' | 'post',
    updateRow: (id: string, patch: Record<string, any>) => void,
  ): Promise<void> {
    ocrLoadingId.value = rowId
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await http.post(
        `/api/workpapers/${wpId.value}/d4/contract-ocr`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
      )
      const data = res.data?.data ?? res.data
      const fields = (data?.extracted_fields ?? {}) as J1OcrFields
      const confidence = data?.confidence ?? 0

      // 构建确认摘要
      const displayLabels: Record<string, string> = {
        date: '日期', amount: '金额', voucherNo: '凭证号',
        invoiceNo: '发票号', docNo: '单据号', payee: '收款方',
        supplier: '供应商', debtorName: '薪酬项目', description: '摘要',
        summary: '概要', staffCount: '人数', approver: '审批人',
      }
      const summary = Object.entries(fields)
        .filter(([, v]) => v != null && v !== '' && v !== 0)
        .map(([k, v]) => `${displayLabels[k] || k}: ${v}`)
        .join('\n')

      const lowConf = confidence < 0.8
      await ElMessageBox.confirm(
        `OCR 置信度 ${(confidence * 100).toFixed(0)}%${lowConf ? '（建议人工核对）' : ''}\n\n${summary || '未提取到有效字段'}`,
        '📎 OCR 提取结果',
        { confirmButtonText: '填入当前行', cancelButtonText: '取消', type: lowConf ? 'warning' : 'info' },
      )

      // 映射填入
      const patch: Record<string, any> = { sampleSource: 'OCR识别' }
      for (const [ocrKey, ocrVal] of Object.entries(fields)) {
        if (ocrVal == null || ocrVal === '' || ocrVal === 0) continue
        const target = FIELD_MAP[ocrKey]
        if (!target) continue
        if (target === '_amount') {
          const amt = typeof ocrVal === 'number' ? ocrVal : parseFloat(String(ocrVal))
          if (amt > 0) {
            patch[direction === 'credit' ? 'creditAmount' : 'debitAmount'] = amt
          }
        } else if (target === '_staffCount') {
          patch.staffCount = typeof ocrVal === 'number' ? ocrVal : parseInt(String(ocrVal), 10)
        } else if (target === '_approver') {
          patch.approver = String(ocrVal)
        } else {
          patch[target] = String(ocrVal)
        }
      }

      updateRow(rowId, patch)
      ElMessage.success('OCR 结果已填入')
    } catch (err: any) {
      if (err !== 'cancel' && err?.message !== 'cancel') {
        ElMessage.warning('OCR 识别失败或已取消')
      }
    } finally {
      ocrLoadingId.value = null
    }
  }

  return { ocrLoadingId, uploadAndMerge }
}
