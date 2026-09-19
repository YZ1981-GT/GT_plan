/**
 * useN2ImportExport — N2 应交税费导入导出三级 composable
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 3.3
 * Requirements: 3.4
 *
 * 职责：
 * - 三操作：exportTemplate(导出模板) / exportData(导出数据) / importData(导入数据)
 * - el-dropdown "导入导出▾" 3 actions
 * - 使用 http (axios) NOT native fetch（需 Authorization header → 401 without it!）
 * - 多税种分sheet导出（5 sheets）:
 *   明细表(N2-2) / 增值税测算表(N2-6) / 其他税费测算表(N2-8) / 房产税测算表(N2-9) / 土地增值税测算表(N2-10)
 * - 后端三端点:
 *   - GET  /api/n2-taxes-payable/{wpId}/export-template?sheet={sheetCode}
 *   - GET  /api/n2-taxes-payable/{wpId}/export-data?sheet={sheetCode}
 *   - POST /api/n2-taxes-payable/{wpId}/import-data (multipart FormData with sheet field)
 * - RFC5987 中文文件名解析
 * - Blob下载: responseType:'blob' → URL.createObjectURL → a.click()
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** N2 支持导入导出的 sheet 编码 */
export type N2ExportSheetCode = 'N2-2' | 'N2-6' | 'N2-8' | 'N2-9' | 'N2-10'

/** N2 导出sheet定义 */
export interface N2ExportSheet {
  code: N2ExportSheetCode
  label: string
}

/** 导入结果 */
export interface N2ImportResult {
  /** 是否成功 */
  success: boolean
  /** 消息 */
  message: string
  /** 导入行数 */
  rowCount?: number
  /** 警告信息 */
  warning?: string
}

export interface UseN2ImportExportOptions {
  wpId: Ref<string>
  projectId: Ref<string>
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 支持导入导出的sheet列表（多税种分sheet） */
export const EXPORT_SHEETS: N2ExportSheet[] = [
  { code: 'N2-2', label: '应交税费明细表' },
  { code: 'N2-6', label: '增值税测算表' },
  { code: 'N2-8', label: '其他税费测算表' },
  { code: 'N2-9', label: '房产税测算表' },
  { code: 'N2-10', label: '土地增值税测算表' },
]

/** API base path */
const API_BASE = '/api/n2-taxes-payable'

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
 * N2 导入导出三级
 *
 * @param options.wpId 底稿ID（reactive）
 * @param options.projectId 项目ID（reactive）
 */
export function useN2ImportExport(options: UseN2ImportExportOptions) {
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
  function getExportableSheets(): N2ExportSheet[] {
    return [...EXPORT_SHEETS]
  }

  // ─── Export Template ───────────────────────────────────────────────────

  /**
   * 导出空白xlsx模板（含表头+格式+编制说明）
   * GET /api/n2-taxes-payable/{wpId}/export-template?sheet={sheetCode}
   */
  async function exportTemplate(sheet?: N2ExportSheetCode): Promise<void> {
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
      const sheetLabel = EXPORT_SHEETS.find((s) => s.code === sheet)?.label ?? '应交税费'
      const filename = parseFilename(
        contentDisposition,
        sheet ? `N2-${sheetLabel}-模板.xlsx` : 'N2-应交税费-模板.xlsx',
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
   * 导出当前数据为xlsx（多税种分sheet导出）
   * GET /api/n2-taxes-payable/{wpId}/export-data?sheet={sheetCode}
   * 不指定sheet时导出所有5个动态行sheet
   */
  async function exportData(sheet?: N2ExportSheetCode): Promise<void> {
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
      const sheetLabel = EXPORT_SHEETS.find((s) => s.code === sheet)?.label ?? '应交税费'
      const filename = parseFilename(
        contentDisposition,
        sheet ? `N2-${sheetLabel}-数据.xlsx` : 'N2-应交税费-数据.xlsx',
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
   * 导入xlsx数据
   * POST /api/n2-taxes-payable/{wpId}/import-data (multipart/form-data with sheet field)
   */
  async function importData(file: File, sheet?: N2ExportSheetCode): Promise<N2ImportResult> {
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
      const result: N2ImportResult = {
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

export default useN2ImportExport
