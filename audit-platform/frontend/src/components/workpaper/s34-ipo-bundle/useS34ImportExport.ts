/**
 * useS34ImportExport — S34 子检查表动态明细行导入导出 composable
 *
 * Spec: .kiro/specs/s34-ipo-review-bundle/ Task 7.3
 * Requirements: 5.3, 5.4
 *
 * 设计规则：
 * - 🔴 必须使用 http(axios) 不用原生 fetch（避免 401 无 Authorization header）
 * - 🔴 中文文件名 RFC5987 编码（后端 StreamingResponse 处理）
 * - 只有动态行表格需要导入导出（非所有子表）
 * - 后端端点模式：/api/workpapers/{wp_id}/import-export/template|data?sheet={code}
 *
 * 比照 useD5ImportExport 模式。
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

// ─── Types ───

export interface S34ImportResult {
  success: boolean
  rowCount: number
  fieldCount: number
  warning?: string
  errors?: string[]
}

export interface UseS34ImportExportOptions {
  /** 子底稿 wp_id */
  wpId: Ref<string>
  /** 项目 ID */
  projectId: Ref<string>
  /** 子 sheet 编码（如 'S34-16-1'） */
  sheetCode: Ref<string>
  /** 导入成功后回调（通常用于刷新数据） */
  onImported?: () => Promise<void> | void
}

// ─── Helpers ───

/**
 * 从 content-disposition 解析文件名（RFC5987 中文支持）
 * 回退默认名称
 */
function extractFilename(disposition: string | undefined, fallback: string): string {
  if (!disposition) return fallback
  // RFC5987: filename*=UTF-8''...
  const utf8Match = disposition.match(/filename\*=UTF-8''([^;\s]+)/i)
  if (utf8Match) return decodeURIComponent(utf8Match[1])
  // 标准 filename="..."
  const stdMatch = disposition.match(/filename="?([^";\n]+)"?/)
  if (stdMatch) return stdMatch[1].trim()
  return fallback
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// ─── Composable ───

export function useS34ImportExport(options: UseS34ImportExportOptions) {
  const { wpId, sheetCode, onImported } = options
  const importing = ref(false)
  const lastError = ref<string | null>(null)

  /**
   * 导出模板（空表头 + 列定义）
   */
  async function exportTemplate(): Promise<void> {
    lastError.value = null
    try {
      const res = await http.get(
        `/api/workpapers/${wpId.value}/import-export/template`,
        { params: { sheet: sheetCode.value }, responseType: 'blob' },
      )
      const disposition = res.headers?.['content-disposition']
      const filename = extractFilename(disposition, `${sheetCode.value}_模板.xlsx`)
      downloadBlob(
        new Blob([res.data], {
          type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        }),
        filename,
      )
    } catch (err: any) {
      lastError.value = err?.response?.data?.message || err.message || '导出模板失败'
      ElMessage.error(lastError.value!)
    }
  }

  /**
   * 导出数据（当前明细行数据）
   */
  async function exportData(): Promise<void> {
    lastError.value = null
    try {
      const res = await http.get(
        `/api/workpapers/${wpId.value}/import-export/data`,
        { params: { sheet: sheetCode.value }, responseType: 'blob' },
      )
      const disposition = res.headers?.['content-disposition']
      const filename = extractFilename(disposition, `${sheetCode.value}_数据.xlsx`)
      downloadBlob(
        new Blob([res.data], {
          type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        }),
        filename,
      )
    } catch (err: any) {
      lastError.value = err?.response?.data?.message || err.message || '导出数据失败'
      ElMessage.error(lastError.value!)
    }
  }

  /**
   * 导入数据（上传 xlsx 文件）
   */
  async function importData(file: File): Promise<S34ImportResult> {
    lastError.value = null
    importing.value = true
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await http.post(
        `/api/workpapers/${wpId.value}/import-export/data`,
        formData,
        {
          params: { sheet: sheetCode.value },
          headers: { 'Content-Type': 'multipart/form-data' },
        },
      )
      const data = res.data?.data ?? res.data
      const result: S34ImportResult = {
        success: data?.ok !== false,
        rowCount: data?.imported_count ?? data?.row_count ?? 0,
        fieldCount: data?.field_count ?? 0,
        warning: data?.warning,
      }
      if (!result.success) {
        result.errors = data?.errors ?? ['导入失败']
        ElMessage.error(result.errors![0])
      } else {
        ElMessage.success(`成功导入 ${result.rowCount} 行`)
        await onImported?.()
      }
      return result
    } catch (err: any) {
      const msg = err?.response?.data?.detail
        || err?.response?.data?.message
        || err.message
        || '导入失败'
      lastError.value = Array.isArray(msg) ? msg.join(', ') : msg
      ElMessage.error(lastError.value!)
      return { success: false, rowCount: 0, fieldCount: 0, errors: [lastError.value!] }
    } finally {
      importing.value = false
    }
  }

  return { importing, lastError, exportTemplate, exportData, importData }
}

export default useS34ImportExport
