/**
 * 归档向导 API — R1 需求 5
 *
 * 端点：
 * - GET  /api/qc/archive-readiness?project_id={pid}  → 归档就绪检查
 * - POST /api/projects/{pid}/archive/orchestrate      → 启动归档编排
 * - GET  /api/projects/{pid}/archive/jobs/{jobId}     → 查询归档作业状态
 * - POST /api/projects/{pid}/archive/jobs/{jobId}/retry → 重试归档作业
 */
import { api } from '@/services/apiProxy'
import type { GateReadinessData } from '@/components/gate/GateReadinessPanel.vue'

// ── 类型定义 ──────────────────────────────────────────────────────────────

export interface ArchiveOrchestrateBody {
  scope: 'final' | 'interim'
  push_to_cloud: boolean
  purge_local: boolean
  gate_eval_id?: string
}

export interface ArchiveOrchestrateResponse {
  archive_job_id: string
  status: string
  estimated_seconds?: number
}

export interface ArchiveJobSection {
  order: string
  name: string
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'skipped'
}

export interface ArchiveJob {
  id: string
  project_id: string
  scope: string
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'partial'
  last_succeeded_section: string | null
  failed_section: string | null
  failed_reason: string | null
  output_url: string | null
  manifest_hash: string | null
  started_at: string | null
  finished_at: string | null
  current_section?: string | null
  sections?: ArchiveJobSection[]
}

// ── API 函数 ──────────────────────────────────────────────────────────────

/** 获取归档就绪检查数据（统一 GateReadinessData schema） */
export async function getArchiveReadiness(projectId: string): Promise<GateReadinessData> {
  return api.get<GateReadinessData>('/api/qc/archive-readiness', {
    params: { project_id: projectId },
  })
}

/** 启动归档编排 */
export async function startArchiveOrchestrate(
  projectId: string,
  body: ArchiveOrchestrateBody,
): Promise<ArchiveOrchestrateResponse> {
  return api.post<ArchiveOrchestrateResponse>(
    `/api/projects/${projectId}/archive/orchestrate`,
    body,
  )
}

/** 查询归档作业状态 */
export async function getArchiveJob(
  projectId: string,
  jobId: string,
): Promise<ArchiveJob> {
  return api.get<ArchiveJob>(
    `/api/projects/${projectId}/archive/jobs/${jobId}`,
  )
}

/** 重试归档作业（从断点续传） */
export async function retryArchiveJob(
  projectId: string,
  jobId: string,
): Promise<ArchiveJob> {
  return api.post<ArchiveJob>(
    `/api/projects/${projectId}/archive/jobs/${jobId}/retry`,
  )
}
