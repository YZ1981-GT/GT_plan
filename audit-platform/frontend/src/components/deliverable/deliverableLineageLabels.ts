/**
 * 交付件溯源展示的中文标签**单一真源**。
 *
 * Spec: deliverable-lineage-wiring-and-writeback-closure — 需求 11.1（禁裸英文值）
 *
 * 🔴 版本链、差异告警、溯源面板都从这里取标签，禁止各写一份 map ——
 * 平台已多次出现"改一处另一处不红"的漂移（memory §避免硬编码）。
 */

/** `word_export_task_versions.created_via` 的中文标签。取值来自后端各处 render_and_store 的实参。 */
export const CREATED_VIA_LABEL: Readonly<Record<string, string>> = Object.freeze({
  generate: '生成',
  onlyoffice_edit: '在线编辑',
  refresh_section: '章节刷新',
  // `refresh_stale` = 批量刷新全部 stale 章节（`refresh_all_stale_sections`），
  // 与单章节刷新是两条不同入口，标签也要分开，否则版本链看不出是哪种刷新。
  refresh_stale: '批量刷新过期章节',
  writeback: '回填',
})

export function createdViaLabel(v: string | null | undefined): string {
  if (!v) return '未记录'
  return CREATED_VIA_LABEL[v] ?? v
}

/**
 * 差异归因（后端 `_attribute` 的结论）中文标签 + tag 色。
 *
 * 🔴 `manual_edit` 是**唯一**指向人的结论，措辞仍保持事实陈述（「文件被在线编辑改动」）
 * 而非指控；其余三态都不得暗示有人改了数字。
 */
export const DRIFT_ATTRIBUTION_LABEL: Readonly<Record<string, string>> = Object.freeze({
  upstream_changed: '上游数据已变更',
  pre_existing: '编辑前已存在（疑似映射配置）',
  manual_edit: '在线编辑改动了单元格',
  unknown: '成因待确认',
})

export const DRIFT_ATTRIBUTION_TAG: Readonly<Record<string, 'warning' | 'info' | 'danger'>> =
  Object.freeze({
    upstream_changed: 'warning',
    pre_existing: 'info',
    manual_edit: 'danger',
    unknown: 'info',
  })

export function driftAttributionLabel(v: string | null | undefined): string {
  if (!v) return DRIFT_ATTRIBUTION_LABEL.unknown
  return DRIFT_ATTRIBUTION_LABEL[v] ?? DRIFT_ATTRIBUTION_LABEL.unknown
}

export function driftAttributionTag(v: string | null | undefined): 'warning' | 'info' | 'danger' {
  if (!v) return 'info'
  return DRIFT_ATTRIBUTION_TAG[v] ?? 'info'
}

/** 期间列中文（Cell_Mapping 的 current / prior） */
export const DRIFT_PERIOD_LABEL: Readonly<Record<string, string>> = Object.freeze({
  current: '本期',
  prior: '上期',
})

export function driftPeriodLabel(v: string | null | undefined): string {
  if (!v) return '-'
  return DRIFT_PERIOD_LABEL[v] ?? v
}

/**
 * `tb_hash` 短标识：取前 8 位。完整 hash 对人无意义，短标识足够比对"是否同一份快照"。
 * 空值返回 null 让调用方决定显示什么（不要在这里编造 '-'）。
 */
export function shortHash(v: string | null | undefined): string | null {
  if (!v) return null
  return v.slice(0, 8)
}

// ── 差异告警的可见性判定（与后端 `should_block_confirm` 同口径）─────────────

/** 差异清单；非数组一律按空处理（后端未检测 / 检测不可用时该键不存在）。 */
export function driftDiffs(
  report: { diffs?: unknown } | null | undefined,
): Array<Record<string, unknown>> {
  const diffs = report?.diffs
  return Array.isArray(diffs) ? (diffs as Array<Record<string, unknown>>) : []
}

/**
 * 是否呈现差异告警。
 *
 * 🔴 判据**必须**与后端 `should_block_confirm` 一致，不能写 `if (report)` ——
 * `{"diffs": []}` 是非空对象但表示「已比对且一致」，朴素判据会让每个配了映射的
 * 报表都常亮一条空告警（用户会学会忽略它，真出问题时也看不见）。
 */
export function shouldShowDriftAlert(
  report: { diffs?: unknown; unavailable?: unknown } | null | undefined,
): boolean {
  if (!report) return false
  if (report.unavailable) return true
  return driftDiffs(report).length > 0
}
