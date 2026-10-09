/**
 * D4-7 月度/产品种子纯函数 —— 从组件提取，守卫直接 import 本文件。
 *
 * spec: four-table-extraction-entry-completion Phase 3
 * Property 10: seedMonthlyFromD42 — D4-7 月度种子与 D4-2 一致性
 * Property 11: prefillProductsFromSegments — D4-7 产品预填与 segment_prefill 一致性
 */

export interface MonthlyData {
  revenue: number[]  // 12 月收入
  cost: number[]     // 12 月成本
  priorRevenue: number
  priorCost: number
}

export interface ProductRow {
  rowId: string
  name: string
  curQty: number
  curRevenue: number
  curCost: number
  priorQty: number
  priorRevenue: number
  priorCost: number
  remark: string
}

/**
 * 从 D4-2 主营明细行 JSON 汇总 12 月收入种子。
 *
 * @param d42RowsJson - `allResponses.get('D4-2-rows')?.remark`（JSON 字符串）
 * @returns MonthlyData（成本侧恒 0，不伪造）；D4-2 无数据/解析失败返回 null。
 *
 * Property 10: seed.revenue[m] = D4-2 所有产品行 months[m] 之和。
 */
export function seedMonthlyFromD42(d42RowsJson: string | null | undefined): MonthlyData | null {
  if (!d42RowsJson) return null
  try {
    const d42Rows = JSON.parse(d42RowsJson)
    if (!Array.isArray(d42Rows) || d42Rows.length === 0) return null
    const revenue = new Array(12).fill(0)
    for (const row of d42Rows) {
      if (Array.isArray(row.months) && row.months.length === 12) {
        row.months.forEach((v: any, i: number) => { revenue[i] += parseFloat(v) || 0 })
      }
    }
    return { revenue, cost: new Array(12).fill(0), priorRevenue: 0, priorCost: 0 }
  } catch {
    return null
  }
}

/**
 * 从 segment_prefill 预填 D4-7 产品行。
 *
 * @param segments - `htmlData.segment_prefill`（后端 render 产出的分部行数组）
 * @param rowIdFactory - 行 ID 工厂（默认随机，测试可注入确定性工厂）
 * @returns ProductRow[]；segments 为空时返回空数组（不伪造）。
 *
 * Property 11: 产品数 = segments.length，字段映射 label→name 等。
 */
export function prefillProductsFromSegments(
  segments: any[] | null | undefined,
  rowIdFactory?: () => string,
): ProductRow[] {
  if (!Array.isArray(segments) || segments.length === 0) return []
  const makeId = rowIdFactory || (() => `pm-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`)
  return segments.map((s: any) => ({
    rowId: makeId(),
    name: s.label || '',
    curQty: 0,
    curRevenue: s.current_revenue ?? 0,
    curCost: s.current_cost ?? 0,
    priorQty: 0,
    priorRevenue: s.prior_revenue ?? 0,
    priorCost: s.prior_cost ?? 0,
    remark: '',
  }))
}
