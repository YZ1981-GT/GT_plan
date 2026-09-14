/**
 * useG7EquityMethodImportExport — G7 长期股权投资(权益法组) 导入导出 composable
 *
 * Spec: .kiro/specs/g7-long-term-equity-method/ Task 9.2
 * Requirements: 7.3
 *
 * 7张动态行表格 × 3端点 = 21端点调用：
 *   POST /api/workpapers/{wpId}/g7-equity-method/export-template?sheet={code}
 *   POST /api/workpapers/{wpId}/g7-equity-method/export-data?sheet={code}
 *   POST /api/workpapers/{wpId}/g7-equity-method/import-data?sheet={code}  (multipart/form-data)
 *
 * sheet codes: G7-4 / G7-5 / G7-6 / G7-13 / G7-14 / G7-15 / G7-16 / G7-17
 * 宽表按区段分sheet导出：G7-13(2sheet) / G7-14(2sheet) / G7-16(2sheet)
 * 原底稿单sheet导出：G7-4；普通单sheet导出：G7-5 / G7-6 / G7-15 / G7-17
 *
 * UI 铁律：el-dropdown「导入导出 ▾」（导出模板/导出数据/导入数据）
 * 使用 axios (http from @/utils/http) 非原生 fetch — for Authorization header
 * 处理 StreamingResponse + 中文文件名 RFC5987 编码
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

// ═══ 类型定义 ═══

/** G7(权益法组) 支持导入导出的 sheet 编码（含 G7-6 会计政策） */
export type G7EquityMethodImportableSheet =
  | 'G7-4'
  | 'G7-5'
  | 'G7-6'
  | 'G7-13'
  | 'G7-14'
  | 'G7-15'
  | 'G7-16'
  | 'G7-17'

/** 导入结果 */
export interface G7EquityMethodImportResult {
  rowCount: number
  fieldCount: number
  warning?: string
  errors?: string[]
}

/** sheet 元数据（供下拉菜单展示） */
export interface G7EquityMethodSheetMeta {
  code: G7EquityMethodImportableSheet
  label: string
  /** 宽表按区段分sheet导出 */
  multiSheet?: boolean
}

// ═══ 常量 ═══

export const G7_EQUITY_METHOD_API_PREFIX = 'g7-equity-method'

/** 7张可导入导出 sheet 的中文标签 */
export const G7_EQUITY_METHOD_IMPORT_EXPORT_SHEETS: G7EquityMethodSheetMeta[] = [
  { code: 'G7-4', label: 'G7-4 被投资单位基本信息' },
  { code: 'G7-5', label: 'G7-5 被投资单位财务信息' },
  { code: 'G7-6', label: 'G7-6 被投资公司会计政策' },
  { code: 'G7-13', label: 'G7-13 投资成本测试表（2区段）', multiSheet: true },
  { code: 'G7-14', label: 'G7-14 权益法测算表（3数据区+净资产/商誉附表）', multiSheet: true },
  { code: 'G7-15', label: 'G7-15 内部交易抵销测算表' },
  { code: 'G7-16', label: 'G7-16 未确认投资损失（2区段）', multiSheet: true },
  { code: 'G7-17', label: 'G7-17 减值测试表' },
]

// ═══ 工具函数 ═══

/**
 * 从 Content-Disposition header 解析文件名
 * 支持 RFC5987 中文编码: filename*=UTF-8''%E5%AF%BC%E5%87%BA.xlsx
 * 以及普通 filename="xxx.xlsx"
 */
function parseFilenameFromHeader(contentDisposition: string | null | undefined): string {
  if (!contentDisposition) return '导出文件.xlsx'

  // RFC5987 filename*=UTF-8''xxx 格式
  const rfc5987Match = contentDisposition.match(/filename\*=(?:UTF-8|utf-8)''(.+?)(?:;|$)/i)
  if (rfc5987Match) {
    try {
      return decodeURIComponent(rfc5987Match[1])
    } catch {
      // fallback
    }
  }

  // 普通 filename="xxx" 或 filename=xxx
  const filenameMatch = contentDisposition.match(/filename="?([^";]+)"?/i)
  if (filenameMatch) {
    return filenameMatch[1].trim()
  }

  return '导出文件.xlsx'
}

/**
 * 下载 Blob 文件
 */
function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

/**
 * sheetName → 可导入导出 sheet code（用于按当前 sheet 过滤下拉项）
 */
export function resolveG7EquityMethodImportableSheet(
  sheetName: string,
): G7EquityMethodImportableSheet | null {
  const m = (sheetName || '').match(/G7-(\d+)/)
  if (!m) return null
  const code = `G7-${m[1]}` as G7EquityMethodImportableSheet
  return G7_EQUITY_METHOD_IMPORT_EXPORT_SHEETS.some((s) => s.code === code) ? code : null
}

// ═══ Composable 接口 ═══

export interface UseG7EquityMethodImportExportOptions {
  wpId: Ref<string>
}

export interface UseG7EquityMethodImportExportReturn {
  /** 是否正在导入中 */
  importing: Ref<boolean>
  /** 最近一次错误信息 */
  lastError: Ref<string | null>
  /** 所有可导入导出的 sheet 元数据 */
  sheets: G7EquityMethodSheetMeta[]
  /** 导出空白模板 */
  exportTemplate: (sheet: G7EquityMethodImportableSheet) => Promise<void>
  /** 导出当前数据 */
  exportData: (sheet: G7EquityMethodImportableSheet) => Promise<void>
  /** 导入数据（multipart/form-data） */
  importData: (
    sheet: G7EquityMethodImportableSheet,
    file: File,
  ) => Promise<G7EquityMethodImportResult | null>
  /** API前缀 */
  apiPrefix: string
}

// ═══ Composable 主体 ═══

export function useG7EquityMethodImportExport(
  options: UseG7EquityMethodImportExportOptions,
): UseG7EquityMethodImportExportReturn {
  const { wpId } = options
  const importing = ref(false)
  const lastError = ref<string | null>(null)

  function apiBase(): string {
    return `/api/workpapers/${wpId.value}/${G7_EQUITY_METHOD_API_PREFIX}`
  }

  /**
   * 导出模板 — POST /api/workpapers/{wp_id}/g7-equity-method/export-template?sheet={code}
   * G7-4按原底稿单sheet导出；G7-13/G7-14/G7-16按区段分sheet导出。
   */
  async function exportTemplate(sheet: G7EquityMethodImportableSheet): Promise<void> {
    lastError.value = null
    try {
      const response = await http.post(`${apiBase()}/export-template`, null, {
        params: { sheet },
        responseType: 'blob',
      })
      const contentDisposition = response.headers?.['content-disposition']
      const filename = parseFilenameFromHeader(contentDisposition) || `${sheet}-模板.xlsx`
      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })
      downloadBlob(blob, filename)
      ElMessage.success(`${sheet} 模板已导出`)
    } catch (err: any) {
      const msg =
        err?.response?.data?.message || err?.response?.data?.detail || err.message || '导出模板失败'
      lastError.value = typeof msg === 'string' ? msg : JSON.stringify(msg)
      ElMessage.error(lastError.value!)
    }
  }

  /**
   * 导出数据 — POST /api/workpapers/{wp_id}/g7-equity-method/export-data?sheet={code}
   * G7-4按原底稿单sheet导出；G7-13/G7-14/G7-16按区段分sheet导出。
   */
  async function exportData(sheet: G7EquityMethodImportableSheet): Promise<void> {
    lastError.value = null
    try {
      const response = await http.post(`${apiBase()}/export-data`, null, {
        params: { sheet },
        responseType: 'blob',
      })
      const contentDisposition = response.headers?.['content-disposition']
      const filename = parseFilenameFromHeader(contentDisposition) || `${sheet}-数据.xlsx`
      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })
      downloadBlob(blob, filename)
      ElMessage.success(`${sheet} 数据已导出`)
    } catch (err: any) {
      const msg =
        err?.response?.data?.message || err?.response?.data?.detail || err.message || '导出数据失败'
      lastError.value = typeof msg === 'string' ? msg : JSON.stringify(msg)
      ElMessage.error(lastError.value!)
    }
  }

  /**
   * 导入数据 — POST /api/workpapers/{wp_id}/g7-equity-method/import-data?sheet={code}
   * multipart/form-data 上传 xlsx 文件
   */
  async function importData(
    sheet: G7EquityMethodImportableSheet,
    file: File,
  ): Promise<G7EquityMethodImportResult | null> {
    lastError.value = null
    importing.value = true
    try {
      const formData = new FormData()
      formData.append('file', file)

      const response = await http.post(`${apiBase()}/import-data`, formData, {
        params: { sheet },
        headers: { 'Content-Type': 'multipart/form-data' },
      })

      const data: any = response.data?.data ?? response.data
      // 后端返回 ok=false 表示有业务错误
      if (data.ok === false) {
        const errors = data.errors || []
        const msg = errors.length > 0 ? errors.join('；') : '导入失败'
        lastError.value = msg
        ElMessage.error(msg)
        return null
      }

      const result: G7EquityMethodImportResult = {
        rowCount: data.imported_count ?? data.rowCount ?? 0,
        fieldCount: data.fieldCount ?? 0,
        warning: data.warning,
        errors: data.errors,
      }

      let msg = `成功导入 ${result.rowCount} 行数据`
      if (result.warning) msg += `（${result.warning}）`
      ElMessage.success(msg)
      return result
    } catch (err: any) {
      const errMsg =
        err?.response?.data?.detail || err?.response?.data?.message || err.message || '导入数据失败'
      lastError.value = Array.isArray(errMsg) ? errMsg.join(', ') : String(errMsg)
      ElMessage.error(lastError.value!)
      return null
    } finally {
      importing.value = false
    }
  }

  return {
    importing,
    lastError,
    sheets: G7_EQUITY_METHOD_IMPORT_EXPORT_SHEETS,
    exportTemplate,
    exportData,
    importData,
    apiPrefix: G7_EQUITY_METHOD_API_PREFIX,
  }
}

export default useG7EquityMethodImportExport
