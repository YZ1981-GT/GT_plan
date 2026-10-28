/**
 * 归档向导 API — R1 需求 5
 *
 * 端点：
 * - GET  /api/projects/{pid}/qc-dashboard/archive-readiness  → 归档就绪检查
 * - POST /api/projects/{pid}/archive/orchestrate      → 启动归档编排
 * - GET  /api/projects/{pid}/archive/jobs/{jobId}     → 查询归档作业状态
 * - POST /api/projects/{pid}/archive/jobs/{jobId}/retry → 重试归档作业
 * - GET  /api/projects/{pid}/archive/jobs/{jobId}/package → 下载归档包（作业 output_url）
 * - POST /api/projects/{pid}/unarchive                → 解除归档（底稿恢复归档前状态）
 *
 * 启动 / 重试要求二次密码确认令牌（spec attachment-archive-and-a-class-evidence 需求 4.3）：
 * 调用方先 `requestConfirmationToken()`，取消即不调用。
 */
import { api } from '@/services/apiProxy'
import { downloadFile } from '@/utils/http'
import { confirmationHeaders } from '@/utils/passwordConfirm'
import { archive as archivePaths, qcDashboard } from './apiPaths'
import type { GateReadinessData } from '@/components/gate/GateReadinessPanel.vue'

// ── 类型定义 ──────────────────────────────────────────────────────────────

export interface ArchiveOrchestrateBody {
  scope: 'final' | 'interim'
  push_to_cloud: boolean
  purge_local: boolean
  gate_eval_id?: string
}

/** 启动接口直接返回作业（与查询同形；改造前前端读不存在的 `archive_job_id`，跳转与轮询都拿到 undefined） */
export type ArchiveOrchestrateResponse = ArchiveJob

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
  /**
   * Batch 3-4: 断点续传与进度计算的权威来源。
   * 每个 key 对应后端步骤名（gate/wp_storage/push_to_cloud/purge_local 等），
   * value.status 为 "succeeded"/"running"/"failed" 等；失败步骤另带 problems（逐项缺件原因）。
   * 前端 progressPercent 应优先读本字段，而非 last_succeeded_section。
   */
  section_progress?: Record<string, { status: string; finished_at?: string; problems?: string[] }>
}

/** 归档在请求内同步执行（打包大项目要几分钟）：启动 / 重试放宽超时 */
const ARCHIVE_RUN_TIMEOUT_MS = 10 * 60 * 1000

// ── API 函数 ──────────────────────────────────────────────────────────────

/** 获取归档就绪检查数据（统一 GateReadinessData schema） */
export async function getArchiveReadiness(projectId: string): Promise<GateReadinessData> {
  return api.get<GateReadinessData>(qcDashboard.archiveReadiness(projectId))
}

/** 启动归档编排 */
export async function startArchiveOrchestrate(
  projectId: string,
  body: ArchiveOrchestrateBody,
  confirmationToken: string,
): Promise<ArchiveOrchestrateResponse> {
  return api.post<ArchiveOrchestrateResponse>(
    archivePaths.orchestrate(projectId),
    body,
    { headers: confirmationHeaders(confirmationToken), timeout: ARCHIVE_RUN_TIMEOUT_MS },
  )
}

/** 查询归档作业状态 */
export async function getArchiveJob(
  projectId: string,
  jobId: string,
): Promise<ArchiveJob> {
  return api.get<ArchiveJob>(archivePaths.job(projectId, jobId))
}

/** 重试归档作业（从断点续传） */
export async function retryArchiveJob(
  projectId: string,
  jobId: string,
  confirmationToken: string,
): Promise<ArchiveJob> {
  return api.post<ArchiveJob>(archivePaths.retry(projectId, jobId), undefined, {
    headers: confirmationHeaders(confirmationToken), timeout: ARCHIVE_RUN_TIMEOUT_MS,
  })
}

/** 下载归档包：带登录令牌的 blob 下载（直接 window.open 不带鉴权头，必 401） */
export async function downloadArchivePackage(outputUrl: string): Promise<void> {
  await downloadFile(outputUrl, { fileName: '归档包.zip' })
}

export interface UnarchiveBody {
  /** 解除原因（留痕） */
  reason: string
  /** 二次确认：用户输入的项目名称，须与项目名称一致 */
  project_code: string
}

export interface UnarchiveResult {
  success: boolean
  message: string
  new_status: string
  /** 恢复为归档前状态的底稿张数 */
  workpapers_restored: number
}

/** 解除归档（admin / 合伙人）。错误由调用方提示（_silent：不弹全局提示） */
export async function unarchiveProject(projectId: string, body: UnarchiveBody): Promise<UnarchiveResult> {
  return api.post<UnarchiveResult>(archivePaths.unarchive(projectId), body, { _silent: true } as any)
}
