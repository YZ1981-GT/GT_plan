/**
 * useK13ImportExport — K13 营业外支出 导入导出 composable
 *
 * Spec: .kiro/specs/k13-non-operating-expense/
 * Task: 3.3
 * Requirements: 3.3, 6.2
 *
 * 动态行表格 × 3端点：
 *   POST /api/workpapers/{wpId}/k13/export-template
 *   POST /api/workpapers/{wpId}/k13/export-data
 *   POST /api/workpapers/{wpId}/k13/import-data  (multipart/form-data)
 *
 * 仅 K13-2 明细表需要导入导出（动态行）
 *
 * UI 铁律：el-dropdown「导入导出 ▾」（导出模板/导出数据/导入数据）
 * 使用 http (axios from @/utils/http) 非原生 fetch — for Authorization header（401 issue）
 * 处理 StreamingResponse + 中文文件名 RFC5987 编码
 * 文件下载：Blob + createObjectURL
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

// ═══ 类型定义 ═══

/** K13 支持导入导出的 sheet 编码（仅 K13-2 明细表，动态行） */
export type K13ImportableSheet = 'K13-2'

/** 导入结果 */
export interface K13ImportResult {
  rowCount: number
  fieldCount: number
  warning?: string
  errors?: string[]
}

/** sheet 元数据（供下拉菜单展示） */
export interface K13SheetMeta {
  code: K13ImportableSheet
  label: string
}

// ═══ 常量 ═══

export const K13_API_PREFIX = 'k13'

/** 可导入导出 sheet 的中文标签（仅 K13-2 明细表） */
export const K13_IMPORT_EXPORT_SHEETS: K13SheetMeta[] = [
  { code: 'K13-2', label: 'K13-2 明细表' },
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
export function resolveK13ImportableSheet(sheetName: string): K13ImportableSheet | null {
  const m = (sheetName || '').match(/K13-(\d+)/)
  if (!m) return null
  const code = `K13-${m[1]}` as K13ImportableSheet
  return K13_IMPORT_EXPORT_SHEETS.some((s) => s.code === code) ? code : null
}

// ═══ Composable 接口 ═══

export interface UseK13ImportExportOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  sheetCode: string
}

export interface UseK13ImportExportReturn {
  /** 是否正在导出中 */
  isExporting: Ref<boolean>
  /** 是否正在导入中 */
  isImporting: Ref<boolean>
  /** 最近一次错误信息 */
  lastError: Ref<string | null>
  /** 所有可导入导出的 sheet 元数据 */
  sheets: K13SheetMeta[]
  /** 导出空白模板 */
  exportTemplate: () => Promise<void>
  /** 导出当前数据 */
  exportData: () => Promise<void>
  /** 导入数据（multipart/form-data） */
  importData: (file: File) => Promise<K13ImportResult | null>
  /** API前缀 */
  apiPrefix: string
}

// ═══ Composable 主体 ═══

export function useK13ImportExport(params: UseK13ImportExportOptions): UseK13ImportExportReturn {
  const { wpId, sheetCode } = params
  const isExporting = ref(false)
  const isImporting = ref(false)
  const lastError = ref<string | null>(null)

  function apiBase(): string {
    return `/api/workpapers/${wpId.value}`
  }

  /**
   * 导出模板 — POST /api/workpapers/{wpId}/k13/export-template
   */
  async function exportTemplate(): Promise<void> {
    lastError.value = null
    isExporting.value = true
    try {
      const response = await http.post(
        `${apiBase()}/k13/export-template`,
        { sheet_code: sheetCode },
        { responseType: 'blob' },
      )
      const contentDisposition = response.headers?.['content-disposition']
      const filename = parseFilenameFromHeader(contentDisposition) || `${sheetCode}-模板.xlsx`
      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })
      downloadBlob(blob, filename)
      ElMessage.success(`${sheetCode} 模板已导出`)
    } catch (err: any) {
      const msg = err?.response?.data?.message || err?.response?.data?.detail || err.message || '导出模板失败'
      lastError.value = typeof msg === 'string' ? msg : JSON.stringify(msg)
      ElMessage.error(lastError.value!)
    } finally {
      isExporting.value = false
    }
  }

  /**
   * 导出数据 — POST /api/workpapers/{wpId}/k13/export-data
   */
  async function exportData(): Promise<void> {
    lastError.value = null
    isExporting.value = true
    try {
      const response = await http.post(
        `${apiBase()}/k13/export-data`,
        { sheet_code: sheetCode },
        { responseType: 'blob' },
      )
      const contentDisposition = response.headers?.['content-disposition']
      const filename = parseFilenameFromHeader(contentDisposition) || `${sheetCode}-数据.xlsx`
      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })
      downloadBlob(blob, filename)
      ElMessage.success(`${sheetCode} 数据已导出`)
    } catch (err: any) {
      const msg = err?.response?.data?.message || err?.response?.data?.detail || err.message || '导出数据失败'
      lastError.value = typeof msg === 'string' ? msg : JSON.stringify(msg)
      ElMessage.error(lastError.value!)
    } finally {
      isExporting.value = false
    }
  }

  /**
   * 导入数据 — POST /api/workpapers/{wpId}/k13/import-data
   * multipart/form-data 上传 xlsx 文件, body 含 sheet_code
   */
  async function importData(file: File): Promise<K13ImportResult | null> {
    lastError.value = null
    isImporting.value = true
    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('sheet_code', sheetCode)

      const response = await http.post(`${apiBase()}/k13/import-data`, formData, {
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

      const result: K13ImportResult = {
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
      isImporting.value = false
    }
  }

  return {
    isExporting,
    isImporting,
    lastError,
    sheets: K13_IMPORT_EXPORT_SHEETS,
    exportTemplate,
    exportData,
    importData,
    apiPrefix: K13_API_PREFIX,
  }
}

export default useK13ImportExport
