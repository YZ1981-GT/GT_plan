/**
 * useG4MainImportExport — G4 债权投资(main组) 导入导出 composable
 *
 * Spec: .kiro/specs/g4-bond-investment-main/ Task 10.1
 * Requirements: 10.1~10.3
 *
 * 3张动态行表格 × 3端点 = 9端点调用：
 *   POST /api/workpapers/{wpId}/g4-main/export-template?sheet={code}
 *   POST /api/workpapers/{wpId}/g4-main/export-data?sheet={code}
 *   POST /api/workpapers/{wpId}/g4-main/import-data?sheet={code}  (multipart/form-data)
 *
 * sheet codes: G4-2 / G4-3 / G4-4
 * G4-2 按5区段分sheet导出（多区块multi-sheet）
 *
 * UI 铁律：el-dropdown「导入导出 ▾」（导出模板/导出数据/导入数据）
 * 使用 axios (http from @/utils/http) 非原生 fetch — for Authorization header
 * 处理 StreamingResponse + 中文文件名 RFC5987 编码
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

// ═══ 类型定义 ═══

/** G4(main) 支持导入导出的 sheet 编码（3张动态行表格） */
export type G4MainImportableSheet = 'G4-2' | 'G4-3' | 'G4-4'

/** 导入结果 */
export interface G4MainImportResult {
  rowCount: number
  fieldCount: number
  warning?: string
  errors?: string[]
}

/** sheet 元数据（供下拉菜单展示） */
export interface G4MainSheetMeta {
  code: G4MainImportableSheet
  label: string
  /** G4-2按5区段分sheet导出 */
  multiSheet?: boolean
}

// ═══ 常量 ═══

export const G4_MAIN_API_PREFIX = 'g4-main'

/** 3张可导入导出 sheet 的中文标签 */
export const G4_MAIN_IMPORT_EXPORT_SHEETS: G4MainSheetMeta[] = [
  { code: 'G4-2', label: 'G4-2 明细表（5区段）', multiSheet: true },
  { code: 'G4-3', label: 'G4-3 调整分录汇总' },
  { code: 'G4-4', label: 'G4-4 利息测算表' },
]

/** G4-2 的5区段子sheet（multi-sheet导出） */
export const G4_2_SEGMENTS = [
  { key: 'basic', label: '基础信息' },
  { key: 'opening', label: '期初余额' },
  { key: 'period', label: '本期变动' },
  { key: 'closing', label: '期末余额+减值' },
  { key: 'amortized', label: '摊余成本+审定' },
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
export function resolveG4MainImportableSheet(sheetName: string): G4MainImportableSheet | null {
  const m = (sheetName || '').match(/G4-(\d+)/)
  if (!m) return null
  const code = `G4-${m[1]}` as G4MainImportableSheet
  return G4_MAIN_IMPORT_EXPORT_SHEETS.some((s) => s.code === code) ? code : null
}

// ═══ Composable 接口 ═══

export interface UseG4MainImportExportOptions {
  wpId: Ref<string>
}

export interface UseG4MainImportExportReturn {
  /** 是否正在导入中 */
  importing: Ref<boolean>
  /** 最近一次错误信息 */
  lastError: Ref<string | null>
  /** 所有可导入导出的 sheet 元数据 */
  sheets: G4MainSheetMeta[]
  /** 导出空白模板 */
  exportTemplate: (sheet: G4MainImportableSheet) => Promise<void>
  /** 导出当前数据 */
  exportData: (sheet: G4MainImportableSheet) => Promise<void>
  /** 导入数据（multipart/form-data） */
  importData: (sheet: G4MainImportableSheet, file: File) => Promise<G4MainImportResult | null>
  /** API前缀 */
  apiPrefix: string
}

// ═══ Composable 主体 ═══

export function useG4MainImportExport(options: UseG4MainImportExportOptions): UseG4MainImportExportReturn {
  const { wpId } = options
  const importing = ref(false)
  const lastError = ref<string | null>(null)

  function apiBase(): string {
    return `/api/workpapers/${wpId.value}/${G4_MAIN_API_PREFIX}`
  }

  /**
   * 导出模板 — POST /api/workpapers/{wp_id}/g4-main/export-template?sheet={code}
   * G4-2 按5区段分sheet导出（后端返回multi-sheet xlsx）
   */
  async function exportTemplate(sheet: G4MainImportableSheet): Promise<void> {
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
   * 导出数据 — POST /api/workpapers/{wp_id}/g4-main/export-data?sheet={code}
   * G4-2 按5区段分sheet导出（后端返回multi-sheet xlsx with data）
   */
  async function exportData(sheet: G4MainImportableSheet): Promise<void> {
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
   * 导入数据 — POST /api/workpapers/{wp_id}/g4-main/import-data?sheet={code}
   * multipart/form-data 上传 xlsx 文件
   */
  async function importData(sheet: G4MainImportableSheet, file: File): Promise<G4MainImportResult | null> {
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

      const result: G4MainImportResult = {
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
    sheets: G4_MAIN_IMPORT_EXPORT_SHEETS,
    exportTemplate,
    exportData,
    importData,
    apiPrefix: G4_MAIN_API_PREFIX,
  }
}

export default useG4MainImportExport
