/**
 * useG6SppiImportExport — G6 其他债权投资(SPPI组) 导入导出 composable
 *
 * Spec: .kiro/specs/g6-other-bond-investment-sppi/ Task 11.1
 * Requirements: 7.3
 *
 * 4张动态行表格 × 3端点 = 12端点调用：
 *   POST /api/workpapers/{wpId}/g6-sppi/export-template?sheet={code}
 *   POST /api/workpapers/{wpId}/g6-sppi/export-data?sheet={code}
 *   POST /api/workpapers/{wpId}/g6-sppi/import-data?sheet={code}  (multipart/form-data)
 *
 * sheet codes: G6-5 / G6-6 / G6-9 / G6-10
 * G6-5按2区段分sheet导出 (基础+审定 / 估值详情)
 * G6-10按2区段分sheet导出 (倒轧计算 / 增减明细)
 * G6-6单sheet导出
 * G6-9单sheet导出
 *
 * UI 铁律：el-dropdown「导入导出 ▾」（导出模板/导出数据/导入数据）
 * 使用 axios (http from @/utils/http) 非原生 fetch — for Authorization header
 * 处理 StreamingResponse + 中文文件名 RFC5987 编码
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

// ═══ 类型定义 ═══

/** G6(SPPI组) 支持导入导出的 sheet 编码（4张动态行表格） */
export type G6SppiImportableSheet = 'G6-5' | 'G6-6' | 'G6-9' | 'G6-10'

/** 导入结果 */
export interface G6SppiImportResult {
  rowCount: number
  fieldCount: number
  warning?: string
  errors?: string[]
}

/** 导入错误详情（后端返回） */
export interface G6SppiImportError {
  row?: number
  field?: string
  reason: string
}

/** sheet 元数据（供下拉菜单展示） */
export interface G6SppiSheetMeta {
  code: G6SppiImportableSheet
  label: string
  /** 多区块分sheet导出标识 */
  multiSheet?: boolean
  /** 多区块描述 */
  multiSheetDesc?: string
}

/** el-dropdown 菜单项 */
export interface G6SppiDropdownOption {
  command: string
  label: string
  icon?: string
  disabled?: boolean
}

// ═══ 常量 ═══

export const G6_SPPI_API_PREFIX = 'g6-sppi'

/** 4张可导入导出 sheet 的中文标签 */
export const G6_SPPI_IMPORT_EXPORT_SHEETS: G6SppiSheetMeta[] = [
  { code: 'G6-5', label: 'G6-5 公允价值测试表（2区段）', multiSheet: true, multiSheetDesc: '基础+审定/估值详情' },
  { code: 'G6-6', label: 'G6-6 利息测算表' },
  { code: 'G6-9', label: 'G6-9 有价证券盘点表' },
  { code: 'G6-10', label: 'G6-10 盘点倒轧表（2区段）', multiSheet: true, multiSheetDesc: '倒轧计算/增减明细' },
]

/** 可导入sheet codes列表 */
export const G6_SPPI_IMPORTABLE_SHEETS: G6SppiImportableSheet[] = ['G6-5', 'G6-6', 'G6-9', 'G6-10']

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
export function resolveG6SppiImportableSheet(sheetName: string): G6SppiImportableSheet | null {
  const m = (sheetName || '').match(/G6-(5|6|9|10)/)
  if (!m) return null
  const code = `G6-${m[1]}` as G6SppiImportableSheet
  return G6_SPPI_IMPORT_EXPORT_SHEETS.some((s) => s.code === code) ? code : null
}

// ═══ Composable 接口 ═══

export interface UseG6SppiImportExportOptions {
  wpId: Ref<string>
  /** 导入成功后回调（通知父组件刷新数据） */
  onImported?: () => void | Promise<void>
}

export interface UseG6SppiImportExportReturn {
  /** 是否正在导出中 */
  isExporting: Ref<boolean>
  /** 是否正在导入中 */
  isImporting: Ref<boolean>
  /** 最近一次导入错误信息列表 */
  importErrors: Ref<G6SppiImportError[]>
  /** 所有可导入导出的 sheet 元数据 */
  sheets: G6SppiSheetMeta[]
  /** 可导入sheet codes */
  importableSheets: G6SppiImportableSheet[]
  /** 导出空白模板 */
  exportTemplate: (sheet: G6SppiImportableSheet) => Promise<void>
  /** 导出当前数据 */
  exportData: (sheet: G6SppiImportableSheet) => Promise<void>
  /** 导入数据（multipart/form-data） */
  importData: (sheet: G6SppiImportableSheet, file: File) => Promise<G6SppiImportResult | null>
  /** 获取el-dropdown下拉菜单选项（针对指定sheet） */
  getDropdownOptions: (sheetCode: G6SppiImportableSheet) => G6SppiDropdownOption[]
  /** loading 状态（导出或导入中） */
  loading: Ref<boolean>
  /** 最近一次错误信息 */
  error: Ref<string | null>
  /** API前缀 */
  apiPrefix: string
}

// ═══ Composable 主体 ═══

export function useG6SppiImportExport(options: UseG6SppiImportExportOptions): UseG6SppiImportExportReturn {
  const { wpId, onImported } = options
  const isExporting = ref(false)
  const isImporting = ref(false)
  const importErrors = ref<G6SppiImportError[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  function apiBase(): string {
    return `/api/workpapers/${wpId.value}/${G6_SPPI_API_PREFIX}`
  }

  /**
   * 获取el-dropdown下拉菜单选项
   * 返回3项：导出模板 / 导出数据 / 导入数据
   */
  function getDropdownOptions(sheetCode: G6SppiImportableSheet): G6SppiDropdownOption[] {
    const meta = G6_SPPI_IMPORT_EXPORT_SHEETS.find((s) => s.code === sheetCode)
    const suffix = meta?.multiSheet ? `（${meta.multiSheetDesc}）` : ''
    return [
      {
        command: `export-template:${sheetCode}`,
        label: `导出模板${suffix}`,
        icon: 'Download',
      },
      {
        command: `export-data:${sheetCode}`,
        label: `导出数据${suffix}`,
        icon: 'Download',
      },
      {
        command: `import-data:${sheetCode}`,
        label: '导入数据',
        icon: 'Upload',
      },
    ]
  }

  /**
   * 导出模板 — POST /api/workpapers/{wp_id}/g6-sppi/export-template?sheet={code}
   * G6-5(2区段分sheet) / G6-10(2区段分sheet) / G6-6,G6-9(单sheet)
   */
  async function exportTemplate(sheet: G6SppiImportableSheet): Promise<void> {
    importErrors.value = []
    error.value = null
    isExporting.value = true
    loading.value = true
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
      const errorMsg = typeof msg === 'string' ? msg : JSON.stringify(msg)
      error.value = errorMsg
      ElMessage.error(errorMsg)
    } finally {
      isExporting.value = false
      loading.value = false
    }
  }

  /**
   * 导出数据 — POST /api/workpapers/{wp_id}/g6-sppi/export-data?sheet={code}
   * G6-5(2区段分sheet) / G6-10(2区段分sheet) / G6-6,G6-9(单sheet)
   */
  async function exportData(sheet: G6SppiImportableSheet): Promise<void> {
    importErrors.value = []
    error.value = null
    isExporting.value = true
    loading.value = true
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
      const errorMsg = typeof msg === 'string' ? msg : JSON.stringify(msg)
      error.value = errorMsg
      ElMessage.error(errorMsg)
    } finally {
      isExporting.value = false
      loading.value = false
    }
  }

  /**
   * 导入数据 — POST /api/workpapers/{wp_id}/g6-sppi/import-data?sheet={code}
   * multipart/form-data 上传 xlsx 文件
   * 返回导入结果；格式错误时后端返回详细错误列表（行号/字段/原因）
   */
  async function importData(sheet: G6SppiImportableSheet, file: File): Promise<G6SppiImportResult | null> {
    importErrors.value = []
    error.value = null
    isImporting.value = true
    loading.value = true
    try {
      const formData = new FormData()
      formData.append('file', file)

      const response = await http.post(`${apiBase()}/import-data`, formData, {
        params: { sheet },
        headers: { 'Content-Type': 'multipart/form-data' },
      })

      const data: any = response.data?.data ?? response.data

      // 后端返回 ok=false 表示有业务错误（格式错误等）
      if (data.ok === false) {
        const errors: G6SppiImportError[] = Array.isArray(data.errors)
          ? data.errors.map((e: any) =>
              typeof e === 'string'
                ? { reason: e }
                : { row: e.row, field: e.field, reason: e.reason || e.message || String(e) },
            )
          : [{ reason: '导入失败' }]
        importErrors.value = errors
        const msg = errors.slice(0, 3).map((e) => {
          const loc = e.row ? `第${e.row}行` : ''
          const fld = e.field ? `[${e.field}]` : ''
          return `${loc}${fld}${e.reason}`
        }).join('；')
        const errorMsg = msg + (errors.length > 3 ? `…共${errors.length}项错误` : '')
        error.value = errorMsg
        ElMessage.error(errorMsg)
        return null
      }

      const result: G6SppiImportResult = {
        rowCount: data.imported_count ?? data.rowCount ?? 0,
        fieldCount: data.fieldCount ?? 0,
        warning: data.warning,
        errors: data.errors,
      }

      let successMsg = `成功导入 ${result.rowCount} 行数据`
      if (result.warning) successMsg += `（${result.warning}）`
      ElMessage.success(successMsg)

      // 通知父组件刷新数据
      await onImported?.()
      return result
    } catch (err: any) {
      const errMsg = err?.response?.data?.detail
        || err?.response?.data?.message
        || err.message
        || '导入数据失败'
      const errorStr = Array.isArray(errMsg) ? errMsg.join(', ') : String(errMsg)
      importErrors.value = [{ reason: errorStr }]
      error.value = errorStr
      ElMessage.error(errorStr)
      return null
    } finally {
      isImporting.value = false
      loading.value = false
    }
  }

  return {
    isExporting,
    isImporting,
    importErrors,
    sheets: G6_SPPI_IMPORT_EXPORT_SHEETS,
    importableSheets: G6_SPPI_IMPORTABLE_SHEETS,
    exportTemplate,
    exportData,
    importData,
    getDropdownOptions,
    loading,
    error,
    apiPrefix: G6_SPPI_API_PREFIX,
  }
}

export default useG6SppiImportExport
