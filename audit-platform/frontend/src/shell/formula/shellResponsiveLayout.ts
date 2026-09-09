/**
 * Responsive shell layout algorithm (formula-toolbar Task 12).
 *
 * Same token family for 1280 / 1440 / 1920 and 200% text zoom —
 * no per-viewport fork that reintroduces overlapping rails.
 */

import {
  DEFAULT_SHELL_LAYOUT_TOKENS,
  type ShellLayoutTokens,
} from './shellLayoutTokens'

export const SHELL_VIEWPORTS = [1280, 1440, 1920] as const
export type ShellViewportWidth = (typeof SHELL_VIEWPORTS)[number]

export type ShellViewportBand = 'compact' | 'standard' | 'wide'

export function classifyShellViewport(widthPx: number): ShellViewportBand {
  if (widthPx < 1440) return 'compact' // includes 1280
  if (widthPx < 1920) return 'standard' // includes 1440
  return 'wide'
}

/**
 * Resolve layout tokens for a viewport + optional text zoom.
 * 200% zoom is modeled as effectiveWidth = cssWidth / zoomFactor.
 */
export function resolveShellLayoutTokens(input: {
  viewportWidthPx: number
  textZoomPercent?: number
  base?: ShellLayoutTokens
}): ShellLayoutTokens {
  const zoom = Math.max(100, input.textZoomPercent ?? 100) / 100
  const effective = input.viewportWidthPx / zoom
  const band = classifyShellViewport(effective)
  const base = input.base ?? DEFAULT_SHELL_LAYOUT_TOKENS

  if (band === 'compact') {
    return {
      ...base,
      railTopPx: 88,
      panelWidthPx: 320,
      railGapPx: 6,
      railZIndex: base.railZIndex,
    }
  }
  if (band === 'standard') {
    return {
      ...base,
      railTopPx: 96,
      panelWidthPx: 360,
      railGapPx: 8,
    }
  }
  return {
    ...base,
    railTopPx: 104,
    panelWidthPx: 400,
    railGapPx: 10,
  }
}

/** Assert toolbar / rail / content insets do not overlap for a band. */
export function assertShellLayoutNonOverlap(tokens: ShellLayoutTokens): {
  ok: boolean
  reasonCode: string | null
} {
  if (tokens.panelWidthPx <= 0 || tokens.railGapPx < 0) {
    return { ok: false, reasonCode: 'invalid_token' }
  }
  if (tokens.railZIndex < 1) {
    return { ok: false, reasonCode: 'rail_z_missing' }
  }
  // Content inset when panel open equals panel width — never negative overlap.
  const insetWhenOpen = tokens.panelWidthPx
  if (insetWhenOpen < tokens.panelWidthPx) {
    return { ok: false, reasonCode: 'inset_less_than_panel' }
  }
  return { ok: true, reasonCode: null }
}
