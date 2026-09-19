/**
 * useD2ImportExport — D2 导入导出通用 composable
 *
 * Spec: .kiro/specs/d2-accounts-receivable-refactor/
 * Task: 37.1
 *
 * 职责：
 * - 导出空白模板（xlsx含表头+格式）
 * - 导出当前数据（xlsx含行数据）
 * - 导入xlsx数据（解析→回写checklist_responses）
 * - 状态管理（importing/lastError）
 * - 成功/失败消息提示
 *
 * Requirements: 19.1-19.7
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 支持导入导出的9个Sheet */
export type ImportableSheet =
  | 'D2-1'
  | 'D2-2'
  | 'D2-3'
  | 'D2-4'
  | 'D2-5'
  | 'D2-6'
  | 'D2-7'
  | 'D2-8'
  | 'D2-9'
  | 'D2-10'
  | 'D2-11'
  | 'D2-12'
  | 'D2-13'

export interface ImportResult {
  rowCount: number
  fieldCount: number
  warning?: string
}

export interface UseD2ImportExportOptions {
  wpId: Ref<string>
  projectId: Ref<string>
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

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

export function useD2ImportExport(options: UseD2ImportExportOptions) {
  const { wpId } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const importing = ref<boolean>(false)
  const lastError = ref<string | null>(null)

  // ─── Export Template ───────────────────────────────────────────────────

  /**
   * 导出空白xlsx模板（含表头+格式+公式）
   * POST /api/workpapers/{wp_id}/d2/export-template?sheet=xxx
   */
  async function exportTemplate(sheet: ImportableSheet): Promise<void> {
    lastError.value = null
    try {
      const response = await fetch(
        `/api/workpapers/${wpId.value}/d2/export-template?sheet=${encodeURIComponent(sheet)}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        }
      )
      if (!response.ok) {
        const errData = await response.json().catch(() => ({ message: '导出失败' }))
        throw new Error(errData.message || `导出模板失败(${response.status})`)
      }
      const blob = await response.blob()
      downloadBlob(blob, `${sheet}-模板.xlsx`)
      ElMessage.success(`${sheet} 模板已导出`)
    } catch (err: any) {
      lastError.value = err.message || '导出模板失败'
      ElMessage.error(lastError.value!)
    }
  }

  // ─── Export Data ───────────────────────────────────────────────────────

  /**
   * 导出当前数据为xlsx
   * POST /api/workpapers/{wp_id}/d2/export-data?sheet=xxx
   */
  async function exportData(sheet: ImportableSheet): Promise<void> {
    lastError.value = null
    try {
      const response = await fetch(
        `/api/workpapers/${wpId.value}/d2/export-data?sheet=${encodeURIComponent(sheet)}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        }
      )
      if (!response.ok) {
        const errData = await response.json().catch(() => ({ message: '导出失败' }))
        throw new Error(errData.message || `导出数据失败(${response.status})`)
      }
      const blob = await response.blob()
      downloadBlob(blob, `${sheet}-数据.xlsx`)
      ElMessage.success(`${sheet} 数据已导出`)
    } catch (err: any) {
      lastError.value = err.message || '导出数据失败'
      ElMessage.error(lastError.value!)
    }
  }

  // ─── Import Data ───────────────────────────────────────────────────────

  /**
   * 导入xlsx数据
   * POST /api/workpapers/{wp_id}/d2/import-data?sheet=xxx (multipart/form-data)
   *
   * @returns ImportResult 或 null（失败时）
   */
  async function importData(sheet: ImportableSheet, file: File): Promise<ImportResult | null> {
    lastError.value = null
    importing.value = true
    try {
      const formData = new FormData()
      formData.append('file', file)

      const response = await fetch(
        `/api/workpapers/${wpId.value}/d2/import-data?sheet=${encodeURIComponent(sheet)}`,
        {
          method: 'POST',
          body: formData,
        }
      )

      if (!response.ok) {
        const errData = await response.json().catch(() => ({ message: '导入失败' }))
        // 400 = 格式校验失败，返回错误列名列表
        if (response.status === 400 && errData.data?.invalid_columns) {
          const cols = (errData.data.invalid_columns as string[]).join(', ')
          throw new Error(`列名不匹配: ${cols}`)
        }
        throw new Error(errData.message || `导入数据失败(${response.status})`)
      }

      const result = await response.json()
      const data: ImportResult = result.data || result

      // 成功提示
      let msg = `成功导入${data.rowCount}行数据，${data.fieldCount}个字段已更新`
      if (data.warning) {
        msg += `（${data.warning}）`
        ElMessage.success({ message: msg, duration: 5000 })
      } else {
        ElMessage.success(msg)
      }

      return data
    } catch (err: any) {
      lastError.value = err.message || '导入数据失败'
      ElMessage.error(lastError.value!)
      return null
    } finally {
      importing.value = false
    }
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 状态
    importing,
    lastError,

    // 操作
    exportTemplate,
    exportData,
    importData,
  }
}

export default useD2ImportExport
