/**
 * useD1ImportExport — D1 监盘核查组通用导入导出 composable
 *
 * Spec: .kiro/specs/d1-inspection-check/
 * Task: 19.2
 *
 * 职责：
 * - 将 4 个 D1 composable（useD1InventoryCount/useD1RelatedPartyCheck/useD1PledgeCheck/useD1SamplingVouching）
 *   中重复的 exportTemplate/exportData/importData 逻辑抽取为可复用模块
 * - 接收 sheetCode/sheetLabel/wpId 参数，提供统一的三个方法
 * - 使用 http（axios instance）发请求，自动附加 auth token
 * - blob 下载使用 createElement('a') + URL.createObjectURL
 * - 错误处理：catch → 返回 ImportResult with errors array
 *
 * Requirements: 20.2
 */
import { type Ref } from 'vue'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 列定义（预留用于未来前端 xlsx 生成/校验） */
export interface ColumnDef {
  field: string
  label: string
  type: 'string' | 'number' | 'date'
}

/** 导入导出 composable 配置 */
export interface UseD1ImportExportOptions {
  /** 底稿 ID（reactive） */
  wpId: Ref<string>
  /** sheet 编码，用于 API 参数：'D1-10' | 'D1-11' | 'D1-12' | 'D1-13' */
  sheetCode: string
  /** sheet 中文标签，用于文件名：'监盘表' | '关联方检查' | '质押检查' | '凭证核对' */
  sheetLabel: string
}

/** 导入结果 */
export interface ImportResult {
  success: boolean
  rowCount: number
  fieldCount: number
  errors?: string[]
}

// ─── Constants ───────────────────────────────────────────────────────────────

const XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 触发浏览器下载 blob 文件
 * @param blob - 文件 Blob
 * @param filename - 下载文件名
 */
function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * 通用导入导出 composable
 *
 * @example
 * ```ts
 * const { exportTemplate, exportData, importData } = useD1ImportExport({
 *   wpId,
 *   sheetCode: 'D1-10',
 *   sheetLabel: '监盘表',
 * })
 * ```
 */
export function useD1ImportExport(options: UseD1ImportExportOptions) {
  const { wpId, sheetCode, sheetLabel } = options

  /**
   * 导出空白模板 xlsx
   * POST /api/workpapers/{wpId}/d1-import-export/export-template?sheet={sheetCode}
   * 触发下载：{sheetCode}_{sheetLabel}模板.xlsx
   */
  async function exportTemplate(): Promise<void> {
    const res = await http.post(
      `/api/workpapers/${wpId.value}/d1-import-export/export-template`,
      null,
      { params: { sheet: sheetCode }, responseType: 'blob' },
    )
    const blob = new Blob([res.data], { type: XLSX_MIME })
    triggerBlobDownload(blob, `${sheetCode}_${sheetLabel}模板.xlsx`)
  }

  /**
   * 导出当前数据 xlsx
   * POST /api/workpapers/{wpId}/d1-import-export/export-data?sheet={sheetCode}
   * 触发下载：{sheetCode}_{sheetLabel}数据.xlsx
   */
  async function exportData(): Promise<void> {
    const res = await http.post(
      `/api/workpapers/${wpId.value}/d1-import-export/export-data`,
      null,
      { params: { sheet: sheetCode }, responseType: 'blob' },
    )
    const blob = new Blob([res.data], { type: XLSX_MIME })
    triggerBlobDownload(blob, `${sheetCode}_${sheetLabel}数据.xlsx`)
  }

  /**
   * 导入 xlsx 数据
   * POST /api/workpapers/{wpId}/d1-import-export/import-data?sheet={sheetCode}
   * Content-Type: multipart/form-data
   *
   * @param file - 用户选择的 xlsx 文件
   * @returns ImportResult — success/rowCount/fieldCount/errors
   */
  async function importData(file: File): Promise<ImportResult> {
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await http.post(
        `/api/workpapers/${wpId.value}/d1-import-export/import-data`,
        formData,
        {
          params: { sheet: sheetCode },
          headers: { 'Content-Type': 'multipart/form-data' },
        },
      )
      // 后端可能返回 {data: {rows, row_count, field_count}} 或直接 {rows, row_count, field_count}
      const data = res.data?.data ?? res.data
      return {
        success: true,
        rowCount: data?.row_count ?? 0,
        fieldCount: data?.field_count ?? 0,
      }
    } catch (err: any) {
      const msg = err?.response?.data?.message || err?.message || '导入失败'
      return {
        success: false,
        rowCount: 0,
        fieldCount: 0,
        errors: [msg],
      }
    }
  }

  return {
    exportTemplate,
    exportData,
    importData,
  }
}

export default useD1ImportExport
