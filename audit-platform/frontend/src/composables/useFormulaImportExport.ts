/**
 * useFormulaImportExport — 公式模块导入导出 composable（Req 23）
 *
 * 对接后端三端点（遵循平台统一「导入导出▾」规范）：
 * - POST /api/formula-management/import-export/export-template — 导出模板（首区块=编报说明）
 * - POST /api/formula-management/import-export/export-data      — 导出当前页面/模块已有公式
 * - POST /api/formula-management/import-export/import-data       — 上传 xlsx，逐条 full_resolve 校验
 *
 * 另提供说明文档单一源拉取（与导出模板编报说明同源，Req 23.6 / 25.3）：
 * - GET  /api/formula-management/reporting-instructions
 *
 * 全部使用 http (axios)，自动携带 Authorization header（不用原生 fetch，避免 401）。
 * 中文文件名由后端按 RFC 5987 编码，前端下载沿用后端建议名或本地回退名。
 *
 * Spec: .kiro/specs/formula-management-library/
 * Task: 14.4
 * Requirements: 23.1, 23.2, 23.3, 23.4, 23.5, 23.6
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
// spec: formula-management-runtime-closure Task 14 — 端点收敛进 apiPaths（纯搬迁）
import { formulaPresets } from '@/services/apiPaths/formula'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 导入被跳过的一条公式（悬空引用 / 无效）。 */
export interface FormulaImportSkip {
  row_number: number
  page_key: string
  target_cell: string
  reason: string
  dangling_refs: string[]
}

/** 导入结果汇总。 */
export interface FormulaImportResult {
  ok: boolean
  imported_count: number
  skipped_count: number
  imported: Array<Record<string, unknown>>
  skipped: FormulaImportSkip[]
  persisted?: { inserted: number; updated: number; total: number }
}

/** 说明文档区块。 */
export interface FormulaDocSection {
  key: string
  title: string
  lines: string[]
}

/** 说明文档（单一源）。 */
export interface FormulaReportingDoc {
  title: string
  version: string
  sections: FormulaDocSection[]
  markdown?: string
}

/** Preset Inventory 中的一页登记项。 */
export interface FormulaPresetPage {
  page_key: string
  scope: string
  preset_status: string
  formula_count: number
  cycle?: string
  wp_code?: string
  sources?: string[]
}

/** 预设覆盖度按作用域分布。 */
export interface FormulaPresetCoverageScope {
  scope: string
  presetted_pages: number
  pending_pages: number
  total_pages: number
  coverage_percent: number
  formula_count: number
}

/** 预设覆盖度摘要。 */
export interface FormulaPresetCoverage {
  total_preset_pages: number
  total_preset_formulas: number
  by_status: { presetted: number; pending: number }
  by_scope: FormulaPresetCoverageScope[]
}

/** Preset Inventory 拉取结果。 */
export interface FormulaPresetInventory {
  pages: FormulaPresetPage[]
  coverage: FormulaPresetCoverage
}

/** 一条预设公式条目。 */
export interface FormulaPresetEntry {
  page_key: string
  target_cell: string
  expression: string
  formula_type: 'auto_calc' | 'logic_check' | 'reasonability'
  refs: unknown[]
  source: string
  description: string
  variant?: string
}

/** 某页面的预设条目集合。 */
export interface FormulaPresetPageDetail {
  page_key: string
  presetted: boolean
  presets: Array<FormulaPresetEntry & { is_custom?: boolean }>
}

/** 新增自定义预设的载荷。 */
export interface CustomPresetPayload {
  page_key: string
  target_cell: string
  expression: string
  formula_type: 'auto_calc' | 'logic_check' | 'reasonability'
  refs?: unknown[]
  description?: string
  variant?: string
}

/** 自定义预设写入结果。 */
export interface CustomPresetSaveResult {
  ok: boolean
  inserted: number
  updated: number
  total: number
}

const XLSX_MIME =
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 下载 Blob 为文件。 */
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

export function useFormulaImportExport() {
  const loading = ref(false)
  const importing = ref(false)

  /**
   * 导出模板（首区块=编报说明 + 示例公式行）
   * POST /import-export/export-template
   */
  async function exportTemplate(): Promise<void> {
    loading.value = true
    try {
      const response = await http.post(
        formulaPresets.exportTemplate,
        {},
        { responseType: 'blob' },
      )
      downloadBlob(new Blob([response.data], { type: XLSX_MIME }), '公式管理_导入模板.xlsx')
      ElMessage.success('模板已导出')
    } catch (err: unknown) {
      ElMessage.error(extractError(err, '导出模板失败'))
    } finally {
      loading.value = false
    }
  }

  /**
   * 导出当前页面/模块已有公式
   * POST /import-export/export-data?page_key=...
   * @param pageKey 可选页面键（scope:key），缺省导出全部
   */
  async function exportData(pageKey?: string): Promise<void> {
    loading.value = true
    try {
      const response = await http.post(
        formulaPresets.exportData,
        {},
        {
          params: pageKey ? { page_key: pageKey } : {},
          responseType: 'blob',
        },
      )
      const suffix = pageKey ? `_${pageKey.replace(/:/g, '_')}` : ''
      downloadBlob(new Blob([response.data], { type: XLSX_MIME }), `公式管理_数据${suffix}.xlsx`)
      ElMessage.success('数据已导出')
    } catch (err: unknown) {
      ElMessage.error(extractError(err, '导出数据失败'))
    } finally {
      loading.value = false
    }
  }

  /**
   * 导入公式数据（逐条 full_resolve 校验，悬空报告并跳过）
   * POST /import-export/import-data (multipart/form-data)
   * @param file 上传的 .xlsx 文件
   * @param opts 可选：page_key 限定 / project_id 上下文 / persist 是否入库
   */
  async function importData(
    file: File,
    opts: { pageKey?: string; projectId?: string; persist?: boolean } = {},
  ): Promise<FormulaImportResult | null> {
    importing.value = true
    try {
      const formData = new FormData()
      formData.append('file', file)
      const params: Record<string, unknown> = {}
      if (opts.pageKey) params.page_key = opts.pageKey
      if (opts.projectId) params.project_id = opts.projectId
      if (opts.persist !== undefined) params.persist = opts.persist

      const response = await http.post(formulaPresets.importData, formData, {
        params,
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      const data = (response.data?.data ?? response.data) as FormulaImportResult

      let msg = `成功导入 ${data.imported_count} 条公式`
      if (data.skipped_count > 0) {
        msg += `，跳过 ${data.skipped_count} 条（引用悬空/无效）`
      }
      ElMessage.success(msg)
      return data
    } catch (err: unknown) {
      ElMessage.error(extractError(err, '导入数据失败'))
      return null
    } finally {
      importing.value = false
    }
  }

  /**
   * 拉取公式管理说明文档（单一源，与导出模板编报说明同源）
   * GET /reporting-instructions?fmt=json|markdown
   */
  async function getReportingInstructions(
    fmt: 'json' | 'markdown' = 'json',
  ): Promise<FormulaReportingDoc | null> {
    try {
      const response = await http.get(formulaPresets.reportingInstructions, {
        params: { fmt },
      })
      return (response.data?.data ?? response.data) as FormulaReportingDoc
    } catch (err: unknown) {
      ElMessage.error(extractError(err, '获取说明文档失败'))
      return null
    }
  }

  /**
   * 拉取 Preset Inventory 逐页登记 + 覆盖度（供预设浏览，Req 25.4）
   * GET /presets/inventory?scope=workpaper|report|note
   */
  async function getPresetInventory(
    scope?: string,
  ): Promise<FormulaPresetInventory | null> {
    try {
      const response = await http.get(formulaPresets.inventory, {
        params: scope ? { scope } : {},
      })
      return (response.data?.data ?? response.data) as FormulaPresetInventory
    } catch (err: unknown) {
      ElMessage.error(extractError(err, '获取预设清单失败'))
      return null
    }
  }

  /**
   * 拉取某页面的预设公式条目（供浏览/编辑，Req 25.4）
   * GET /presets/page?page_key=scope:key
   */
  async function getPresetPage(
    pageKey: string,
  ): Promise<FormulaPresetPageDetail | null> {
    try {
      const response = await http.get(formulaPresets.page, {
        params: { page_key: pageKey },
      })
      return (response.data?.data ?? response.data) as FormulaPresetPageDetail
    } catch (err: unknown) {
      ElMessage.error(extractError(err, '获取页面预设失败'))
      return null
    }
  }

  /**
   * 新增/更新一条平台级自定义预设（写 formula_custom_presets.json，隔离于 seed）
   * POST /presets/custom（require edit role；悬空引用 → 422 携清单不落库）
   * @param payload 自定义预设条目
   * @param projectId 可选：项目上下文，供引用解析
   */
  async function saveCustomPreset(
    payload: CustomPresetPayload,
    projectId?: string,
  ): Promise<CustomPresetSaveResult | null> {
    loading.value = true
    try {
      const response = await http.post(
        formulaPresets.custom,
        payload,
        { params: projectId ? { project_id: projectId } : {} },
      )
      const data = (response.data?.data ?? response.data) as CustomPresetSaveResult
      ElMessage.success(
        data.inserted > 0 ? '自定义预设已新增' : '自定义预设已更新',
      )
      return data
    } catch (err: unknown) {
      // 悬空引用 422 携 dangling_refs 清单，友好展示
      const e = err as {
        response?: { status?: number; data?: { detail?: unknown; message?: unknown } }
      }
      const detail = e?.response?.data?.detail
      if (e?.response?.status === 422 && detail && typeof detail === 'object') {
        const d = detail as { message?: string; dangling_refs?: string[] }
        const refs = (d.dangling_refs || []).join('、')
        ElMessage.error(`${d.message || '公式引用悬空'}${refs ? '：' + refs : ''}`)
      } else {
        ElMessage.error(extractError(err, '保存自定义预设失败'))
      }
      return null
    } finally {
      loading.value = false
    }
  }

  return {
    exportTemplate,
    exportData,
    importData,
    getReportingInstructions,
    getPresetInventory,
    getPresetPage,
    saveCustomPreset,
    loading,
    importing,
  }
}

// ─── Error extraction ──────────────────────────────────────────────────────────

function extractError(err: unknown, fallback: string): string {
  const e = err as {
    response?: { data?: { detail?: unknown; message?: unknown } }
    message?: string
  }
  const detail = e?.response?.data?.detail ?? e?.response?.data?.message
  if (typeof detail === 'string') return detail
  if (e?.message) return e.message
  return fallback
}

export default useFormulaImportExport
