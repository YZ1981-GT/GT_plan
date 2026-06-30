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
  | 'confirmation-diff-checklist'
  | 'confirmation-fraud-risk'
  | 'confirmation-reliability'
  | 'b50-risk-assessment'
  | 'b22a-control-matrix'
  | 'b22b-deficiency-evaluation'
  | 'b23-process-control'
  | 'b30-group-audit'
  | 'b2-bundle'
  | 'b13-bundle'
  | 'b19-bundle'
  | 'b51-bundle'
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
  | 'd4-operating-revenue'
  | 'd3-prepaid-accounts'
  | 'd5-receivables-financing'
  | 'd6-contract-assets'
  | 'd7-contract-liabilities'
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
const GtA111SigningForm = defineAsyncComponent(() => import('./GtA111SigningForm.vue'))
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
const GtA10Bundle = defineAsyncComponent(() => import('./GtA10Bundle.vue'))
const GtA11Bundle = defineAsyncComponent(() => import('./GtA11Bundle.vue'))
const GtA12Bundle = defineAsyncComponent(() => import('./GtA12Bundle.vue'))
const GtA15Bundle = defineAsyncComponent(() => import('./GtA15Bundle.vue'))
const GtA16Bundle = defineAsyncComponent(() => import('./GtA16Bundle.vue'))
const GtA17Bundle = defineAsyncComponent(() => import('./GtA17Bundle.vue'))
const GtConfirmationSummary = defineAsyncComponent(() => import('./confirmation/GtConfirmationSummary.vue'))
const GtConfirmationEntityVerify = defineAsyncComponent(() => import('./confirmation/entityVerify/GtConfirmationEntityVerify.vue'))
const GtConfirmationFollowup = defineAsyncComponent(() => import('./confirmation/followup/GtConfirmationFollowup.vue'))
const GtConfirmationDiffReconcile = defineAsyncComponent(() => import('./confirmation/diffReconcile/GtConfirmationDiffReconcile.vue'))
const GtConfirmationAlternativeD05 = defineAsyncComponent(() => import('./confirmation/alternativeD05/GtConfirmationAlternativeD05.vue'))
const GtConfirmationAlternativeD06 = defineAsyncComponent(() => import('./confirmation/alternativeD06/GtConfirmationAlternativeD06.vue'))
const GtConfirmationDiffChecklist = defineAsyncComponent(() => import('./confirmation/diffChecklist/GtConfirmationDiffChecklist.vue'))
const GtConfirmationFraudRisk = defineAsyncComponent(() => import('./confirmation/fraudRisk/GtConfirmationFraudRisk.vue'))
const GtConfirmationReliability = defineAsyncComponent(() => import('./confirmation/reliability/GtConfirmationReliability.vue'))
const GtB50RiskAssessment = defineAsyncComponent(() => import('./GtB50RiskAssessment.vue'))
const GtB22AControlMatrix = defineAsyncComponent(() => import('./GtB22AControlMatrix.vue'))
const GtB22BDeficiencyEvaluation = defineAsyncComponent(() => import('./GtB22BDeficiencyEvaluation.vue'))
const GtCControlTest = defineAsyncComponent(() => import('./GtCControlTest.vue'))
const GtB23ProcessControl = defineAsyncComponent(() => import('./GtB23ProcessControl.vue'))
const GtB30GroupAudit = defineAsyncComponent(() => import('./GtB30GroupAudit.vue'))
const GtB2Bundle = defineAsyncComponent(() => import('./GtB2Bundle.vue'))
const GtB13Bundle = defineAsyncComponent(() => import('./GtB13Bundle.vue'))
const GtB19Bundle = defineAsyncComponent(() => import('./GtB19Bundle.vue'))
const GtB51Bundle = defineAsyncComponent(() => import('./GtB51Bundle.vue'))
const GtF2StocktakeBundle = defineAsyncComponent(() => import('./GtF2StocktakeBundle.vue'))
const GtReviewBundle = defineAsyncComponent(() => import('./GtReviewBundle.vue'))
const GtD1NotesReceivable = defineAsyncComponent(() => import('./GtD1NotesReceivable.vue'))
const GtD2AccountsReceivable = defineAsyncComponent(() => import('./GtD2AccountsReceivable.vue'))
const GtA112DualChecklist = defineAsyncComponent(() => import('./GtA112DualChecklist.vue'))
const GtA115DisclosureChecklist = defineAsyncComponent(() => import('./GtA115DisclosureChecklist.vue'))

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
    componentType: 'a1-11-signing-form',
    component: GtA111SigningForm,
    icon: '✍️',
    label: 'A1-11 签发流转控制表',
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
    componentType: 'a10-bundle',
    component: GtA10Bundle,
    icon: '📋',
    label: 'A10 前期审计程序',
    emits: [],
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
    componentType: 'a12-bundle',
    component: GtA12Bundle,
    icon: '📋',
    label: 'A12 期初余额审计',
    emits: [],
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
    componentType: 'a16-bundle',
    component: GtA16Bundle,
    icon: '📜',
    label: 'A16 管理层声明书',
    emits: [],
    contextProps: 'standard',
  },
  {
    componentType: 'a17-bundle',
    component: GtA17Bundle,
    icon: '📋',
    label: 'A17 审计总结聚合',
    emits: [],
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
  {
    componentType: 'c-control-test',
    component: GtCControlTest,
    icon: '🧪',
    label: 'C 控制测试',
    emits: ['save', 'completed'],
    contextProps: 'standard',
  },
  {
    componentType: 'd1-notes-receivable',
    component: GtD1NotesReceivable,
    icon: '📄',
    label: 'D1 应收票据',
    emits: ['save', 'completed'],
    contextProps: 'standard',
  },
  {
    componentType: 'd2-accounts-receivable',
    component: GtD2AccountsReceivable,
    icon: '💰',
    label: 'D2 应收账款',
    emits: ['save', 'completed'],
    contextProps: 'standard',
  },
  {
    componentType: 'b50-risk-assessment',
    component: GtB50RiskAssessment,
    icon: '🎯',
    label: 'B50 重大错报风险评估',
    emits: ['save', 'completed'],
    contextProps: 'standard',
  },
  {
    componentType: 'b22a-control-matrix',
    component: GtB22AControlMatrix,
    icon: '🛡️',
    label: 'B22A 内部控制了解程序表',
    emits: ['save', 'completed'],
    contextProps: 'standard',
  },
  {
    componentType: 'b22b-deficiency-evaluation',
    component: GtB22BDeficiencyEvaluation,
    icon: '⚠️',
    label: 'B22B 内部控制缺陷评价表',
    emits: ['save', 'completed'],
    contextProps: 'standard',
  },
  {
    componentType: 'b23-process-control',
    component: GtB23ProcessControl,
    icon: '🔄',
    label: 'B23 业务流程与控制了解表',
    emits: ['save', 'completed'],
    contextProps: 'standard',
  },
  {
    componentType: 'b30-group-audit',
    component: GtB30GroupAudit,
    icon: '🏢',
    label: 'B30 集团审计范围确定',
    emits: ['save', 'completed'],
    contextProps: 'standard',
  },
  {
    componentType: 'b2-bundle',
    component: GtB2Bundle,
    icon: '📋',
    label: 'B2 业务承接程序',
    emits: [],
    contextProps: 'standard',
  },
  {
    componentType: 'b13-bundle',
    component: GtB13Bundle,
    icon: '📋',
    label: 'B13 初步分析性程序',
    emits: [],
    contextProps: 'standard',
  },
  {
    componentType: 'b19-bundle',
    component: GtB19Bundle,
    icon: '📋',
    label: 'B19 审计工作方案',
    emits: [],
    contextProps: 'standard',
  },
  {
    componentType: 'b51-bundle',
    component: GtB51Bundle,
    icon: '📋',
    label: 'B51 舞弊风险识别',
    emits: [],
    contextProps: 'standard',
  },
  {
    componentType: 'f2-stocktake-bundle',
    component: GtF2StocktakeBundle,
    icon: '📦',
    label: 'F2 存货监盘',
    emits: [],
    contextProps: 'standard',
  },
  {
    componentType: 'a1-12-dual-checklist',
    component: GtA112DualChecklist,
    icon: '✅',
    label: 'A1-12 重大事项决定程序核查表',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'a1-15-disclosure-checklist',
    component: GtA115DisclosureChecklist,
    icon: '📋',
    label: 'A1-15 企业会计准则财务报表列报及披露核对表',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'a1-17-corresponding-data',
    component: defineAsyncComponent(() => import('./GtA117CorrespondingData.vue')),
    icon: '📊',
    label: 'A1-17 对应数据程序表',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'a17-6-closing-meeting',
    component: defineAsyncComponent(() => import('./GtA176ClosingMeeting.vue')),
    icon: '📋',
    label: 'A17-6 总结会会议纪要',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'a18-1-regulatory-submission',
    component: defineAsyncComponent(() => import('./GtA181RegulatorySubmission.vue')),
    icon: '📨',
    label: 'A18-1 向监管部门报送审计小结',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'a18-2-regulatory-communication',
    component: defineAsyncComponent(() => import('./GtA182RegulatoryCommunication.vue')),
    icon: '📮',
    label: 'A18-2 与监管层沟通函',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'a8-1-other-info-representation',
    component: defineAsyncComponent(() => import('./GtA81OtherInfoRepresentation.vue')),
    icon: '📋',
    label: 'A8-1 管理层对其他信息的书面声明',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'a11-1-subsequent-events-inquiry',
    component: defineAsyncComponent(() => import('./GtA111SubsequentEventsInquiry.vue')),
    icon: '📅',
    label: 'A11-1 期后事项问询函',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'a17-3-consultation-record',
    component: defineAsyncComponent(() => import('./GtA173ConsultationRecord.vue')),
    icon: '📋',
    label: 'A17-3 业务咨询记录',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'a17-3-1-consultation-execution',
    component: defineAsyncComponent(() => import('./GtA1731ConsultationExecution.vue')),
    icon: '📋',
    label: 'A17-3-1 咨询结果执行',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'a17-4-disagreement-record',
    component: defineAsyncComponent(() => import('./GtA174DisagreementRecord.vue')),
    icon: '📋',
    label: 'A17-4 重大专业分歧事项记录',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'a17-7-independence-declaration',
    component: defineAsyncComponent(() => import('./GtA177IndependenceDeclaration.vue')),
    icon: '✍️',
    label: 'A17-7 独立性声明书',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'a9-1-deficiency-letter',
    component: defineAsyncComponent(() => import('./GtA91DeficiencyLetter.vue')),
    icon: '📋',
    label: 'A9-1 内控缺陷沟通函',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'a9-2-deficiency-letter-governance',
    component: defineAsyncComponent(() => import('./GtA91DeficiencyLetter.vue')),
    icon: '📋',
    label: 'A9-2 治理层内控缺陷沟通函',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'a27-1-it-audit-memo',
    component: defineAsyncComponent(() => import('./GtA271ItAuditMemo.vue')),
    icon: '💻',
    label: 'A27-1 IT审计总结备忘录',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'a12-1-legal-confirmation',
    component: defineAsyncComponent(() => import('./GtA121LegalConfirmation.vue')),
    icon: '⚖️',
    label: 'A12-1 法律事务确认函',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'a10-1-governance-communication',
    component: defineAsyncComponent(() => import('./GtA101GovernanceCommunication.vue')),
    icon: '📋',
    label: 'A10-1 与治理层沟通函',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'a17-1-audit-summary',
    component: defineAsyncComponent(() => import('./GtA171AuditSummary.vue')),
    icon: '📋',
    label: 'A17-1 重大事项概要汇总',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'a17-2-1-kam',
    component: defineAsyncComponent(() => import('./GtA1721Kam.vue')),
    icon: '🔑',
    label: 'A17-2-1 关键审计事项',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'a5-1-cashflow-audit',
    component: defineAsyncComponent(() => import('./GtA51CashflowAudit.vue')),
    icon: '💰',
    label: 'A5-1 现金流量表审计',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'a3-8-goodwill-impairment',
    component: defineAsyncComponent(() => import('./GtA38GoodwillImpairment.vue')),
    icon: '💠',
    label: 'A3-8 商誉减值测试',
    emits: ['save', 'jump-to-workpaper'],
    contextProps: 'standard',
  },
  {
    componentType: 'b1-4-due-diligence-report',
    component: defineAsyncComponent(() => import('./GtB14DueDiligenceReport.vue')),
    icon: '📋',
    label: 'B1-4 尽职调查报告',
    emits: ['save'],
    contextProps: 'standard',
  },
  {
    componentType: 'd4-operating-revenue',
    component: defineAsyncComponent(() => import('./GtD4OperatingRevenue.vue')),
    icon: '💹',
    label: 'D4 营业收入',
    emits: ['save', 'completed'],
    contextProps: 'standard',
  },
  {
    componentType: 'd3-prepaid-accounts',
    component: defineAsyncComponent(() => import('./GtD3PrepaidAccounts.vue')),
    icon: '💰',
    label: 'D3 预收账款',
    emits: ['save', 'completed'],
    contextProps: 'standard',
  },
  {
    componentType: 'd5-receivables-financing',
    component: defineAsyncComponent(() => import('./GtD5ReceivablesFinancing.vue')),
    icon: '📈',
    label: 'D5 应收款项融资',
    emits: ['save', 'completed'],
    contextProps: 'standard',
  },
  {
    componentType: 'd6-contract-assets',
    component: defineAsyncComponent(() => import('./GtD6ContractAssets.vue')),
    icon: '📋',
    label: 'D6 合同资产',
    emits: ['save', 'completed'],
    contextProps: 'standard',
  },
  {
    componentType: 'd7-contract-liabilities',
    component: defineAsyncComponent(() => import('./GtD7ContractLiabilities.vue')),
    icon: '📋',
    label: 'D7 合同负债',
    emits: ['save', 'completed'],
    contextProps: 'standard',
  },
  {
    componentType: 'review-bundle',
    component: GtReviewBundle,
    icon: '✍️',
    label: '角色复核聚合',
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
