/**
 * useE1ImportExport — 导入导出三级(复用D4模式) composable
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 16b.2
 *
 * 职责：
 * - 三操作：exportTemplate(导出模板), exportData(导出数据), importData(导入数据)
 * - 使用 @/utils/http (axios实例，NOT fetch) — 拦截器自动加 Bearer token
 * - Blob下载: http.post(url, null, {params, responseType:'blob'}) → new Blob → URL.createObjectURL → a.click()
 * - RFC5987 filename from Content-Disposition header
 * - 账户科目白名单验证 (1001/1002/1012)
 * - Endpoint pattern: POST /api/workpapers/{wpId}/e1/export-template?sheet=
 *                     POST /api/workpapers/{wpId}/e1/export-data?sheet=
 *                     POST /api/workpapers/{wpId}/e1/import-data?sheet=
 *
 * Requirements: 13.2, 13.3
 */
import { ref, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface UseE1ImportExportOptions {
  wpId: Ref<string>
  sheet: Ref<string>
}

export interface ImportResult {
  success: boolean
  message: string
  rowCount?: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 允许的科目编码白名单 */
const ACCOUNT_CODE_WHITELIST = ['1001', '1002', '1012']

/** 支持导入导出的sheet列表 */
const EXPORTABLE_SHEETS = [
  'E1-2', 'E1-3', 'E1-5', 'E1-6', 'E1-7', 'E1-8', 'E1-9',
  'E1-10', 'E1-20', 'E1-21', 'E1-22',
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 从 Content-Disposition header 解析文件名（RFC5987 编码）
 * 优先读 filename*=UTF-8''...，fallback到 filename="..."
 */
function parseFilenameFromHeader(header: string | null): string {
  if (!header) return 'export.xlsx'

  // RFC5987: filename*=UTF-8''encoded_name
  const utf8Match = header.match(/filename\*=UTF-8''(.+?)(?:;|$)/i)
  if (utf8Match) {
    try {
      return decodeURIComponent(utf8Match[1])
    } catch { /* fallthrough */ }
  }

  // Standard: filename="name"
  const stdMatch = header.match(/filename="?(.+?)"?(?:;|$)/)
  if (stdMatch) return stdMatch[1]

  return 'export.xlsx'
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

export function useE1ImportExport(options: UseE1ImportExportOptions) {
  const { wpId, sheet } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const isExporting = ref(false)
  const isImporting = ref(false)
  const lastError = ref<string | null>(null)

  // ─── Validation ────────────────────────────────────────────────────────

  /** 校验科目编码白名单 */
  function validateAccountCode(code: string): boolean {
    return ACCOUNT_CODE_WHITELIST.includes(code)
  }

  /** 当前sheet是否支持导入导出 */
  function isSheetExportable(): boolean {
    return EXPORTABLE_SHEETS.includes(sheet.value)
  }

  // ─── Export Template ───────────────────────────────────────────────────

  async function exportTemplate(): Promise<void> {
    if (!isSheetExportable()) {
      lastError.value = `Sheet ${sheet.value} 不支持导出`
      return
    }
    isExporting.value = true
    lastError.value = null
    try {
      const { default: http } = await import('@/utils/http')
      const response = await (http as any).post(
        `/api/workpapers/${wpId.value}/e1/export-template`,
        null,
        { params: { sheet: sheet.value }, responseType: 'blob' },
      )
      const blob = new Blob([response.data])
      const filename = parseFilenameFromHeader(
        response.headers?.['content-disposition'] || null,
      )
      downloadBlob(blob, filename)
    } catch (err: any) {
      lastError.value = err?.message || '导出模板失败'
    } finally {
      isExporting.value = false
    }
  }

  // ─── Export Data ───────────────────────────────────────────────────────

  async function exportData(): Promise<void> {
    if (!isSheetExportable()) {
      lastError.value = `Sheet ${sheet.value} 不支持导出`
      return
    }
    isExporting.value = true
    lastError.value = null
    try {
      const { default: http } = await import('@/utils/http')
      const response = await (http as any).post(
        `/api/workpapers/${wpId.value}/e1/export-data`,
        null,
        { params: { sheet: sheet.value }, responseType: 'blob' },
      )
      const blob = new Blob([response.data])
      const filename = parseFilenameFromHeader(
        response.headers?.['content-disposition'] || null,
      )
      downloadBlob(blob, filename)
    } catch (err: any) {
      lastError.value = err?.message || '导出数据失败'
    } finally {
      isExporting.value = false
    }
  }

  // ─── Import Data ───────────────────────────────────────────────────────

  async function importData(file: File): Promise<ImportResult> {
    if (!isSheetExportable()) {
      const msg = `Sheet ${sheet.value} 不支持导入`
      lastError.value = msg
      return { success: false, message: msg }
    }
    isImporting.value = true
    lastError.value = null
    try {
      const { default: http } = await import('@/utils/http')
      const formData = new FormData()
      formData.append('file', file)

      const response = await (http as any).post(
        `/api/workpapers/${wpId.value}/e1/import-data`,
        formData,
        {
          params: { sheet: sheet.value },
          headers: { 'Content-Type': 'multipart/form-data' },
        },
      )

      // ResponseWrapperMiddleware envelope
      const data = response.data?.data ?? response.data
      return {
        success: true,
        message: data?.message || '导入成功',
        rowCount: data?.row_count,
      }
    } catch (err: any) {
      const msg = err?.response?.data?.message || err?.message || '导入数据失败'
      lastError.value = msg
      return { success: false, message: msg }
    } finally {
      isImporting.value = false
    }
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    isExporting,
    isImporting,
    lastError,
    validateAccountCode,
    isSheetExportable,
    exportTemplate,
    exportData,
    importData,
  }
}
