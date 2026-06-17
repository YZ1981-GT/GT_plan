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
  | 'audit-legend'
  | 'checklist-table'
  | 'analytical-review'

/** 注册表条目：包含 lazy component / 图标 / emits / 描述 */
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
const GtReviewChecklist = defineAsyncComponent(() => import('./ReviewChecklistPanel.vue'))
const GtWordTemplate = defineAsyncComponent(() => import('./WorkpaperWordEditor.vue'))
const GtIndependenceSigning = defineAsyncComponent(() => import('./IndependenceSigning.vue'))
const GtAuditLegend = defineAsyncComponent(() => import('./AuditLegendPanel.vue'))
const GtChecklistTable = defineAsyncComponent(() => import('./GtChecklistTable.vue'))
const GtAnalyticalReview = defineAsyncComponent(() => import('./GtAnalyticalReview.vue'))

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
  },
  {
    componentType: 'a2-adjustment-console',
    component: GtA2AdjustmentConsole,
    icon: '📝',
    label: 'A2 调整分录中控台',
    emits: ['save'],
  },
  {
    componentType: 'a3-consolidation-console',
    component: GtA3ConsolidationConsole,
    icon: '🔗',
    label: 'A3 合并流程中控台',
    emits: ['save'],
  },
  {
    componentType: 'a-program-console',
    component: GtAProgramConsole,
    icon: '📋',
    label: 'A 程序表中控台',
    emits: ['save'],
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
  },
  {
    componentType: 'audit-sheet',
    component: GtAuditSheet,
    icon: '📊',
    label: '审定表',
    emits: ['save', 'field-change', 'open-formula', 'restore'],
  },
  {
    componentType: 'bad-debt-sheet',
    component: GtBadDebtSheet,
    icon: '💰',
    label: '坏账准备明细表',
    emits: [], // GtBadDebtSheet 自取数自落库，无 emit
  },
  {
    componentType: 'cf-verification',
    component: GtCfVerification,
    icon: '💧',
    label: '现金流量表核查',
    emits: [],
  },
  {
    componentType: 'procedure-table',
    component: GtProcedureTable,
    icon: '📋',
    label: '程序表',
    emits: ['save'],
  },
  {
    componentType: 'report-analysis',
    component: GtReportAnalysis,
    icon: '📈',
    label: '报表分析',
    emits: [],
  },
  {
    componentType: 'misstatement-summary',
    component: GtMisstatementSummary,
    icon: '⚠️',
    label: '错报汇总',
    emits: [],
  },
  {
    componentType: 'review-checklist',
    component: GtReviewChecklist,
    icon: '✍️',
    label: '复核面板',
    emits: ['save'],
  },
  {
    componentType: 'word-template',
    component: GtWordTemplate,
    icon: '📄',
    label: 'Word 模板编辑',
    emits: [],
  },
  {
    componentType: 'independence-signing',
    component: GtIndependenceSigning,
    icon: '✍️',
    label: '独立性签署',
    emits: [],
  },
  {
    componentType: 'audit-legend',
    component: GtAuditLegend,
    icon: '📋',
    label: '审计标识一览表',
    emits: ['save'],
  },
  {
    componentType: 'checklist-table',
    component: GtChecklistTable,
    icon: '✅',
    label: '核对表',
    emits: ['save'],
  },
  {
    componentType: 'analytical-review',
    component: GtAnalyticalReview,
    icon: '📊',
    label: '分析性复核',
    emits: ['save'],
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
