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
import { defineAsyncComponent, type Component } from 'vue'

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
  | 'a11-bundle'
  | 'a15-bundle'
  | 'confirmation-summary'
  | 'confirmation-entity-verify'
  | 'confirmation-followup'
  | 'confirmation-diff-reconcile'
  | 'confirmation-alternative-d05'
  | 'confirmation-alternative-d06'
  | 'confirmation-diff-checklist'
  | 'confirmation-fraud-risk'
  | 'confirmation-reliability'

/**
 * 上下文 props 策略：声明组件需要哪些上下文信息。
 * GtWpRenderer 根据此声明自动透传，新增 componentType 无需修改 if 链。
 *
 * - 'standard'  → { wp-id, project-id, wp-code, year }（绝大多数 HTML 组件）
 * - 'custom'    → { wp-generated, project-id, wp-code, year }（自定义/程序表）
 * - 'form-type' → { form-type: componentType }（D 子模式）
 * - 'none'      → {}（纯展示，无需额外上下文）
 */
export type ContextPropsStrategy = 'standard' | 'custom' | 'form-type' | 'none'

/** 注册表条目：包含 lazy component / 图标 / emits / 描述 / 上下文 props 策略 */
export interface HtmlRendererEntry {
  /** 组件类型唯一标识 */
  componentType: HtmlComponentType
  /** lazy-loaded SFC */
  component: Component
  /** sheet tab 图标 */
  icon: string
  /** 中文名称（用于错误提示 / 文档） */
  label: string
  /** 子组件 emit 的事件列表（用于 GtWpRenderer 透传 + 测试断言） */
  emits: readonly string[]
  /**
   * 上下文 props 策略。GtWpRenderer 根据此字段自动构建 props，
   * 新增 componentType 只需设置此字段，无需修改 GtWpRenderer 的 if 链。
   * 默认 'none'（不传额外 props）。
   */
  contextProps?: ContextPropsStrategy
}

// ─── lazy components ────────────────────────────────────────────────────────

const GtA1Dashboard = defineAsyncComponent(() => import('./GtA1Dashboard.vue'))
const GtA2AdjustmentConsole = defineAsyncComponent(() => import('./GtA2AdjustmentConsole.vue'))
const GtA3ConsolidationConsole = defineAsyncComponent(() => import('./GtA3ConsolidationConsole.vue'))
const GtAProgramConsole = defineAsyncComponent(() => import('./GtAProgramConsole.vue'))
const GtBIndex = defineAsyncComponent(() => import('./GtBIndex.vue'))
const GtCNoteTable = defineAsyncComponent(() => import('./GtCNoteTable.vue'))
const GtDForm = defineAsyncComponent(() => import('./GtDForm/GtDForm.vue'))
const GtEControlTest = defineAsyncComponent(() => import('./GtEControlTest.vue'))
const GtHStaticDoc = defineAsyncComponent(() => import('./GtHStaticDoc.vue'))
const GtCustomWpEditor = defineAsyncComponent(() => import('./GtCustomWpEditor.vue'))
const GtAuditSheet = defineAsyncComponent(() => import('./GtAuditSheet.vue'))
const GtBadDebtSheet = defineAsyncComponent(() => import('./GtBadDebtSheet.vue'))
const GtCfVerification = defineAsyncComponent(() => import('./CashFlowVerification.vue'))
const GtProcedureTable = defineAsyncComponent(() => import('./ProcedureTableRenderer.vue'))
const GtReportAnalysis = defineAsyncComponent(() => import('./ReportAnalysisPanel.vue'))
const GtMisstatementSummary = defineAsyncComponent(() => import('./MisstatementSummaryView.vue'))
const GtReviewChecklist = defineAsyncComponent(() => import('./GtReviewChecklist.vue'))
const GtWordTemplate = defineAsyncComponent(() => import('./WorkpaperWordEditor.vue'))
const GtIndependenceSigning = defineAsyncComponent(() => import('./IndependenceSigning.vue'))
const GtWpPopupSigning = defineAsyncComponent(() => import('./WpPopupSigning.vue'))
const GtAuditLegend = defineAsyncComponent(() => import('./AuditLegendPanel.vue'))
const GtChecklistTable = defineAsyncComponent(() => import('./GtChecklistTable.vue'))
const GtAnalyticalReview = defineAsyncComponent(() => import('./GtAnalyticalReview.vue'))
const GtA17Summary = defineAsyncComponent(() => import('./GtA17Summary.vue'))
const GtKamWorkpaper = defineAsyncComponent(() => import('./GtKamWorkpaper.vue'))
const GtRegulatoryLetter = defineAsyncComponent(() => import('./GtRegulatoryLetter.vue'))
const GtGoodwillImpairment = defineAsyncComponent(() => import('./GtGoodwillImpairment.vue'))
const GtSegmentReport = defineAsyncComponent(() => import('./GtSegmentReport.vue'))
const GtContingentLiability = defineAsyncComponent(() => import('./GtContingentLiability.vue'))
const GtDiscontinuedOperations = defineAsyncComponent(() => import('./GtDiscontinuedOperations.vue'))
const GtMisstatementWorkpaper = defineAsyncComponent(() => import('./GtMisstatementWorkpaper.vue'))
const GtA14_3Workbook = defineAsyncComponent(() => import('./GtA14_3Workbook.vue'))
const GtA11Bundle = defineAsyncComponent(() => import('./GtA11Bundle.vue'))
const GtA15Bundle = defineAsyncComponent(() => import('./GtA15Bundle.vue'))
const GtConfirmationSummary = defineAsyncComponent(() => import('./confirmation/GtConfirmationSummary.vue'))
const GtConfirmationEntityVerify = defineAsyncComponent(() => import('./confirmation/entityVerify/GtConfirmationEntityVerify.vue'))
const GtConfirmationFollowup = defineAsyncComponent(() => import('./confirmation/followup/GtConfirmationFollowup.vue'))
const GtConfirmationDiffReconcile = defineAsyncComponent(() => import('./confirmation/diffReconcile/GtConfirmationDiffReconcile.vue'))
const GtConfirmationAlternativeD05 = defineAsyncComponent(() => import('./confirmation/alternativeD05/GtConfirmationAlternativeD05.vue'))
const GtConfirmationAlternativeD06 = defineAsyncComponent(() => import('./confirmation/alternativeD06/GtConfirmationAlternativeD06.vue'))
const GtConfirmationDiffChecklist = defineAsyncComponent(() => import('./confirmation/diffChecklist/GtConfirmationDiffChecklist.vue'))
const GtConfirmationFraudRisk = defineAsyncComponent(() => import('./confirmation/fraudRisk/GtConfirmationFraudRisk.vue'))
const GtConfirmationReliability = defineAsyncComponent(() => import('./confirmation/reliability/GtConfirmationReliability.vue'))

// ─── 注册表（单一来源） ─────────────────────────────────────────────────────

/** 5 个 D 子模式共享同一个 GtDForm 组件，通过 form-type prop 路由 */
const D_FORM_SUBTYPES = [
  'd-form-table',
  'd-form-paragraph',
  'd-form-qa',
  'd-form-confirmation',
  'd-form-review',
] as const

const REGISTRY_LIST: HtmlRendererEntry[] = [
  {
    componentType: 'a1-dashboard',
    component: GtA1Dashboard,
    icon: '🎯',
    label: 'A1 项目总控仪表盘',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'a2-adjustment-console',
    component: GtA2AdjustmentConsole,
    icon: '📝',
    label: 'A2 调整分录中控台',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'a3-consolidation-console',
    component: GtA3ConsolidationConsole,
    icon: '🔗',
    label: 'A3 合并流程中控台',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'a-program-console',
    component: GtAProgramConsole,
    icon: '📋',
    label: 'A 程序表中控台',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'b-index',
    component: GtBIndex,
    icon: '🗂️',
    label: 'B 底稿目录',
    emits: ['save'],
  },
  {
    componentType: 'c-note-table',
    component: GtCNoteTable,
    icon: '📝',
    label: 'C 附注披露嵌套表',
    emits: [
      'save',
      'subtable-toggle',
      'standard-switch',
      'sync-to-disclosure-notes',
      'jump-to-reference',
      'open-formula',
    ],
  },
  // D 子模式（5 种）共享 GtDForm，差异由 form-type prop 控制
  ...D_FORM_SUBTYPES.map<HtmlRendererEntry>((subtype) => ({
    componentType: subtype,
    component: GtDForm,
    icon: subtype === 'd-form-paragraph'
      ? '📄'
      : subtype === 'd-form-qa'
        ? '❓'
        : subtype === 'd-form-confirmation'
          ? '✉️'
          : subtype === 'd-form-review'
            ? '✍️'
            : '📑',
    label: `D 检查表 (${subtype.replace('d-form-', '')})`,
    emits: ['save'],
    contextProps: 'form-type' as const,
  })),
  {
    componentType: 'e-control-test',
    component: GtEControlTest,
    icon: '🧪',
    label: 'E 控制测试',
    emits: [
      'save',
      'trigger-procedure-trimming-suggestion',
      'conclusion-change',
      'step-advance',
    ],
    contextProps: 'standard',
  },
  {
    componentType: 'h-static-doc',
    component: GtHStaticDoc,
    icon: '📖',
    label: 'H 辅助说明',
    emits: [], // 只读
  },
  {
    componentType: 'custom',
    component: GtCustomWpEditor,
    icon: '📎',
    label: '自定义底稿',
    emits: ['save'],
    contextProps: 'custom',
  },
  {
    componentType: 'audit-sheet',
    component: GtAuditSheet,
    icon: '📊',
    label: '审定表',
    emits: ['save', 'field-change', 'open-formula', 'restore'],
    contextProps: 'standard',
  },
  {
    componentType: 'bad-debt-sheet',
    component: GtBadDebtSheet,
    icon: '💰',
    label: '坏账准备明细表',
    emits: [], // GtBadDebtSheet 自取数自落库，无 emit
    contextProps: 'standard',
  },
  {
    componentType: 'cf-verification',
    component: GtCfVerification,
    icon: '💧',
    label: '现金流量表核查',
    emits: [],
    contextProps: 'standard',
  },
  {
    componentType: 'procedure-table',
    component: GtProcedureTable,
    icon: '📋',
    label: '程序表',
    emits: ['save'],
    contextProps: 'custom',
  },
  {
    componentType: 'report-analysis',
    component: GtReportAnalysis,
    icon: '📈',
    label: '报表分析',
    emits: [],
    contextProps: 'standard',
  },
  {
    componentType: 'misstatement-summary',
    component: GtMisstatementSummary,
    icon: '⚠️',
    label: '错报汇总',
    emits: [],
    contextProps: 'standard',
  },
  {
    componentType: 'review-checklist',
    component: GtReviewChecklist,
    icon: '✍️',
    label: '复核面板',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'word-template',
    component: GtWordTemplate,
    icon: '📄',
    label: 'Word 模板编辑',
    emits: [],
    contextProps: 'standard',
  },
  {
    componentType: 'independence-signing',
    component: GtIndependenceSigning,
    icon: '✍️',
    label: '独立性签署',
    emits: [],
    contextProps: 'standard',
  },
  {
    componentType: 'wp-popup-signing',
    component: GtWpPopupSigning,
    icon: '✍️',
    label: '签字流转控制表',
    emits: ['save', 'completed'],
    contextProps: 'standard',
  },
  {
    componentType: 'audit-legend',
    component: GtAuditLegend,
    icon: '📋',
    label: '审计标识一览表',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'checklist-table',
    component: GtChecklistTable,
    icon: '✅',
    label: '核对表',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'analytical-review',
    component: GtAnalyticalReview,
    icon: '📊',
    label: '分析性复核',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'a17-summary',
    component: GtA17Summary,
    icon: '📋',
    label: 'A17 重大事项概要',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'kam-workpaper',
    component: GtKamWorkpaper,
    icon: '🔑',
    label: 'A17-2-1 关键审计事项',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'regulatory-letter',
    component: GtRegulatoryLetter,
    icon: '📮',
    label: 'A18-2 监管沟通函',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'goodwill-impairment',
    component: GtGoodwillImpairment,
    icon: '💎',
    label: '商誉减值测试',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'segment-report',
    component: GtSegmentReport,
    icon: '🏢',
    label: '经营分部',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'contingent-liability',
    component: GtContingentLiability,
    icon: '⚖️',
    label: '或有事项',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'discontinued-operations',
    component: GtDiscontinuedOperations,
    icon: '📉',
    label: '终止经营',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'misstatement-workpaper',
    component: GtMisstatementWorkpaper,
    icon: '⚠️',
    label: 'A13 错报套件',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'a14-3-workbook',
    component: GtA14_3Workbook,
    icon: '🖥️',
    label: 'A14-3 IT缺陷',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'a11-bundle',
    component: GtA11Bundle,
    icon: '📅',
    label: 'A11 期后事项套件',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'a15-bundle',
    component: GtA15Bundle,
    icon: '🔄',
    label: 'A15 持续经营套件',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'confirmation-summary',
    component: GtConfirmationSummary,
    icon: '✉️',
    label: '函证结果汇总表',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'confirmation-entity-verify',
    component: GtConfirmationEntityVerify,
    icon: '🔍',
    label: '核实被函证单位信息',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'confirmation-followup',
    component: GtConfirmationFollowup,
    icon: '📋',
    label: '跟函过程控制',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'confirmation-diff-reconcile',
    component: GtConfirmationDiffReconcile,
    icon: '⚖️',
    label: '函证差异调节表',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'confirmation-alternative-d05',
    component: GtConfirmationAlternativeD05,
    icon: '🔄',
    label: '替代程序(合同负债及销售)',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'confirmation-alternative-d06',
    component: GtConfirmationAlternativeD06,
    icon: '🔄',
    label: '替代程序(应收及销售)',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'confirmation-diff-checklist',
    component: GtConfirmationDiffChecklist,
    icon: '📊',
    label: '函证差异检查表',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'confirmation-fraud-risk',
    component: GtConfirmationFraudRisk,
    icon: '🚨',
    label: '舞弊风险评价表',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'confirmation-reliability',
    component: GtConfirmationReliability,
    icon: '🔐',
    label: '回函可靠性验证',
    emits: ['save'],
    contextProps: 'standard',
  },
]

/** 注册表 Map（O(1) 查找） */
export const HTML_RENDERER_REGISTRY: ReadonlyMap<HtmlComponentType, HtmlRendererEntry> =
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
export const HTML_COMPONENT_TYPE_SET: ReadonlySet<HtmlComponentType> = new Set(
  REGISTRY_LIST.map((e) => e.componentType),
)

/**
 * GtWpRenderer 路由集合（含 skip placeholder）。
 * 与 useEditorMode.HTML_COMPONENT_TYPES 一致：判定底稿是否应走 GtWpRenderer 而非 Univer。
 * skip 是占位符不在 registry 中，但仍由 GtWpRenderer 内部分支渲染 SkippedSheetPlaceholder。
 */
export const HTML_RENDERER_ROUTE_SET: ReadonlySet<string> = new Set([
  ...HTML_COMPONENT_TYPE_SET,
  'skip',
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
