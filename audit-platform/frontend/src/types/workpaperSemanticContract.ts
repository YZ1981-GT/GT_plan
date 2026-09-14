/**
 * 底稿内容语义契约 TypeScript 类型定义
 *
 * 与后端 backend/app/schemas/workpaper_semantic_contract.py 保持一致。
 *
 * 分层说明:
 * - `sheet_type` (SheetContentType): 描述 sheet 的**业务语义角色**。
 *   用于导航分组、权限判定、来源面板和状态汇总。
 * - `componentType` (WpComponentType): 描述 sheet 的**前端渲染组件**。
 *   用于 htmlRendererRegistry 分发渲染。
 *
 * 两者正交：同一 sheet_type 可由不同 componentType 渲染，反之亦然。
 * 渲染分发仍由 componentType 完成，语义分层由 sheet_type 承接。
 */

import type { EvidenceRef } from './evidenceRef'

// ---------------------------------------------------------------------------
// SheetContentType
// ---------------------------------------------------------------------------

/**
 * Sheet 的审计语义角色枚举值。
 * 每个值对应一种业务含义，与渲染组件 (componentType) 无关。
 */
export type SheetContentType =
  | 'control_panel'       // 程序控制台、科目驾驶舱
  | 'audit_sheet'         // 审定表
  | 'detail_table'        // 明细表
  | 'analysis'            // 账龄、趋势、毛利率、集中度等分析
  | 'procedure'           // 审计程序执行表
  | 'control_understanding' // 内控了解
  | 'control_test'        // 控制测试
  | 'confirmation_summary'  // 函证汇总视图
  | 'disclosure'          // 附注披露表
  | 'adjustment'          // 调整分录视图
  | 'conclusion'          // 科目结论和复核
  | 'legacy'             // 历史/修订前/只读
  | 'unknown'            // 迁移期未知类型

/** 所有合法 SheetContentType 值列表 */
export const SHEET_CONTENT_TYPES: SheetContentType[] = [
  'control_panel',
  'audit_sheet',
  'detail_table',
  'analysis',
  'procedure',
  'control_understanding',
  'control_test',
  'confirmation_summary',
  'disclosure',
  'adjustment',
  'conclusion',
  'legacy',
  'unknown',
]

// ---------------------------------------------------------------------------
// FieldSourceContract
// ---------------------------------------------------------------------------

/** 字段来源类型 */
export type FieldSourceType =
  | 'trial_balance'
  | 'formula'
  | 'manual'
  | 'linked'
  | 'ai_generated'

/** 所有合法 FieldSourceType 值列表 */
export const FIELD_SOURCE_TYPES: FieldSourceType[] = [
  'trial_balance',
  'formula',
  'manual',
  'linked',
  'ai_generated',
]

/** 字段 stale 策略 */
export type StalePolicy =
  | 'refresh_on_tb_updated'
  | 'refresh_on_report_regen'
  | 'manual_refresh'
  | 'none'

/** 所有合法 StalePolicy 值列表 */
export const STALE_POLICIES: StalePolicy[] = [
  'refresh_on_tb_updated',
  'refresh_on_report_regen',
  'manual_refresh',
  'none',
]

/** 字段来源契约 */
export interface FieldSourceContract {
  field_id: string
  label: string
  source_type: FieldSourceType
  source_ref: Record<string, unknown>
  editable: boolean
  override_allowed: boolean
  requires_confirmation: boolean
  traceable: boolean
  stale_policy: StalePolicy
}

// ---------------------------------------------------------------------------
// ProgramStatusContract
// ---------------------------------------------------------------------------

/** 审计程序执行状态 */
export type ProgramStatus =
  | 'not_started'
  | 'in_progress'
  | 'completed'
  | 'reviewed'
  | 'rejected'

/** 所有合法 ProgramStatus 值列表 */
export const PROGRAM_STATUSES: ProgramStatus[] = [
  'not_started',
  'in_progress',
  'completed',
  'reviewed',
  'rejected',
]

/** 复核状态 */
export type ReviewStatus =
  | 'pending'
  | 'approved'
  | 'rejected'

/** 所有合法 ReviewStatus 值列表 */
export const REVIEW_STATUSES: ReviewStatus[] = [
  'pending',
  'approved',
  'rejected',
]

/** 审计程序状态契约 */
export interface ProgramStatusContract {
  project_id: string
  account_package_id: string
  program_code: string
  sheet_name: string
  applicable: boolean
  status: ProgramStatus
  evidence_refs: EvidenceRef[]
  conclusion: string | null
  review_status: ReviewStatus
  not_applicable_reason: string | null
  updated_by: string | null
  updated_at: string | null
  reviewer: string | null
  reviewed_at: string | null
}

// ---------------------------------------------------------------------------
// Type guards
// ---------------------------------------------------------------------------

/** 判断是否为合法的 SheetContentType */
export function isSheetContentType(value: unknown): value is SheetContentType {
  return typeof value === 'string' && SHEET_CONTENT_TYPES.includes(value as SheetContentType)
}

/** 判断是否为合法的 FieldSourceType */
export function isFieldSourceType(value: unknown): value is FieldSourceType {
  return typeof value === 'string' && FIELD_SOURCE_TYPES.includes(value as FieldSourceType)
}

/** 判断是否为合法的 StalePolicy */
export function isStalePolicy(value: unknown): value is StalePolicy {
  return typeof value === 'string' && STALE_POLICIES.includes(value as StalePolicy)
}

/** 判断是否为合法的 ProgramStatus */
export function isProgramStatus(value: unknown): value is ProgramStatus {
  return typeof value === 'string' && PROGRAM_STATUSES.includes(value as ProgramStatus)
}

/** 判断是否为合法的 ReviewStatus */
export function isReviewStatus(value: unknown): value is ReviewStatus {
  return typeof value === 'string' && REVIEW_STATUSES.includes(value as ReviewStatus)
}
