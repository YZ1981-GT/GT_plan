/**
 * F1 主入口从底稿渲染配置（本 sheet 的 `html_data`）取给附注披露 Tab 的两项上下文。
 *
 * 原先内联在 `GtF1Prepayment.vue` 的 computed 里；附注页离屏同步（spec note-pull-followup-closure R1）要按同一取法
 * 从渲染配置取，故抽成纯函数由主入口与离屏 provider 共用（只复用不复制）。
 */

import { resolveRenderSheet } from '@/composables/useWpRenderer'
import {
  F1_DISCLOSURE_SHEET_NAME,
  type F1DisclosureVariant,
} from './f1NoteSectionMap'

export interface F1ImpairmentPrefill {
  end: number
  prior: number
}

type HtmlData = Record<string, any> | null | undefined

/**
 * 在整本底稿 render-config 中定位 F1 披露 sheet 的 html_data。
 *
 * `GtF1Prepayment` 已由外壳选中真实 sheet 后直接接收 `props.htmlData`；离屏同步没有这层路由，
 * 因而必须用与宿主 `currentSheet` 相同的名称语义定位。除 canonical 名外兼容源模板中的
 * 「上市」/「国有企业」写法，最后用宿主同款关键词兜底。
 */
export function f1DisclosureHtmlDataOf(
  renderConfig: { sheets?: readonly any[] } | null | undefined,
  variant: F1DisclosureVariant,
): HtmlData {
  const sheets = Array.isArray(renderConfig?.sheets) ? renderConfig.sheets : []
  const aliases = variant === 'listed'
    ? [F1_DISCLOSURE_SHEET_NAME.listed, '附注披露信息(上市)']
    : [F1_DISCLOSURE_SHEET_NAME.soe, '附注披露信息(国有企业)']
  for (const locator of aliases) {
    const matched = resolveRenderSheet(sheets, locator)
    if (matched) return matched.html_data
  }
  const fallback = sheets.find((sheet) => {
    const name = String(sheet?.sheet_name ?? '')
    return variant === 'listed'
      ? /附注.*上市/.test(name)
      : /附注.*(国企|国有)/.test(name)
  })
  return fallback?.html_data ?? null
}

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
