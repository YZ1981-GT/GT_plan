/**
 * bundleSheetAliases.ts — Bundle 内 sheet 别名路由配置
 *
 * 当 wp_code 对应的不是独立底稿而是 bundle 内部的 sub-sheet 时，
 * GtIndexChip 的 resolveAndNavigateToWp 查此表做 fallback 路由：
 *   ref "A11-WP-1" → navigate to parent "A11" with query ?sheet=A11-WP-1
 *
 * 设计规范：design.md §Sheet / Tab 路由契约
 *
 * 新增 bundle 内部 tab 路由时只需在此文件加一行。
 */

export interface BundleSheetAlias {
  /** 父 bundle 的 wp_code（必须在 wp_index 中存在） */
  parent: string
  /** 传给父 bundle 的 sheet/tab query 参数 */
  sheet: string
}

/**
 * key = 虚拟 wp_code（不作为独立底稿存在于 wp_index 中）
 * value = 路由到父 bundle + sheet query
 */
export const BUNDLE_SHEET_ALIASES: Record<string, BundleSheetAlias> = {
  // ─── A11 bundle ────────────────────────────────────────────────────────
  'A11-WP-1': { parent: 'A11', sheet: 'A11-WP-1' },  // xlsx 审定表（≠ docx A11-1）

  // ─── A13 bundle ────────────────────────────────────────────────────────
  // A13-2~5 有独立 _WP_CODE_OVERRIDE，通常直接打开；
  // 但如果作为 bundle 内 tab 导航也支持：
  // 'A13-2': { parent: 'A13', sheet: 'A13-2' },
  // 'A13-3': { parent: 'A13', sheet: 'A13-3' },

  // ─── A14-3 workbook ────────────────────────────────────────────────────
  // A14-3 各 sheet 由 a14-3-workbook Tab 容器管理
  // 暂无需 alias（A14-3 自身是独立底稿）

  // ─── A15 bundle ────────────────────────────────────────────────────────
  // A15-1 是独立底稿（有 wp_index 条目），不需要 alias
}
