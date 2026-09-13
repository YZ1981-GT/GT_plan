/**
 * htmlRendererRegistry — HTML 底稿渲染器组件注册表
 *
 * 重构动机（2026-05-28 复盘）：HTML componentType 11 类原本硬编码 4 处需同步：
 *   1. useEditorMode.HTML_COMPONENT_TYPES Set
 *   2. GtWpRenderer.vue v-if/v-else-if 分发链
 *   3. useWpClassification fallback 推断
 *   4. 后端 workpaper_sheet_classification 表种子
 * 本注册表统一前端 1+2 的来源，新增类型只改这一份配置。
 *
 * 设计要点：
 *  - lazy import：每个 component 用 `defineAsyncComponent(() => import(...))`，
 *    冷启动只加载当前底稿用到的子组件
 *  - icon 与 componentType 一一映射（GtWpRenderer 的 sheet tab 复用）
 *  - emits 声明式列出，方便测试 + 文档生成
 *  - placeholder（univer/skip/unknown）走 GtWpRenderer 内部 fallback，不在此注册
 *
 * @example
 *   import { HTML_RENDERER_REGISTRY, isHtmlComponentType } from './htmlRendererRegistry'
 *   const entry = HTML_RENDERER_REGISTRY.get('a-program-console')
 *   if (entry) {
 *     // entry.component is the lazy-loaded SFC
 *     // entry.icon is '📋'
 *   }
 */
import { coreEntries } from './registry/entries/core'
import { formsEntries } from './registry/entries/forms'
import { programsEntries } from './registry/entries/programs'
import { confirmationsEntries } from './registry/entries/confirmations'
import { reportsEntries } from './registry/entries/reports'
import { specializedEntries } from './registry/entries/specialized'

/** HTML 底稿组件类型（与 useEditorMode.HTML_COMPONENT_TYPES 保持一致） */
export type HtmlComponentType =
  | 'a1-dashboard'
  | 'a2-adjustment-console'
  | 'a3-consolidation-console'
  | 'a-program-console'
  | 'b-index'
  | 'c-note-table'
  | 'd-form-table'
  | 'd-form-paragraph'
  | 'd-form-qa'
  | 'd-form-confirmation'
  | 'd-form-review'
  | 'e-control-test'
  | 'h-static-doc'
  | 'custom'
  | 'audit-sheet'
  | 'bad-debt-sheet'
  | 'cf-verification'
  | 'procedure-table'
  | 'report-analysis'
  | 'misstatement-summary'
  | 'review-checklist'
  | 'word-template'
  | 'independence-signing'
  | 'wp-popup-signing'
  | 'a1-11-signing-form'
  | 'audit-legend'
  | 'checklist-table'
  | 'analytical-review'
  | 'a17-summary'
  | 'kam-workpaper'
  | 'regulatory-letter'
  | 'goodwill-impairment'
  | 'segment-report'
  | 'contingent-liability'
  | 'discontinued-operations'
  | 'misstatement-workpaper'
  | 'a14-3-workbook'
  | 'a10-bundle'
  | 'a11-bundle'
  | 'a12-bundle'
  | 'a15-bundle'
  | 'a17-bundle'
  | 'a16-bundle'
  | 'confirmation-summary'
  | 'confirmation-entity-verify'
  | 'confirmation-followup'
  | 'confirmation-diff-reconcile'
  | 'confirmation-alternative-d05'
  | 'confirmation-alternative-d06'
  | 'confirmation-alternative-f05'
  | 'confirmation-alternative-f06'
  | 'confirmation-diff-securities'
  | 'confirmation-diff-nonsecurities'
  | 'confirmation-alternative-g06'
  | 'confirmation-alternative-h05'
  | 'confirmation-alternative-k05'
  | 'confirmation-alternative-k06'
  | 'confirmation-alternative-l05'
  | 'g14-credit-impairment-loss'
  | 'h10-asset-disposal-income'
  | 'h1-fixed-assets'
  | 'h5-oil-gas-assets'
  | 'h7-biological-assets'
  | 'h2-construction-in-progress'
  | 'h3-investment-property'
  | 'h4-engineering-materials'
  | 'h6-asset-disposal-clearing'
  | 'h8-right-of-use-assets'
  | 'h9-lease-liabilities'
  | 'g13-fair-value-changes'
  | 'g12-net-hedge-gains'
  | 'g11-investment-income'
  | 'g10-trading-financial-liabilities'
  | 'g9-other-noncurrent-financial'
  | 'g8-other-equity-instruments'
  | 'g7-long-term-equity-subsidiary'
  | 'g7-long-term-equity-method'
  | 'g7-long-term-equity-main'
  | 'g6-other-bond-investment-ecl'
  | 'g6-other-bond-investment-sppi'
  | 'g6-other-bond-investment-main'
  | 'g5-long-term-receivable'
  | 'g4-bond-investment-ecl'
  | 'g4-bond-investment-sppi'
  | 'g4-bond-investment-main'
  | 'g3-dividend-receivable'
  | 'g2-interest-receivable'
  | 'g1-trading-financial-assets'
  | 'f5-cost-of-sales'
  | 'f4-accounts-payable'
  | 'f3-notes-payable'
  | 'f2-inventory-valuation-impairment'
  | 'f2-inventory-special'
  | 'f2-inventory-main'
  | 'f1-prepayment'
  | 'confirmation-diff-checklist'
  | 'confirmation-fraud-risk'
  | 'confirmation-reliability'
  | 'confirmation-wealth-list'
  | 'confirmation-send-list-e03'
  | 'confirmation-send-list-e04'
  | 'confirmation-send-list-e05'
  | 'b50-risk-assessment'
  | 'b22a-control-matrix'
  | 'b22b-deficiency-evaluation'
  | 'b22b-control-matrix'
  | 'b22c-design-effectiveness'
  | 'b23-process-control'
  | 'b30-group-audit'
  | 'b2-bundle'
  | 'b13-bundle'
  | 'b19-bundle'
  | 'b51-bundle'
  | 'b60-strategy'
  | 'b2-12-evaluation'
  | 'f2-stocktake-bundle'
  | 'c-control-test'
  | 'd1-notes-receivable'
  | 'd2-accounts-receivable'
  | 'a1-12-dual-checklist'
  | 'a1-15-disclosure-checklist'
  | 'a1-17-corresponding-data'
  | 'a17-6-closing-meeting'
  | 'a18-1-regulatory-submission'
  | 'a18-2-regulatory-communication'
  | 'a8-1-other-info-representation'
  | 'a11-1-subsequent-events-inquiry'
  | 'a17-3-consultation-record'
  | 'a17-3-1-consultation-execution'
  | 'a17-4-disagreement-record'
  | 'a17-7-independence-declaration'
  | 'a9-1-deficiency-letter'
  | 'a9-2-deficiency-letter-governance'
  | 'a27-1-it-audit-memo'
  | 'a12-1-legal-confirmation'
  | 'a10-1-governance-communication'
  | 'a17-1-audit-summary'
  | 'a17-2-1-kam'
  | 'a5-1-cashflow-audit'
  | 'a3-8-goodwill-impairment'
  | 'b1-4-due-diligence-report'
  | 'b1-risk-assessment'
  | 'b1-3-business-evaluation'
  | 'b1-5-kaa-check'
  | 'd4-operating-revenue'
  | 'd3-prepaid-accounts'
  | 'd5-receivables-financing'
  | 'd6-contract-assets'
  | 'd7-contract-liabilities'
  | 'e1-monetary-fund'
  | 'c1-entity-level-control'
  | 'c22-itgc-bundle'
  | 'c23-journal-entry-control'
  | 'c24-journal-entry-detail'
  | 'c25-internal-audit-reliance'
  | 'c26-info-processing-control'
  | 'l1-short-term-loans'
  | 'l2-interest-payable'
  | 'l3-long-term-loans'
  | 'l4-bonds-payable'
  | 'l5-long-term-payables'
  | 'l6-special-payables'
  | 'l7-other-noncurrent-liabilities'
  | 'l8-financial-expenses'
  | 'm1-dividends-payable'
  | 'm2-paid-in-capital'
  | 'm3-treasury-stock'
  | 'm4-capital-reserve'
  | 'm5-surplus-reserve'
  | 'm6-retained-earnings'
  | 'm7-special-reserve'
  | 'm8-general-risk-reserve'
  | 'm9-other-comprehensive-income'
  | 'm10-other-equity-instruments'
  | 'n1-deferred-tax-assets'
  | 'n2-taxes-payable'
  | 'n3-deferred-tax-liabilities'
  | 'n4-taxes-and-surcharges'
  | 'n5-income-tax-expense'
  | 's3-policy-change'
  | 's4-nonmonetary-exchange'
  | 's5-debt-restructuring'
  | 's6-fund-occupation'
  | 's12-cpa-expert'
  | 's13-mgmt-expert'
  | 's14-accounting-estimate'
  | 's15-eps-roe'
  | 's20-revenue-deduction'
  | 's21-data-asset'
  | 's32-fraud-bundle'
  | 's33-ann14-bundle'
  | 's34-ipo-bundle'
  | 's35-refinance-bundle'
  | 'i1-intangible-assets'
  | 'i2-development-expenditure'
  | 'i3-goodwill'
  | 'i4-long-term-prepaid'
  | 'i5-other-noncurrent-assets'
  | 'i6-research-development-expense'
  | 'j1-employee-compensation'
  | 'j2-defined-benefit-plan'
  | 'j3-share-based-payment'
  | 'k1-other-receivables'
  | 'k2-other-current-assets'
  | 'k3-other-payables'
  | 'k4-other-current-liabilities'
  | 'k5-provisions'
  | 'k6-held-for-sale'
  | 'k7-deferred-income'
  | 'k8-selling-expenses'
  | 'k9-admin-expenses'
  | 'k10-other-income'
  | 'k11-asset-impairment-loss'
  | 'k12-non-operating-income'
  | 'k13-non-operating-expense'
  | 'review-bundle'

/**
 * 上下文 props 策略：声明组件需要哪些上下文信息。
 * GtWpRenderer 根据此声明自动透传，新增 componentType 无需修改 if 链。
 *
 * - 'standard'  → { wp-id, project-id, wp-code, year }（绝大多数 HTML 组件）
 * - 'custom'    → { wp-generated, project-id, wp-code, year }（自定义/程序表）
 * - 'form-type' → { form-type: componentType }（D 子模式）
 * - 'none'      → {}（纯展示，无需额外上下文）
 */
// 条目类型单一真源：registry/types.ts。
// 此处只 re-export，避免单体与 entries/*.ts 各持一份定义 —— 两份定义会让
// componentType 一窄一宽（HtmlComponentType 联合 vs string），装配时类型不兼容。
export type { ContextPropsStrategy, HtmlRendererEntry } from './registry/types'
import type { ContextPropsStrategy, HtmlRendererEntry } from './registry/types'

// ─── 注册表（单一来源） ─────────────────────────────────────────────────────

// 条目本体在 ./registry/entries/*.ts（按渲染器家族分域，membership is the
// array itself）。本文件只装配 + 派生视图 + 工具函数，因此 20 个直接 import
// 单体的生产文件与 import barrel 的测试拿到的是**同一批 entry 对象**
// （registrySplitEquivalence.pbt.spec.ts 断言 component 引用 Object.is 同源）。
const REGISTRY_LIST: HtmlRendererEntry[] = [
  ...coreEntries,
  ...formsEntries,
  ...programsEntries,
  ...confirmationsEntries,
  ...reportsEntries,
  ...specializedEntries,
]

/**
 * 校验 componentType 唯一，重复立即 fail-closed。
 *
 * 在 HTML_RENDERER_REGISTRY 的 Map 构造之前调用：Map 对重复 key 是后写静默覆盖，
 * 不先断言的话重复注册会变成「悄悄只剩最后一个」而不是报错。
 */
export function assertUniqueRegistryComponentTypes(
  entries: Iterable<HtmlRendererEntry>,
): void {
  const seen = new Set<string>()
  for (const entry of entries) {
    if (seen.has(entry.componentType)) {
      throw new Error(`htmlRendererRegistry componentType 重复声明: ${entry.componentType}`)
    }
    seen.add(entry.componentType)
  }
}

/** 注册表 Map（O(1) 查找） */
assertUniqueRegistryComponentTypes(REGISTRY_LIST)
export const HTML_RENDERER_REGISTRY: ReadonlyMap<string, HtmlRendererEntry> =
  new Map(REGISTRY_LIST.map((e) => [e.componentType, e]))

/** placeholder 类型（univer/skip）的图标，渲染走 GtWpRenderer 内部 fallback */
export const PLACEHOLDER_ICONS: Readonly<Record<string, string>> = {
  univer: '📊',
  skip: '⏭️',
}

/**
 * HTML 类型集合（仅 registry 注册的真实组件，不含 skip placeholder）。
 * 用于 GtWpRenderer 判断是否需要 lazy 加载组件。
 */
export const HTML_COMPONENT_TYPE_SET: ReadonlySet<string> = new Set(
  REGISTRY_LIST.map((e) => e.componentType),
)

/**
 * GtWpRenderer 路由集合（含 skip / confirmation-hub placeholder）。
 * 与 useEditorMode.HTML_COMPONENT_TYPES 一致：判定底稿是否应走 GtWpRenderer 而非 Univer。
 *
 * 集合内但不在 registry 中的两个 placeholder：
 * - skip：由 GtWpRenderer 内部分支渲染 SkippedSheetPlaceholder。
 * - confirmation-hub：D0/E0/F0/G0/H0/K0/L0 函证枢纽的 **workbook 级** componentType。
 *   这些底稿是多 sheet 工作簿（底稿目录 / X0A 程序表 / X0-1 汇总 / X0-2~X0-8 各函证底稿），
 *   每个 sheet 自身的 componentType 都已在 registry 注册（confirmation-summary /
 *   confirmation-entity-verify / confirmation-followup / confirmation-diff-reconcile /
 *   confirmation-diff-checklist / confirmation-alternative-* / confirmation-reliability /
 *   confirmation-fraud-risk 等）。GtWpRenderer 按 **per-sheet** componentType 分发，
 *   workbook 级 confirmation-hub 只用于判定"走 HTML 渲染器而非 Univer"，
 *   因此无需（也不应）注册组件；函证管理中心台账由编辑器顶部入口按钮跳转承载。
 */
export const HTML_RENDERER_ROUTE_SET: ReadonlySet<string> = new Set([
  ...HTML_COMPONENT_TYPE_SET,
  'skip',
  'confirmation-hub',
])

// ─── 工具函数 ────────────────────────────────────────────────────────────────

export function isHtmlComponentType(ct: string): ct is HtmlComponentType {
  return HTML_COMPONENT_TYPE_SET.has(ct as HtmlComponentType)
}

export function getRendererEntry(ct: string): HtmlRendererEntry | undefined {
  return HTML_RENDERER_REGISTRY.get(ct as HtmlComponentType)
}

export function getSheetIcon(ct: string): string {
  return getRendererEntry(ct)?.icon ?? PLACEHOLDER_ICONS[ct] ?? '📄'
}

/**
 * 获取 componentType 的上下文 props 策略。
 * GtWpRenderer 使用此函数代替硬编码 if 链来构建子组件 props。
 */
export function getContextPropsStrategy(ct: string): ContextPropsStrategy {
  const entry = getRendererEntry(ct)
  return entry?.contextProps ?? 'none'
}
