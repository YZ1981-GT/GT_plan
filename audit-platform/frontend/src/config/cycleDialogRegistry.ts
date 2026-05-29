/**
 * cycleDialogRegistry — 循环特定 Dialog 配置注册表
 *
 * 将 WorkpaperEditor.vue 中 15+ 个硬编码的 cycle dialog 抽取为配置驱动。
 * CycleDialogSlot 组件消费此注册表，根据 wp_code 匹配动态渲染 trigger 按钮 + 异步加载 dialog。
 *
 * 锚定 spec workpaper-editor-slimdown Sprint 2 Task 3.1
 */
export interface CycleDialogConfig {
  id: string                    // 唯一标识
  cycle: string                 // 循环代号 F/G/H/I/K/L/M/N
  wpCodePattern: RegExp         // wp_code 匹配正则（匹配 wpDetail.wp_code）
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  component: () => Promise<any> // 异步加载 dialog 组件（dynamic import .vue）
  triggerLabel: string          // 按钮文字
  triggerIcon: string           // emoji/icon
  triggerType: 'primary' | 'warning' | 'default'  // el-button type
  requiresSheet?: boolean       // 是否需要 activeSheetId（trigger 显示依赖 sheet 级匹配）
}

export const cycleDialogRegistry: CycleDialogConfig[] = [
  // ─── F 循环（采购存货）─────────────────────────────────────────────────────
  {
    id: 'f-stocktake',
    cycle: 'F',
    wpCodePattern: /^F2/i,
    component: () => import('@/components/workpaper/InventoryStocktakeDialog.vue'),
    triggerLabel: '开始监盘',
    triggerIcon: '📦',
    triggerType: 'primary',
    requiresSheet: true,
  },
  {
    id: 'f-impairment',
    cycle: 'F',
    wpCodePattern: /^F2/i,
    component: () => import('@/components/workpaper/InventoryImpairmentDialog.vue'),
    triggerLabel: 'AI 分析跌价',
    triggerIcon: '🤖',
    triggerType: 'warning',
    requiresSheet: true,
  },
  // ─── H 循环（固定资产+在建工程+使用权资产+租赁负债）─────────────────────────
  {
    id: 'h-stocktake',
    cycle: 'H',
    wpCodePattern: /^H\d/i,
    component: () => import('@/components/workpaper/FixedAssetStocktakeDialog.vue'),
    triggerLabel: '固定资产盘点',
    triggerIcon: '🏗️',
    triggerType: 'primary',
    requiresSheet: true,
  },
  {
    id: 'h-depreciation-calc',
    cycle: 'H',
    wpCodePattern: /^H\d/i,
    component: () => import('@/components/workpaper/DepreciationCalcDialog.vue'),
    triggerLabel: '自动计算',
    triggerIcon: '🧮',
    triggerType: 'primary',
    requiresSheet: true,
  },
  {
    id: 'h-asset-impairment',
    cycle: 'H',
    wpCodePattern: /^H\d/i,
    component: () => import('@/components/workpaper/AssetImpairmentDialog.vue'),
    triggerLabel: 'AI 辅助分析',
    triggerIcon: '🤖',
    triggerType: 'warning',
    requiresSheet: true,
  },
  // ─── I 循环（无形资产+商誉+开发支出）──────────────────────────────────────
  {
    id: 'i-goodwill-impairment',
    cycle: 'I',
    wpCodePattern: /^I3/i,
    component: () => import('@/components/workpaper/GoodwillImpairmentDialog.vue'),
    triggerLabel: 'AI 辅助分析',
    triggerIcon: '🤖',
    triggerType: 'warning',
    requiresSheet: true,
  },
  {
    id: 'i-capitalization-check',
    cycle: 'I',
    wpCodePattern: /^I2/i,
    component: () => import('@/components/workpaper/CapitalizationCheckDialog.vue'),
    triggerLabel: '资本化时点判断',
    triggerIcon: '🧮',
    triggerType: 'primary',
    requiresSheet: true,
  },
  {
    id: 'i-amortization-calc',
    cycle: 'I',
    wpCodePattern: /^I[14]/i,
    component: () => import('@/components/workpaper/AmortizationCalcDialog.vue'),
    triggerLabel: '自动计算',
    triggerIcon: '🧮',
    triggerType: 'primary',
    requiresSheet: true,
  },
  // ─── G 循环（投资）────────────────────────────────────────────────────────
  {
    id: 'g-fair-value-test',
    cycle: 'G',
    wpCodePattern: /^G([1-9]|1[0-4])(\b|-|$)/i,
    component: () => import('@/components/workpaper/FairValueTestDialog.vue'),
    triggerLabel: '公允价值测试',
    triggerIcon: '📊',
    triggerType: 'primary',
    requiresSheet: true,
  },
  {
    id: 'g-ecl-calc',
    cycle: 'G',
    wpCodePattern: /^G[46](\b|-|$|\d)/i,
    component: () => import('@/components/workpaper/ECLCalcDialog.vue'),
    triggerLabel: 'ECL 计算',
    triggerIcon: '🧮',
    triggerType: 'primary',
    requiresSheet: true,
  },
  {
    id: 'g-classification-check',
    cycle: 'G',
    wpCodePattern: /^G1(\b|-|$|\d)/i,
    component: () => import('@/components/workpaper/ClassificationCheckDialog.vue'),
    triggerLabel: '分类辅助',
    triggerIcon: '🏷️',
    triggerType: 'primary',
    requiresSheet: true,
  },
  // ─── K 循环（管理）────────────────────────────────────────────────────────
  {
    id: 'k-expense-analysis',
    cycle: 'K',
    wpCodePattern: /^K[89](\b|-|$|\d)/i,
    component: () => import('@/components/workpaper/ExpenseAnalysisDialog.vue'),
    triggerLabel: '费用分析',
    triggerIcon: '📊',
    triggerType: 'primary',
  },
  {
    id: 'k-impairment-summary',
    cycle: 'K',
    wpCodePattern: /^K11(\b|-|$|\d)/i,
    component: () => import('@/components/workpaper/ImpairmentSummaryDialog.vue'),
    triggerLabel: '减值汇总',
    triggerIcon: '📋',
    triggerType: 'primary',
  },
  // ─── L 循环（筹资）────────────────────────────────────────────────────────
  {
    id: 'l-interest-calc',
    cycle: 'L',
    wpCodePattern: /^L[13](\b|-|$|\d)/i,
    component: () => import('@/components/workpaper/InterestCalcDialog.vue'),
    triggerLabel: '利息测算',
    triggerIcon: '🧮',
    triggerType: 'primary',
  },
  {
    id: 'l-bond-amortization',
    cycle: 'L',
    wpCodePattern: /^L5(\b|-|$|\d)/i,
    component: () => import('@/components/workpaper/BondAmortizationDialog.vue'),
    triggerLabel: '摊余成本',
    triggerIcon: '📊',
    triggerType: 'primary',
  },
  // ─── M 循环（股东权益）────────────────────────────────────────────────────
  {
    id: 'm-equity-movement',
    cycle: 'M',
    wpCodePattern: /^M6(\b|-|$|\d)/i,
    component: () => import('@/components/workpaper/EquityMovementDialog.vue'),
    triggerLabel: '权益变动',
    triggerIcon: '📊',
    triggerType: 'primary',
  },
  // ─── N 循环（税费）────────────────────────────────────────────────────────
  {
    id: 'n-income-tax-calc',
    cycle: 'N',
    wpCodePattern: /^N5(\b|-|$|\d)/i,
    component: () => import('@/components/workpaper/IncomeTaxCalcDialog.vue'),
    triggerLabel: '所得税测算',
    triggerIcon: '🧮',
    triggerType: 'primary',
  },
]

/**
 * 根据 wp_code 查找匹配的 dialog 配置列表
 */
export function getMatchedDialogs(wpCode: string): CycleDialogConfig[] {
  if (!wpCode) return []
  const code = wpCode.toUpperCase()
  return cycleDialogRegistry.filter(config => config.wpCodePattern.test(code))
}
