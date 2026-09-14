/**
 * useSEstimateImportExport — S 类计算型底稿导入导出三级 composable
 *
 * Spec: .kiro/specs/s-estimate-calculation-workpapers/
 * Task: 6.3
 * Requirements: 10.1, 10.2, 10.3, 10.4
 *
 * 职责：
 * - 三操作：exportTemplate(导出模板) / exportData(导出数据) / importData(导入数据)
 * - el-dropdown "导入导出▾" 3 actions
 * - 使用 http (axios) NOT native fetch（需 Authorization header → 401 without it!）
 * - 多 sheet 导出支持（S21 多区块分 sheet / S20 双明细分 sheet）:
 *   - S21-2 开发支出资本化分析（12月 × 7类目 grid — dynamic detail）
 *   - S20-unrelated 与主营无关收入明细（动态行）
 *   - S20-noSubstance 不具备商业实质收入明细（动态行）
 * - 后端三端点:
 *   - GET  /api/s-estimate/{wp_id}/export-template?sheet=xxx
 *   - GET  /api/s-estimate/{wp_id}/export-data?sheet=xxx
 *   - POST /api/s-estimate/{wp_id}/import-data (multipart/form-data + sheet query param)
 * - RFC5987 中文文件名解析
 * - Blob下载: responseType:'blob' → URL.createObjectURL → a.click()
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** S 类支持导入导出的 sheet（动态行表格） */
export type SEstimateImportableSheet =
  | 'S21-2'          // 开发支出资本化分析（12月×7类目 grid）
  | 'S20-unrelated'  // 与主营业务无关的业务收入明细
  | 'S20-noSubstance' // 不具备商业实质的收入明细

/** 导入结果 */
export interface SEstimateImportResult {
  /** 是否成功 */
  success: boolean
  /** 消息 */
  message: string
  /** 导入行数 */
  rowCount?: number
  /** 警告信息 */
  warning?: string
}

export interface UseSEstimateImportExportOptions {
  wpId: Ref<string>
  projectId: Ref<string>
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 支持导入导出的 sheet 列表（动态行表格） */
export const S_ESTIMATE_IMPORTABLE_SHEETS: { value: SEstimateImportableSheet; label: string }[] = [
  { value: 'S21-2', label: '开发支出资本化分析（分月归集）' },
  { value: 'S20-unrelated', label: '与主营业务无关的业务收入明细' },
  { value: 'S20-noSubstance', label: '不具备商业实质的收入明细' },
]

/** 可导出 sheet 编码列表 */
const EXPORTABLE_SHEETS: SEstimateImportableSheet[] = ['S21-2', 'S20-unrelated', 'S20-noSubstance']

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 构建 API URL（wp_id 嵌入路径）
 */
function buildApiUrl(wpId: string, action: string): string {
  return `/api/s-estimate/${wpId}/${action}`
}

/**
 * 从 Content-Disposition 解析文件名（支持 RFC5987 编码的中文名）
 * 优先读 filename*=UTF-8''...，fallback 到 filename="..."
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
 * S 类计算型底稿导入导出三级
 *
 * @param options.wpId 底稿ID（reactive）
 * @param options.projectId 项目ID（reactive）
 */
export function useSEstimateImportExport(options: UseSEstimateImportExportOptions) {
  const { wpId } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const isExporting = ref(false)
  const isImporting = ref(false)
  const lastError = ref<string | null>(null)

  // ─── Validation ────────────────────────────────────────────────────────

  /** 当前 sheet 是否支持导入导出 */
  function isSheetExportable(sheet: string): boolean {
    return EXPORTABLE_SHEETS.includes(sheet as SEstimateImportableSheet)
  }

  /** 获取所有可导出 sheet 列表 */
  function getExportableSheets(): SEstimateImportableSheet[] {
    return [...EXPORTABLE_SHEETS]
  }

  // ─── Export Template ───────────────────────────────────────────────────

  /**
   * 导出空白 xlsx 模板（含表头 + 格式 + 编制说明）
   * GET /api/s-estimate/{wp_id}/export-template?sheet=xxx
   */
  async function exportTemplate(sheetName: string): Promise<void> {
    if (!wpId.value) return
    isExporting.value = true
    lastError.value = null

    try {
      const params: Record<string, string> = { sheet: sheetName }

      const response = await http.get(
        buildApiUrl(wpId.value, 'export-template'),
        { params, responseType: 'blob' },
      )

      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })

      const contentDisposition = response.headers?.['content-disposition'] ?? null
      const filename = parseFilename(
        contentDisposition,
        `S类计算底稿-${sheetName}-模板.xlsx`,
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
   * 导出当前数据为 xlsx
   * GET /api/s-estimate/{wp_id}/export-data?sheet=xxx
   */
  async function exportData(sheetName: string): Promise<void> {
    if (!wpId.value) return
    isExporting.value = true
    lastError.value = null

    try {
      const params: Record<string, string> = { sheet: sheetName }

      const response = await http.get(
        buildApiUrl(wpId.value, 'export-data'),
        { params, responseType: 'blob' },
      )

      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })

      const contentDisposition = response.headers?.['content-disposition'] ?? null
      const filename = parseFilename(
        contentDisposition,
        `S类计算底稿-${sheetName}-数据.xlsx`,
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
   * 导入 xlsx 数据
   * POST /api/s-estimate/{wp_id}/import-data (multipart/form-data)
   */
  async function importData(sheetName: string, file: File): Promise<SEstimateImportResult | null> {
    if (!wpId.value) return null
    isImporting.value = true
    lastError.value = null

    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('sheet', sheetName)
      formData.append('wp_id', wpId.value)

      const response = await http.post(
        buildApiUrl(wpId.value, 'import-data'),
        formData,
        {
          params: { sheet: sheetName },
          headers: { 'Content-Type': 'multipart/form-data' },
        },
      )

      // 兼容 ResponseWrapperMiddleware 信封
      const data: any = response.data?.data ?? response.data
      const result: SEstimateImportResult = {
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

export default useSEstimateImportExport
