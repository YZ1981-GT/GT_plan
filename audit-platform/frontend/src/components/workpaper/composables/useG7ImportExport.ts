/**
 * useG7ImportExport — G7 长期股权投资(main组) 导入导出 composable
 *
 * Spec: .kiro/specs/g7-long-term-equity-main/ Task 2.4
 * Requirements: 5.6, 6.1, 6.4
 *
 * 2张动态行表格 × 3端点 = 6端点调用：
 *   POST /api/workpapers/{wpId}/g7-main/export-template?sheet={code}
 *   POST /api/workpapers/{wpId}/g7-main/export-data?sheet={code}
 *   POST /api/workpapers/{wpId}/g7-main/import-data?sheet={code}  (multipart/form-data)
 *
 * sheet codes: G7-2 / G7-3
 * G7-2 按原表三大业务区导出（成本法/权益法/减值准备），并支持导入原始模板。
 *
 * UI 铁律：el-dropdown「导入导出 ▾」（导出模板/导出数据/导入数据）
 * 使用 axios (http from @/utils/http) 非原生 fetch — for Authorization header
 * 处理 StreamingResponse + 中文文件名 RFC5987 编码
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

// ═══ 类型定义 ═══

/** G7(main) 支持导入导出的 sheet 编码（2张动态行表格） */
export type G7MainImportableSheet = 'G7-2' | 'G7-3'

/** 导入结果 */
export interface G7MainImportResult {
  rowCount: number
  fieldCount: number
  warning?: string
  errors?: string[]
}

/** sheet 元数据（供下拉菜单展示） */
export interface G7MainSheetMeta {
  code: G7MainImportableSheet
  label: string
  /** G7-2按三大业务区分sheet导出 */
  multiSheet?: boolean
}

// ═══ 常量 ═══

export const G7_MAIN_API_PREFIX = 'g7-main'

/** 2张可导入导出 sheet 的中文标签 */
export const G7_MAIN_IMPORT_EXPORT_SHEETS: G7MainSheetMeta[] = [
  { code: 'G7-2', label: 'G7-2 明细表（成本法/权益法/减值）', multiSheet: true },
  { code: 'G7-3', label: 'G7-3 调整分录汇总' },
]

/** G7-2 的三大业务区（multi-sheet导出） */
export const G7_2_SEGMENTS = [
  { key: 'cost', label: '成本法' },
  { key: 'equity', label: '权益法' },
  { key: 'impairment', label: '减值准备' },
] as const

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
export function resolveG7MainImportableSheet(sheetName: string): G7MainImportableSheet | null {
  const m = (sheetName || '').match(/G7-(\d+)/)
  if (!m) return null
  const code = `G7-${m[1]}` as G7MainImportableSheet
  return G7_MAIN_IMPORT_EXPORT_SHEETS.some((s) => s.code === code) ? code : null
}

// ═══ Composable 接口 ═══

export interface UseG7ImportExportOptions {
  wpId: Ref<string>
}

export interface UseG7ImportExportReturn {
  /** 是否正在导入中 */
  importing: Ref<boolean>
  /** 最近一次错误信息 */
  lastError: Ref<string | null>
  /** 所有可导入导出的 sheet 元数据 */
  sheets: G7MainSheetMeta[]
  /** 导出空白模板 */
  exportTemplate: (sheet: G7MainImportableSheet) => Promise<void>
  /** 导出当前数据 */
  exportData: (sheet: G7MainImportableSheet) => Promise<void>
  /** 导入数据（multipart/form-data） */
  importData: (sheet: G7MainImportableSheet, file: File) => Promise<G7MainImportResult | null>
  /** API前缀 */
  apiPrefix: string
}

// ═══ Composable 主体 ═══

export function useG7ImportExport(options: UseG7ImportExportOptions): UseG7ImportExportReturn {
  const { wpId } = options
  const importing = ref(false)
  const lastError = ref<string | null>(null)

  function apiBase(): string {
    return `/api/workpapers/${wpId.value}/${G7_MAIN_API_PREFIX}`
  }

  /**
   * 导出模板 — POST /api/workpapers/{wp_id}/g7-main/export-template?sheet={code}
   * G7-2 按三大业务区分sheet导出（后端返回multi-sheet xlsx）
   */
  async function exportTemplate(sheet: G7MainImportableSheet): Promise<void> {
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
      const msg = err?.response?.data?.message || err?.response?.data?.detail || err.message || '导出模板失败'
      lastError.value = typeof msg === 'string' ? msg : JSON.stringify(msg)
      ElMessage.error(lastError.value!)
    }
  }

  /**
   * 导出数据 — POST /api/workpapers/{wp_id}/g7-main/export-data?sheet={code}
   * G7-2 按三大业务区分sheet导出（后端返回multi-sheet xlsx with data）
   */
  async function exportData(sheet: G7MainImportableSheet): Promise<void> {
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
      const msg = err?.response?.data?.message || err?.response?.data?.detail || err.message || '导出数据失败'
      lastError.value = typeof msg === 'string' ? msg : JSON.stringify(msg)
      ElMessage.error(lastError.value!)
    }
  }

  /**
   * 导入数据 — POST /api/workpapers/{wp_id}/g7-main/import-data?sheet={code}
   * multipart/form-data 上传 xlsx 文件
   */
  async function importData(sheet: G7MainImportableSheet, file: File): Promise<G7MainImportResult | null> {
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

      const result: G7MainImportResult = {
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
      const errMsg = err?.response?.data?.detail
        || err?.response?.data?.message
        || err.message
        || '导入数据失败'
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
    sheets: G7_MAIN_IMPORT_EXPORT_SHEETS,
    exportTemplate,
    exportData,
    importData,
    apiPrefix: G7_MAIN_API_PREFIX,
  }
}

export default useG7ImportExport
