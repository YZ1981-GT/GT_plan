/**
 * G12/G13/G14/H10「底稿目录」Tab 路由：b-index sheet → 循环 HTML 目录组件（D4TabIndex 同级体验）
 */
export const GCYCLE_INDEX_WP_CODES = ['G12', 'G13', 'G14', 'H10'] as const
export type GCycleIndexWpCode = (typeof GCYCLE_INDEX_WP_CODES)[number]

export const GCYCLE_INDEX_COMPONENT_MAP: Record<GCycleIndexWpCode, string> = {
  G12: 'g12-net-hedge-gains',
  G13: 'g13-fair-value-changes',
  G14: 'g14-credit-impairment-loss',
  H10: 'h10-asset-disposal-income',
}

export function isGCycleIndexWpCode(wpCode: string): wpCode is GCycleIndexWpCode {
  return (GCYCLE_INDEX_WP_CODES as readonly string[]).includes(wpCode)
}

/** b-index + G12/G13/G14/H10 → 委托到循环目录组件 */
export function isCycleDelegatedIndexSheet(sheetComponentType: string, wpCode: string): boolean {
  return sheetComponentType === 'b-index' && isGCycleIndexWpCode(wpCode)
}

export function resolveCycleIndexComponentType(sheetComponentType: string, wpCode: string): string {
  if (isCycleDelegatedIndexSheet(sheetComponentType, wpCode)) {
    return GCYCLE_INDEX_COMPONENT_MAP[wpCode as GCycleIndexWpCode]
  }
  return sheetComponentType
}

export interface CycleArchitectureSheet {
  sheet_name?: string
  componentType?: string
  component_type?: string
}

/** b-index html_data 无 navigation_rows 时，从 render-config sheets 构造架构树数据 */
/** 从 render-config sheetCache 中取 cycle_workpapers（force 专属 renderer 时各 sheet 同源） */
export function pickCycleWorkpapersFromCache(
  sheetCache?: Record<string, unknown>,
): unknown[] | undefined {
  if (!sheetCache) return undefined
  for (const sheetData of Object.values(sheetCache)) {
    const list = (sheetData as Record<string, unknown> | null)?.cycle_workpapers
    if (Array.isArray(list) && list.length > 0) return list
  }
  return undefined
}

/** 目录页 htmlData：去掉 navigation_rows（强制从 availableSheets 重建架构树），并补全 cycle_workpapers */
export function buildDirectoryHtmlData(
  htmlData: Record<string, unknown> | undefined,
  sheetCache?: Record<string, unknown>,
): Record<string, unknown> | undefined {
  if (!htmlData && !sheetCache) return undefined
  const base = htmlData ? { ...htmlData } : {}
  delete (base as { navigation_rows?: unknown }).navigation_rows
  const existing = base.cycle_workpapers
  if (!Array.isArray(existing) || existing.length === 0) {
    const fromCache = pickCycleWorkpapersFromCache(sheetCache)
    if (fromCache) base.cycle_workpapers = fromCache
  }
  return Object.keys(base).length > 0 ? base : undefined
}

export function buildCycleArchitectureHtmlData(
  htmlData: Record<string, unknown> | undefined,
  availableSheets?: CycleArchitectureSheet[],
  wpCode?: string,
): Record<string, unknown> {
  const base = htmlData ? { ...htmlData } : {}
  const rows = base.navigation_rows
  if (Array.isArray(rows) && rows.length > 0) return base
  if (!availableSheets?.length) return base

  return {
    ...base,
    navigation_rows: availableSheets
      .filter((s) => {
        const ct = s.componentType ?? s.component_type
        const name = s.sheet_name || ''
        if (ct === 'b-index') return false
        if (name.includes('底稿目录')) return false
        return !!name
      })
      .map((s, i) => {
        const name = s.sheet_name || ''
        const m = name.match(/([A-Z]\d+[A-Z]?(?:-\d+)*)\s*$/)
        return {
          seq: i + 1,
          content: name,
          sheet_name: name,
          index_ref: m ? m[1] : (wpCode ?? ''),
          component_type: s.componentType ?? s.component_type ?? 'skip',
          no_print: false,
        }
      }),
  }
}
