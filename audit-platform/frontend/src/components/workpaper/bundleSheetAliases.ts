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

  // ─── S33 应对14号公告核查程序 bundle ─────────────────────────────────────
  // S33-1~S33-9 在 wp_code_overrides 映射为 skip，
  // 外部 GtIndexChip 点击 S33-x 时 fallback 路由到 S33 parent bundle。
  'S33-1': { parent: 'S33', sheet: 'S33-1' },
  'S33-2': { parent: 'S33', sheet: 'S33-2' },
  'S33-3': { parent: 'S33', sheet: 'S33-3' },
  'S33-4': { parent: 'S33', sheet: 'S33-4' },
  'S33-5': { parent: 'S33', sheet: 'S33-5' },
  'S33-6': { parent: 'S33', sheet: 'S33-6' },
  'S33-7': { parent: 'S33', sheet: 'S33-7' },
  'S33-8': { parent: 'S33', sheet: 'S33-8' },
  'S33-9': { parent: 'S33', sheet: 'S33-9' },

  // ─── S34 首发审核（IPO）特项底稿 bundle ──────────────────────────────────
  // S34-1~S34-41 在 wp_code_overrides 映射为 skip，
  // 外部 GtIndexChip 点击 S34-x 时 fallback 路由到 S34 parent bundle。
  // 子 sheet 编码（S34-x-n）也路由到对应父 Tab。
  'S34-1': { parent: 'S34', sheet: 'S34-1' },
  'S34-2': { parent: 'S34', sheet: 'S34-2' },
  'S34-3': { parent: 'S34', sheet: 'S34-3' },
  'S34-4': { parent: 'S34', sheet: 'S34-4' },
  'S34-5': { parent: 'S34', sheet: 'S34-5' },
  'S34-6': { parent: 'S34', sheet: 'S34-6' },
  'S34-7': { parent: 'S34', sheet: 'S34-7' },
  'S34-8': { parent: 'S34', sheet: 'S34-8' },
  'S34-9': { parent: 'S34', sheet: 'S34-9' },
  'S34-10': { parent: 'S34', sheet: 'S34-10' },
  'S34-11': { parent: 'S34', sheet: 'S34-11' },
  'S34-12': { parent: 'S34', sheet: 'S34-12' },
  'S34-13': { parent: 'S34', sheet: 'S34-13' },
  'S34-14': { parent: 'S34', sheet: 'S34-14' },
  'S34-15': { parent: 'S34', sheet: 'S34-15' },
  'S34-16': { parent: 'S34', sheet: 'S34-16' },
  'S34-16-1': { parent: 'S34', sheet: 'S34-16' },
  'S34-16-2': { parent: 'S34', sheet: 'S34-16' },
  'S34-17': { parent: 'S34', sheet: 'S34-17' },
  'S34-18': { parent: 'S34', sheet: 'S34-18' },
  'S34-18-1': { parent: 'S34', sheet: 'S34-18' },
  'S34-19': { parent: 'S34', sheet: 'S34-19' },
  'S34-20': { parent: 'S34', sheet: 'S34-20' },
  'S34-20-1': { parent: 'S34', sheet: 'S34-20' },
  'S34-21': { parent: 'S34', sheet: 'S34-21' },
  'S34-22': { parent: 'S34', sheet: 'S34-22' },
  'S34-23': { parent: 'S34', sheet: 'S34-23' },
  'S34-24': { parent: 'S34', sheet: 'S34-24' },
  'S34-25': { parent: 'S34', sheet: 'S34-25' },
  'S34-25-1': { parent: 'S34', sheet: 'S34-25' },
  'S34-25-2': { parent: 'S34', sheet: 'S34-25' },
  'S34-25-3': { parent: 'S34', sheet: 'S34-25' },
  'S34-26': { parent: 'S34', sheet: 'S34-26' },
  'S34-27': { parent: 'S34', sheet: 'S34-27' },
  'S34-28': { parent: 'S34', sheet: 'S34-28' },
  'S34-29': { parent: 'S34', sheet: 'S34-29' },
  'S34-30': { parent: 'S34', sheet: 'S34-30' },
  'S34-30-1': { parent: 'S34', sheet: 'S34-30' },
  'S34-31': { parent: 'S34', sheet: 'S34-31' },
  'S34-32': { parent: 'S34', sheet: 'S34-32' },
  'S34-33': { parent: 'S34', sheet: 'S34-33' },
  'S34-34': { parent: 'S34', sheet: 'S34-34' },
  'S34-34-1': { parent: 'S34', sheet: 'S34-34' },
  'S34-34-2': { parent: 'S34', sheet: 'S34-34' },
  'S34-35': { parent: 'S34', sheet: 'S34-35' },
  'S34-36': { parent: 'S34', sheet: 'S34-36' },
  'S34-37': { parent: 'S34', sheet: 'S34-37' },
  'S34-38': { parent: 'S34', sheet: 'S34-38' },
  'S34-39': { parent: 'S34', sheet: 'S34-39' },
  'S34-40': { parent: 'S34', sheet: 'S34-40' },
  'S34-41': { parent: 'S34', sheet: 'S34-41' },
  'S34-2-1': { parent: 'S34', sheet: 'S34-2' },
  'S34-2-2': { parent: 'S34', sheet: 'S34-2' },
  'S34-3-1': { parent: 'S34', sheet: 'S34-3' },
  'S34-4-1': { parent: 'S34', sheet: 'S34-4' },
  'S34-8-1': { parent: 'S34', sheet: 'S34-8' },
  'S34-8-2': { parent: 'S34', sheet: 'S34-8' },
  'S34-9-1': { parent: 'S34', sheet: 'S34-9' },
  'S34-11-1': { parent: 'S34', sheet: 'S34-11' },

  // ─── S35 再融资审核特项底稿 bundle ─────────────────────────────────────
  // S35-1~S35-5 在 wp_code_overrides 映射为 skip，
  // 外部 GtIndexChip 点击 S35-x 时 fallback 路由到 S35 parent bundle。
  // 子 sheet 编码（S35-x-1）也路由到对应父 Tab。
  'S35-1': { parent: 'S35', sheet: 'S35-1' },
  'S35-2': { parent: 'S35', sheet: 'S35-2' },
  'S35-3': { parent: 'S35', sheet: 'S35-3' },
  'S35-4': { parent: 'S35', sheet: 'S35-4' },
  'S35-5': { parent: 'S35', sheet: 'S35-5' },
  'S35-1-1': { parent: 'S35', sheet: 'S35-1' },
  'S35-2-1': { parent: 'S35', sheet: 'S35-2' },
  'S35-3-1': { parent: 'S35', sheet: 'S35-3' },
}
