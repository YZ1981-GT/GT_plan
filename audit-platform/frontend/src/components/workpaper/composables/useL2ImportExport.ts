/**
 * useL2ImportExport — L2 应付利息导入导出三级 composable
 *
 * Spec: .kiro/specs/l2-interest-payable/
 * Task: 3.3
 * Requirements: 6.5
 *
 * 职责：
 * - 三操作：exportTemplate(导出模板) / exportData(导出数据) / importData(导入数据)
 * - el-dropdown "导入导出▾" 3 actions
 * - 使用 http (axios) NOT native fetch（需 Authorization header → 401 without it!）
 * - 多section导出 by sheet
 * - 后端三端点:
 *   - GET  /api/l2-interest-payable/{wpId}/export-template
 *   - GET  /api/l2-interest-payable/{wpId}/export-data
 *   - POST /api/l2-interest-payable/{wpId}/import-data
 * - RFC5987 中文文件名解析
 * - Blob下载: responseType:'blob' → URL.createObjectURL → a.click()
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** L2 支持导入导出的 sheet */
export type L2ImportableSheet =
  | 'L2-2'   // 明细表（动态行，核心导入导出）

/** 导入结果 */
export interface L2ImportResult {
  /** 是否成功 */
  success: boolean
  /** 消息 */
  message: string
  /** 导入行数 */
  rowCount?: number
  /** 警告信息 */
  warning?: string
}

export interface UseL2ImportExportOptions {
  wpId: Ref<string>
  projectId: Ref<string>
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 支持导入导出的sheet列表 */
const EXPORTABLE_SHEETS: L2ImportableSheet[] = ['L2-2']

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
 * L2 导入导出三级
 *
 * @param options.wpId 底稿ID（reactive）
 * @param options.projectId 项目ID（reactive）
 */
export function useL2ImportExport(options: UseL2ImportExportOptions) {
  const { wpId, projectId } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const isExporting = ref(false)
  const isImporting = ref(false)
  const lastError = ref<string | null>(null)

  // ─── Validation ────────────────────────────────────────────────────────

  /** 当前sheet是否支持导入导出 */
  function isSheetExportable(sheet: string): boolean {
    return EXPORTABLE_SHEETS.includes(sheet as L2ImportableSheet)
  }

  // ─── Export Template ───────────────────────────────────────────────────

  /**
   * 导出空白xlsx模板（含表头+格式+编制说明）
   * GET /api/l2-interest-payable/{wpId}/export-template?sheet=xxx
   */
  async function exportTemplate(sheet?: L2ImportableSheet): Promise<void> {
    if (!wpId.value) return
    isExporting.value = true
    lastError.value = null

    try {
      const params: Record<string, string> = {}
      if (sheet) params.sheet = sheet

      const response = await http.get(
        `/api/l2-interest-payable/${wpId.value}/export-template`,
        { params, responseType: 'blob' },
      )

      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })

      const contentDisposition = response.headers?.['content-disposition'] ?? null
      const filename = parseFilename(
        contentDisposition,
        sheet ? `L2-${sheet}-模板.xlsx` : 'L2-应付利息-模板.xlsx',
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
   * GET /api/l2-interest-payable/{wpId}/export-data?sheet=xxx
   */
  async function exportData(sheet?: L2ImportableSheet): Promise<void> {
    if (!wpId.value) return
    isExporting.value = true
    lastError.value = null

    try {
      const params: Record<string, string> = {}
      if (sheet) params.sheet = sheet

      const response = await http.get(
        `/api/l2-interest-payable/${wpId.value}/export-data`,
        { params, responseType: 'blob' },
      )

      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })

      const contentDisposition = response.headers?.['content-disposition'] ?? null
      const filename = parseFilename(
        contentDisposition,
        sheet ? `L2-${sheet}-数据.xlsx` : 'L2-应付利息-数据.xlsx',
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
   * POST /api/l2-interest-payable/{wpId}/import-data (multipart/form-data)
   */
  async function importData(file: File, sheet?: L2ImportableSheet): Promise<L2ImportResult> {
    if (!wpId.value) {
      return { success: false, message: '底稿ID为空' }
    }
    isImporting.value = true
    lastError.value = null

    try {
      const formData = new FormData()
      formData.append('file', file)

      const params: Record<string, string> = {}
      if (sheet) params.sheet = sheet

      const response = await http.post(
        `/api/l2-interest-payable/${wpId.value}/import-data`,
        formData,
        {
          params,
          headers: { 'Content-Type': 'multipart/form-data' },
        },
      )

      // 兼容 ResponseWrapperMiddleware 信封
      const data: any = response.data?.data ?? response.data
      const result: L2ImportResult = {
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

    // 校验
    isSheetExportable,

    // 操作
    exportTemplate,
    exportData,
    importData,
  }
}

export default useL2ImportExport
