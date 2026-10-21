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
import api from '@/services/apiProxy'
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

/**
 * 自定义预设写入结果。
 *
 * 管理员直接生效（`pending_review=false`，带新增 / 更新计数）；其他人提交为全局候选
 * （`pending_review=true`，带候选记录），由管理员在「全局公式设置 → 发布记录」审核后才生效。
 */
export interface CustomPresetSaveResult {
  ok: boolean
  pending_review?: boolean
  inserted?: number
  updated?: number
  total?: number
  candidate?: { id: string; status: string }
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
   * 导出 JSON 标准公式包（跨环境迁移用，优化建议 #8）。
   * 从后端获取全部有效公式定义（全局 + 系统预设），按域和作用范围结构化输出为 JSON。
   * 公式包格式：{ version, exported_at, domains: { [domain]: { scope, slots: [...] } } }
   *
   * @param opts.domain 限定导出某域（不传 = 全部域）
   * @param opts.scope 限定导出某作用范围
   * @param opts.projectId 从某项目导出有效定义（含项目适配）
   */
  async function exportFormulaPackage(
    opts: { domain?: string; scope?: string; projectId?: string } = {},
  ): Promise<void> {
    loading.value = true
    try {
      const domains = opts.domain ? [opts.domain] : ['report', 'tb_detail', 'cross_check', 'wp', 'note', 'consol_note']
      const pack: Record<string, unknown> = {
        version: '1.0',
        format: 'gt_formula_package',
        exported_at: new Date().toISOString(),
        source: opts.projectId ? `project:${opts.projectId}` : 'global',
        domains: {} as Record<string, unknown>,
      }

      for (const domain of domains) {
        try {
          let data: any
          if (opts.projectId) {
            data = await api.get(`/api/projects/${opts.projectId}/formula-settings/${domain}/effective`) as any
          } else {
            const scope = opts.scope || '*'
            data = await api.get(`/api/formula-settings/${domain}/global`, { params: { scope } }) as any
          }
          const slots = (data?.slots || []).filter((s: any) => s.definition && Object.values(s.definition).some((v: unknown) => v))
          if (slots.length) {
            (pack.domains as Record<string, unknown>)[domain] = {
              scope: data?.scope || opts.scope || '*',
              slot_count: slots.length,
              slots: slots.map((s: any) => ({
                slot_key: s.slot_key,
                label: s.label,
                layer: s.layer,
                definition: s.definition,
              })),
            }
          }
        } catch { /* 单域取失败不阻断 */ }
      }

      const json = JSON.stringify(pack, null, 2)
      const blob = new Blob([json], { type: 'application/json' })
      const suffix = opts.projectId ? `_项目` : '_全局'
      downloadBlob(blob, `公式包${suffix}_${new Date().toISOString().slice(0, 10)}.json`)
      const count = Object.values(pack.domains as Record<string, any>).reduce((a, d) => a + (d.slot_count || 0), 0)
      ElMessage.success(`已导出 ${count} 条公式定义`)
    } catch (err: unknown) {
      ElMessage.error(extractError(err, '导出公式包失败'))
    } finally {
      loading.value = false
    }
  }

  /**
   * 导入 JSON 标准公式包（跨环境迁移用，优化建议 #8）。
   * 解析包文件，逐域逐条调用公式设置的保存接口写入。只做预览不直接写入，返回解析结果供用户确认。
   *
   * @param file JSON 公式包文件
   * @returns 解析结果 { domains, total_slots, errors }
   */
  async function importFormulaPackage(
    file: File,
  ): Promise<{ domains: Record<string, { slot_count: number; slots: any[] }>; total: number; errors: string[] } | null> {
    importing.value = true
    try {
      const text = await file.text()
      let pack: any
      try { pack = JSON.parse(text) } catch {
        ElMessage.error('文件不是合法的 JSON 格式')
        return null
      }
      if (pack?.format !== 'gt_formula_package') {
        ElMessage.error('该文件不是标准公式包格式（缺少 format: "gt_formula_package" 标识）')
        return null
      }
      const domains = pack.domains || {}
      const errors: string[] = []
      let total = 0
      const validDomains = ['report', 'tb_detail', 'cross_check', 'wp', 'note', 'consol_note']
      const result: Record<string, { slot_count: number; slots: any[] }> = {}

      for (const [domain, data] of Object.entries(domains)) {
        if (!validDomains.includes(domain)) {
          errors.push(`跳过未知域「${domain}」`)
          continue
        }
        const d = data as any
        const slots = Array.isArray(d?.slots) ? d.slots : []
        const validSlots = slots.filter((s: any) => s?.slot_key && s?.definition)
        if (validSlots.length !== slots.length) {
          errors.push(`域「${domain}」有 ${slots.length - validSlots.length} 条缺少 slot_key 或 definition`)
        }
        result[domain] = { slot_count: validSlots.length, slots: validSlots }
        total += validSlots.length
      }

      ElMessage.success(`已解析公式包：${total} 条定义（${Object.keys(result).length} 个域）${errors.length ? `，${errors.length} 条警告` : ''}`)
      return { domains: result, total, errors }
    } catch (err: unknown) {
      ElMessage.error(extractError(err, '导入公式包失败'))
      return null
    } finally {
      importing.value = false
    }
  }

  /**
   * 新增/更新一条平台级自定义预设（存数据库：管理员直接生效，其他人提交全局候选待审核）
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
      if (data.pending_review) {
        ElMessage.success('已提交为全局候选，管理员审核通过后生效')
      } else {
        ElMessage.success((data.inserted ?? 0) > 0 ? '自定义预设已新增' : '自定义预设已更新')
      }
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

  /**
   * 应用已解析的 JSON 公式包到指定项目（复盘修复 #8：importFormulaPackage 的写入步骤）。
   * 逐域调用 save_overrides 端点写入本项目层。
   *
   * @param projectId 目标项目 ID
   * @param parsed importFormulaPackage 返回的解析结果
   * @returns 写入统计 { written, skipped, errors }
   */
  async function applyFormulaPackage(
    projectId: string,
    parsed: { domains: Record<string, { slot_count: number; slots: any[] }> },
  ): Promise<{ written: number; skipped: number; errors: string[] }> {
    loading.value = true
    let written = 0; let skipped = 0; const errors: string[] = []
    try {
      for (const [domain, data] of Object.entries(parsed.domains)) {
        const items = data.slots.map((s: any) => ({
          slot_key: s.slot_key,
          definition: s.definition,
        }))
        if (!items.length) continue
        try {
          await api.post(`/api/projects/${projectId}/formula-settings/${domain}/overrides`, {
            items,
            source: 'formula_package_import',
          })
          written += items.length
        } catch (e: any) {
          const msg = e?.response?.data?.detail || e?.message || '写入失败'
          errors.push(`域「${domain}」写入失败：${msg}`)
          skipped += items.length
        }
      }
      if (written > 0) ElMessage.success(`已写入 ${written} 条公式定义${skipped ? `，${skipped} 条跳过` : ''}`)
      if (errors.length) ElMessage.warning(errors.join('；').slice(0, 300))
      return { written, skipped, errors }
    } catch (err: unknown) {
      ElMessage.error(extractError(err, '应用公式包失败'))
      return { written, skipped, errors }
    } finally {
      loading.value = false
    }
  }

  return {
    exportTemplate,
    exportData,
    importData,
    exportFormulaPackage,
    importFormulaPackage,
    applyFormulaPackage,
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
