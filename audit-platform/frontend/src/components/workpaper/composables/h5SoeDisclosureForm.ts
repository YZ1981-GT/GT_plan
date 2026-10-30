/**
 * H5 油气资产国企披露表：汇总四行、层级期末合计、补充披露文本（底稿披露 Tab `H5TabDisclosureSoe` 与附注页离屏同步共用，
 * spec note-pull-followup-closure R1）。三段原在 Tab 组件里内联（`summaryRows` 计算属性 / `syncToNote` 的空表判断与
 * 层级合计 / 文本 hydrate），原样抽到这里。上市侧没有附注落点（见 `h5NoteSectionMap.H5_LISTED_NOT_APPLICABLE_REASON`）。
 */
import type { H5LayerTotals } from './h5NoteSectionMap'

/** 国企补充披露文本的持久化键（与 Tab 的 `H5_SOE_TEXT_ITEM` 同值，守卫钉住） */
export const H5_SOE_TEXT_ITEM = 'H5-disc-soe-text'

/** `substantive:adjudicated` 事件带来的审定数（Tab 挂载期间才有，离屏为 null） */
export interface H5AdjudicatedData {
  costAudited: number
  depletionAudited: number
  impairmentAudited: number
  netValue: number
}

export interface H5SoeSummaryRow {
  item: string
  endBalance: number
  beginBalance: number
}

type ResponseMap = ReadonlyMap<string, { remark?: string | null } | undefined>

/** 汇总四行：有审定事件数据用事件数据，否则按 H5-1 原值 / 折耗明细的审定数合计 */
export function buildH5SoeSummaryRows(adjudicated: H5AdjudicatedData | null, responses: ResponseMap): H5SoeSummaryRow[] {
  const data = adjudicated
  if (data) {
    return [
      { item: '油气资产原值', endBalance: data.costAudited, beginBalance: 0 },
      { item: '减：累计折耗', endBalance: data.depletionAudited, beginBalance: 0 },
      { item: '减：减值准备', endBalance: data.impairmentAudited, beginBalance: 0 },
      { item: '油气资产净值', endBalance: data.netValue, beginBalance: 0 },
    ]
  }
  // Fallback from allResponses
  let costTotal = 0
  let deplTotal = 0
  const costRaw = responses.get('H5-1-cost-rows')
  const deplRaw = responses.get('H5-1-depletion-rows')
  if (costRaw?.remark) { try { costTotal = JSON.parse(costRaw.remark).reduce((s: number, r: any) => s + (Number(r.audited) || 0), 0) } catch {} }
  if (deplRaw?.remark) { try { deplTotal = JSON.parse(deplRaw.remark).reduce((s: number, r: any) => s + (Number(r.audited) || 0), 0) } catch {} }
  return [
    { item: '油气资产原值', endBalance: costTotal, beginBalance: 0 },
    { item: '减：累计折耗', endBalance: deplTotal, beginBalance: 0 },
    { item: '减：减值准备', endBalance: 0, beginBalance: 0 },
    { item: '油气资产净值', endBalance: costTotal - deplTotal, beginBalance: 0 },
  ]
}

/** 汇总全为 0（Tab 提示「请先填写披露数据」且不同步） */
export function h5SoeSummaryIsEmpty(rows: readonly H5SoeSummaryRow[]): boolean {
  return rows.every((r) => r.endBalance === 0 && r.beginBalance === 0)
}

/** 载荷用的层级期末合计（按行名取） */
export function h5SoeLayerTotals(rows: readonly H5SoeSummaryRow[]): H5LayerTotals {
  return {
    cost: rows.find((r) => r.item === '油气资产原值')?.endBalance ?? 0,
    depletion: rows.find((r) => r.item === '减：累计折耗')?.endBalance ?? 0,
    impairment: rows.find((r) => r.item === '减：减值准备')?.endBalance ?? 0,
  }
}

/** 已保存的补充披露文本 */
export function readH5SoeDisclosureText(responses: ResponseMap): string {
  return String(responses.get(H5_SOE_TEXT_ITEM)?.remark ?? '')
}
