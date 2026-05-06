/**
 * 质控抽查工作台 API
 */
import http from '@/utils/http'

// ─── Types ──────────────────────────────────────────────────────────────────

export interface QcInspection {
  id: string
  project_id: string
  project_name?: string
  strategy: 'random' | 'risk_based' | 'full_cycle' | 'mixed'
  params: Record<string, any>
  reviewer_id: string
  status: 'pending' | 'in_progress' | 'completed'
  started_at: string | null
  completed_at: string | null
  report_url: string | null
  created_at: string
  item_count?: number
}

export interface QcInspectionItem {
  id: string
  inspection_id: string
  wp_id: string
  wp_code: string
  wp_name?: string
  audit_cycle?: string
  status: 'pending' | 'in_progress' | 'completed'
  findings: Record<string, any> | null
  qc_verdict: 'pass' | 'conditional_pass' | 'fail' | null
  completed_at: string | null
}

export interface QcInspectionListResponse {
  items: QcInspection[]
  total: number
}

export interface QcInspectionDetail extends QcInspection {
  items: QcInspectionItem[]
}

export interface VerdictPayload {
  verdict: 'pass' | 'conditional_pass' | 'fail'
  findings: string
}

export interface ReportGenerationResult {
  job_id?: string
  report_url?: string
  status: 'queued' | 'completed'
}

// ─── API Paths ──────────────────────────────────────────────────────────────

const BASE = '/api/qc/inspections'

// ─── API Functions ──────────────────────────────────────────────────────────

/** 获取抽查批次列表 */
export async function getInspections(): Promise<QcInspectionListResponse> {
  const { data } = await http.get(BASE)
  if (Array.isArray(data)) {
    return { items: data, total: data.length }
  }
  return data
}

/** 获取抽查批次详情（含 items） */
export async function getInspectionDetail(id: string): Promise<QcInspectionDetail> {
  const { data } = await http.get(`${BASE}/${id}`)
  return data
}

/** 录入质控结论 */
export async function submitVerdict(
  inspectionId: string,
  itemId: string,
  payload: VerdictPayload,
): Promise<QcInspectionItem> {
  const { data } = await http.post(
    `${BASE}/${inspectionId}/items/${itemId}/verdict`,
    payload,
  )
  return data
}

/** 生成质控报告 Word（异步） */
export async function generateReport(inspectionId: string): Promise<ReportGenerationResult> {
  const { data } = await http.post(`${BASE}/${inspectionId}/report`)
  return data
}
