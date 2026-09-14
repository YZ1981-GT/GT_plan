/**
 * useM2ImportExport — M2 实收资本（股本）导入导出三级 composable
 *
 * Spec: .kiro/specs/m2-paid-in-capital/
 * Task: 3.3
 * Requirements: 7.7
 *
 * 职责：
 * - 导入导出三级：el-dropdown（导出模板 / 导出数据 / 导入数据）
 * - 后端三端点 per sheet（动态行表格才需要导入导出）：
 *   - GET /api/m2-paid-in-capital/export-template?sheet=xxx
 *   - GET /api/m2-paid-in-capital/export-data?sheet=xxx&wp_id=yyy
 *   - POST /api/m2-paid-in-capital/import-data (multipart with file)
 * - 使用 http (axios) NOT native fetch（需 Authorization header → 401 without it!）
 * - 动态行sheet：M2-2明细表(上市/非上市两版本) / M2-4外币投资
 * - StreamingResponse 中文文件名 RFC5987 编码
 * - Blob下载: responseType:'blob' → URL.createObjectURL → a.click()
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** M2 支持导入导出的 sheet（动态行表格） */
export type M2ImportableSheet =
  | 'M2-2-listed'     // 明细表（上市公司版）
  | 'M2-2-unlisted'   // 明细表（非上市公司版）
  | 'M2-4'            // 外币投资汇率测算表

/** 导入结果 */
export interface M2ImportResult {
  /** 导入行数 */
  rowCount: number
  /** 导入字段数 */
  fieldCount: number
  /** 警告信息 */
  warning?: string
}

export interface UseM2ImportExportOptions {
  wpId: Ref<string>
  projectId: Ref<string>
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** M2 动态行sheet列表（仅这些支持导入导出） */
export const M2_IMPORTABLE_SHEETS: { value: M2ImportableSheet; label: string }[] = [
  { value: 'M2-2-listed', label: '明细表(上市公司版)' },
  { value: 'M2-2-unlisted', label: '明细表(非上市公司版)' },
  { value: 'M2-4', label: '外币投资汇率' },
]

/** API base path */
const API_BASE = '/api/m2-paid-in-capital'

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
 * M2 导入导出三级
 *
 * @param options.wpId 底稿ID（reactive）
 * @param options.projectId 项目ID（reactive）
 */
export function useM2ImportExport(options: UseM2ImportExportOptions) {
  const { wpId, projectId } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const isExporting = ref(false)
  const isImporting = ref(false)
  const lastError = ref<string | null>(null)

  // ─── Export Template ───────────────────────────────────────────────────

  /**
   * 导出空白xlsx模板（含表头+格式+编制说明）
   * GET /api/m2-paid-in-capital/export-template?sheet=xxx
   */
  async function exportTemplate(sheet?: M2ImportableSheet): Promise<void> {
    if (!wpId.value) return
    isExporting.value = true
    lastError.value = null

    try {
      const params: Record<string, string> = { wp_id: wpId.value }
      if (sheet) params.sheet = sheet

      const response = await http.get(
        `${API_BASE}/export-template`,
        { params, responseType: 'blob' },
      )

      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })

      const contentDisposition = response.headers?.['content-disposition'] ?? null
      const filename = parseFilename(
        contentDisposition,
        sheet ? `M2-实收资本-${sheet}-模板.xlsx` : 'M2-实收资本-模板.xlsx',
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
   * 导出当前数据为xlsx（多sheet分别导出）
   * GET /api/m2-paid-in-capital/export-data?sheet=xxx&wp_id=yyy
   */
  async function exportData(sheet?: M2ImportableSheet): Promise<void> {
    if (!wpId.value) return
    isExporting.value = true
    lastError.value = null

    try {
      const params: Record<string, string> = { wp_id: wpId.value }
      if (sheet) params.sheet = sheet

      const response = await http.get(
        `${API_BASE}/export-data`,
        { params, responseType: 'blob' },
      )

      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })

      const contentDisposition = response.headers?.['content-disposition'] ?? null
      const filename = parseFilename(
        contentDisposition,
        sheet ? `M2-实收资本-${sheet}-数据.xlsx` : 'M2-实收资本-数据.xlsx',
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
   * 导入xlsx数据
   * POST /api/m2-paid-in-capital/import-data (multipart/form-data)
   */
  async function importData(file: File, sheet?: M2ImportableSheet): Promise<M2ImportResult | null> {
    if (!wpId.value) return null
    isImporting.value = true
    lastError.value = null

    try {
      const formData = new FormData()
      formData.append('file', file)
      if (sheet) formData.append('sheet', sheet)
      formData.append('wp_id', wpId.value)

      const response = await http.post(
        `${API_BASE}/import-data`,
        formData,
        {
          headers: { 'Content-Type': 'multipart/form-data' },
        },
      )

      // 兼容 ResponseWrapperMiddleware 信封
      const data: any = response.data?.data ?? response.data
      const result: M2ImportResult = {
        rowCount: data.imported_count ?? data.rowCount ?? 0,
        fieldCount: data.field_count ?? data.fieldCount ?? 0,
        warning: data.warning,
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
      return null
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

    // 操作
    exportTemplate,
    exportData,
    importData,
  }
}

export default useM2ImportExport
