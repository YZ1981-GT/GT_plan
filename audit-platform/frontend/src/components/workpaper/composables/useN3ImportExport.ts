/**
 * useN3ImportExport — N3 递延所得税负债导入导出三级 composable
 *
 * Spec: .kiro/specs/n3-deferred-tax-liabilities/
 * Task: 3.3
 * Requirements: 3.4
 *
 * 职责：
 * - 三操作：exportTemplate(导出模板) / exportData(导出数据) / importData(导入数据)
 * - el-dropdown "导入导出▾" 3 actions
 * - 使用 http (axios) NOT native fetch（需 Authorization header → 401 without it!）
 * - 动态行表格(N3-2明细表)为主要导入导出目标
 * - 后端三端点:
 *   - GET  /api/n3-deferred-tax-liabilities/{wpId}/export-template
 *   - GET  /api/n3-deferred-tax-liabilities/{wpId}/export-data
 *   - POST /api/n3-deferred-tax-liabilities/{wpId}/import-data (multipart FormData)
 * - RFC5987 中文文件名解析
 * - Blob下载: responseType:'blob' → URL.createObjectURL → a.click()
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** N3 支持导入导出的 sheet 编码（N3-2明细表为主要动态行目标） */
export type N3ExportSheetCode = 'N3-2'

/** N3 导出sheet定义 */
export interface N3ExportSheet {
  code: N3ExportSheetCode
  label: string
}

/** 导入结果 */
export interface N3ImportResult {
  /** 是否成功 */
  success: boolean
  /** 消息 */
  message: string
  /** 导入行数 */
  rowCount?: number
  /** 警告信息 */
  warning?: string
}

export interface UseN3ImportExportOptions {
  wpId: Ref<string>
  projectId: Ref<string>
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 支持导入导出的sheet列表（N3-2明细表是唯一动态行表格） */
export const EXPORT_SHEETS: N3ExportSheet[] = [
  { code: 'N3-2', label: '递延所得税负债明细表' },
]

/** API base path */
const API_BASE = '/api/n3-deferred-tax-liabilities'

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
 * N3 导入导出三级
 *
 * @param options.wpId 底稿ID（reactive）
 * @param options.projectId 项目ID（reactive）
 */
export function useN3ImportExport(options: UseN3ImportExportOptions) {
  const { wpId, projectId } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const isExporting = ref(false)
  const isImporting = ref(false)
  const lastError = ref<string | null>(null)

  // ─── Validation ────────────────────────────────────────────────────────

  /** 当前sheet是否支持导入导出 */
  function isSheetExportable(sheet: string): boolean {
    return EXPORT_SHEETS.some((s) => s.code === sheet)
  }

  /** 获取所有可导出sheet列表 */
  function getExportableSheets(): N3ExportSheet[] {
    return [...EXPORT_SHEETS]
  }

  // ─── Export Template ───────────────────────────────────────────────────

  /**
   * 导出空白xlsx模板（含表头+格式+编制说明）
   * GET /api/n3-deferred-tax-liabilities/{wpId}/export-template
   */
  async function exportTemplate(sheet?: N3ExportSheetCode): Promise<void> {
    if (!wpId.value) return
    isExporting.value = true
    lastError.value = null

    try {
      const params: Record<string, string> = {}
      if (sheet) params.sheet = sheet

      const response = await http.get(
        `${API_BASE}/${wpId.value}/export-template`,
        { params, responseType: 'blob' },
      )

      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })

      const contentDisposition = response.headers?.['content-disposition'] ?? null
      const sheetLabel = EXPORT_SHEETS.find((s) => s.code === sheet)?.label ?? '递延所得税负债'
      const filename = parseFilename(
        contentDisposition,
        sheet ? `N3-${sheetLabel}-模板.xlsx` : 'N3-递延所得税负债-模板.xlsx',
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
   * 导出当前数据为xlsx（N3-2明细表动态行数据）
   * GET /api/n3-deferred-tax-liabilities/{wpId}/export-data
   */
  async function exportData(sheet?: N3ExportSheetCode): Promise<void> {
    if (!wpId.value) return
    isExporting.value = true
    lastError.value = null

    try {
      const params: Record<string, string> = {}
      if (sheet) params.sheet = sheet

      const response = await http.get(
        `${API_BASE}/${wpId.value}/export-data`,
        { params, responseType: 'blob' },
      )

      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })

      const contentDisposition = response.headers?.['content-disposition'] ?? null
      const sheetLabel = EXPORT_SHEETS.find((s) => s.code === sheet)?.label ?? '递延所得税负债'
      const filename = parseFilename(
        contentDisposition,
        sheet ? `N3-${sheetLabel}-数据.xlsx` : 'N3-递延所得税负债-数据.xlsx',
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
   * 导入xlsx数据（N3-2明细表动态行）
   * POST /api/n3-deferred-tax-liabilities/{wpId}/import-data (multipart/form-data)
   */
  async function importData(file: File, sheet?: N3ExportSheetCode): Promise<N3ImportResult> {
    if (!wpId.value) {
      return { success: false, message: '底稿ID为空' }
    }
    isImporting.value = true
    lastError.value = null

    try {
      const formData = new FormData()
      formData.append('file', file)
      if (sheet) formData.append('sheet', sheet)

      const response = await http.post(
        `${API_BASE}/${wpId.value}/import-data`,
        formData,
        {
          headers: { 'Content-Type': 'multipart/form-data' },
        },
      )

      // 兼容 ResponseWrapperMiddleware 信封
      const data: any = response.data?.data ?? response.data
      const result: N3ImportResult = {
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
    EXPORT_SHEETS,

    // 校验
    isSheetExportable,
    getExportableSheets,

    // 操作
    exportTemplate,
    exportData,
    importData,
  }
}

export default useN3ImportExport
