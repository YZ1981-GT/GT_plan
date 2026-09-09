/**
 * Shell-owned layout tokens (formula-toolbar Task 11).
 * Custom / guidance must consume these — never invent fixed offsets.
 */

export const SHELL_LAYOUT_TOKEN_VERSION = '1.0' as const

export interface ShellLayoutTokens {
  railGapPx: number
  railTopPx: number
  railRightPx: number
  railZIndex: number
  panelWidthPx: number
  contentInsetRightPx: number
}

export const DEFAULT_SHELL_LAYOUT_TOKENS: ShellLayoutTokens = {
  railGapPx: 8,
  railTopPx: 96,
  railRightPx: 0,
  railZIndex: 120,
  panelWidthPx: 380,
  contentInsetRightPx: 0,
}

export function shellLayoutCssVars(
  tokens: ShellLayoutTokens = DEFAULT_SHELL_LAYOUT_TOKENS,
  openPanel: boolean,
): Record<string, string> {
  const inset = openPanel ? tokens.panelWidthPx : tokens.contentInsetRightPx
  return {
    '--wp-shell-rail-gap': `${tokens.railGapPx}px`,
    '--wp-shell-rail-top': `${tokens.railTopPx}px`,
    '--wp-shell-rail-right': `${tokens.railRightPx}px`,
    '--wp-shell-rail-z': String(tokens.railZIndex),
    '--wp-shell-panel-width': `${tokens.panelWidthPx}px`,
    '--wp-shell-content-inset-right': `${inset}px`,
  }
}
