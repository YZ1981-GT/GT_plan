/**
 * Phase 14/15/16: 门禁引擎 + 任务树 + 取证版本链 API 服务层
 */
import { api } from './apiProxy'
import { governance as P } from './apiPaths'

// ── Phase 14: Gate Engine ──────────────────────────────────────

export interface GateRuleHit {
  rule_code: string
  error_code: string
  severity: 'blocking' | 'warning' | 'info'
  message: string
  location: Record<string, any>
  suggested_action: string
}

export interface GateEvaluateResponse {
  decision: 'allow' | 'warn' | 'block'
  hit_rules: GateRuleHit[]
  trace_id: string
}

export interface SoDCheckResponse {
  allowed: boolean
  conflict_type?: string
  policy_code?: string
  trace_id: string
}

export interface TraceReplayResponse {
  trace_id: string
  events: any[]
  replay_status: 'complete' | 'partial' | 'broken'
}

export async function evaluateGate(params: {
  gate_type: string
  project_id: string
  wp_id?: string
  actor_id: string
  context?: Record<string, any>
}): Promise<GateEvaluateResponse> {
  const { data } = await api.post(P.gate.evaluate, params)
  return data
}

export async function checkSoD(params: {
  project_id: string
  wp_id: string
  actor_id: string
  target_role: string
}): Promise<SoDCheckResponse> {
  const { data } = await api.post(P.sod.check, params)
  return data
}

export async function replayTrace(
  traceId: string,
  level: 'L1' | 'L2' | 'L3' = 'L1'
): Promise<TraceReplayResponse> {
  const { data } = await api.get(P.trace.replay(traceId), { params: { level } })
  return data
}

export async function queryTraces(params: {
  project_id: string
  event_type?: string
  object_type?: string
  page?: number
  page_size?: number
}) {
  const { data } = await api.get(P.trace.query, { params })
  return data
}

// ── Phase 15: Task Tree ────────────────────────────────────────

export interface TaskNode {
  id: string
  project_id: string
  node_level: 'unit' | 'account' | 'workpaper' | 'evidence'
  parent_id?: string
  ref_id: string
  status: 'pending' | 'in_progress' | 'blocked' | 'done'
  assignee_id?: string
  due_at?: string
  meta?: Record<string, any>
}

export interface IssueTicket {
  id: string
  project_id: string
  source: 'L2' | 'L3' | 'Q'
  severity: 'blocker' | 'major' | 'minor' | 'suggestion'
  category: string
  title: string
  owner_id: string
  due_at?: string
  status: string
  trace_id: string
  created_at?: string
  closed_at?: string
}

export async function listTaskTree(params: {
  project_id: string
  root_level?: string
  status?: string
  assignee_id?: string
  page?: number
  page_size?: number
}) {
  const { data } = await api.get(P.taskTree.list, { params })
  return data
}

export async function getTreeStats(projectId: string) {
  const { data } = await api.get(P.taskTree.stats, { params: { project_id: projectId } })
  return data
}

export async function transitNodeStatus(nodeId: string, nextStatus: string, operatorId: string) {
  const { data } = await api.put(P.taskTree.status(nodeId), {
    next_status: nextStatus,
    operator_id: operatorId,
  })
  return data
}

export async function reassignNode(params: {
  task_node_id: string
  assignee_id: string
  operator_id: string
  reason_code: string
}) {
  const { data } = await api.post(P.taskTree.reassign, params)
  return data
}

export async function replayEvent(params: {
  event_id: string
  operator_id: string
  reason_code: string
}) {
  const { data } = await api.post(P.taskEvents.replay, params)
  return data
}

export async function listEvents(params: {
  project_id: string
  status?: string
  page?: number
  page_size?: number
}) {
  const { data } = await api.get(P.taskEvents.list, { params })
  return data
}

export async function createIssueFromConversation(params: {
  conversation_id: string
  task_node_id?: string
  operator_id: string
  sla_level: 'P0' | 'P1' | 'P2'
}) {
  const { data } = await api.post(P.issues.fromConversation, params)
  return data
}

export async function listIssues(params: {
  project_id: string
  status?: string
  severity?: string
  source?: string
  owner_id?: string
  page?: number
  page_size?: number
}) {
  const { data } = await api.get(P.issues.list, { params })
  return data
}

export async function updateIssueStatus(issueId: string, params: {
  status: string
  operator_id: string
  reason_code: string
  evidence_refs?: any[]
}) {
  const { data } = await api.put(P.issues.status(issueId), params)
  return data
}

export async function escalateIssue(issueId: string, params: {
  from_level: string
  to_level: string
  reason_code: string
}) {
  const { data } = await api.post(P.issues.escalate(issueId), params)
  return data
}

// ── Phase 16: Version Line + Integrity + Conflicts ─────────────

export async function queryVersionLine(projectId: string, objectType?: string, objectId?: string) {
  const { data } = await api.get(P.versionLine(projectId), {
    params: { object_type: objectType, object_id: objectId },
  })
  return data
}

export async function checkExportIntegrity(exportId: string) {
  const { data } = await api.get(P.exportIntegrity(exportId))
  return data
}

export async function detectConflicts(projectId: string, wpId: string) {
  const { data } = await api.post(P.offline.detectConflicts, {
    project_id: projectId,
    wp_id: wpId,
  })
  return data
}

export async function resolveConflict(params: {
  conflict_id: string
  resolution: 'accept_local' | 'accept_remote' | 'manual_merge'
  merged_value?: Record<string, any>
  resolver_id: string
  reason_code: string
}) {
  const { data } = await api.post(P.offline.resolveConflict, params)
  return data
}

export async function listConflicts(params: {
  project_id: string
  status?: string
  page?: number
  page_size?: number
}) {
  const { data } = await api.get(P.offline.listConflicts, { params })
  return data
}

export async function replayConsistency(projectId: string, snapshotId?: string) {
  const { data } = await api.post(P.consistency.replay, {
    project_id: projectId,
    snapshot_id: snapshotId,
  })
  return data
}

export async function getConsistencyReport(projectId: string) {
  const { data } = await api.get(P.consistency.report(projectId))
  return data
}
