/**
 * useSSpecialImportExport — S 类交易/专家/检查型底稿导入导出三级 composable
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/
 * Task: 7.2
 * Requirements: 11.3
 *
 * 职责：
 * - 三操作：exportTemplate(导出模板) / exportData(导出数据) / importData(导入数据)
 * - el-dropdown "导入导出▾" 3 actions
 * - 使用 http (axios) NOT native fetch（需 Authorization header → 401 without it!）
 * - 对接后端三端点：
 *   - GET  /api/s-special/{wp_id}/export-template?sheet=xxx
 *   - GET  /api/s-special/{wp_id}/export-data?sheet=xxx
 *   - POST /api/s-special/{wp_id}/import-data (multipart/form-data + sheet query param)
 * - RFC5987 中文文件名解析
 * - Blob下载: responseType:'blob' → URL.createObjectURL → a.click()
 *
 * 动态行表格（需要导入导出）：
 * - S17-2 合并报表口径非经常性损益明细
 * - S17-3 个别报表口径非经常性损益明细
 * - S1-1  对法律法规的考虑记录表
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** S 类交易型支持导入导出的 sheet（动态行表格） */
export type SSpecialImportableSheet =
  | 'S17-2'    // 合并报表口径非经常性损益明细
  | 'S17-3'    // 个别报表口径非经常性损益明细
  | 'S1-1'     // 对法律法规的考虑记录表

/** 导入结果 */
export interface SSpecialImportResult {
  success: boolean
  message: string
  rowCount?: number
  warning?: string
}

export interface UseSSpecialImportExportOptions {
  wpId: Ref<string>
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 支持导入导出的 sheet 列表 */
export const S_SPECIAL_IMPORTABLE_SHEETS: { value: SSpecialImportableSheet; label: string }[] = [
  { value: 'S17-2', label: '合并报表口径—非经常性损益明细' },
  { value: 'S17-3', label: '个别报表口径—非经常性损益明细' },
  { value: 'S1-1', label: '对法律法规的考虑记录表' },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function buildApiUrl(wpId: string, action: string): string {
  return `/api/s-special/${wpId}/${action}`
}

function parseFilename(contentDisposition: string | null, fallback: string): string {
  if (!contentDisposition) return fallback
  const rfc5987Match = contentDisposition.match(/filename\*=UTF-8''(.+?)(?:;|$)/i)
  if (rfc5987Match) {
    try { return decodeURIComponent(rfc5987Match[1]) } catch { /* fallback */ }
  }
  const plainMatch = contentDisposition.match(/filename="?(.+?)"?(?:;|$)/)
  if (plainMatch) return plainMatch[1]
  return fallback
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.style.display = 'none'
  document.body.appendChild(a)
  a.click()
  setTimeout(() => {
    URL.revokeObjectURL(url)
    document.body.removeChild(a)
  }, 100)
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useSSpecialImportExport(options: UseSSpecialImportExportOptions) {
  const { wpId } = options

  const isExporting = ref(false)
  const isImporting = ref(false)
  const lastError = ref<string | null>(null)

  /**
   * 导出空白模板
   * GET /api/s-special/{wp_id}/export-template?sheet=xxx
   */
  async function exportTemplate(sheetName: string): Promise<void> {
    if (!wpId.value) return
    isExporting.value = true
    lastError.value = null
    try {
      const response = await http.get(
        buildApiUrl(wpId.value, 'export-template'),
        { params: { sheet: sheetName }, responseType: 'blob' },
      )
      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })
      const contentDisposition = response.headers?.['content-disposition'] ?? null
      const filename = parseFilename(contentDisposition, `${sheetName}-模板.xlsx`)
      downloadBlob(blob, filename)
      ElMessage.success('模板已导出')
    } catch (err: any) {
      lastError.value = err?.response?.data?.message || err.message || '导出模板失败'
      ElMessage.error(lastError.value!)
    } finally {
      isExporting.value = false
    }
  }

  /**
   * 导出当前数据
   * GET /api/s-special/{wp_id}/export-data?sheet=xxx
   */
  async function exportData(sheetName: string): Promise<void> {
    if (!wpId.value) return
    isExporting.value = true
    lastError.value = null
    try {
      const response = await http.get(
        buildApiUrl(wpId.value, 'export-data'),
        { params: { sheet: sheetName }, responseType: 'blob' },
      )
      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })
      const contentDisposition = response.headers?.['content-disposition'] ?? null
      const filename = parseFilename(contentDisposition, `${sheetName}-数据.xlsx`)
      downloadBlob(blob, filename)
      ElMessage.success('数据已导出')
    } catch (err: any) {
      lastError.value = err?.response?.data?.message || err.message || '导出数据失败'
      ElMessage.error(lastError.value!)
    } finally {
      isExporting.value = false
    }
  }

  /**
   * 导入数据
   * POST /api/s-special/{wp_id}/import-data (multipart/form-data)
   */
  async function importData(sheetName: string, file: File): Promise<SSpecialImportResult | null> {
    if (!wpId.value) return null
    isImporting.value = true
    lastError.value = null
    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('sheet', sheetName)

      const response = await http.post(
        buildApiUrl(wpId.value, 'import-data'),
        formData,
        {
          params: { sheet: sheetName },
          headers: { 'Content-Type': 'multipart/form-data' },
        },
      )

      const data: any = response.data?.data ?? response.data
      const result: SSpecialImportResult = {
        success: true,
        message: '',
        rowCount: data.imported_count ?? data.rowCount ?? 0,
        warning: data.warning,
      }
      let msg = `成功导入 ${result.rowCount} 行数据`
      if (result.warning) msg += `（${result.warning}）`
      result.message = msg
      ElMessage.success(msg)
      return result
    } catch (err: any) {
      const errMsg = err?.response?.data?.detail
        || err?.response?.data?.message
        || err.message
        || '导入数据失败'
      lastError.value = Array.isArray(errMsg) ? errMsg.join(', ') : String(errMsg)
      ElMessage.error(lastError.value!)
      return { success: false, message: lastError.value! }
    } finally {
      isImporting.value = false
    }
  }

  return {
    isExporting,
    isImporting,
    lastError,
    exportTemplate,
    exportData,
    importData,
  }
}

export default useSSpecialImportExport
