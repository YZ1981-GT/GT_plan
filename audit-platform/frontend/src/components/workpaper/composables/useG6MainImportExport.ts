/**
 * useG6MainImportExport — G6 其他债权投资(main组) 导入导出 composable
 *
 * Spec: .kiro/specs/g6-other-bond-investment-main/ Task 1.12
 * Requirements: 5.3, 6.3, 7.1, 7.4
 *
 * 3张动态行表格 × 3端点 = 9端点调用：
 *   POST /api/workpapers/{wpId}/g6-main/export-template?sheet={code}
 *   POST /api/workpapers/{wpId}/g6-main/export-data?sheet={code}
 *   POST /api/workpapers/{wpId}/g6-main/import-data?sheet={code}  (multipart/form-data)
 *
 * sheet codes: G6-2 / G6-3 / G6-4
 * G6-2按3区段分sheet导出 (基础信息/期初+变动/期末+审定)
 * G6-3按2区段分sheet导出 (未审+调整/审定数)
 * G6-4单sheet导出
 *
 * UI 铁律：el-dropdown「导入导出 ▾」（导出模板/导出数据/导入数据）
 * 使用 axios (http from @/utils/http) 非原生 fetch — for Authorization header
 * 处理 StreamingResponse + 中文文件名 RFC5987 编码
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

// ═══ 类型定义 ═══

/** G6(main组) 支持导入导出的 sheet 编码（3张动态行表格） */
export type G6MainImportableSheet = 'G6-2' | 'G6-3' | 'G6-4'

/** 导入结果 */
export interface G6MainImportResult {
  rowCount: number
  fieldCount: number
  warning?: string
  errors?: string[]
}

/** 导入错误详情（后端返回） */
export interface G6MainImportError {
  row?: number
  field?: string
  reason: string
}

/** sheet 元数据（供下拉菜单展示） */
export interface G6MainSheetMeta {
  code: G6MainImportableSheet
  label: string
  /** 多区块分sheet导出标识 */
  multiSheet?: boolean
  /** 多区块描述 */
  multiSheetDesc?: string
}

/** el-dropdown 菜单项 */
export interface G6MainDropdownOption {
  command: string
  label: string
  icon?: string
  disabled?: boolean
}

// ═══ 常量 ═══

export const G6_MAIN_API_PREFIX = 'g6-main'

/** 3张可导入导出 sheet 的中文标签 */
export const G6_MAIN_IMPORT_EXPORT_SHEETS: G6MainSheetMeta[] = [
  { code: 'G6-2', label: 'G6-2 明细表（3区段）', multiSheet: true, multiSheetDesc: '基础信息/期初+变动/期末+审定' },
  { code: 'G6-3', label: 'G6-3 坏账准备（2区段）', multiSheet: true, multiSheetDesc: '未审+调整/审定数' },
  { code: 'G6-4', label: 'G6-4 调整分录' },
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
export function resolveG6MainImportableSheet(sheetName: string): G6MainImportableSheet | null {
  const m = (sheetName || '').match(/G6-(\d+)/)
  if (!m) return null
  const code = `G6-${m[1]}` as G6MainImportableSheet
  return G6_MAIN_IMPORT_EXPORT_SHEETS.some((s) => s.code === code) ? code : null
}

// ═══ Composable 接口 ═══

export interface UseG6MainImportExportOptions {
  wpId: Ref<string>
  /** 导入成功后回调（通知父组件刷新数据） */
  onImported?: () => void | Promise<void>
}

export interface UseG6MainImportExportReturn {
  /** 是否正在导出中 */
  isExporting: Ref<boolean>
  /** 是否正在导入中 */
  isImporting: Ref<boolean>
  /** 最近一次导入错误信息列表 */
  importErrors: Ref<G6MainImportError[]>
  /** 所有可导入导出的 sheet 元数据 */
  sheets: G6MainSheetMeta[]
  /** 导出空白模板 */
  exportTemplate: (sheet: G6MainImportableSheet) => Promise<void>
  /** 导出当前数据 */
  exportData: (sheet: G6MainImportableSheet) => Promise<void>
  /** 导入数据（multipart/form-data） */
  importData: (sheet: G6MainImportableSheet, file: File) => Promise<G6MainImportResult | null>
  /** 获取el-dropdown下拉菜单选项（针对指定sheet） */
  getDropdownOptions: (sheetCode: G6MainImportableSheet) => G6MainDropdownOption[]
  /** API前缀 */
  apiPrefix: string
}

// ═══ Composable 主体 ═══

export function useG6MainImportExport(options: UseG6MainImportExportOptions): UseG6MainImportExportReturn {
  const { wpId, onImported } = options
  const isExporting = ref(false)
  const isImporting = ref(false)
  const importErrors = ref<G6MainImportError[]>([])

  function apiBase(): string {
    return `/api/workpapers/${wpId.value}/${G6_MAIN_API_PREFIX}`
  }

  /**
   * 获取el-dropdown下拉菜单选项
   * 返回3项：导出模板 / 导出数据 / 导入数据
   */
  function getDropdownOptions(sheetCode: G6MainImportableSheet): G6MainDropdownOption[] {
    const meta = G6_MAIN_IMPORT_EXPORT_SHEETS.find((s) => s.code === sheetCode)
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
   * 导出模板 — POST /api/workpapers/{wp_id}/g6-main/export-template?sheet={code}
   * 多区块sheet按分sheet导出（后端返回multi-sheet xlsx）
   */
  async function exportTemplate(sheet: G6MainImportableSheet): Promise<void> {
    importErrors.value = []
    isExporting.value = true
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
      ElMessage.error(errorMsg)
    } finally {
      isExporting.value = false
    }
  }

  /**
   * 导出数据 — POST /api/workpapers/{wp_id}/g6-main/export-data?sheet={code}
   * G6-2(3区段分sheet) / G6-3(2区段分sheet) / G6-4(单sheet)
   */
  async function exportData(sheet: G6MainImportableSheet): Promise<void> {
    importErrors.value = []
    isExporting.value = true
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
      ElMessage.error(errorMsg)
    } finally {
      isExporting.value = false
    }
  }

  /**
   * 导入数据 — POST /api/workpapers/{wp_id}/g6-main/import-data?sheet={code}
   * multipart/form-data 上传 xlsx 文件
   * 返回导入结果；格式错误时后端返回详细错误列表（行号/字段/原因）
   */
  async function importData(sheet: G6MainImportableSheet, file: File): Promise<G6MainImportResult | null> {
    importErrors.value = []
    isImporting.value = true
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
        const errors: G6MainImportError[] = Array.isArray(data.errors)
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
        ElMessage.error(msg + (errors.length > 3 ? `…共${errors.length}项错误` : ''))
        return null
      }

      const result: G6MainImportResult = {
        rowCount: data.imported_count ?? data.rowCount ?? 0,
        fieldCount: data.fieldCount ?? 0,
        warning: data.warning,
        errors: data.errors,
      }

      let msg = `成功导入 ${result.rowCount} 行数据`
      if (result.warning) msg += `（${result.warning}）`
      ElMessage.success(msg)

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
      ElMessage.error(errorStr)
      return null
    } finally {
      isImporting.value = false
    }
  }

  return {
    isExporting,
    isImporting,
    importErrors,
    sheets: G6_MAIN_IMPORT_EXPORT_SHEETS,
    exportTemplate,
    exportData,
    importData,
    getDropdownOptions,
    apiPrefix: G6_MAIN_API_PREFIX,
  }
}

export default useG6MainImportExport
