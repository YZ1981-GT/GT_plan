/**
 * useL3ImportExport — L3 长期借款导入导出三级 composable
 *
 * Spec: .kiro/specs/l3-long-term-loans/
 * Task: 3.3
 * Requirements: 11.3
 *
 * 职责：
 * - 导入导出三级：el-dropdown（导出模板 / 导出数据 / 导入数据）
 * - 后端端点（Phase 5 创建，此处先定义接口）：
 *   - GET /api/workpapers/{wpId}/l3/export-template — 导出空模板
 *   - GET /api/workpapers/{wpId}/l3/export-data — 导出当前数据
 *   - POST /api/workpapers/{wpId}/l3/import-data — 导入数据
 * - 使用 http (axios) 确保 Authorization header 自动附带
 * - 导出文件下载：responseType: 'blob' + URL.createObjectURL
 * - StreamingResponse 中文文件名：RFC5987 编码（后端处理）
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** L3 支持导入导出的 sheet（动态行表格） */
export type L3ImportableSheet =
  | 'L3-2'   // 明细表（32列按借款列示）
  | 'L3-4'   // 征信核对
  | 'L3-5'   // 利息测算
  | 'L3-6'   // 合同检查
  | 'L3-7'   // 逾期检查
  | 'L3-8'   // 抵质押检查

/** 导入结果 */
export interface L3ImportResult {
  /** 导入行数 */
  rowCount: number
  /** 导入字段数 */
  fieldCount: number
  /** 警告信息 */
  warning?: string
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 从 Content-Disposition 解析文件名（支持 RFC5987 编码的中文名）
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
 * 下载 Blob 为文件
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

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L3 导入导出三级
 *
 * @param wpId 底稿ID（reactive）
 * @param projectId 项目ID（reactive）
 */
export function useL3ImportExport(wpId: Ref<string>, projectId: Ref<string>) {
  // ─── State ─────────────────────────────────────────────────────────────

  const isExporting = ref(false)
  const isImporting = ref(false)
  const lastError = ref<string | null>(null)

  // ─── Export Template ───────────────────────────────────────────────────

  /**
   * 导出空白xlsx模板（含表头+格式+编制说明）
   * GET /api/workpapers/{wpId}/l3/export-template?sheet=xxx
   */
  async function exportTemplate(sheet?: L3ImportableSheet): Promise<void> {
    if (!wpId.value) return
    isExporting.value = true
    lastError.value = null

    try {
      const params: Record<string, string> = {}
      if (sheet) params.sheet = sheet

      const response = await http.get(
        `/api/workpapers/${wpId.value}/l3/export-template`,
        { params, responseType: 'blob' },
      )

      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })

      const contentDisposition = response.headers?.['content-disposition'] ?? null
      const filename = parseFilename(
        contentDisposition,
        sheet ? `L3-${sheet}-模板.xlsx` : 'L3-长期借款-模板.xlsx',
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
   * GET /api/workpapers/{wpId}/l3/export-data?sheet=xxx
   */
  async function exportData(sheet?: L3ImportableSheet): Promise<void> {
    if (!wpId.value) return
    isExporting.value = true
    lastError.value = null

    try {
      const params: Record<string, string> = {}
      if (sheet) params.sheet = sheet

      const response = await http.get(
        `/api/workpapers/${wpId.value}/l3/export-data`,
        { params, responseType: 'blob' },
      )

      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })

      const contentDisposition = response.headers?.['content-disposition'] ?? null
      const filename = parseFilename(
        contentDisposition,
        sheet ? `L3-${sheet}-数据.xlsx` : 'L3-长期借款-数据.xlsx',
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
   * POST /api/workpapers/{wpId}/l3/import-data?sheet=xxx (multipart/form-data)
   */
  async function importData(file: File, sheet?: L3ImportableSheet): Promise<L3ImportResult | null> {
    if (!wpId.value) return null
    isImporting.value = true
    lastError.value = null

    try {
      const formData = new FormData()
      formData.append('file', file)

      const params: Record<string, string> = {}
      if (sheet) params.sheet = sheet

      const response = await http.post(
        `/api/workpapers/${wpId.value}/l3/import-data`,
        formData,
        {
          params,
          headers: { 'Content-Type': 'multipart/form-data' },
        },
      )

      // 兼容 ResponseWrapperMiddleware 信封
      const data: any = response.data?.data ?? response.data
      const result: L3ImportResult = {
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

export default useL3ImportExport
