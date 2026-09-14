/**
 * useN4ImportExport — N4 税金及附加导入导出三级 composable
 *
 * Spec: .kiro/specs/n4-taxes-and-surcharges/
 * Task: 3.3
 * Requirements: 3.4
 *
 * 职责：
 * - 三操作：exportTemplate(导出模板) / exportData(导出数据) / importData(导入数据)
 * - el-dropdown "导入导出▾" 3 actions
 * - 使用 http (axios) NOT native fetch（需 Authorization header → 401 without it!）
 * - 动态行表格导入导出目标：
 *   - N4-2 明细表（税种明细：计税依据×税率）
 * - 后端三端点:
 *   - POST /api/n4/export-template  (body: { wpId, sheet? })
 *   - POST /api/n4/export-data      (body: { wpId, sheet? })
 *   - POST /api/n4/import-data      (multipart FormData + wpId + sheet)
 * - RFC5987 中文文件名解析
 * - Blob下载: responseType:'blob' → URL.createObjectURL → a.click()
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** N4 支持导入导出的 sheet 编码（动态行表格） */
export type N4ExportSheetCode = 'N4-2'

/** N4 导出sheet定义 */
export interface N4ExportSheet {
  code: N4ExportSheetCode
  label: string
}

/** 导入结果 */
export interface N4ImportResult {
  /** 是否成功 */
  success: boolean
  /** 消息 */
  message: string
  /** 导入行数 */
  rowCount?: number
  /** 警告信息 */
  warning?: string
}

export interface UseN4ImportExportOptions {
  wpId: Ref<string>
  projectId: Ref<string>
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 支持导入导出的sheet列表（动态行表格） */
export const N4_EXPORT_SHEETS: N4ExportSheet[] = [
  { code: 'N4-2', label: '明细表' },
]

/** API base path */
const API_BASE = '/api/n4'

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 从 Content-Disposition 解析文件名（支持 RFC5987 编码的中文名）
 * 优先读 filename*=UTF-8''...，fallback到 filename="..."
 */
function parseFilename(contentDisposition: string | null, fallback: string): string {
  if (!contentDisposition) return fallback

  // 优先匹配 filename*=UTF-8''xxx（RFC5987）
  const rfc5987Match = contentDisposition.match(/filename\*=UTF-8''(.+?)(?:;|$)/i)
  if (rfc5987Match) {
    try {
      return decodeURIComponent(rfc5987Match[1])
    } catch {
      // 解码失败用 fallback
    }
  }

  // 兜底 filename="xxx"
  const plainMatch = contentDisposition.match(/filename="?(.+?)"?(?:;|$)/)
  if (plainMatch) return plainMatch[1]

  return fallback
}

/**
 * 触发 Blob 下载
 */
function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.style.display = 'none'
  document.body.appendChild(a)
  a.click()
  // Cleanup
  setTimeout(() => {
    URL.revokeObjectURL(url)
    document.body.removeChild(a)
  }, 100)
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * N4 导入导出三级
 *
 * @param options.wpId 底稿ID（reactive）
 * @param options.projectId 项目ID（reactive）
 */
export function useN4ImportExport(options: UseN4ImportExportOptions) {
  const { wpId, projectId } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const isExporting = ref(false)
  const isImporting = ref(false)
  const lastError = ref<string | null>(null)

  // ─── Validation ────────────────────────────────────────────────────────

  /** 当前sheet是否支持导入导出 */
  function isSheetExportable(sheet: string): boolean {
    return N4_EXPORT_SHEETS.some((s) => s.code === sheet)
  }

  /** 获取所有可导出sheet列表 */
  function getExportableSheets(): N4ExportSheet[] {
    return [...N4_EXPORT_SHEETS]
  }

  // ─── Export Template ───────────────────────────────────────────────────

  /**
   * 导出空白xlsx模板（含表头+格式+编制说明）
   * POST /api/n4/export-template
   */
  async function exportTemplate(sheet?: N4ExportSheetCode): Promise<void> {
    if (!wpId.value) return
    isExporting.value = true
    lastError.value = null

    try {
      const response = await http.post(
        `${API_BASE}/export-template`,
        { wpId: wpId.value, sheet: sheet ?? 'N4-2' },
        { responseType: 'blob' },
      )

      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })

      const contentDisposition = response.headers?.['content-disposition'] ?? null
      const sheetLabel = N4_EXPORT_SHEETS.find((s) => s.code === sheet)?.label ?? '税金及附加'
      const filename = parseFilename(
        contentDisposition,
        `N4-${sheetLabel}-模板.xlsx`,
      )

      downloadBlob(blob, filename)
      ElMessage.success('模板已导出')
    } catch (err: any) {
      lastError.value = err?.response?.data?.message || err.message || '导出模板失败'
      ElMessage.error(lastError.value!)
    } finally {
      isExporting.value = false
    }
  }

  // ─── Export Data ───────────────────────────────────────────────────────

  /**
   * 导出当前数据为xlsx
   * POST /api/n4/export-data
   */
  async function exportData(sheet?: N4ExportSheetCode): Promise<void> {
    if (!wpId.value) return
    isExporting.value = true
    lastError.value = null

    try {
      const response = await http.post(
        `${API_BASE}/export-data`,
        { wpId: wpId.value, sheet: sheet ?? 'N4-2' },
        { responseType: 'blob' },
      )

      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })

      const contentDisposition = response.headers?.['content-disposition'] ?? null
      const sheetLabel = N4_EXPORT_SHEETS.find((s) => s.code === sheet)?.label ?? '税金及附加'
      const filename = parseFilename(
        contentDisposition,
        `N4-${sheetLabel}-数据.xlsx`,
      )

      downloadBlob(blob, filename)
      ElMessage.success('数据已导出')
    } catch (err: any) {
      lastError.value = err?.response?.data?.message || err.message || '导出数据失败'
      ElMessage.error(lastError.value!)
    } finally {
      isExporting.value = false
    }
  }

  // ─── Import Data ───────────────────────────────────────────────────────

  /**
   * 导入xlsx数据（动态行表格）
   * POST /api/n4/import-data (multipart/form-data)
   */
  async function importData(file: File, sheet?: N4ExportSheetCode): Promise<N4ImportResult> {
    if (!wpId.value) {
      return { success: false, message: '底稿ID为空' }
    }
    isImporting.value = true
    lastError.value = null

    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('wpId', wpId.value)
      formData.append('sheet', sheet ?? 'N4-2')

      const response = await http.post(
        `${API_BASE}/import-data`,
        formData,
        {
          headers: { 'Content-Type': 'multipart/form-data' },
        },
      )

      // 兼容 ResponseWrapperMiddleware 信封
      const data: any = response.data?.data ?? response.data
      const result: N4ImportResult = {
        success: true,
        message: data?.message || '导入成功',
        rowCount: data?.imported_count ?? data?.row_count ?? 0,
        warning: data?.warning,
      }

      let msg = `成功导入 ${result.rowCount} 行数据`
      if (result.warning) {
        msg += `（${result.warning}）`
      }
      ElMessage.success(msg)
      return result
    } catch (err: any) {
      const errMsg = err?.response?.data?.detail
        || err?.response?.data?.message
        || err.message
        || '导入数据失败'

      // 格式校验失败（400）可能返回数组
      if (Array.isArray(errMsg)) {
        lastError.value = `列名不匹配: ${errMsg.join(', ')}`
      } else {
        lastError.value = errMsg
      }
      ElMessage.error(lastError.value!)
      return { success: false, message: lastError.value! }
    } finally {
      isImporting.value = false
    }
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 状态
    isExporting,
    isImporting,
    lastError,

    // 常量
    N4_EXPORT_SHEETS,

    // 校验
    isSheetExportable,
    getExportableSheets,

    // 操作
    exportTemplate,
    exportData,
    importData,
  }
}

export default useN4ImportExport
