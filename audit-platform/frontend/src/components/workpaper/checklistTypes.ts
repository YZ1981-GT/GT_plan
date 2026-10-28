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
  has_standard_ref?: boolean
  allow_custom_items?: boolean
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

/**
 * 空的 checklist HTML 载荷（props 默认值）。
 *
 * 🔴 必须放在模块级而非 SFC `<script setup>` 内：`defineProps` 的默认值会被
 * 编译器提升到 setup() 之外，引用组件内局部变量会报
 * 「cannot reference locally declared variables」（vite build 直接失败，
 * vue-tsc 查不出——2026-10-28 服务器部署实测）。
 */
export const EMPTY_CHECKLIST_HTML_DATA: ChecklistHtmlData = {
  template: {
    wp_code: '',
    title: '',
    sections: [],
    toc: [],
    stats: { total_actionable: 0, total_guidance: 0, total_sections: 0 },
  },
  responses: {},
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
