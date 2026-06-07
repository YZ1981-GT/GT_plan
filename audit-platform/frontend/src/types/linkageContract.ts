/**
 * LinkageContract 统一数据联动契约类型定义
 *
 * P0 增强版：枚举与后端 Python schema 严格一致
 */

/** 数据来源/目标类型 */
export type SourceType =
  | 'trial_balance'
  | 'ledger'
  | 'audit_sheet'
  | 'workpaper'
  | 'adjustment'
  | 'report'
  | 'note'
  | 'attachment'
  | 'ai'

export type TargetType = SourceType

/** 联动状态 */
export type LinkageStatus = 'current' | 'stale' | 'conflict' | 'manual_override'

/** 置信度 */
export type LinkageConfidence = 'system' | 'manual' | 'ai_suggested' | 'ai_confirmed'

/** 置信度到高/中/低映射 */
export const CONFIDENCE_LEVEL_MAP: Record<LinkageConfidence, 'high' | 'medium' | 'low'> = {
  system: 'high',
  manual: 'high',
  ai_confirmed: 'medium',
  ai_suggested: 'low',
}

/** 所有合法的 SourceType/TargetType 值 */
export const SOURCE_TYPE_VALUES: SourceType[] = [
  'trial_balance', 'ledger', 'audit_sheet', 'workpaper',
  'adjustment', 'report', 'note', 'attachment', 'ai',
]

/** 所有合法的 LinkageStatus 值 */
export const LINKAGE_STATUS_VALUES: LinkageStatus[] = [
  'current', 'stale', 'conflict', 'manual_override',
]

/** 所有合法的 LinkageConfidence 值 */
export const LINKAGE_CONFIDENCE_VALUES: LinkageConfidence[] = [
  'system', 'manual', 'ai_suggested', 'ai_confirmed',
]

/** 统一数据联动契约 */
export interface LinkageContract {
  source_type: SourceType
  source_id: string
  source_cell?: string | null
  target_type: TargetType
  target_id: string
  target_cell?: string | null
  amount?: string | null
  basis?: string | null
  status: LinkageStatus
  confidence: LinkageConfidence
  route?: string | null
  audit_log_id?: string | null
  conflict_id?: string | null
}

/** 路由解析请求 */
export interface ResolveRouteRequest {
  target_type: TargetType
  target_id: string
  target_cell?: string | null
}

/** 路由解析响应 */
export interface ResolveRouteResponse {
  route: string | null
  resolved_id?: string | null
  error?: string | null
}
