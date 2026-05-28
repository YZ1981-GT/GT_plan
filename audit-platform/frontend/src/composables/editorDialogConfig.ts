/**
 * editorDialogConfig - WorkpaperEditor template dialog metadata [V3 Req 12.1.4]
 *
 * Centralized declaration of all cycle dialog metadata in WorkpaperEditor.vue,
 * providing observability for devtools and documentation navigation.
 *
 * NOTE: this is observational metadata and does NOT replace the existing
 * <XxxDialog> instantiations in WorkpaperEditor.vue (each has unique props).
 *
 * @example
 *   import { TEMPLATE_DIALOGS, getDialogsByCycle } from './editorDialogConfig'
 *   const fDialogs = getDialogsByCycle('F')
 */

export interface TemplateDialogConfig {
  key: string
  title: string
  componentPath: string
  triggers: string[]
  cycle: string
  dialogStateKey: string
  width?: string
  appendToBody?: boolean
  fullscreen?: boolean
}

/**
 * 17 dialog entries reconciled with WorkpaperEditor.vue (V3 Sprint 4 12.1.4).
 */
export const TEMPLATE_DIALOGS: TemplateDialogConfig[] = [
  // ----- F cycle (purchase / inventory) -----
  {
    key: 'inventoryStocktake',
    title: '存货监盘',
    componentPath: '@/components/workpaper/InventoryStocktakeDialog.vue',
    triggers: ['cycle:F', 'wp_code:F2-21~F2-26'],
    cycle: 'F',
    dialogStateKey: 'stocktake',
    width: '900px',
    appendToBody: true,
  },
  {
    key: 'inventoryImpairment',
    title: '跌价准备 AI 分析',
    componentPath: '@/components/workpaper/InventoryImpairmentDialog.vue',
    triggers: ['cycle:F', 'wp_code:F2-47~F2-49'],
    cycle: 'F',
    dialogStateKey: 'impairment',
    width: '800px',
    appendToBody: true,
  },
  // ----- H cycle (fixed assets / construction in progress) -----
  {
    key: 'fixedAssetStocktake',
    title: '固定资产监盘',
    componentPath: '@/components/workpaper/FixedAssetStocktakeDialog.vue',
    triggers: ['cycle:H', 'wp_code:H1-9~H1-14'],
    cycle: 'H',
    dialogStateKey: 'hStocktake',
    width: '900px',
    appendToBody: true,
  },
  {
    key: 'depreciationCalc',
    title: '折旧自动测算',
    componentPath: '@/components/workpaper/DepreciationCalcDialog.vue',
    triggers: ['cycle:H', 'wp_code:H1-12', 'wp_code:H3-7', 'wp_code:H5-12'],
    cycle: 'H',
    dialogStateKey: 'depreciationCalc',
    width: '900px',
    appendToBody: true,
  },
  {
    key: 'assetImpairment',
    title: '减值 DCF 分析',
    componentPath: '@/components/workpaper/AssetImpairmentDialog.vue',
    triggers: ['cycle:H', 'wp_code:H1-14'],
    cycle: 'H',
    dialogStateKey: 'assetImpairment',
    width: '900px',
    appendToBody: true,
  },
  // ----- I cycle (intangible / goodwill / R&D) -----
  {
    key: 'goodwillImpairment',
    title: '商誉减值 DCF 分析',
    componentPath: '@/components/workpaper/GoodwillImpairmentDialog.vue',
    triggers: ['cycle:I', 'wp_code:I3-6', 'wp_code:I3-7'],
    cycle: 'I',
    dialogStateKey: 'goodwillImpairment',
    width: '900px',
    appendToBody: true,
  },
  {
    key: 'capitalizationCheck',
    title: '资本化时点判断',
    componentPath: '@/components/workpaper/CapitalizationCheckDialog.vue',
    triggers: ['cycle:I', 'wp_code:I2-6'],
    cycle: 'I',
    dialogStateKey: 'capitalizationCheck',
    width: '800px',
    appendToBody: true,
  },
  {
    key: 'amortizationCalc',
    title: '摊销自动测算',
    componentPath: '@/components/workpaper/AmortizationCalcDialog.vue',
    triggers: ['cycle:I', 'wp_code:I1-10', 'wp_code:I1-11', 'wp_code:I4-6', 'wp_code:I4-7'],
    cycle: 'I',
    dialogStateKey: 'amortizationCalc',
    width: '900px',
    appendToBody: true,
  },
  // ----- G cycle (investments) -----
  {
    key: 'fairValueTest',
    title: '公允价值测试',
    componentPath: '@/components/workpaper/FairValueTestDialog.vue',
    triggers: ['cycle:G', 'wp_code:G1', 'wp_code:G6', 'wp_code:G8'],
    cycle: 'G',
    dialogStateKey: 'fairValueTest',
    width: '900px',
    appendToBody: true,
  },
  {
    key: 'eclCalc',
    title: 'ECL 三阶段计算',
    componentPath: '@/components/workpaper/ECLCalcDialog.vue',
    triggers: ['cycle:G', 'wp_code:G4', 'wp_code:G6'],
    cycle: 'G',
    dialogStateKey: 'eclCalc',
    width: '900px',
    appendToBody: true,
  },
  {
    key: 'classificationCheck',
    title: '金融资产分类辅助',
    componentPath: '@/components/workpaper/ClassificationCheckDialog.vue',
    triggers: ['cycle:G', 'wp_code:G1-8', 'wp_code:G1-10'],
    cycle: 'G',
    dialogStateKey: 'classificationCheck',
    width: '800px',
    appendToBody: true,
  },
  // ----- K cycle (admin) -----
  {
    key: 'expenseAnalysis',
    title: '费用分析',
    componentPath: '@/components/workpaper/ExpenseAnalysisDialog.vue',
    triggers: ['cycle:K', 'wp_code:K8', 'wp_code:K9'],
    cycle: 'K',
    dialogStateKey: 'expenseAnalysis',
    width: '900px',
    appendToBody: true,
  },
  {
    key: 'impairmentSummary',
    title: '跨循环减值汇总',
    componentPath: '@/components/workpaper/ImpairmentSummaryDialog.vue',
    triggers: ['cycle:K', 'wp_code:K11'],
    cycle: 'K',
    dialogStateKey: 'impairmentSummary',
    width: '900px',
    appendToBody: true,
  },
  // ----- L cycle (debt / financing) -----
  {
    key: 'interestCalc',
    title: '利息测算',
    componentPath: '@/components/workpaper/InterestCalcDialog.vue',
    triggers: ['cycle:L', 'wp_code:L1', 'wp_code:L3'],
    cycle: 'L',
    dialogStateKey: 'interestCalc',
    width: '800px',
    appendToBody: true,
  },
  {
    key: 'bondAmortization',
    title: '摊余成本测算',
    componentPath: '@/components/workpaper/BondAmortizationDialog.vue',
    triggers: ['cycle:L', 'wp_code:L5'],
    cycle: 'L',
    dialogStateKey: 'bondAmortization',
    width: '900px',
    appendToBody: true,
  },
  // ----- M cycle (equity) -----
  {
    key: 'equityMovement',
    title: '权益变动表',
    componentPath: '@/components/workpaper/EquityMovementDialog.vue',
    triggers: ['cycle:M', 'wp_code:M6'],
    cycle: 'M',
    dialogStateKey: 'equityMovement',
    width: '900px',
    appendToBody: true,
  },
  // ----- N cycle (taxes) -----
  {
    key: 'incomeTaxCalc',
    title: '所得税费用测算',
    componentPath: '@/components/workpaper/IncomeTaxCalcDialog.vue',
    triggers: ['cycle:N', 'wp_code:N5'],
    cycle: 'N',
    dialogStateKey: 'incomeTaxCalc',
    width: '900px',
    appendToBody: true,
  },
]


/** Find a dialog config by its unique key. */
export function getDialogByKey(key: string): TemplateDialogConfig | undefined {
  return TEMPLATE_DIALOGS.find((d) => d.key === key)
}

/** Filter dialog configs by cycle letter (case-insensitive). */
export function getDialogsByCycle(cycle: string): TemplateDialogConfig[] {
  if (!cycle) return []
  const target = cycle.toUpperCase()
  return TEMPLATE_DIALOGS.filter((d) => d.cycle === target)
}

/** Find the first dialog config whose triggers include the given string. */
export function getDialogByTrigger(trigger: string): TemplateDialogConfig | undefined {
  return TEMPLATE_DIALOGS.find((d) => d.triggers.includes(trigger))
}
