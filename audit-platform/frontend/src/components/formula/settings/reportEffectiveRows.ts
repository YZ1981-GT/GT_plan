/**
 * 公式管理中心报表行：读有效定义 + 按上下文保存（spec formula-global-settings-sync，R1.2 / R1.4 / R6.1 / R6.2）。
 *
 * - **项目上下文**：行 = 本项目有效定义（全局 → 订阅模板 / 本项目适配），每行带层级标签；
 *   保存 = 一次写本项目适配（原子；CAS 用本项目版本，没有本项目行时不带版本），不影响其他项目；
 *   「恢复为全局」= 删除本项目适配。此前读的是「有项目行就只显示项目行」的旧口径，
 *   只适配过几行的项目会把其余全局行全部藏掉，而且保存会打到全局行（非管理员 403）。
 * - **无项目上下文**（管理员从全局入口打开）：行 = 准则模板行，保存走报表配置接口（全局行 = 直接发布，
 *   CAS 用 `formula_version`）。
 *
 * 批量保存只发「改过的行」（`_orig` 快照比对），不再把整张表逐行 PUT 一遍。
 */
import { api } from '@/services/apiProxy'
import { reportConfig as P_rc } from '@/services/apiPaths'
import { formulaSettingsApi, type Definition, type EffectiveResult, type EffectiveSlot } from '@/composables/formula/useFormulaSettings'

/** 弹窗可编辑的报表公式字段（执行字段 + 说明）。 */
export const REPORT_EDIT_FIELDS = ['formula', 'aje_formula', 'rje_formula', 'formula_category', 'formula_description'] as const
/** 参与「与全局是否相同」判定的执行字段（与后端 report 域 exec_fields 同口径）。 */
const EXEC_FIELDS = ['formula', 'aje_formula', 'rje_formula', 'formula_category'] as const

const norm = (v: unknown) => (v == null ? '' : String(v).trim())
const snap = (src: any, fields: readonly string[]) => JSON.stringify(fields.map((f) => norm(src?.[f])))

/** 每个项目的有效定义只拉一次（同一次打开内各报表共用）；保存 / 恢复 / 订阅后失效。 */
const cache = new Map<string, Promise<EffectiveResult>>()

export function invalidateEffectiveReport(projectId?: string): void {
  if (projectId) cache.delete(projectId)
  else cache.clear()
}

function loadEffective(projectId: string): Promise<EffectiveResult> {
  const hit = cache.get(projectId)
  if (hit) return hit
  const req = formulaSettingsApi.effective(projectId, 'report')
  cache.set(projectId, req)
  // 失败或响应不成形不留缓存（下次再取）
  const drop = () => { if (cache.get(projectId) === req) cache.delete(projectId) }
  req.then((r) => { if (!Array.isArray(r?.slots)) drop() }, drop)
  return req
}

/** 给行记下载入时的快照（批量保存据此只发改过的行）。 */
export function markLoaded<T extends Record<string, any>>(rows: T[]): T[] {
  for (const r of rows) (r as any)._orig = snap(r, REPORT_EDIT_FIELDS)
  return rows
}

export function rowChanged(row: any): boolean {
  return typeof row?._orig === 'string' && row._orig !== snap(row, REPORT_EDIT_FIELDS)
}

function toRow(s: EffectiveSlot, reportType: string, projectId: string): Record<string, any> {
  const st = s.structure || {}
  const d = s.definition || {}
  const code = s.slot_key.slice(reportType.length + 1)
  return {
    id: s.slot_key, report_type: reportType, row_code: code, applicable_standard: `project:${projectId}`,
    row_number: st.row_number ?? 0, row_name: st.row_name || code, indent_level: st.indent_level ?? 0,
    is_total_row: !!st.is_total_row, parent_row_code: st.parent_row_code ?? null,
    formula: d.formula ?? null, aje_formula: d.aje_formula ?? null, rje_formula: d.rje_formula ?? null,
    formula_category: d.formula_category ?? null, formula_description: d.formula_description ?? null,
    formula_source: d.formula_source ?? null,
    _slot_key: s.slot_key, _layer: s.layer, _layer_label: s.layer_label, _pending: s.pending, _disabled: s.disabled,
    _local_version: s.local_version,
    _upstream: snap(s.global_definition || s.preset_definition, EXEC_FIELDS),
  }
}

/** 本项目某类报表的有效行（按行号排序）；接口不可用时返回 null，调用方回退旧口径。 */
export async function fetchEffectiveReportRows(projectId: string, reportType: string): Promise<{
  rows: Record<string, any>[]; canEditGlobal: boolean; scope: string
} | null> {
  let eff: EffectiveResult
  try {
    eff = await loadEffective(projectId)
  } catch {
    return null
  }
  if (!Array.isArray(eff?.slots)) return null // 响应不成形（旧后端 / 代理改写）→ 回退旧口径，不当成「没有公式」
  const prefix = `${reportType}:`
  const rows = eff.slots.filter((s) => s.slot_key.startsWith(prefix)).map((s) => toRow(s, reportType, projectId))
  rows.sort((a, b) => (a.row_number ?? 0) - (b.row_number ?? 0))
  return { rows: markLoaded(rows), canEditGlobal: !!eff.can_edit_global, scope: eff.scope || '' }
}

function pickFields(row: any): Definition {
  const out: Definition = {}
  for (const f of REPORT_EDIT_FIELDS) out[f] = norm(row[f]) || null
  return out
}

/**
 * 保存报表行的公式字段。返回写进本项目适配的公式位（调用方据此弹「应用范围」）。
 * 失败抛错（调用方提示）；成功后就地更新版本、层级与快照。
 */
export async function saveReportRows(projectId: string | undefined, rows: any[]): Promise<{ projectSlotKeys: string[] }> {
  const projectRows = projectId ? rows.filter((r) => r._slot_key) : []
  const legacyRows = rows.filter((r) => !projectRows.includes(r))
  if (projectRows.length && projectId) {
    const res = await formulaSettingsApi.saveOverrides(projectId, 'report', projectRows.map((r) => ({
      slot_key: r._slot_key, definition: pickFields(r), expected_version: r._local_version ?? null, label: r.row_name,
    })))
    const versions = new Map((res?.saved || []).map((s) => [s.slot_key, s.version]))
    for (const r of projectRows) {
      r._local_version = versions.get(r._slot_key) ?? r._local_version
      const same = r._upstream === snap(r, EXEC_FIELDS)
      r._layer = same ? 'global' : 'project'
      r._layer_label = same ? '全局' : '本项目'
    }
    invalidateEffectiveReport(projectId)
  }
  for (const r of legacyRows) {
    const saved: any = await api.put(P_rc.detail(r.id), { ...pickFields(r), expected_version: r.formula_version ?? 1 })
    if (saved?.formula_version != null) r.formula_version = saved.formula_version
  }
  markLoaded(rows)
  return { projectSlotKeys: projectRows.map((r) => r._slot_key) }
}

/** 恢复为全局：删除这些行的本项目适配（订阅模板来的回到模板定义）。 */
export async function restoreReportRows(projectId: string, rows: any[]): Promise<void> {
  const keys = rows.map((r) => r._slot_key).filter(Boolean)
  if (!keys.length) return
  const versions = keys.map((k) => {
    const row = rows.find((r) => r._slot_key === k)
    return row?._local_version ?? row?.version ?? 1
  })
  await formulaSettingsApi.restoreGlobal(projectId, 'report', keys, versions)
  invalidateEffectiveReport(projectId)
}

/** 行上「恢复全局」按钮是否可用：本项目改过或暂缓固定的行。 */
export function canRestoreRow(row: any): boolean {
  return !!row?._slot_key && (row._layer === 'project' || row._layer === 'pinned')
}
