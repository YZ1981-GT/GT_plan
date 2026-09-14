/**
 * H3 底稿内行级跳转（H3-5 ↔ H3-12 等）
 */
import { ref, type InjectionKey, type Ref } from 'vue'

export type H3NavSheet = 'H3-5' | 'H3-12'

export interface H3RowFocusTarget {
  sheet: H3NavSheet
  rowId?: string
  assetName?: string
  titleCertNo?: string
  sourceRef?: string
  /** H3-5 内定位到证→账追查区 */
  section?: 'trace' | 'vouch'
}

export interface H3RowNavigation {
  highlightRowId: Ref<string>
  navigateToRow: (target: H3RowFocusTarget) => void
  consumeFocus: (sheet: H3NavSheet) => H3RowFocusTarget | null
  rowHighlightClass: (rowId: string) => string
  pendingSection: Ref<H3RowFocusTarget['section'] | undefined>
}

export const H3RowNavigationKey: InjectionKey<H3RowNavigation> = Symbol('h3RowNavigation')

const SHEET_LABEL: Record<H3NavSheet, string> = {
  'H3-5': 'H3-5 增减检查',
  'H3-12': 'H3-12 产权核对',
}

export function createH3RowNavigation(
  emitNavigate: (sheetName: string) => void,
): H3RowNavigation {
  const pendingFocus = ref<H3RowFocusTarget | null>(null)
  const highlightRowId = ref('')
  const pendingSection = ref<H3RowFocusTarget['section']>()

  let clearTimer: ReturnType<typeof setTimeout> | null = null

  function flashRow(rowId: string): void {
    highlightRowId.value = rowId
    if (clearTimer) clearTimeout(clearTimer)
    clearTimer = setTimeout(() => {
      if (highlightRowId.value === rowId) highlightRowId.value = ''
    }, 5000)
  }

  function navigateToRow(target: H3RowFocusTarget): void {
    pendingFocus.value = target
    pendingSection.value = target.section
    emitNavigate(SHEET_LABEL[target.sheet])
    if (target.rowId) flashRow(target.rowId)
  }

  function consumeFocus(sheet: H3NavSheet): H3RowFocusTarget | null {
    const f = pendingFocus.value
    if (!f || f.sheet !== sheet) return null
    pendingFocus.value = null
    if (f.rowId) flashRow(f.rowId)
    return f
  }

  function rowHighlightClass(rowId: string): string {
    return highlightRowId.value && highlightRowId.value === rowId ? 'h3-row-deeplink-hl' : ''
  }

  return {
    highlightRowId,
    navigateToRow,
    consumeFocus,
    rowHighlightClass,
    pendingSection,
  }
}
