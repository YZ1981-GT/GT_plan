/**
 * createImportExport — 参数化工厂：底稿导入导出 composable
 *
 * Feature: platform-global-hardening
 * Requirements: 6.5, 6.6
 *
 * 用于收敛 useD2ImportExport / useF1ImportExport / useK1ImportExport 等同构实现。
 * 每个循环底稿的 ImportExport composable 结构相同：
 *   - POST /{prefix}/export-template?sheet=xxx → 下载模板 xlsx
 *   - POST /{prefix}/export-data?sheet=xxx → 下载数据 xlsx
 *   - POST /{prefix}/import-data?sheet=xxx → 上传 xlsx 导入
 *
 * 此工厂使用 fetch + Authorization header（复用既有 token），
 * 与 useWorkpaperImportExport 保持等价行为。
 */
import { ref, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ImportExportConfig {
  /** 底稿 wp_id */
  wpId: Ref<string>
  /** API 前缀（如 'd2' / 'f1' / 'k8'） */
  prefix: string
  /** 自定义端点路径覆盖（极少用） */
  endpoints?: {
    exportTemplate?: string
    exportData?: string
    importData?: string
  }
}

export interface ImportResult {
  rowCount: number
  fieldCount: number
  warning?: string
}

export interface ImportExportReturn {
  /** 是否正在导入 */
  loading: Ref<boolean>
  /** 最后一次错误信息 */
  error: Ref<string | null>
  /** 导出模板 */
  exportTemplate: (sheet: string) => Promise<void>
  /** 导出数据 */
  exportData: (sheet: string) => Promise<void>
  /** 导入数据 */
  importData: (sheet: string, file: File) => Promise<ImportResult | null>
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getAuthToken(): string | null {
  try {
    const raw = localStorage.getItem('token') || localStorage.getItem('auth_token')
    return raw || null
  } catch {
    return null
  }
}

function buildHeaders(): HeadersInit {
  const headers: Record<string, string> = {}
  const token = getAuthToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  return headers
}

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

// ─── Factory ─────────────────────────────────────────────────────────────────

export function createImportExport(config: ImportExportConfig): ImportExportReturn {
  const { wpId, prefix, endpoints } = config

  const loading = ref(false)
  const error = ref<string | null>(null)

  function apiBase(): string {
    return `/api/workpapers/${wpId.value}/${prefix}`
  }

  async function exportTemplate(sheet: string): Promise<void> {
    error.value = null
    const url = endpoints?.exportTemplate
      ? `${endpoints.exportTemplate}?sheet=${encodeURIComponent(sheet)}`
      : `${apiBase()}/export-template?sheet=${encodeURIComponent(sheet)}`

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: buildHeaders(),
        credentials: 'include',
      })
      if (!response.ok) {
        const text = await response.text().catch(() => '')
        throw new Error(text || `导出模板失败 (${response.status})`)
      }
      const blob = await response.blob()
      downloadBlob(blob, `${sheet}-模板.xlsx`)
    } catch (err: any) {
      error.value = err?.message || '导出模板失败'
    }
  }

  async function exportData(sheet: string): Promise<void> {
    error.value = null
    const url = endpoints?.exportData
      ? `${endpoints.exportData}?sheet=${encodeURIComponent(sheet)}`
      : `${apiBase()}/export-data?sheet=${encodeURIComponent(sheet)}`

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: buildHeaders(),
        credentials: 'include',
      })
      if (!response.ok) {
        const text = await response.text().catch(() => '')
        throw new Error(text || `导出数据失败 (${response.status})`)
      }
      const blob = await response.blob()
      downloadBlob(blob, `${sheet}-数据.xlsx`)
    } catch (err: any) {
      error.value = err?.message || '导出数据失败'
    }
  }

  async function importData(sheet: string, file: File): Promise<ImportResult | null> {
    error.value = null
    loading.value = true

    const url = endpoints?.importData
      ? `${endpoints.importData}?sheet=${encodeURIComponent(sheet)}`
      : `${apiBase()}/import-data?sheet=${encodeURIComponent(sheet)}`

    try {
      const formData = new FormData()
      formData.append('file', file)

      const headers = buildHeaders() as Record<string, string>
      // 不设 Content-Type，让浏览器自动设置 multipart boundary

      const response = await fetch(url, {
        method: 'POST',
        headers,
        credentials: 'include',
        body: formData,
      })

      if (!response.ok) {
        const text = await response.text().catch(() => '')
        throw new Error(text || `导入数据失败 (${response.status})`)
      }

      const json = await response.json()
      const data = json?.data ?? json

      if (data.ok === false) {
        const msg = (data.errors || []).join('；') || '导入失败'
        error.value = msg
        return null
      }

      return {
        rowCount: data.imported_count ?? data.rowCount ?? 0,
        fieldCount: data.fieldCount ?? 0,
        warning: data.warning,
      }
    } catch (err: any) {
      error.value = err?.message || '导入数据失败'
      return null
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    error,
    exportTemplate,
    exportData,
    importData,
  }
}
