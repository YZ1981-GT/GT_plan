/**
 * F1 主入口从底稿渲染配置（本 sheet 的 `html_data`）取给附注披露 Tab 的两项上下文。
 *
 * 原先内联在 `GtF1Prepayment.vue` 的 computed 里；附注页离屏同步（spec note-pull-followup-closure R1）要按同一取法
 * 从渲染配置取，故抽成纯函数由主入口与离屏 provider 共用（只复用不复制）。
 */

export interface F1ImpairmentPrefill {
  end: number
  prior: number
}

type HtmlData = Record<string, any> | null | undefined

/**
 * 被审计单位名称 —— 国企披露②表「债权单位」列的缺省值。
 *
 * 源 xlsx `附注披露信息(国企)` A18~A20 = `=RIGHT($A$3,LEN($A$3)-SEARCH("：",$A$3))`
 * （从底稿目录「被审计单位：XXX」截出）。这里读 render 已下发的 `project_context.client_name`，
 * 不去解析底稿目录 sheet 的单元格。
 */
export function f1ClientNameOf(htmlData: HtmlData): string {
  const ctx = htmlData?.project_context ?? htmlData?.projectContext ?? {}
  return String(ctx.client_name ?? ctx.clientName ?? '').trim()
}

/**
 * 减值准备（坏账准备-预付账款）四表库预填（render `impairment_prefill`）。
 * `null` = 四表库无该备抵科目 → 披露侧保持手工录入（宁缺勿造）。
 */
export function f1ImpairmentPrefillOf(htmlData: HtmlData): F1ImpairmentPrefill | null {
  const raw = htmlData?.impairment_prefill ?? htmlData?.impairmentPrefill
  if (!raw || typeof raw !== 'object') return null
  return { end: Number(raw.end ?? 0) || 0, prior: Number(raw.prior ?? 0) || 0 }
}
