/**
 * 质控年度报告 API — Round 3 需求 9
 *
 * POST /api/qc/annual-reports?year=       — 触发异步年报生成
 * GET  /api/qc/annual-reports             — 列出历史年报
 * GET  /api/qc/annual-reports/{id}/download — 下载年报
 */
import http from '@/utils/http'

// ─── Types ──────────────────────────────────────────────────────────────────

export interface AnnualReport {
  id: string
  year: number
  status: string
  created_at: string
  file_path?: string
  message?: string
}

export interface AnnualReportListResponse {
  items: AnnualReport[]
  total: number
}

export interface GenerateReportResult {
  job_id: string | null
  year: number
  status: string
  message: string
}

// ─── API Paths ──────────────────────────────────────────────────────────────

const BASE = '/api/qc/annual-reports'

// ─── API Functions ──────────────────────────────────────────────────────────

/** 列出历史年报 */
export async function listAnnualReports(
  page = 1,
  pageSize = 20,
): Promise<AnnualReportListResponse> {
  const { data } = await http.get(BASE, { params: { page, page_size: pageSize } })
  if (Array.isArray(data)) {
    return { items: data, total: data.length }
  }
  return data
}

/** 触发年报生成 */
export async function generateAnnualReport(year: number): Promise<GenerateReportResult> {
  const { data } = await http.post(`${BASE}?year=${year}`)
  return data
}

/** 下载年报 */
export function getAnnualReportDownloadUrl(reportId: string): string {
  return `${BASE}/${reportId}/download`
}

/** 下载年报（blob） */
export async function downloadAnnualReport(reportId: string, year: number): Promise<void> {
  const response = await http.get(`${BASE}/${reportId}/download`, {
    responseType: 'blob',
  })
  const blob = new Blob([response.data])
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `qc_annual_report_${year}.docx`
  link.click()
  URL.revokeObjectURL(link.href)
}
