/**
 * useM10ImportExport — M10 其他权益工具导入导出三级 composable
 *
 * Spec: .kiro/specs/m10-other-equity-instruments/
 * Task: 3.3
 * Requirements: 6.6
 *
 * 职责：
 * - 三操作：exportTemplate(导出模板) / exportData(导出数据) / importData(导入数据)
 * - el-dropdown "导入导出▾" 3 actions
 * - 使用 http (axios) NOT native fetch（需 Authorization header → 401 without it!）
 * - 多sheet导出支持（M10-2 明细表为主要导入导出目标，永续债/优先股动态行）:
 *   - M10-2 明细表（primary — 永续债/优先股明细动态行）
 * - 后端三端点:
 *   - GET  /api/m10/export-template?sheet=M10-2
 *   - GET  /api/m10/export-data?wp_id={wpId}&sheet=M10-2
 *   - POST /api/m10/import-data (multipart/form-data: file + wp_id + sheet)
 * - RFC5987 中文文件名解析
 * - Blob下载: responseType:'blob' → URL.createObjectURL → a.click()
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** M10 支持导入导出的 sheet（动态行表格） */
export type M10ImportableSheet =
  | 'M10-2'   // 明细表（永续债/优先股明细，primary）

/** 导入结果 */
export interface M10ImportResult {
  /** 是否成功 */
  success: boolean
  /** 消息 */
  message: string
  /** 导入行数 */
  rowCount?: number
  /** 警告信息 */
  warning?: string
}

export interface UseM10ImportExportOptions {
  wpId: Ref<string>
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 支持导入导出的sheet列表（动态行表格） */
export const M10_IMPORTABLE_SHEETS: { value: M10ImportableSheet; label: string }[] = [
  { value: 'M10-2', label: '明细表（永续债/优先股明细）' },
]

/** 可导出sheet编码列表 */
const EXPORTABLE_SHEETS: M10ImportableSheet[] = ['M10-2']

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
 * M10 导入导出三级
 *
 * @param options.wpId 底稿ID（reactive）
 */
export function useM10ImportExport(options: UseM10ImportExportOptions) {
  const { wpId } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const isExporting = ref(false)
  const isImporting = ref(false)
  const lastError = ref<string | null>(null)

  // ─── Validation ────────────────────────────────────────────────────────

  /** 当前sheet是否支持导入导出 */
  function isSheetExportable(sheet: string): boolean {
    return EXPORTABLE_SHEETS.includes(sheet as M10ImportableSheet)
  }

  /** 获取所有可导出sheet列表 */
  function getExportableSheets(): M10ImportableSheet[] {
    return [...EXPORTABLE_SHEETS]
  }

  // ─── Export Template ───────────────────────────────────────────────────

  /**
   * 导出空白xlsx模板（含表头+格式+编制说明）
   * GET /api/m10/export-template?sheet=xxx
   */
  async function exportTemplate(sheet: string): Promise<void> {
    if (!wpId.value) return
    isExporting.value = true
    lastError.value = null

    try {
      const params: Record<string, string> = { sheet }

      const response = await http.get(
        '/api/m10/export-template',
        { params, responseType: 'blob' },
      )

      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })

      const contentDisposition = response.headers?.['content-disposition'] ?? null
      const filename = parseFilename(
        contentDisposition,
        `M10-其他权益工具-${sheet}-模板.xlsx`,
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
   * GET /api/m10/export-data?wp_id={wpId}&sheet=xxx
   */
  async function exportData(sheet: string): Promise<void> {
    if (!wpId.value) return
    isExporting.value = true
    lastError.value = null

    try {
      const params: Record<string, string> = {
        wp_id: wpId.value,
        sheet,
      }

      const response = await http.get(
        '/api/m10/export-data',
        { params, responseType: 'blob' },
      )

      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })

      const contentDisposition = response.headers?.['content-disposition'] ?? null
      const filename = parseFilename(
        contentDisposition,
        `M10-其他权益工具-${sheet}-数据.xlsx`,
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
   * 导入xlsx数据（M10-2 明细表为主要目标，永续债/优先股动态行）
   * POST /api/m10/import-data (multipart/form-data: file + wp_id + sheet)
   */
  async function importData(sheet: string, file: File): Promise<M10ImportResult | null> {
    if (!wpId.value) return null
    isImporting.value = true
    lastError.value = null

    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('wp_id', wpId.value)
      formData.append('sheet', sheet)

      const response = await http.post(
        '/api/m10/import-data',
        formData,
        {
          headers: { 'Content-Type': 'multipart/form-data' },
        },
      )

      // 兼容 ResponseWrapperMiddleware 信封
      const data: any = response.data?.data ?? response.data
      const result: M10ImportResult = {
        success: true,
        message: '',
        rowCount: data.imported_count ?? data.rowCount ?? 0,
        warning: data.warning,
      }

      let msg = `成功导入 ${result.rowCount} 行数据`
      if (result.warning) {
        msg += `（${result.warning}）`
      }
      result.message = msg
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

    // 验证
    isSheetExportable,
    getExportableSheets,

    // 操作
    exportTemplate,
    exportData,
    importData,
  }
}

export default useM10ImportExport
