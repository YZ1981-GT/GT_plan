/**
 * editorDialogConfig - WorkpaperEditor template dialog metadata [V3 Req 12.1.4]
 *
 * Centralized declaration of all cycle dialog metadata in WorkpaperEditor.vue,
 * providing observability for devtools and documentation navigation.
 *
 * Phase 2 扩展（workpaper-editor-shrink-phase2 §4.1）：
 * 新增 component / triggerButton / triggerVisible / propsFactory 字段，
 * 支持 CycleDialogHost 配置驱动渲染 + CycleTriggerPanel 配置驱动按钮。
 * 所有新增字段为 optional，既有消费方（devtools 枚举）不受影响。
 *
 * @example
 *   import { TEMPLATE_DIALOGS, getDialogsByCycle } from './editorDialogConfig'
 *   const fDialogs = getDialogsByCycle('F')
 */

import type { Component } from 'vue'
import type { WorkpaperDetail } from '@/services/workpaperApi'

/**
 * CycleDialogHost / CycleTriggerPanel 渲染时传入的上下文。
 * propsFactory 从此 context 派生每个 dialog 的 props。
 */
export interface DialogPropsContext {
  projectId: string
  wpId: string
  wpDetail: WorkpaperDetail
  sheetNavActiveId: string
}

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
  /** 组件 lazy import 工厂（CycleDialogHost 用） */
  component?: () => Promise<{ default: Component }>
  /** trigger 按钮配置（CycleTriggerPanel 用） */
  triggerButton?: {
    icon: string
    label: string
    type?: 'primary' | 'warning'
    plain?: boolean
  }
  /** trigger 可见性判断函数（接收 wp_code + sheetId） */
  triggerVisible?: (wpCode: string, sheetId: string) => boolean
  /** dialog props 工厂（从 context 派生 props） */
  propsFactory?: (ctx: DialogPropsContext) => Record<string, any>
}

/**
 * 17 dialog entries reconciled with WorkpaperEditor.vue (V3 Sprint 4 12.1.4).
 * Phase 2 扩展：每条 entry 补充 component + propsFactory，trigger entry 补充 triggerButton + triggerVisible。
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
    component: () => import('@/components/workpaper/InventoryStocktakeDialog.vue'),
    triggerButton: { icon: '📦', label: '开始监盘', type: 'primary', plain: true },
    triggerVisible: (wpCode: string) => /^F2-(2[1-6])(\b|-|$)/.test(wpCode.toUpperCase()),
    propsFactory: (ctx: DialogPropsContext) => ({
      projectId: ctx.projectId,
      wpId: ctx.wpId,
      wpCode: ctx.wpDetail.wp_code || '',
      stocktakeId: ctx.sheetNavActiveId,
    }),
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
    component: () => import('@/components/workpaper/InventoryImpairmentDialog.vue'),
    triggerButton: { icon: '🤖', label: 'AI 分析跌价', type: 'warning', plain: true },
    triggerVisible: (wpCode: string) => /^F2-4[7-9](\b|-|$)/.test(wpCode.toUpperCase()),
    propsFactory: (ctx: DialogPropsContext) => ({
      projectId: ctx.projectId,
      wpId: ctx.wpId,
      targetSheet: ctx.sheetNavActiveId,
    }),
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
    component: () => import('@/components/workpaper/FixedAssetStocktakeDialog.vue'),
    triggerButton: { icon: '🏗️', label: '固定资产盘点', type: 'primary', plain: true },
    triggerVisible: (wpCode: string) => /^H1-(9|1[0-4])(\b|-|$)/.test(wpCode.toUpperCase()),
    propsFactory: (ctx: DialogPropsContext) => ({
      projectId: ctx.projectId,
      wpId: ctx.wpId,
      wpCode: ctx.wpDetail.wp_code || '',
      stocktakeId: ctx.sheetNavActiveId,
    }),
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
    component: () => import('@/components/workpaper/DepreciationCalcDialog.vue'),
    triggerButton: { icon: '🧮', label: '自动计算', type: 'primary', plain: true },
    triggerVisible: (wpCode: string) =>
      /^H1-12(\b|-|$)/.test(wpCode.toUpperCase()) ||
      /^H3-7(\b|-|$)/.test(wpCode.toUpperCase()) ||
      /^H5-12(\b|-|$)/.test(wpCode.toUpperCase()),
    propsFactory: (ctx: DialogPropsContext) => ({
      projectId: ctx.projectId,
      wpId: ctx.wpId,
      targetSheet: ctx.sheetNavActiveId,
    }),
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
    component: () => import('@/components/workpaper/AssetImpairmentDialog.vue'),
    triggerButton: { icon: '🤖', label: 'AI 辅助分析', type: 'warning', plain: true },
    triggerVisible: (wpCode: string) => /^H1-14(\b|-|$)/.test(wpCode.toUpperCase()),
    propsFactory: (ctx: DialogPropsContext) => ({
      projectId: ctx.projectId,
      wpId: ctx.wpId,
      targetSheet: ctx.sheetNavActiveId,
    }),
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
    component: () => import('@/components/workpaper/GoodwillImpairmentDialog.vue'),
    triggerButton: { icon: '🤖', label: 'AI 辅助分析', type: 'warning', plain: true },
    triggerVisible: (wpCode: string) => /^I3-[67](\b|-|$)/.test(wpCode.toUpperCase()),
    propsFactory: (ctx: DialogPropsContext) => ({
      projectId: ctx.projectId,
      wpId: ctx.wpId,
      targetSheet: ctx.sheetNavActiveId,
    }),
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
    component: () => import('@/components/workpaper/CapitalizationCheckDialog.vue'),
    triggerButton: { icon: '🧮', label: '资本化时点判断', type: 'primary', plain: true },
    triggerVisible: (wpCode: string) => /^I2-6(\b|-|$)/.test(wpCode.toUpperCase()),
    propsFactory: (ctx: DialogPropsContext) => ({
      projectId: ctx.projectId,
      wpId: ctx.wpId,
      targetSheet: ctx.sheetNavActiveId,
    }),
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
    component: () => import('@/components/workpaper/AmortizationCalcDialog.vue'),
    triggerButton: { icon: '🧮', label: '自动计算', type: 'primary', plain: true },
    triggerVisible: (wpCode: string) =>
      /^I1-1[01](\b|-|$)/.test(wpCode.toUpperCase()) ||
      /^I4-[67](\b|-|$)/.test(wpCode.toUpperCase()),
    propsFactory: (ctx: DialogPropsContext) => ({
      projectId: ctx.projectId,
      wpId: ctx.wpId,
      targetSheet: ctx.sheetNavActiveId,
    }),
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
    component: () => import('@/components/workpaper/FairValueTestDialog.vue'),
    triggerButton: { icon: '📊', label: '公允价值测试', type: 'primary', plain: true },
    triggerVisible: (wpCode: string) =>
      /^G1(\b|-|$|\d)/.test(wpCode.toUpperCase()) ||
      /^G6(\b|-|$|\d)/.test(wpCode.toUpperCase()) ||
      /^G8(\b|-|$|\d)/.test(wpCode.toUpperCase()),
    propsFactory: (ctx: DialogPropsContext) => ({
      projectId: ctx.projectId,
      wpId: ctx.wpId,
      targetSheet: ctx.sheetNavActiveId,
    }),
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
    component: () => import('@/components/workpaper/ECLCalcDialog.vue'),
    triggerButton: { icon: '🧮', label: 'ECL 计算', type: 'primary', plain: true },
    triggerVisible: (wpCode: string) =>
      /^G4(\b|-|$|\d)/.test(wpCode.toUpperCase()) ||
      /^G6(\b|-|$|\d)/.test(wpCode.toUpperCase()),
    propsFactory: (ctx: DialogPropsContext) => ({
      projectId: ctx.projectId,
      wpId: ctx.wpId,
      targetSheet: ctx.sheetNavActiveId,
    }),
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
    component: () => import('@/components/workpaper/ClassificationCheckDialog.vue'),
    triggerButton: { icon: '🏷️', label: '分类辅助', type: 'primary', plain: true },
    triggerVisible: (wpCode: string) =>
      /^G1-8(\b|-|$)/.test(wpCode.toUpperCase()) ||
      /^G1-10(\b|-|$)/.test(wpCode.toUpperCase()),
    propsFactory: (ctx: DialogPropsContext) => ({
      projectId: ctx.projectId,
      wpId: ctx.wpId,
      targetSheet: ctx.sheetNavActiveId,
    }),
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
    component: () => import('@/components/workpaper/ExpenseAnalysisDialog.vue'),
    triggerButton: { icon: '📊', label: '费用分析', type: 'primary', plain: true },
    triggerVisible: (wpCode: string) => /^K[89](\b|-|$|\d)/.test(wpCode.toUpperCase()),
    propsFactory: (ctx: DialogPropsContext) => ({
      projectId: ctx.projectId,
      wpId: ctx.wpId,
      targetSheet: ctx.sheetNavActiveId,
    }),
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
    component: () => import('@/components/workpaper/ImpairmentSummaryDialog.vue'),
    triggerButton: { icon: '📋', label: '减值汇总', type: 'primary', plain: true },
    triggerVisible: (wpCode: string) => /^K11(\b|-|$|\d)/.test(wpCode.toUpperCase()),
    propsFactory: (ctx: DialogPropsContext) => ({
      projectId: ctx.projectId,
      wpId: ctx.wpId,
      targetSheet: ctx.sheetNavActiveId,
    }),
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
    component: () => import('@/components/workpaper/InterestCalcDialog.vue'),
    triggerButton: { icon: '🧮', label: '利息测算', type: 'primary', plain: true },
    triggerVisible: (wpCode: string) => /^L[13](\b|-|$|\d)/.test(wpCode.toUpperCase()),
    propsFactory: (ctx: DialogPropsContext) => ({
      projectId: ctx.projectId,
      workpaperId: ctx.wpId,
      wpCode: (ctx.wpDetail.wp_code || 'L1').startsWith('L3') ? 'L3' : 'L1',
      targetSheet: ctx.sheetNavActiveId,
    }),
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
    component: () => import('@/components/workpaper/BondAmortizationDialog.vue'),
    triggerButton: { icon: '📊', label: '摊余成本', type: 'primary', plain: true },
    triggerVisible: (wpCode: string) => /^L5(\b|-|$|\d)/.test(wpCode.toUpperCase()),
    propsFactory: (ctx: DialogPropsContext) => ({
      projectId: ctx.projectId,
      workpaperId: ctx.wpId,
      targetSheet: ctx.sheetNavActiveId,
    }),
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
    component: () => import('@/components/workpaper/EquityMovementDialog.vue'),
    triggerButton: { icon: '📊', label: '权益变动', type: 'primary', plain: true },
    triggerVisible: (wpCode: string) => /^M6(\b|-|$|\d)/.test(wpCode.toUpperCase()),
    propsFactory: (ctx: DialogPropsContext) => ({
      projectId: ctx.projectId,
      wpId: ctx.wpId,
      targetSheet: ctx.sheetNavActiveId,
    }),
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
    component: () => import('@/components/workpaper/IncomeTaxCalcDialog.vue'),
    triggerButton: { icon: '🧮', label: '所得税测算', type: 'primary', plain: true },
    triggerVisible: (wpCode: string) => /^N5(\b|-|$|\d)/.test(wpCode.toUpperCase()),
    propsFactory: (ctx: DialogPropsContext) => ({
      projectId: ctx.projectId,
      wpId: ctx.wpId,
      targetSheet: ctx.sheetNavActiveId,
    }),
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
