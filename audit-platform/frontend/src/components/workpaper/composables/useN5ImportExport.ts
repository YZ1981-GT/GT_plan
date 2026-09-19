/**
 * useN5ImportExport — N5 所得税费用导入导出三级 composable
 *
 * Spec: .kiro/specs/n5-income-tax-expense/
 * Task: 3.3
 * Requirements: 4.6
 *
 * 职责：
 * - 三操作：exportTemplate(导出模板) / exportData(导出数据) / importData(导入数据)
 * - el-dropdown "导入导出▾" 3 actions
 * - 使用 http (axios) NOT native fetch（需 Authorization header → 401 without it!）
 * - 动态行表格导入导出目标：
 *   - N5-2 明细表（当期/递延分项明细）
 *   - N5-5 纳税调整明细表（107行大表，支持分sheet导出：按分类收入/扣除/资产/特殊/其他）
 *   - N5-6-1 研发加计扣除（研发项目明细）
 *   - N5-7 财产损失（损失项目明细）
 * - **Special: 纳税调整明细分sheet导出**（N5-5额外参数 category 按分类导出子表）
 * - 后端三端点:
 *   - GET  /api/n5-income-tax-expense/{wpId}/export-template?sheet=xxx
 *   - GET  /api/n5-income-tax-expense/{wpId}/export-data?sheet=xxx[&category=xxx]
 *   - POST /api/n5-income-tax-expense/{wpId}/import-data?sheet=xxx (multipart FormData)
 * - RFC5987 中文文件名解析
 * - Blob下载: responseType:'blob' → URL.createObjectURL → a.click()
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** N5 支持导入导出的 sheet 编码（动态行表格） */
export type N5ExportSheetCode =
  | 'N5-2'    // 明细表
  | 'N5-5'    // 纳税调整明细表（107行，支持分sheet导出）
  | 'N5-6-1'  // 研发加计扣除
  | 'N5-7'    // 财产损失

/** N5-5 纳税调整分类（分sheet导出用） */
export type N5TaxAdjustmentCategory =
  | 'income'   // 收入类调整
  | 'deduction' // 扣除类调整
  | 'asset'    // 资产类调整
  | 'special'  // 特殊事项调整
  | 'other'    // 其他调整

/** N5 导出sheet定义 */
export interface N5ExportSheet {
  code: N5ExportSheetCode
  label: string
}

/** N5-5 纳税调整分类导出定义 */
export interface N5AdjustmentCategoryOption {
  value: N5TaxAdjustmentCategory
  label: string
}

/** 导入结果 */
export interface N5ImportResult {
  /** 是否成功 */
  success: boolean
  /** 消息 */
  message: string
  /** 导入行数 */
  rowCount?: number
  /** 警告信息 */
  warning?: string
}

export interface UseN5ImportExportOptions {
  wpId: Ref<string>
  projectId: Ref<string>
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 支持导入导出的sheet列表（动态行表格） */
export const EXPORT_SHEETS: N5ExportSheet[] = [
  { code: 'N5-2', label: '明细表' },
  { code: 'N5-5', label: '纳税调整明细表' },
  { code: 'N5-6-1', label: '研发加计扣除' },
  { code: 'N5-7', label: '财产损失' },
]

/** N5-5 纳税调整分类列表（分sheet导出用） */
export const ADJUSTMENT_CATEGORIES: N5AdjustmentCategoryOption[] = [
  { value: 'income', label: '收入类调整' },
  { value: 'deduction', label: '扣除类调整' },
  { value: 'asset', label: '资产类调整' },
  { value: 'special', label: '特殊事项调整' },
  { value: 'other', label: '其他调整' },
]

/** API base path */
const API_BASE = '/api/n5-income-tax-expense'

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
 * N5 导入导出三级
 *
 * @param options.wpId 底稿ID（reactive）
 * @param options.projectId 项目ID（reactive）
 */
export function useN5ImportExport(options: UseN5ImportExportOptions) {
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
  function getExportableSheets(): N5ExportSheet[] {
    return [...EXPORT_SHEETS]
  }

  /** 获取纳税调整分类列表（N5-5分sheet导出用） */
  function getAdjustmentCategories(): N5AdjustmentCategoryOption[] {
    return [...ADJUSTMENT_CATEGORIES]
  }

  // ─── Export Template ───────────────────────────────────────────────────

  /**
   * 导出空白xlsx模板（含表头+格式+编制说明）
   * GET /api/n5-income-tax-expense/{wpId}/export-template?sheet=xxx
   */
  async function exportTemplate(sheet?: N5ExportSheetCode): Promise<void> {
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
      const sheetLabel = EXPORT_SHEETS.find((s) => s.code === sheet)?.label ?? '所得税费用'
      const filename = parseFilename(
        contentDisposition,
        sheet ? `N5-${sheetLabel}-模板.xlsx` : 'N5-所得税费用-模板.xlsx',
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
   * GET /api/n5-income-tax-expense/{wpId}/export-data?sheet=xxx[&category=xxx]
   *
   * Special: N5-5 纳税调整明细表支持分sheet导出（按分类导出子表）
   * 传 category 参数可导出指定分类的调整项
   *
   * @param sheet 目标sheet编码
   * @param category N5-5专用：纳税调整分类（不传则导出全部107行）
   */
  async function exportData(
    sheet?: N5ExportSheetCode,
    category?: N5TaxAdjustmentCategory,
  ): Promise<void> {
    if (!wpId.value) return
    isExporting.value = true
    lastError.value = null

    try {
      const params: Record<string, string> = {}
      if (sheet) params.sheet = sheet
      // N5-5 纳税调整明细分sheet导出：传 category 按分类导出
      if (category && sheet === 'N5-5') {
        params.category = category
      }

      const response = await http.get(
        `${API_BASE}/${wpId.value}/export-data`,
        { params, responseType: 'blob' },
      )

      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })

      const contentDisposition = response.headers?.['content-disposition'] ?? null
      const sheetLabel = EXPORT_SHEETS.find((s) => s.code === sheet)?.label ?? '所得税费用'
      const categoryLabel = category
        ? ADJUSTMENT_CATEGORIES.find((c) => c.value === category)?.label ?? ''
        : ''
      const suffix = categoryLabel ? `-${categoryLabel}` : ''
      const filename = parseFilename(
        contentDisposition,
        sheet ? `N5-${sheetLabel}${suffix}-数据.xlsx` : 'N5-所得税费用-数据.xlsx',
      )

      downloadBlob(blob, filename)
      ElMessage.success(categoryLabel ? `${categoryLabel}数据已导出` : '数据已导出')
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
   * POST /api/n5-income-tax-expense/{wpId}/import-data?sheet=xxx (multipart/form-data)
   */
  async function importData(file: File, sheet?: N5ExportSheetCode): Promise<N5ImportResult> {
    if (!wpId.value) {
      return { success: false, message: '底稿ID为空' }
    }
    isImporting.value = true
    lastError.value = null

    try {
      const formData = new FormData()
      formData.append('file', file)
      if (sheet) formData.append('sheet', sheet)

      const params: Record<string, string> = {}
      if (sheet) params.sheet = sheet

      const response = await http.post(
        `${API_BASE}/${wpId.value}/import-data`,
        formData,
        {
          params,
          headers: { 'Content-Type': 'multipart/form-data' },
        },
      )

      // 兼容 ResponseWrapperMiddleware 信封
      const data: any = response.data?.data ?? response.data
      const result: N5ImportResult = {
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
    ADJUSTMENT_CATEGORIES,

    // 校验
    isSheetExportable,
    getExportableSheets,
    getAdjustmentCategories,

    // 操作
    exportTemplate,
    exportData,
    importData,
  }
}

export default useN5ImportExport
