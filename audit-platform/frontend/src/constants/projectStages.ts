/**
 * 项目环节（税审取数链）—— 单一真源，按分组组织。
 *
 * 消费方：
 * - `layouts/ThreeColumnLayout.vue` 左侧项目导航（分组标题 + 带图标的条目）
 * - `views/ProjectEntryHome.vue` 落地页中央的流程提示文案
 *
 * 🔴 分组顺序即业务取数链顺序（导入 → 试算/报表 → 底稿 → 报告），
 *    改顺序等于改流程提示，两个消费方会同时变。
 *
 * 🔴 `routeName` 必须是 `router/domains/*` 里真实存在的路由名。
 *    没有对应页面的条目一律 `pending: true`（渲染成灰色不可点 + tooltip 说明），
 *    **不许指向不存在的路径** —— 那样点了就是白屏/404。
 */
import type { Component } from 'vue'
import {
  Upload, Search, Grid, EditPen, Document, DataAnalysis,
  Notebook, Connection, Tickets, Finished,
} from '@element-plus/icons-vue'

export interface ProjectStage {
  /** 稳定 key（高亮匹配、测试锚点用，不随文案变） */
  key: string
  /** 侧栏标签 */
  label: string
  /** 流程提示里的短标签（侧栏标签过长时用，缺省回落 label） */
  shortLabel?: string
  icon: Component
  /** 目标路由名（`projects/:projectId/...` 下的具名路由） */
  routeName?: string
  /**
   * 附带的 query（可选）。用于「同一页面的不同页签」—— 如「报表分析」= Reports + `tab=report_analysis`。
   * 🔴 有 query 的条目在高亮判定里优先于同路由的无 query 条目，否则两项会同时高亮。
   */
  query?: Readonly<Record<string, string>>
  /**
   * 尚无对应页面：渲染为灰色不可点。
   * 🔴 与「没填 routeName」严格等价 —— 两者必须同时成立，守卫会校验。
   */
  pending?: boolean
  /** pending 条目的说明（tooltip），讲清缺什么 */
  pendingReason?: string
}

export interface ProjectStageGroup {
  key: string
  /** 分组标题（侧栏上方的灰色小字） */
  title: string
  items: readonly ProjectStage[]
}

export const PROJECT_STAGE_GROUPS: readonly ProjectStageGroup[] = [
  {
    key: 'data',
    title: '数据导入与账务查询',
    items: [
      { key: 'ledger-import', label: '数据导入', icon: Upload, routeName: 'LedgerImport' },
      { key: 'ledger-query', label: '账务查询', icon: Search, routeName: 'LedgerPenetration' },
    ],
  },
  {
    key: 'trial-report',
    title: '试算平衡与报表',
    items: [
      { key: 'trial-balance', label: '试算平衡表', icon: Grid, routeName: 'TrialBalance' },
      { key: 'adjustments', label: '调整分录', icon: EditPen, routeName: 'Adjustments' },
      { key: 'reports', label: '审定报表', icon: Document, routeName: 'Reports' },
      // 「报表分析」是 ReportView 里的 report_analysis 页签，不是独立路由。
      // ReportView 进入时读 `?tab=`（白名单校验）初始化页签；已在本页时由菜单发
      // `report:switch-tab` 事件原地切（见 ThreeColumnLayout.onProjectStageClick）。
      {
        key: 'report-analysis',
        label: '报表分析',
        icon: DataAnalysis,
        routeName: 'Reports',
        query: { tab: 'report_analysis' },
      },
    ],
  },
  {
    key: 'workpaper',
    title: '税审底稿',
    items: [
      { key: 'wp-mapping', label: '底稿映射', icon: Connection, routeName: 'AccountMapping' },
      // 点击时布局层另外弹出二级栏「底稿目录」（TaxWorkpaperSubnav），见 TAX_WORKPAPER_STAGE_KEY
      { key: 'workpapers', label: '税审底稿', icon: Notebook, routeName: 'TaxWorkpapers' },
    ],
  },
  {
    key: 'report',
    title: '鉴证报告',
    items: [
      // 页面已就位（占位页 TaxReturnPage）：表单结构与行次待定义，但入口可点。
      { key: 'tax-return', label: '纳税申报表', icon: Tickets, routeName: 'TaxReturn' },
      // 指向税审报告正文页，不是 AuditReport（那是财报审计报告编辑器，另一份文书）
      { key: 'tax-audit-report', label: '税审报告', icon: Finished, routeName: 'TaxAuditReport' },
    ],
  },
] as const

/** 带二级栏（底稿目录）的环节 key。只有这一项会弹出二级栏 */
export const TAX_WORKPAPER_STAGE_KEY = 'workpapers'

/** 拍平后的全部条目（高亮匹配、流程文案、守卫都用它） */
export const PROJECT_STAGES: readonly ProjectStage[] =
  PROJECT_STAGE_GROUPS.flatMap(g => g.items)

/**
 * 流程提示文案：「数据导入与账务查询 → 试算平衡与报表 → 税审底稿 → 鉴证报告」。
 *
 * 🔴 用**分组标题**而不是「每组第一项」：后者会把 `pending` 条目也排进流程
 *    （鉴证报告组第一项「纳税申报表」尚无页面），读起来像在指路到一个点不开的地方。
 */
export function projectStageFlowText(): string {
  return PROJECT_STAGE_GROUPS.map(g => g.title).join(' → ')
}
