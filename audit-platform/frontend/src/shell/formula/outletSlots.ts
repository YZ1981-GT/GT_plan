/**
 * Named toolbar outlet slot identifiers (formula-toolbar Task 5).
 * Kept crypto-free so browser hosts can import without node:crypto.
 */

/** Frozen named outlet slot names. */
export const PRIMARY_OUTLET_SLOT = 'page-capabilities-primary' as const
export const COMPATIBILITY_OUTLET_SLOT = 'page-capabilities-compatibility' as const

/** CSS class that must NEVER be treated as a Vue slot / mounted outlet. */
export const GT_WP_TOOLBAR_RIGHT_CSS_CLASS = 'gt-wp-toolbar__right' as const
