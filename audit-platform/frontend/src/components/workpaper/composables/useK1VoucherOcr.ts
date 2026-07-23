/**
 * useK1VoucherOcr — K1 凭证检查行级 OCR（/api/d4/contract-ocr）
 *
 * 对齐 K12/K13：上传 → 确认 → 回填 supportingDoc / remark。
 */
import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

export function useK1VoucherOcr(_wpId?: Ref<string>) {
  const ocrLoading = ref(false)

  async function runOcr(
    file: File,
    onConfirm: (text: string, fileName: string) => void,
  ): Promise<void> {
    if (ocrLoading.value) return
    ocrLoading.value = true
    try {
      const formData = new FormData()
      formData.append('file', file)
      ElMessage.info('正在 OCR 识别…')
      const res = await http.post('/api/d4/contract-ocr', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        _silent: true,
      } as any)
      const ocrData = res?.data?.data ?? res?.data ?? {}
      const ocrText = String(ocrData.text || ocrData.content || '').trim()
      if (!ocrText) {
        ElMessage.warning('OCR 未识别到文字内容')
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
