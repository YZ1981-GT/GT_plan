import type { WpComponentType } from '@/types/componentCapabilities.generated'
import type {
  FieldSourceContract,
  SheetContentType,
} from '@/types/workpaperSemanticContract'

/** 跨底稿引用 wire；cell 在后端可显式为 null。 */
export interface CrossRefWire {
  wp_code: string
  cell: string | null
}

export interface SheetRenderConfigWire {
  sheet_name: string
  /** 后端裁决的 canonical sheet code；无法可靠映射时为 null。 */
  sheet_code?: string | null
  sheet_code_reason?: string | null
  whole_workbook?: boolean
  componentType: WpComponentType
  schema: Record<string, any> | null
  html_data: Record<string, any> | null
  cross_refs: CrossRefWire[]
  sheet_type?: SheetContentType | null
  field_sources?: Record<string, FieldSourceContract> | null
}

export interface RenderPermissionsWire {
  edit: boolean
}

export interface RenderDecisionWire {
  sheet_key: string
  chosen_component_type: WpComponentType
  candidate_sources: string[]
  winning_source: string
  override_hit: boolean
  redirect_applied: boolean
  fallback_reason?: string | null
}

export interface FillResultWire {
  value: number | string | null
  source: string
  label: string
  status: 'ok' | 'unavailable'
}

/** GET /api/workpapers/{id}/render-config 的唯一前端 wire 类型。 */
export interface RenderConfigWire {
  wp_id: string
  wp_code: string
  project_id: string
  scope: 'standalone' | 'consolidated' | 'parent_only' | 'both'
  is_real_workpaper: boolean
  template_version: string | null
  sheets: SheetRenderConfigWire[]

  /** 普通渲染分支字段；redirect 分支不下发。 */
  audit_year?: number | null
  applicable_standards?: string[]
  fill_results?: Record<string, FillResultWire>
  guidance?: Record<string, any> | null

  /** redirect 分支字段。 */
  redirect?: boolean
  delegated_module?: string | null
  target_path?: string | null

  /** word-template 分支字段。 */
  sign_status?: string | null
  permissions?: RenderPermissionsWire | null

  /** active：由 WpDecisionTracePanel 只读消费。 */
  decision_trace?: RenderDecisionWire[]
}

/**
 * 根字段生命周期必须穷尽 RenderConfigWire；无当前消费方的字段显式登记为 reserved，
 * 禁止仅在类型中漂浮。新增字段未分类会在 vue-tsc 阶段失败。
 */
export const RENDER_CONFIG_FIELD_STATUS = {
  wp_id: 'active',
  wp_code: 'active',
  project_id: 'active',
  scope: 'reserved',
  is_real_workpaper: 'active',
  template_version: 'active',
  sheets: 'active',
  audit_year: 'active',
  applicable_standards: 'active',
  fill_results: 'active',
  guidance: 'reserved',
  redirect: 'active',
  delegated_module: 'active',
  target_path: 'active',
  sign_status: 'reserved',
  permissions: 'reserved',
  decision_trace: 'active',
} as const satisfies Record<keyof RenderConfigWire, 'active' | 'reserved'>

// 迁移期兼容导出；类型真源仅为上述 Wire 定义。
export type CrossRefEntry = CrossRefWire
export type SheetRenderConfig = SheetRenderConfigWire
export type RenderConfig = RenderConfigWire
