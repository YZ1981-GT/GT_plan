/**
 * checklistTypes — 核对表组件共享类型（spec workpaper-frontend-large-component-split, Req 2）
 *
 * 从 GtChecklistTable.vue 抽出的类型定义，供主组件 / composable / 展示型子组件复用。
 * 仅类型（无运行时），依赖单向：主组件 / composable / 子组件 → 本文件。
 */

export interface ChecklistChild {
  id: string
  content: string
  standard_ref: string
}

export interface ChecklistItem {
  id: string
  type: 'actionable' | 'guidance' | 'header'
  standard_ref: string
  content: string
  preset_wp_ref?: string
  children: ChecklistChild[]
}

export interface ChecklistSection {
  id: string
  title: string
  items: ChecklistItem[]
}

export interface TocEntry {
  id: string
  title: string
  applicable: boolean | null
}

export interface ChecklistStats {
  total_actionable: number
  total_guidance: number
  total_sections: number
}

export interface ChecklistTemplate {
  wp_code: string
  title: string
  sections: ChecklistSection[]
  toc: TocEntry[]
  stats: ChecklistStats
}

export interface ResponseData {
  conclusion: string | null
  remark: string | null
  wp_ref: string | null
}

export interface ChecklistHtmlData {
  template: ChecklistTemplate
  responses: Record<string, ResponseData>
}

/** 复核签字提示（A17-5 复核建议） */
export interface ReviewSignHint {
  suggested_conclusion?: string
  reason?: string
  sign_status?: string | null
}

/** 搜索匹配结果（Task 8） */
export interface SearchMatch {
  sectionId: string
  sectionTitle: string
  item: ChecklistItem
  matchField: 'content' | 'standard_ref' | 'child'
}
