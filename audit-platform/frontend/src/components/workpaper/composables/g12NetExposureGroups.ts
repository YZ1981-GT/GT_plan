/**
 * G12-5 同项目多币种分组（UI 折叠展示）
 */
import type { G12NetExposureRow } from './useG12NetExposure'

export interface G12NetExposureItemGroup {
  key: string
  item: string
  hedgeRelationId: string
  rows: G12NetExposureRow[]
  currencies: string[]
}

export function normNetExposureItem(item: string): string {
  return item.trim()
}

export function groupNetExposureRows(rows: G12NetExposureRow[]): G12NetExposureItemGroup[] {
  const map = new Map<string, G12NetExposureItemGroup>()
  for (const r of rows) {
    const key = normNetExposureItem(r.item) || `__row_${r.rowId}`
    if (!map.has(key)) {
      map.set(key, {
        key,
        item: r.item,
        hedgeRelationId: r.hedgeRelationId,
        rows: [],
        currencies: [],
      })
    }
    const g = map.get(key)!
    g.rows.push(r)
    if (r.currency && !g.currencies.includes(r.currency)) g.currencies.push(r.currency)
    if (r.hedgeRelationId && !g.hedgeRelationId) g.hedgeRelationId = r.hedgeRelationId
  }
  return [...map.values()]
}
