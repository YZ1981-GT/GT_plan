/**
 * EQCR（独立复核合伙人）API 服务层
 *
 * Refinement Round 5 Task 4 — 对齐后端 `backend/app/routers/eqcr.py`：
 *   - GET /api/eqcr/projects                        → listMyProjects
 *   - GET /api/eqcr/projects/{projectId}/overview   → getProjectOverview
 *
 * Refinement Round 5 Task 6 — 新增 5 个判断域聚合 + 意见 CRUD：
 *   - GET /api/eqcr/projects/{projectId}/materiality      → getMateriality
 *   - GET /api/eqcr/projects/{projectId}/estimates        → getEstimates
 *   - GET /api/eqcr/projects/{projectId}/related-parties  → getRelatedParties
 *   - GET /api/eqcr/projects/{projectId}/going-concern    → getGoingConcern
 *   - GET /api/eqcr/projects/{projectId}/opinion-type     → getOpinionType
 *   - POST /api/eqcr/opinions                              → createOpinion
 *   - PATCH /api/eqcr/opinions/{opinionId}                 → updateOpinion
 *
 * 注意后端返回结构同时覆盖 R5 工作台（Task 4）与 ProjectView（Task 6），
 * 此处集中维护类型，避免下游页面各自 re-declare。
 */
import { api } from '@/services/apiProxy'
import { eqcr as P } from '@/services/apiPaths'

// ─── 类型定义 ────────────────────────────────────────────────────────────────

/** EQCR 工作台进度枚举（与后端 `eqcr_service._classify_progress` 对齐） */
export type EqcrProgress = 'not_started' | 'in_progress' | 'approved' | 'disagree'

/** 5 个基础判断域（component_auditor 是合并审计扩展，工作台不计入） */
export type EqcrCoreDomain =
  | 'materiality'
  | 'estimate'
  | 'related_party'
  | 'going_concern'
  | 'opinion_type'

/** 意见所有 domain（含组成部分审计师扩展，Task 22 使用） */
export type EqcrOpinionDomain = EqcrCoreDomain | 'component_auditor'

/** EQCR 意见 verdict（后端 eqcr_opinions.verdict） */
export type EqcrVerdict = 'agree' | 'disagree' | 'need_more_evidence'

/** 审计报告状态（ReportStatus 枚举对齐） */
export type ReportStatusValue = 'draft' | 'review' | 'eqcr_approved' | 'final'

/** 工作台卡片 */
export interface EqcrProjectCard {
  project_id: string
  project_name: string
  client_name: string | null
  /** 签字日 ISO `YYYY-MM-DD`，无则 null */
  signing_date: string | null
  /** 距签字日的天数，null 表示未设定签字日 */
  days_to_signing: number | null
  my_progress: EqcrProgress
  judgment_counts: {
    unreviewed: number
    reviewed: number
  }
  report_status: ReportStatusValue | null
}

/** 项目 EQCR 总览（ProjectView 页壳用） */
export interface EqcrProjectOverview {
  project: {
    id: string
    name: string
    client_name: string | null
    signing_date: string | null
    report_scope: string | null
    status: string
    audit_period_start: string | null
    audit_period_end: string | null
  }
  my_role_confirmed: boolean
  report_status: ReportStatusValue | null
  opinion_summary: {
    by_domain: Record<EqcrCoreDomain, EqcrVerdict | null>
    total: number
  }
  note_count: number
  shadow_comp_count: number
  disagreement_count: number
}

/** EQCR 意见（与 eqcr_opinions 表对齐） */
export interface EqcrOpinion {
  id: string
  project_id: string
  domain: EqcrOpinionDomain
  verdict: EqcrVerdict
  comment: string | null
  extra_payload: Record<string, any> | null
  created_by: string | null
  created_at: string | null
  updated_at: string | null
}

/** 5 个域聚合接口统一返回结构 */
export interface EqcrDomainPayload<TData> {
  project_id: string
  domain: EqcrOpinionDomain
  data: TData
  current_opinion: EqcrOpinion | null
  history_opinions: EqcrOpinion[]
}

/** 重要性 Tab 数据 */
export interface EqcrMaterialitySnapshot {
  year: number
  benchmark_type: string | null
  benchmark_amount: string | null
  overall_percentage: string | null
  overall_materiality: string | null
  performance_ratio: string | null
  performance_materiality: string | null
  trivial_ratio: string | null
  trivial_threshold: string | null
  is_override: boolean
  override_reason: string | null
}

export interface EqcrMaterialityData {
  current: EqcrMaterialitySnapshot | null
  prior_years: EqcrMaterialitySnapshot[]
}

/** 会计估计 Tab 条目 */
export interface EqcrEstimateItem {
  wp_index_id: string
  wp_code: string | null
  wp_name: string | null
  audit_cycle: string | null
  index_status: string | null
  file_status: string | null
  review_status: string | null
  working_paper_id: string | null
}

export interface EqcrEstimateData {
  items: EqcrEstimateItem[]
  match_strategy: string
  keywords: string[]
}

/** 关联方 Tab 数据 */
export interface EqcrRelatedPartyRegistry {
  id: string
  name: string
  relation_type: string | null
  is_controlled_by_same_party: boolean
  created_at: string | null
}

export interface EqcrRelatedPartyTransaction {
  id: string
  related_party_id: string
  amount: string | null
  transaction_type: string | null
  is_arms_length: boolean | null
  evidence_refs: any
  created_at: string | null
}

export interface EqcrRelatedPartyData {
  registries: EqcrRelatedPartyRegistry[]
  transactions: EqcrRelatedPartyTransaction[]
  summary: {
    registry_count: number
    transaction_count: number
  }
}

/** 持续经营 Tab 数据 */
export interface EqcrGoingConcernEvaluation {
  id: string
  evaluation_date: string | null
  conclusion: string | null
  key_indicators: any
  management_plan: string | null
  auditor_conclusion: string | null
}

export interface EqcrGoingConcernIndicator {
  id: string
  indicator_type: string | null
  indicator_value: any
  threshold: any
  is_triggered: boolean
  severity: string | null
  notes: string | null
}

export interface EqcrGoingConcernData {
  current_evaluation: EqcrGoingConcernEvaluation | null
  prior_evaluations: EqcrGoingConcernEvaluation[]
  indicators: EqcrGoingConcernIndicator[]
}

/** 审计意见 Tab 数据 */
export interface EqcrAuditReportSnapshot {
  id: string
  year: number
  opinion_type: string | null
  company_type: string | null
  status: ReportStatusValue | null
  report_date: string | null
  signing_partner: string | null
  paragraphs: any
}

export interface EqcrOpinionTypeData {
  current_report: EqcrAuditReportSnapshot | null
  prior_reports: EqcrAuditReportSnapshot[]
}

/** 创建意见请求体 */
export interface EqcrOpinionCreateInput {
  project_id: string
  domain: EqcrOpinionDomain
  verdict: EqcrVerdict
  comment?: string | null
  extra_payload?: Record<string, any> | null
}

/** 更新意见请求体 */
export interface EqcrOpinionUpdateInput {
  verdict?: EqcrVerdict
  comment?: string | null
  extra_payload?: Record<string, any> | null
}

// ─── API 调用 ────────────────────────────────────────────────────────────────

export const eqcrApi = {
  /** 获取本人作为 EQCR 的项目卡片列表（按签字日升序） */
  async listMyProjects(): Promise<EqcrProjectCard[]> {
    const data = await api.get<EqcrProjectCard[]>(P.projects)
    return Array.isArray(data) ? data : []
  },

  /** 获取项目 EQCR 总览（用于 EqcrProjectView 页壳） */
  async getProjectOverview(projectId: string): Promise<EqcrProjectOverview> {
    return api.get<EqcrProjectOverview>(P.projectOverview(projectId))
  },

  /** 重要性 Tab 数据聚合 + 本域意见历史（需求 2.2） */
  async getMateriality(
    projectId: string,
  ): Promise<EqcrDomainPayload<EqcrMaterialityData>> {
    return api.get<EqcrDomainPayload<EqcrMaterialityData>>(P.materiality(projectId))
  },

  /** 会计估计 Tab 数据（需求 2.3） */
  async getEstimates(
    projectId: string,
  ): Promise<EqcrDomainPayload<EqcrEstimateData>> {
    return api.get<EqcrDomainPayload<EqcrEstimateData>>(P.estimates(projectId))
  },

  /** 关联方 Tab 数据（需求 2.4） */
  async getRelatedParties(
    projectId: string,
  ): Promise<EqcrDomainPayload<EqcrRelatedPartyData>> {
    return api.get<EqcrDomainPayload<EqcrRelatedPartyData>>(
      P.relatedParties(projectId),
    )
  },

  /** 持续经营 Tab 数据（需求 2.5） */
  async getGoingConcern(
    projectId: string,
  ): Promise<EqcrDomainPayload<EqcrGoingConcernData>> {
    return api.get<EqcrDomainPayload<EqcrGoingConcernData>>(
      P.goingConcern(projectId),
    )
  },

  /** 审计意见类型 Tab 数据（需求 2.6） */
  async getOpinionType(
    projectId: string,
  ): Promise<EqcrDomainPayload<EqcrOpinionTypeData>> {
    return api.get<EqcrDomainPayload<EqcrOpinionTypeData>>(
      P.opinionType(projectId),
    )
  },

  /** 新建一条 EQCR 意见（需求 2.7） */
  async createOpinion(payload: EqcrOpinionCreateInput): Promise<EqcrOpinion> {
    return api.post<EqcrOpinion>(P.opinions, payload)
  },

  /** 更新一条 EQCR 意见（仅创建人或 admin 可调） */
  async updateOpinion(
    opinionId: string,
    patch: EqcrOpinionUpdateInput,
  ): Promise<EqcrOpinion> {
    return api.patch<EqcrOpinion>(P.opinionDetail(opinionId), patch)
  },
}

export default eqcrApi
