/**
 * useTemplateLibrarySource — D13 ADR JSON 源只读判断 composable
 *
 * D13 ADR：JSON 源类资源（4 个）禁止 UI 直接编辑，只读 + 引导更新流程：
 *   - prefill_formula_mapping  → backend/data/prefill_formula_mapping.json
 *   - cross_wp_references      → backend/data/cross_wp_references.json
 *   - audit_report_templates   → backend/data/audit_report_templates_seed.json
 *   - wp_account_mapping       → backend/data/wp_account_mapping.json
 *
 * 编辑路径分流：
 *   - JSON 源（4 个）→ 编辑文件后调 reseed
 *   - DB 表（report_config / gt_wp_coding / wp_template_metadata 等）→ UI 直接编辑
 *
 * 用途：FormulaTab / AuditReportTab / WpTemplateMgmt 等组件统一引用此 composable
 * 替代散落在各组件内的硬编码字符串，避免维护漂移。
 *
 * Validates: D13 ADR + Sprint 5 Task 5.5
 */

export type TemplateLibraryResource =
  | 'prefill_formula_mapping'
  | 'cross_wp_references'
  | 'audit_report_templates'
  | 'wp_account_mapping'
  | 'report_config'
  | 'gt_wp_coding'
  | 'wp_template_metadata'
  | 'note_templates'
  | 'accounting_standards'
  | 'template_sets'

/** 4 个 JSON 源类资源（D13 ADR 显式清单） */
export const JSON_READONLY_RESOURCES = [
  'prefill_formula_mapping',
  'cross_wp_references',
  'audit_report_templates',
  'wp_account_mapping',
] as const

export type JsonReadonlyResource = (typeof JSON_READONLY_RESOURCES)[number]

/** JSON 源资源 → 文件路径映射（与 backend/data/ 实际文件名一致） */
const JSON_SOURCE_FILES: Record<JsonReadonlyResource, string> = {
  prefill_formula_mapping: 'backend/data/prefill_formula_mapping.json',
  cross_wp_references: 'backend/data/cross_wp_references.json',
  audit_report_templates: 'backend/data/audit_report_templates_seed.json',
  wp_account_mapping: 'backend/data/wp_account_mapping.json',
}

/**
 * 判断指定资源是否为 JSON 源只读类型
 *
 * @example
 *   isJsonSource('prefill_formula_mapping') // true
 *   isJsonSource('report_config')           // false
 */
export function isJsonSource(resource: TemplateLibraryResource | string): boolean {
  return (JSON_READONLY_RESOURCES as readonly string[]).includes(resource)
}

/**
 * 获取 JSON 源资源的文件路径（DB 表类资源返回空字符串）
 */
export function getJsonSourceFile(resource: TemplateLibraryResource | string): string {
  if (!isJsonSource(resource)) return ''
  return JSON_SOURCE_FILES[resource as JsonReadonlyResource]
}

/**
 * 获取只读引导提示文本（用于 tooltip / alert 等）
 *
 * DB 表类资源返回空字符串（调用方应先调 isJsonSource 判断）。
 *
 * @example
 *   getReadonlyHint('prefill_formula_mapping')
 *   // → 'JSON 源只读 — 如需修改，请编辑 backend/data/prefill_formula_mapping.json 后调用 reseed'
 */
export function getReadonlyHint(resource: TemplateLibraryResource | string): string {
  if (!isJsonSource(resource)) return ''
  const filePath = JSON_SOURCE_FILES[resource as JsonReadonlyResource]
  return `JSON 源只读 — 如需修改，请编辑 ${filePath} 后调用 reseed`
}

/**
 * 获取简短只读 badge 文本（用于表格行 / 列表项）
 */
export function getReadonlyBadgeText(): string {
  return 'JSON 只读'
}

/**
 * Vue Composable 入口
 *
 * @example
 *   const { isJsonSource, getReadonlyHint } = useTemplateLibrarySource()
 *   const hint = getReadonlyHint('prefill_formula_mapping')
 */
export function useTemplateLibrarySource() {
  return {
    isJsonSource,
    getJsonSourceFile,
    getReadonlyHint,
    getReadonlyBadgeText,
    JSON_READONLY_RESOURCES,
  }
}
