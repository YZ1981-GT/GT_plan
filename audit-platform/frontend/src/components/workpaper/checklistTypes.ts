/**
 * checklistTypes — 核对表组件共享类型（spec workpaper-frontend-large-component-split, Req 2）
 *
 * 从 GtChecklistTable.vue 抽出的类型定义，供主组件 / composable / 展示型子组件复用。
 * 类型之外只有一个运行时常量（空核对表默认值），依赖单向：主组件 / composable / 子组件 → 本文件。
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
  /** 结论选项：completion = 是 / 否 / 不适用；缺省按编码（A17-5 → completion，其余 → disclosure） */
  conclusion_mode?: 'completion' | 'disclosure'
}

/** 结论选项「是 / 否 / 不适用」（A17-5、A30）；组件里拿它比较，不写字面量 */
export const CONCLUSION_MODE_COMPLETION = 'completion' as const

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

/**
 * 空核对表（GtChecklistTable 的 htmlData 默认值）。放在这里而不是组件的 `<script setup>` 里：
 * defineProps 的默认值会被提升到 setup() 之外，引用本地变量编译期即报错（组件整页加载失败）。
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
