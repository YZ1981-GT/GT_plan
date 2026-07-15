/**
 * procedureConsoleOverlay.ts — 程序控制台 task overlay 纯逻辑
 *
 * Feature: procedure-delegation-notification / Task 14（Design F2/F3/F5）
 *
 * 本模块只含纯函数与常量，供 GtAProgramConsole.vue、ProcedureReviewPanel.vue 复用，
 * 并可用 vitest/fast-check 直接验证（无 Vue/DOM 依赖）：
 * - 统一中文术语（需求 14.1：循环责任人 / 底稿主编 / 程序执行人 / 操作复核人 / 业务合伙人·QC·EQCR）。
 * - task overlay 检测：render-config 注入 task_id/materialization_required 时才进入委派/执行态。
 * - 深链定位：仅按 sheet_key + definition_key 精确匹配，绝不按 program_no 猜测（需求 9.6 / P28）。
 * - 成员状态动作派生：与 MyProcedureTasks.vue 的 transition 契约一致（需求 6 / 9.7）。
 */

// ─── 统一中文术语（需求 14.1）─────────────────────────────────────────────────
// 不得把高阶复核（业务合伙人/QC/EQCR）显示为程序行 reviewer。
export const ROLE_TERMS = {
  cycleOwner: '循环责任人',
  workpaperLead: '底稿主编',
  procedureAssignee: '程序执行人',
  operationReviewer: '操作复核人',
  highOrderReviewer: '业务合伙人 / QC / EQCR',
} as const

// 程序行任务工作流状态中文标签（与 MyProcedureTasks.vue 保持一致）。
export const WORKFLOW_LABELS: Record<string, string> = {
  unassigned: '未分配',
  assigned: '待确认',
  acknowledged: '已确认',
  in_progress: '进行中',
  submitted: '待复核',
  changes_requested: '已退回',
  reviewed: '已复核',
  cancelled: '已取消',
}

// 适用性（细裁）中文标签。
export const APPLICABILITY_LABELS: Record<string, string> = {
  execute: '执行',
  not_applicable: '不适用',
}

export type TagType = 'primary' | 'success' | 'warning' | 'danger' | 'info' | ''

/** 工作流状态 → el-tag 类型。 */
export function workflowTagType(status: string | null | undefined): TagType {
  switch (status) {
    case 'reviewed': return 'success'
    case 'submitted': return 'warning'
    case 'changes_requested': return 'danger'
    case 'cancelled': return 'info'
    case 'in_progress': return 'primary'
    case 'acknowledged': return 'primary'
    default: return ''
  }
}

/** 工作流状态中文标签（未知值原样返回）。 */
export function workflowLabel(status: string | null | undefined): string {
  if (!status) return '—'
  return WORKFLOW_LABELS[status] || status
}

// ─── task overlay 检测 ────────────────────────────────────────────────────────

/** overlay 行（render-config 注入的 task 叠加字段子集）。 */
export interface OverlayRow {
  program_no?: number | string
  definition_key?: string | null
  sheet_key?: string | null
  task_id?: string | null
  materialization_required?: boolean
  workflow_status?: string | null
  applicability_status?: string | null
  assignee_staff_id?: string | null
  reviewer_staff_id?: string | null
  assignment_version?: number
  lock_version?: number
  due_at?: string | null
  [k: string]: any
}

/**
 * 是否存在 task overlay（任一行带 task_id 或 materialization_required 标记）。
 * PROCEDURE_ROW_TASKS_ENABLED 关闭时 render-config 不注入这些字段 → 返回 false，
 * 控制台回退到既有只读/裁剪展示（expand 阶段不改既有读语义）。
 */
export function hasTaskOverlay(rows: OverlayRow[] | null | undefined): boolean {
  if (!Array.isArray(rows)) return false
  return rows.some(
    (r) => r && (typeof r.task_id === 'string' || r.materialization_required === true),
  )
}

/**
 * 该行是否未物化（有 definition 无 task）。未物化行只展示不可写（需求 2.7）。
 * 以后端权威信号 materialization_required 为准（overlay 保证：无 task ⇒ true，有 task ⇒ false）。
 */
export function isUnmaterialized(row: OverlayRow | null | undefined): boolean {
  return !!row && row.materialization_required === true
}

// ─── 深链定位（需求 9.6 / P28）──────────────────────────────────────────────

export interface DeepLinkResolution {
  matched: boolean
  row: OverlayRow | null
  /** 模板已变化：给了 definition_key 但当前 sheet 找不到（不按 program_no 降级）。 */
  templateChanged: boolean
}

/**
 * 按 sheet_key + definition_key 精确定位深链目标行。
 * - 无 definition_key 入参 → 不定位（matched=false, templateChanged=false）。
 * - 有 definition_key 但匹配不到 → templateChanged=true（提示“模板已变化”，绝不按 program_no 猜测）。
 * - sheetKey 传入时同时校验 sheet_key（跨 sheet 不误配）。
 */
export function resolveDeepLink(
  rows: OverlayRow[] | null | undefined,
  sheetKey: string | null | undefined,
  definitionKey: string | null | undefined,
): DeepLinkResolution {
  if (!definitionKey) return { matched: false, row: null, templateChanged: false }
  if (!Array.isArray(rows) || rows.length === 0) {
    return { matched: false, row: null, templateChanged: true }
  }
  const hit = rows.find((r) => {
    if (!r || r.definition_key !== definitionKey) return false
    if (sheetKey && r.sheet_key && r.sheet_key !== sheetKey) return false
    return true
  })
  if (hit) return { matched: true, row: hit, templateChanged: false }
  return { matched: false, row: null, templateChanged: true }
}

// ─── 成员状态动作派生（需求 6 / 9.7；与 transition 契约一致）────────────────

export type ProcedureActionKey =
  | 'acknowledge' | 'start' | 'submit' | 'review' | 'request_changes'

export interface ProcedureAction {
  key: ProcedureActionKey
  label: string
  type: TagType
}

/**
 * 依 my_role + workflow_status + applicability 派生可用状态动作。
 * 仅 applicability=execute 的行有动作；未物化行无动作（无 task_id 交由调用方拦截）。
 * 与 MyProcedureTasks.vue rowActions 完全一致，保证控制台与任务页行为统一。
 */
export function memberActions(
  row: OverlayRow & { my_role?: 'assignee' | 'reviewer' | null },
): ProcedureAction[] {
  const acts: ProcedureAction[] = []
  if (!row || !row.task_id) return acts
  if (row.applicability_status && row.applicability_status !== 'execute') return acts
  const status = row.workflow_status
  if (row.my_role === 'assignee') {
    if (status === 'assigned') acts.push({ key: 'acknowledge', label: '确认接收', type: 'primary' })
    else if (status === 'acknowledged') acts.push({ key: 'start', label: '开始执行', type: 'primary' })
    else if (status === 'changes_requested') acts.push({ key: 'start', label: '继续修改', type: 'warning' })
    else if (status === 'in_progress') acts.push({ key: 'submit', label: '提交复核', type: 'success' })
  } else if (row.my_role === 'reviewer') {
    if (status === 'submitted') {
      acts.push({ key: 'review', label: '复核通过', type: 'success' })
      acts.push({ key: 'request_changes', label: '退回', type: 'danger' })
    }
  }
  return acts
}

/** 生成 request_id（幂等键；crypto.randomUUID 优先，降级时间戳+随机）。 */
export function newRequestId(): string {
  const c: any = (globalThis as any).crypto
  if (c?.randomUUID) return c.randomUUID()
  return `req-${Date.now()}-${Math.random().toString(16).slice(2)}`
}
